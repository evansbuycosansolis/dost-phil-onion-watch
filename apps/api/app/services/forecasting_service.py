from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from statistics import mean

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DemandEstimate, ForecastModelMetric, ForecastOutput, ForecastRun, HarvestReport, Municipality

try:
    from statsmodels.tsa.statespace.sarimax import SARIMAX
except Exception:  # pragma: no cover
    SARIMAX = None

try:
    from sklearn.ensemble import RandomForestRegressor
except Exception:  # pragma: no cover
    RandomForestRegressor = None


MODEL_CATALOG: tuple[tuple[str, str], ...] = (
    ("baseline_seasonal_naive", "baseline"),
    ("stat_sarima", "statistical"),
    ("ml_random_forest", "ml"),
)
MODEL_FALLBACK_PRIORITY = {
    "ml_random_forest": 0,
    "stat_sarima": 1,
    "baseline_seasonal_naive": 2,
}


@dataclass
class ModelEvaluation:
    model_name: str
    model_family: str
    prediction_next_month: float | None
    is_available: bool
    holdout_actual: float | None
    holdout_prediction: float | None
    holdout_mae: float | None
    holdout_mape: float | None
    score: float | None
    details: dict[str, float | int | str | None]
    rank: int | None = None
    fallback_rank: int | None = None


@dataclass
class MunicipalityForecast:
    municipality_id: int
    next_month_supply_tons: float
    next_quarter_trend: float
    shortage_probability: float
    oversupply_probability: float
    confidence_score: float
    error_mae: float
    selected_model: str
    selected_model_score: float | None
    fallback_order: list[str]
    selection_metadata: dict[str, object]


def _month_key(d: date) -> int:
    return d.year * 12 + d.month


def _build_series(db: Session, municipality_id: int) -> list[tuple[date, float]]:
    rows = db.execute(
        select(HarvestReport.reporting_month, func.sum(HarvestReport.volume_tons))
        .where(HarvestReport.municipality_id == municipality_id)
        .group_by(HarvestReport.reporting_month)
        .order_by(HarvestReport.reporting_month)
    ).all()
    return [(month, float(total or 0.0)) for month, total in rows]


def _seasonal_naive(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) >= 12:
        return float(values[-12])
    return float(values[-1])


