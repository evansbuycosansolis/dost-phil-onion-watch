from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DemandEstimate, ForecastOutput, ForecastRun, HarvestReport, Municipality

try:
    from statsmodels.tsa.statespace.sarimax import SARIMAX
except Exception:  # pragma: no cover
    SARIMAX = None


@dataclass
class MunicipalityForecast:
    municipality_id: int
    next_month_supply_tons: float
    next_quarter_trend: float
    shortage_probability: float
    oversupply_probability: float
    confidence_score: float
    error_mae: float


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


def _seasonal_naive(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) >= 12:
        return float(values[-12])
    return float(values[-1])


def _sarima_forecast(values: list[float]) -> float | None:
    if SARIMAX is None or len(values) < 6:
        return None
    try:
        model = SARIMAX(values, order=(1, 1, 1), seasonal_order=(1, 0, 0, 12), enforce_stationarity=False, enforce_invertibility=False)
        fit = model.fit(disp=False)
        pred = fit.forecast(steps=1)
        return float(pred[0])
    except Exception:
        return None


def _ml_forecast(series: list[tuple[date, float]]) -> float | None:
    if len(series) < 4:
        return None
    keys = np.array([_month_key(month) for month, _ in series], dtype=float)
    values = np.array([value for _, value in series], dtype=float)

    x = np.column_stack([keys, np.roll(values, 1)])
    x = x[1:]
    y = values[1:]

    model = RandomForestRegressor(n_estimators=120, random_state=42)
    model.fit(x, y)

    next_key = keys[-1] + 1
    next_features = np.array([[next_key, values[-1]]], dtype=float)
    return float(model.predict(next_features)[0])


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

    forecast_run = ForecastRun(run_month=run_month, model_used="seasonal_naive+sarima+rf", status="running")
    db.add(forecast_run)
    db.flush()

    outputs: list[MunicipalityForecast] = []

    for municipality_id in municipalities:
        series = _build_series(db, municipality_id)
        values = [value for _, value in series]
        if not values:
            continue

        baseline = _seasonal_naive(values)
        sarima = _sarima_forecast(values)
        ml = _ml_forecast(series)

        preds = [baseline]
        if sarima is not None:
            preds.append(sarima)
        if ml is not None:
            preds.append(ml)

        next_supply = float(np.mean(preds))
        trend = _quarter_trend(values)
        demand = _demand_reference(db, municipality_id, run_month)

        if demand <= 0:
            shortage = 0.2 if next_supply > 0 else 0.6
            oversupply = 0.1
        else:
            ratio = next_supply / demand
            shortage = float(np.clip(1.0 - ratio, 0.0, 1.0))
            oversupply = float(np.clip(ratio - 1.0, 0.0, 1.0))

        conf = _confidence(values)
        mae = float(np.mean(np.abs(np.diff(values)))) if len(values) > 1 else 0.0

        outputs.append(
            MunicipalityForecast(
                municipality_id=municipality_id,
                next_month_supply_tons=max(next_supply, 0.0),
                next_quarter_trend=trend,
                shortage_probability=shortage,
                oversupply_probability=oversupply,
                confidence_score=conf,
                error_mae=mae,
            )
        )

    for output in outputs:
        record = ForecastOutput(
            forecast_run_id=forecast_run.id,
            municipality_id=output.municipality_id,
            period_start=run_month,
            period_end=date(run_month.year + (1 if run_month.month == 12 else 0), 1 if run_month.month == 12 else run_month.month + 1, 1),
            next_month_supply_tons=round(output.next_month_supply_tons, 2),
            next_quarter_trend=round(output.next_quarter_trend, 4),
            shortage_probability=round(output.shortage_probability, 4),
            oversupply_probability=round(output.oversupply_probability, 4),
            confidence_score=round(output.confidence_score, 4),
            error_mae=round(output.error_mae, 4),
        )
        db.add(record)

    forecast_run.status = "completed"
    forecast_run.metrics_json = {
        "generated_at": datetime.utcnow().isoformat(),
        "num_municipalities": len(outputs),
        "avg_confidence": round(float(np.mean([o.confidence_score for o in outputs])) if outputs else 0.0, 4),
    }

    db.flush()
    return forecast_run


def get_latest_forecast_run(db: Session) -> ForecastRun | None:
    return db.scalar(select(ForecastRun).order_by(ForecastRun.id.desc()).limit(1))


def get_forecast_outputs(db: Session, run_id: int) -> list[ForecastOutput]:
    return list(db.scalars(select(ForecastOutput).where(ForecastOutput.forecast_run_id == run_id)))


def forecast_history(db: Session, limit: int = 12) -> list[ForecastRun]:
    return list(db.scalars(select(ForecastRun).order_by(ForecastRun.id.desc()).limit(limit)))