def _sarima_forecast(values: list[float]) -> float | None:
    if SARIMAX is None or len(values) < 6:
        return None
    try:
        model = SARIMAX(
            values,
            order=(1, 1, 1),
            seasonal_order=(1, 0, 0, 12),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fit = model.fit(disp=False)
        pred = fit.forecast(steps=1)
        return float(pred[0])
    except Exception:
        return None


def _ml_forecast(series: list[tuple[date, float]]) -> float | None:
    if RandomForestRegressor is None:
        return None
    if len(series) < 4:
        return None

    keys = np.array([_month_key(month) for month, _ in series], dtype=float)
    values = np.array([value for _, value in series], dtype=float)

    x = np.column_stack([keys, np.roll(values, 1)])
    x = x[1:]
    y = values[1:]
    if len(y) < 2:
        return None

    model = RandomForestRegressor(n_estimators=120, random_state=42)
    model.fit(x, y)

    next_key = keys[-1] + 1
    next_features = np.array([[next_key, values[-1]]], dtype=float)
    return float(model.predict(next_features)[0])


def _predict_candidate(model_name: str, values: list[float], series: list[tuple[date, float]]) -> float | None:
    if model_name == "baseline_seasonal_naive":
        return _seasonal_naive(values)
    if model_name == "stat_sarima":
        return _sarima_forecast(values)
    if model_name == "ml_random_forest":
        return _ml_forecast(series)
    return None


def _compute_error_metrics(actual: float | None, predicted: float | None) -> tuple[float | None, float | None]:
    if actual is None or predicted is None:
        return None, None
    mae = abs(actual - predicted)
    denom = max(abs(actual), 1e-6)
    mape = (mae / denom) * 100.0
    return float(mae), float(mape)


def _score_candidate(mae: float | None, scale_reference: float) -> float | None:
    if mae is None:
        return None
    normalized = mae / max(scale_reference, 1.0)
    score = max(0.0, 1.0 - min(normalized, 2.0) / 2.0)
    return float(round(score, 6))


def _evaluate_models(series: list[tuple[date, float]]) -> list[ModelEvaluation]:
    values = [value for _, value in series]
    if not values:
        return []

    holdout_actual = values[-1] if len(values) > 1 else None
    train_values = values[:-1] if len(values) > 1 else values
    train_series = series[:-1] if len(series) > 1 else series
    scale_reference = float(np.mean(np.abs(train_values))) if train_values else float(np.mean(np.abs(values)))

    evaluations: list[ModelEvaluation] = []
    for model_name, model_family in MODEL_CATALOG:
        next_month_prediction = _predict_candidate(model_name, values, series)
        holdout_prediction = _predict_candidate(model_name, train_values, train_series) if holdout_actual is not None else None
        holdout_mae, holdout_mape = _compute_error_metrics(holdout_actual, holdout_prediction)
        score = _score_candidate(holdout_mae, scale_reference)
        evaluations.append(
            ModelEvaluation(
                model_name=model_name,
                model_family=model_family,
                prediction_next_month=next_month_prediction,
                is_available=next_month_prediction is not None,
                holdout_actual=holdout_actual,
                holdout_prediction=holdout_prediction,
                holdout_mae=holdout_mae,
                holdout_mape=holdout_mape,
                score=score,
                details={
                    "history_points": len(values),
                    "train_points": len(train_values),
                },
            )
        )

    def sort_key(item: ModelEvaluation) -> tuple[float, float, float, int]:
        availability = 0.0 if item.is_available else 1.0
        score = item.score if item.score is not None else -1.0
        mae = item.holdout_mae if item.holdout_mae is not None else float("inf")
        priority = MODEL_FALLBACK_PRIORITY.get(item.model_name, 99)
        return (availability, -score, mae, priority)

    ranked = sorted(evaluations, key=sort_key)
    fallback_counter = 1
    for idx, candidate in enumerate(ranked, start=1):
        candidate.rank = idx
        if candidate.is_available:
            candidate.fallback_rank = fallback_counter
            fallback_counter += 1

    return ranked


def _quarter_trend(values: list[float]) -> float:
    if len(values) < 4:
        return 0.0
    recent = values[-3:]
    previous = values[-6:-3] if len(values) >= 6 else values[:-3]
    if not previous:
        return 0.0
    prev_avg = float(np.mean(previous))
    recent_avg = float(np.mean(recent))
    if prev_avg == 0:
        return 0.0
    return (recent_avg - prev_avg) / prev_avg


def _demand_reference(db: Session, municipality_id: int, run_month: date) -> float:
    value = db.scalar(
        select(func.avg(DemandEstimate.demand_tons)).where(
            DemandEstimate.municipality_id == municipality_id,
            DemandEstimate.reporting_month <= run_month,
        )
    )
    return float(value or 0.0)


def _confidence(values: list[float]) -> float:
    if len(values) < 3:
        return 0.45
    cv = float(np.std(values) / (np.mean(values) + 1e-6))
    base = 0.85 - min(cv, 1.0) * 0.35
    return max(0.35, min(0.95, base))


def run_forecasting(db: Session, run_month: date) -> ForecastRun:
    municipalities = [row[0] for row in db.execute(select(Municipality.id)).all()]
    if not municipalities:
        raise ValueError("No municipalities available for forecasting")

    forecast_run = ForecastRun(run_month=run_month, model_used="baseline+sarima+rf_registry", status="running")
    db.add(forecast_run)
    db.flush()

    outputs: list[MunicipalityForecast] = []
    all_evaluations: list[ModelEvaluation] = []

    for municipality_id in municipalities:
        series = _build_series(db, municipality_id)
        values = [value for _, value in series]
        if not values:
            continue

        evaluations = _evaluate_models(series)
        all_evaluations.extend(evaluations)
        available = [candidate for candidate in evaluations if candidate.is_available]
        selected = available[0] if available else None

        selected_prediction = selected.prediction_next_month if selected and selected.prediction_next_month is not None else _seasonal_naive(values)
        if selected_prediction is None:
            continue

        trend = _quarter_trend(values)
        demand = _demand_reference(db, municipality_id, run_month)

        if demand <= 0:
            shortage = 0.2 if selected_prediction > 0 else 0.6
            oversupply = 0.1
        else:
            ratio = selected_prediction / demand
            shortage = float(np.clip(1.0 - ratio, 0.0, 1.0))
            oversupply = float(np.clip(ratio - 1.0, 0.0, 1.0))

        conf = _confidence(values)
        default_mae = float(np.mean(np.abs(np.diff(values)))) if len(values) > 1 else 0.0
        error_mae = selected.holdout_mae if selected and selected.holdout_mae is not None else default_mae

        fallback_order = [candidate.model_name for candidate in available]
        selected_model_name = selected.model_name if selected else "baseline_seasonal_naive"
        selected_model_score = selected.score if selected else None

        outputs.append(
            MunicipalityForecast(
                municipality_id=municipality_id,
                next_month_supply_tons=max(float(selected_prediction), 0.0),
                next_quarter_trend=trend,
                shortage_probability=shortage,
                oversupply_probability=oversupply,
                confidence_score=conf,
                error_mae=error_mae,
                selected_model=selected_model_name,
                selected_model_score=selected_model_score,
                fallback_order=fallback_order,
                selection_metadata={
                    "selection_reason": "score_ranked_fallback",
                    "candidate_scores": {candidate.model_name: candidate.score for candidate in evaluations},
                    "candidate_holdout_mae": {candidate.model_name: candidate.holdout_mae for candidate in evaluations},
                    "available_models": fallback_order,
                },
            )
        )

        for candidate in evaluations:
            db.add(
                ForecastModelMetric(
                    forecast_run_id=forecast_run.id,
                    municipality_id=municipality_id,
                    model_name=candidate.model_name,
                    model_family=candidate.model_family,
                    is_available=candidate.is_available,
                    prediction_next_month=(round(candidate.prediction_next_month, 4) if candidate.prediction_next_month is not None else None),
                    holdout_actual=(round(candidate.holdout_actual, 4) if candidate.holdout_actual is not None else None),
                    holdout_prediction=(round(candidate.holdout_prediction, 4) if candidate.holdout_prediction is not None else None),
                    holdout_mae=(round(candidate.holdout_mae, 4) if candidate.holdout_mae is not None else None),
                    holdout_mape=(round(candidate.holdout_mape, 4) if candidate.holdout_mape is not None else None),
                    score=(round(candidate.score, 6) if candidate.score is not None else None),
                    rank=candidate.rank,
                    selected=(candidate.model_name == selected_model_name),
                    fallback_rank=candidate.fallback_rank,
                    details_json=candidate.details,
                )
            )

    for output in outputs:
        period_end_year = run_month.year + (1 if run_month.month == 12 else 0)
        period_end_month = 1 if run_month.month == 12 else run_month.month + 1
        db.add(
            ForecastOutput(
                forecast_run_id=forecast_run.id,
                municipality_id=output.municipality_id,
                period_start=run_month,
                period_end=date(period_end_year, period_end_month, 1),
                next_month_supply_tons=round(output.next_month_supply_tons, 2),
                next_quarter_trend=round(output.next_quarter_trend, 4),
                shortage_probability=round(output.shortage_probability, 4),
                oversupply_probability=round(output.oversupply_probability, 4),
                confidence_score=round(output.confidence_score, 4),
                error_mae=round(output.error_mae, 4),
                selected_model=output.selected_model,
                selected_model_score=(round(output.selected_model_score, 6) if output.selected_model_score is not None else None),
                fallback_order_json=output.fallback_order,
                selection_metadata_json=output.selection_metadata,
            )
        )

    selected_distribution = Counter(output.selected_model for output in outputs)
    selected_scores = [output.selected_model_score for output in outputs if output.selected_model_score is not None]

    mae_by_model: dict[str, list[float]] = defaultdict(list)
    availability_counts: Counter[str] = Counter()
    for candidate in all_evaluations:
        if candidate.is_available:
            availability_counts[candidate.model_name] += 1
        if candidate.holdout_mae is not None:
            mae_by_model[candidate.model_name].append(candidate.holdout_mae)

    forecast_run.status = "completed"
    forecast_run.metrics_json = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "num_municipalities": len(outputs),
        "avg_confidence": round(float(np.mean([o.confidence_score for o in outputs])) if outputs else 0.0, 4),
        "avg_selected_model_score": round(float(np.mean(selected_scores)) if selected_scores else 0.0, 6),
        "selected_model_distribution": dict(selected_distribution),
        "model_availability_counts": dict(availability_counts),
        "model_avg_holdout_mae": {model_name: round(float(mean(values)), 4) for model_name, values in mae_by_model.items() if values},
    }

    db.flush()
    return forecast_run


def get_latest_forecast_run(db: Session) -> ForecastRun | None:
    return db.scalar(select(ForecastRun).order_by(ForecastRun.id.desc()).limit(1))


def get_forecast_outputs(db: Session, run_id: int) -> list[ForecastOutput]:
    return list(db.scalars(select(ForecastOutput).where(ForecastOutput.forecast_run_id == run_id)))


def get_forecast_model_metrics(db: Session, run_id: int) -> list[ForecastModelMetric]:
    return list(
        db.scalars(
            select(ForecastModelMetric)
            .where(ForecastModelMetric.forecast_run_id == run_id)
            .order_by(ForecastModelMetric.municipality_id, ForecastModelMetric.rank)
        )
    )


def build_run_model_diagnostics(db: Session, run_id: int) -> dict[str, object]:
    metrics = get_forecast_model_metrics(db, run_id)
    if not metrics:
        return {
            "run_id": run_id,
            "selected_model_counts": {},
            "model_avg_score": {},
            "model_avg_holdout_mae": {},
            "municipality_diagnostics": [],
        }

    municipality_map: dict[int, str] = {
        municipality_id: name
        for municipality_id, name in db.execute(select(Municipality.id, Municipality.name)).all()
    }

    selected_counts: Counter[str] = Counter()
    score_by_model: dict[str, list[float]] = defaultdict(list)
    mae_by_model: dict[str, list[float]] = defaultdict(list)
    by_municipality: dict[int, dict[str, object]] = {}

    for row in metrics:
        if row.score is not None:
            score_by_model[row.model_name].append(float(row.score))
        if row.holdout_mae is not None:
            mae_by_model[row.model_name].append(float(row.holdout_mae))
        if row.selected:
            selected_counts[row.model_name] += 1

        muni = by_municipality.setdefault(
            row.municipality_id,
            {
                "municipality_id": row.municipality_id,
                "municipality_name": municipality_map.get(row.municipality_id, f"Municipality {row.municipality_id}"),
                "selected_model": None,
                "selected_score": None,
                "fallback_order": [],
                "candidates": [],
            },
        )

        if row.fallback_rank is not None and row.model_name not in muni["fallback_order"]:
            muni["fallback_order"].append((row.fallback_rank, row.model_name))

        if row.selected:
            muni["selected_model"] = row.model_name
            muni["selected_score"] = row.score

        muni["candidates"].append(
            {
                "model_name": row.model_name,
                "model_family": row.model_family,
                "is_available": row.is_available,
                "prediction_next_month": row.prediction_next_month,
                "holdout_mae": row.holdout_mae,
                "holdout_mape": row.holdout_mape,
                "score": row.score,
                "rank": row.rank,
                "selected": row.selected,
            }
        )

    municipality_diagnostics: list[dict[str, object]] = []
    for municipality_id in sorted(by_municipality):
        muni = by_municipality[municipality_id]
        fallback_pairs = sorted(muni["fallback_order"], key=lambda pair: pair[0])
        fallback_order = [name for _, name in fallback_pairs]
        muni["fallback_order"] = fallback_order
        municipality_diagnostics.append(muni)

    return {
        "run_id": run_id,
        "selected_model_counts": dict(selected_counts),
        "model_avg_score": {name: round(float(mean(values)), 6) for name, values in score_by_model.items() if values},
        "model_avg_holdout_mae": {name: round(float(mean(values)), 4) for name, values in mae_by_model.items() if values},
        "municipality_diagnostics": municipality_diagnostics,
    }


def latest_model_diagnostics(db: Session) -> dict[str, object]:
    latest_run = get_latest_forecast_run(db)
    if not latest_run:
        return {
            "run_id": None,
            "selected_model_counts": {},
            "model_avg_score": {},
            "model_avg_holdout_mae": {},
            "municipality_diagnostics": [],
        }
    return build_run_model_diagnostics(db, latest_run.id)


def forecast_history(db: Session, limit: int = 12) -> list[ForecastRun]:
    return list(db.scalars(select(ForecastRun).order_by(ForecastRun.id.desc()).limit(limit)))
