from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AnomalyEvent,
    AnomalyThresholdConfig,
    AnomalyThresholdVersion,
    FarmgatePriceReport,
    HarvestReport,
    ImportRecord,
    Municipality,
    RetailPriceReport,
    RiskScore,
    StockReleaseLog,
    Warehouse,
    WarehouseStockReport,
    WholesalePriceReport,
)

try:
    from sklearn.ensemble import IsolationForest
except Exception:  # pragma: no cover
    IsolationForest = None


DEFAULT_ANOMALY_THRESHOLDS: dict[str, dict[str, float | int]] = {
    "stock_release_mismatch": {
        "stock_percentile_high": 75,
        "release_percentile_low": 25,
        "min_stock_tons": 80,
        "base_score": 0.52,
        "stock_ratio_weight": 0.16,
        "release_ratio_weight": 0.14,
    },
    "price_stock_conflict": {
        "min_stock_tons": 100,
        "price_rise_pct_threshold": 0.20,
        "base_score": 0.50,
        "delta_weight": 1.00,
        "stock_weight": 0.08,
    },
    "import_harvest_collision": {
        "harvest_tons_threshold": 800,
        "imports_tons_threshold": 250,
        "price_drop_pct_threshold": 0.12,
        "base_score": 0.45,
        "drop_weight": 0.95,
        "import_weight": 0.06,
    },
    "price_spread_outlier": {
        "spread_threshold": 28,
        "base_score": 0.40,
        "spread_weight": 0.012,
        "min_farmgate_price": 1,
    },
    "stock_movement_discrepancy": {
        "discrepancy_threshold": 1.30,
        "iforest_contamination": 0.20,
        "iforest_min_samples": 5,
        "base_score": 0.45,
        "discrepancy_weight": 0.18,
        "iforest_boost": 0.20,
    },
}


def supported_anomaly_types() -> list[str]:
    return sorted(DEFAULT_ANOMALY_THRESHOLDS.keys())


def _severity_from_score(score: float) -> str:
    if score >= 0.85:
        return "critical"
    if score >= 0.65:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _latest_previous_month(month: date) -> date:
    if month.month == 1:
        return date(month.year - 1, 12, 1)
    return date(month.year, month.month - 1, 1)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _round(value: Any, digits: int = 4) -> float:
    return round(_as_float(value), digits)


def _score_cap(score: float) -> float:
    return float(max(0.0, min(1.0, score)))


def _rule_contribution(
    *,
    component: str,
    value: float,
    threshold: float,
    operator: str,
    passed: bool,
    weight: float,
) -> dict[str, Any]:
    return {
        "component": component,
        "value": _round(value, 4),
        "threshold": _round(threshold, 4),
        "operator": operator,
        "passed": bool(passed),
        "weight": _round(weight, 4),
    }


def _score_component(*, component: str, value: float, note: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "component": component,
        "value": _round(value, 4),
    }
    if note:
        payload["note"] = note
    return payload


def _insert_event(
    db: Session,
    *,
    reporting_month: date,
    anomaly_type: str,
    scope_type: str,
    summary: str,
    score: float,
    municipality_id: int | None = None,
    warehouse_id: int | None = None,
    market_id: int | None = None,
    metrics: dict[str, Any] | None = None,
) -> AnomalyEvent:
    severity = _severity_from_score(score)
    event = AnomalyEvent(
        reporting_month=reporting_month,
        anomaly_type=anomaly_type,
        scope_type=scope_type,
        municipality_id=municipality_id,
        warehouse_id=warehouse_id,
        market_id=market_id,
        severity=severity,
        summary=summary,
        supporting_metrics_json=metrics or {},
        status="open",
    )
    db.add(event)
    db.flush()

    risk = RiskScore(
        anomaly_event_id=event.id,
        scope_type=scope_type,
        scope_id=warehouse_id or municipality_id or market_id or 0,
        score=_round(score, 4),
        method="hybrid_rules+stats",
        details_json=metrics or {},
    )
    db.add(risk)
    db.flush()
    return event


def _compute_z(value: float, arr: list[float]) -> float:
    if not arr:
        return 0.0
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    if std <= 1e-6:
        return 0.0
    return (value - mean) / std


def _validate_threshold_patch(thresholds: dict[str, Any]) -> dict[str, float | int]:
    validated: dict[str, float | int] = {}
    for key, value in thresholds.items():
        if isinstance(value, bool):
            validated[key] = int(value)
            continue
        if isinstance(value, (int, float)):
            validated[key] = value
            continue
        raise ValueError(f"Threshold '{key}' must be numeric")
    return validated


def ensure_default_threshold_configs(db: Session) -> list[AnomalyThresholdConfig]:
    existing_by_type = {
        row.anomaly_type: row
        for row in db.scalars(
            select(AnomalyThresholdConfig).where(AnomalyThresholdConfig.is_active.is_(True))
        ).all()
    }

    created: list[AnomalyThresholdConfig] = []
    for anomaly_type, defaults in DEFAULT_ANOMALY_THRESHOLDS.items():
        if anomaly_type in existing_by_type:
            continue
        config = AnomalyThresholdConfig(
            anomaly_type=anomaly_type,
            thresholds_json=deepcopy(defaults),
            version=1,
            is_active=True,
            change_reason="default_bootstrap",
        )
        db.add(config)
        db.flush()
        db.add(
            AnomalyThresholdVersion(
                config_id=config.id,
                anomaly_type=anomaly_type,
                version=1,
                thresholds_json=deepcopy(defaults),
                change_reason="default_bootstrap",
                changed_by=None,
            )
        )
        created.append(config)

    if created:
        db.flush()
    return created


def _active_config_by_type(db: Session) -> dict[str, AnomalyThresholdConfig]:
    ensure_default_threshold_configs(db)
    rows = db.scalars(
        select(AnomalyThresholdConfig)
        .where(AnomalyThresholdConfig.is_active.is_(True))
        .order_by(AnomalyThresholdConfig.anomaly_type)
    ).all()
    return {row.anomaly_type: row for row in rows}


def list_threshold_configs(db: Session) -> list[AnomalyThresholdConfig]:
    return list(_active_config_by_type(db).values())


def get_threshold_config(db: Session, anomaly_type: str) -> AnomalyThresholdConfig | None:
    return _active_config_by_type(db).get(anomaly_type)


def list_threshold_versions(db: Session, anomaly_type: str, limit: int = 50) -> list[AnomalyThresholdVersion]:
    return list(
        db.scalars(
            select(AnomalyThresholdVersion)
            .where(AnomalyThresholdVersion.anomaly_type == anomaly_type)
            .order_by(AnomalyThresholdVersion.version.desc())
            .limit(limit)
        )
    )


def update_threshold_config(
    db: Session,
    *,
    anomaly_type: str,
    thresholds_patch: dict[str, Any],
    changed_by: int | None,
    reason: str,
) -> tuple[AnomalyThresholdConfig, dict[str, Any], dict[str, Any]]:
    if anomaly_type not in DEFAULT_ANOMALY_THRESHOLDS:
        raise ValueError(f"Unsupported anomaly_type: {anomaly_type}")

    config = get_threshold_config(db, anomaly_type)
    if config is None:
        ensure_default_threshold_configs(db)
        config = get_threshold_config(db, anomaly_type)
    if config is None:
        raise ValueError(f"No threshold config found for: {anomaly_type}")

    patch = _validate_threshold_patch(thresholds_patch)
    before = deepcopy(config.thresholds_json or {})
    merged = deepcopy(DEFAULT_ANOMALY_THRESHOLDS[anomaly_type])
    merged.update(before)
    merged.update(patch)

    next_version = int(config.version) + 1
    config.thresholds_json = merged
    config.version = next_version
    config.last_changed_by = changed_by
    config.change_reason = reason
    config.updated_by = changed_by

    db.add(
        AnomalyThresholdVersion(
            config_id=config.id,
            anomaly_type=anomaly_type,
            version=next_version,
            thresholds_json=deepcopy(merged),
            changed_by=changed_by,
            change_reason=reason,
            created_by=changed_by,
            updated_by=changed_by,
        )
    )
    db.flush()
    return config, before, merged


def _threshold_bundle(db: Session) -> dict[str, dict[str, Any]]:
    configs = _active_config_by_type(db)
    bundle: dict[str, dict[str, Any]] = {}
    for anomaly_type, defaults in DEFAULT_ANOMALY_THRESHOLDS.items():
        config = configs.get(anomaly_type)
        merged = deepcopy(defaults)
        version = 1
        if config:
            merged.update(config.thresholds_json or {})
            version = int(config.version)
        bundle[anomaly_type] = {
            "thresholds": merged,
            "version": version,
        }
    return bundle

def run_anomaly_detection(db: Session, reporting_month: date) -> list[AnomalyEvent]:
    events: list[AnomalyEvent] = []
    previous_month = _latest_previous_month(reporting_month)
    threshold_bundle = _threshold_bundle(db)

    stock_subquery = (
        select(
            WarehouseStockReport.warehouse_id.label("warehouse_id"),
            func.coalesce(func.sum(WarehouseStockReport.current_stock_tons), 0.0).label("stock_tons"),
        )
        .where(WarehouseStockReport.reporting_month == reporting_month)
        .group_by(WarehouseStockReport.warehouse_id)
        .subquery()
    )
    release_subquery = (
        select(
            StockReleaseLog.warehouse_id.label("warehouse_id"),
            func.coalesce(func.sum(StockReleaseLog.volume_tons), 0.0).label("release_tons"),
        )
        .where(StockReleaseLog.reporting_month == reporting_month)
        .group_by(StockReleaseLog.warehouse_id)
        .subquery()
    )

    warehouse_rows = db.execute(
        select(
            Warehouse.id,
            Warehouse.name,
            Warehouse.municipality_id,
            func.coalesce(stock_subquery.c.stock_tons, 0.0),
            func.coalesce(release_subquery.c.release_tons, 0.0),
        )
        .join(stock_subquery, stock_subquery.c.warehouse_id == Warehouse.id, isouter=True)
        .join(release_subquery, release_subquery.c.warehouse_id == Warehouse.id, isouter=True)
    ).all()

    stocks = [float(row[3]) for row in warehouse_rows]
    releases = [float(row[4]) for row in warehouse_rows]

    # Rule 1: high stock but low releases by warehouse.
    stock_release_cfg = threshold_bundle["stock_release_mismatch"]
    stock_release_t = stock_release_cfg["thresholds"]
    stock_threshold = float(np.percentile(stocks, _as_float(stock_release_t.get("stock_percentile_high"), 75))) if stocks else 0.0
    release_threshold = float(np.percentile(releases, _as_float(stock_release_t.get("release_percentile_low"), 25))) if releases else 0.0
    min_stock_tons = _as_float(stock_release_t.get("min_stock_tons"), 80.0)

    for warehouse_id, warehouse_name, _, stock, release in warehouse_rows:
        stock = _as_float(stock)
        release = _as_float(release)

        effective_stock_threshold = max(stock_threshold, min_stock_tons)
        stock_pass = stock >= effective_stock_threshold
        release_pass = release <= release_threshold

        if not (stock_pass and release_pass):
            continue

        base_score = _as_float(stock_release_t.get("base_score"), 0.52)
        stock_ratio = stock / max(effective_stock_threshold, 1e-6)
        stock_boost = max(0.0, stock_ratio - 1.0) * _as_float(stock_release_t.get("stock_ratio_weight"), 0.16)
        release_ratio = release / max(release_threshold, 1e-6) if release_threshold > 0 else 0.0
        release_boost = max(0.0, 1.0 - release_ratio) * _as_float(stock_release_t.get("release_ratio_weight"), 0.14)
        score = _score_cap(base_score + stock_boost + release_boost)

        metrics = {
            "threshold_config_version": stock_release_cfg["version"],
            "thresholds": {
                "stock_threshold": _round(effective_stock_threshold),
                "release_threshold": _round(release_threshold),
                "stock_percentile_high": _round(stock_release_t.get("stock_percentile_high", 75), 2),
                "release_percentile_low": _round(stock_release_t.get("release_percentile_low", 25), 2),
            },
            "rule_contributions": [
                _rule_contribution(
                    component="warehouse_stock_tons",
                    value=stock,
                    threshold=effective_stock_threshold,
                    operator=">=",
                    passed=stock_pass,
                    weight=0.6,
                ),
                _rule_contribution(
                    component="warehouse_release_tons",
                    value=release,
                    threshold=release_threshold,
                    operator="<=",
                    passed=release_pass,
                    weight=0.4,
                ),
            ],
            "score_contributions": [
                _score_component(component="base_score", value=base_score),
                _score_component(component="stock_ratio_boost", value=stock_boost),
                _score_component(component="release_gap_boost", value=release_boost),
            ],
            "inputs": {
                "stock_tons": _round(stock),
                "release_tons": _round(release),
                "stock_ratio": _round(stock_ratio),
                "release_ratio": _round(release_ratio),
            },
            "final_score": _round(score),
            "explanation": "Warehouse stock is elevated while release volume is below peer-adjusted threshold.",
        }

        events.append(
            _insert_event(
                db,
                reporting_month=reporting_month,
                anomaly_type="stock_release_mismatch",
                scope_type="warehouse",
                warehouse_id=warehouse_id,
                summary=f"{warehouse_name} has elevated stock with unusually low releases.",
                score=score,
                metrics=metrics,
            )
        )

    # Rule 2: price rise despite adequate stock by municipality.
    municipality_rows = db.execute(select(Municipality.id, Municipality.name)).all()
    price_stock_cfg = threshold_bundle["price_stock_conflict"]
    price_stock_t = price_stock_cfg["thresholds"]
    for municipality_id, municipality_name in municipality_rows:
        stock = _as_float(
            db.scalar(
                select(func.coalesce(func.sum(WarehouseStockReport.current_stock_tons), 0.0)).where(
                    WarehouseStockReport.municipality_id == municipality_id,
                    WarehouseStockReport.reporting_month == reporting_month,
                )
            )
        )
        retail_now = _as_float(
            db.scalar(
                select(func.coalesce(func.avg(RetailPriceReport.price_per_kg), 0.0)).where(
                    RetailPriceReport.municipality_id == municipality_id,
                    RetailPriceReport.reporting_month == reporting_month,
                )
            )
        )
        retail_prev = _as_float(
            db.scalar(
                select(func.coalesce(func.avg(RetailPriceReport.price_per_kg), 0.0)).where(
                    RetailPriceReport.municipality_id == municipality_id,
                    RetailPriceReport.reporting_month == previous_month,
                )
            )
        )
        if retail_prev <= 0:
            continue

        delta_pct = (retail_now - retail_prev) / retail_prev
        min_stock = _as_float(price_stock_t.get("min_stock_tons"), 100.0)
        delta_threshold = _as_float(price_stock_t.get("price_rise_pct_threshold"), 0.2)

        stock_pass = stock >= min_stock
        delta_pass = delta_pct >= delta_threshold
        if not (stock_pass and delta_pass):
            continue

        base_score = _as_float(price_stock_t.get("base_score"), 0.5)
        delta_boost = max(0.0, delta_pct - delta_threshold) * _as_float(price_stock_t.get("delta_weight"), 1.0)
        stock_boost = max(0.0, min(stock / max(min_stock, 1e-6), 2.0) - 1.0) * _as_float(price_stock_t.get("stock_weight"), 0.08)
        score = _score_cap(base_score + delta_boost + stock_boost)

        metrics = {
            "threshold_config_version": price_stock_cfg["version"],
            "thresholds": {
                "min_stock_tons": _round(min_stock),
                "price_rise_pct_threshold": _round(delta_threshold),
            },
            "rule_contributions": [
                _rule_contribution(
                    component="municipality_stock_tons",
                    value=stock,
                    threshold=min_stock,
                    operator=">=",
                    passed=stock_pass,
                    weight=0.45,
                ),
                _rule_contribution(
                    component="retail_price_delta_pct",
                    value=delta_pct,
                    threshold=delta_threshold,
                    operator=">=",
                    passed=delta_pass,
                    weight=0.55,
                ),
            ],
            "score_contributions": [
                _score_component(component="base_score", value=base_score),
                _score_component(component="price_delta_boost", value=delta_boost),
                _score_component(component="stock_support_boost", value=stock_boost),
            ],
            "inputs": {
                "retail_now": _round(retail_now),
                "retail_prev": _round(retail_prev),
                "delta_pct": _round(delta_pct),
                "stock_tons": _round(stock),
            },
            "final_score": _round(score),
            "explanation": "Retail prices rose sharply even though local stock remained above threshold.",
        }

        events.append(
            _insert_event(
                db,
                reporting_month=reporting_month,
                anomaly_type="price_stock_conflict",
                scope_type="municipality",
                municipality_id=municipality_id,
                summary=f"{municipality_name} retail prices surged despite adequate reported stock.",
                score=score,
                metrics=metrics,
            )
        )
    # Rule 3: price crash during high harvest and import overlap.
    import_harvest_cfg = threshold_bundle["import_harvest_collision"]
    import_harvest_t = import_harvest_cfg["thresholds"]

    harvest_by_month = _as_float(
        db.scalar(select(func.coalesce(func.sum(HarvestReport.volume_tons), 0.0)).where(HarvestReport.reporting_month == reporting_month))
    )
    imports_by_month = _as_float(
        db.scalar(select(func.coalesce(func.sum(ImportRecord.volume_tons), 0.0)).where(ImportRecord.reporting_month == reporting_month))
    )
    retail_now_global = _as_float(
        db.scalar(select(func.coalesce(func.avg(RetailPriceReport.price_per_kg), 0.0)).where(RetailPriceReport.reporting_month == reporting_month))
    )
    retail_prev_global = _as_float(
        db.scalar(select(func.coalesce(func.avg(RetailPriceReport.price_per_kg), 0.0)).where(RetailPriceReport.reporting_month == previous_month))
    )

    if retail_prev_global > 0:
        drop_pct = (retail_prev_global - retail_now_global) / retail_prev_global
        harvest_threshold = _as_float(import_harvest_t.get("harvest_tons_threshold"), 800)
        imports_threshold = _as_float(import_harvest_t.get("imports_tons_threshold"), 250)
        drop_threshold = _as_float(import_harvest_t.get("price_drop_pct_threshold"), 0.12)

        harvest_pass = harvest_by_month >= harvest_threshold
        imports_pass = imports_by_month >= imports_threshold
        drop_pass = drop_pct >= drop_threshold

        if harvest_pass and imports_pass and drop_pass:
            base_score = _as_float(import_harvest_t.get("base_score"), 0.45)
            drop_boost = max(0.0, drop_pct - drop_threshold) * _as_float(import_harvest_t.get("drop_weight"), 0.95)
            import_boost = max(0.0, imports_by_month / max(imports_threshold, 1e-6) - 1.0) * _as_float(import_harvest_t.get("import_weight"), 0.06)
            score = _score_cap(base_score + drop_boost + import_boost)

            metrics = {
                "threshold_config_version": import_harvest_cfg["version"],
                "thresholds": {
                    "harvest_tons_threshold": _round(harvest_threshold),
                    "imports_tons_threshold": _round(imports_threshold),
                    "price_drop_pct_threshold": _round(drop_threshold),
                },
                "rule_contributions": [
                    _rule_contribution(
                        component="provincial_harvest_tons",
                        value=harvest_by_month,
                        threshold=harvest_threshold,
                        operator=">=",
                        passed=harvest_pass,
                        weight=0.35,
                    ),
                    _rule_contribution(
                        component="imports_tons",
                        value=imports_by_month,
                        threshold=imports_threshold,
                        operator=">=",
                        passed=imports_pass,
                        weight=0.30,
                    ),
                    _rule_contribution(
                        component="retail_price_drop_pct",
                        value=drop_pct,
                        threshold=drop_threshold,
                        operator=">=",
                        passed=drop_pass,
                        weight=0.35,
                    ),
                ],
                "score_contributions": [
                    _score_component(component="base_score", value=base_score),
                    _score_component(component="drop_pct_boost", value=drop_boost),
                    _score_component(component="import_intensity_boost", value=import_boost),
                ],
                "inputs": {
                    "harvest_tons": _round(harvest_by_month),
                    "imports_tons": _round(imports_by_month),
                    "retail_now": _round(retail_now_global),
                    "retail_prev": _round(retail_prev_global),
                    "retail_drop_pct": _round(drop_pct),
                },
                "final_score": _round(score),
                "explanation": "Provincial retail prices dropped during simultaneous high harvest and import arrivals.",
            }

            events.append(
                _insert_event(
                    db,
                    reporting_month=reporting_month,
                    anomaly_type="import_harvest_collision",
                    scope_type="provincial",
                    summary="Retail prices dropped materially during high harvest and significant import arrivals.",
                    score=score,
                    metrics=metrics,
                )
            )

    # Rule 4: abnormal farmgate-wholesale-retail spread by municipality.
    spread_cfg = threshold_bundle["price_spread_outlier"]
    spread_t = spread_cfg["thresholds"]
    spread_threshold = _as_float(spread_t.get("spread_threshold"), 28)
    min_farmgate = _as_float(spread_t.get("min_farmgate_price"), 1)

    for municipality_id, municipality_name in municipality_rows:
        farm = _as_float(
            db.scalar(
                select(func.coalesce(func.avg(FarmgatePriceReport.price_per_kg), 0.0)).where(
                    FarmgatePriceReport.municipality_id == municipality_id,
                    FarmgatePriceReport.reporting_month == reporting_month,
                )
            )
        )
        wholesale = _as_float(
            db.scalar(
                select(func.coalesce(func.avg(WholesalePriceReport.price_per_kg), 0.0)).where(
                    WholesalePriceReport.municipality_id == municipality_id,
                    WholesalePriceReport.reporting_month == reporting_month,
                )
            )
        )
        retail = _as_float(
            db.scalar(
                select(func.coalesce(func.avg(RetailPriceReport.price_per_kg), 0.0)).where(
                    RetailPriceReport.municipality_id == municipality_id,
                    RetailPriceReport.reporting_month == reporting_month,
                )
            )
        )
        spread = retail - farm

        farm_pass = farm >= min_farmgate
        spread_pass = spread >= spread_threshold
        if not (farm_pass and spread_pass):
            continue

        base_score = _as_float(spread_t.get("base_score"), 0.4)
        spread_boost = max(0.0, spread - spread_threshold) * _as_float(spread_t.get("spread_weight"), 0.012)
        score = _score_cap(base_score + spread_boost)

        metrics = {
            "threshold_config_version": spread_cfg["version"],
            "thresholds": {
                "spread_threshold": _round(spread_threshold),
                "min_farmgate_price": _round(min_farmgate),
            },
            "rule_contributions": [
                _rule_contribution(
                    component="farmgate_price",
                    value=farm,
                    threshold=min_farmgate,
                    operator=">=",
                    passed=farm_pass,
                    weight=0.20,
                ),
                _rule_contribution(
                    component="farmgate_to_retail_spread",
                    value=spread,
                    threshold=spread_threshold,
                    operator=">=",
                    passed=spread_pass,
                    weight=0.80,
                ),
            ],
            "score_contributions": [
                _score_component(component="base_score", value=base_score),
                _score_component(component="spread_excess_boost", value=spread_boost),
            ],
            "inputs": {
                "farmgate": _round(farm),
                "wholesale": _round(wholesale),
                "retail": _round(retail),
                "spread": _round(spread),
            },
            "final_score": _round(score),
            "explanation": "Farmgate-to-retail spread exceeded configured tolerance.",
        }

        events.append(
            _insert_event(
                db,
                reporting_month=reporting_month,
                anomaly_type="price_spread_outlier",
                scope_type="municipality",
                municipality_id=municipality_id,
                summary=f"{municipality_name} shows abnormal farmgate-to-retail spread.",
                score=score,
                metrics=metrics,
            )
        )

    # Rule 5: statistical / unsupervised discrepancy on stock vs releases.
    discrepancy_cfg = threshold_bundle["stock_movement_discrepancy"]
    discrepancy_t = discrepancy_cfg["thresholds"]

    features = []
    context = []
    for warehouse_id, warehouse_name, _, stock, release in warehouse_rows:
        stock_val = _as_float(stock)
        release_val = _as_float(release)
        z_stock = _compute_z(stock_val, stocks)
        z_release = _compute_z(release_val, releases)
        discrepancy = z_stock - z_release
        features.append([stock_val, release_val, discrepancy])
        context.append((warehouse_id, warehouse_name, stock_val, release_val, discrepancy))

    if features:
        matrix = np.array(features, dtype=float)
        anomaly_mask = np.zeros(len(features), dtype=bool)
        isolation_strengths = np.zeros(len(features), dtype=float)

        min_samples = int(_as_float(discrepancy_t.get("iforest_min_samples"), 5))
        contamination = float(_as_float(discrepancy_t.get("iforest_contamination"), 0.2))
        used_iforest = IsolationForest is not None and len(features) >= min_samples

        if used_iforest:
            clf = IsolationForest(contamination=contamination, random_state=42)
            preds = clf.fit_predict(matrix)
            anomaly_mask = preds == -1
            scores = clf.decision_function(matrix)
            isolation_strengths = np.maximum(-scores, 0.0)
        else:
            discrepancy_threshold = _as_float(discrepancy_t.get("discrepancy_threshold"), 1.3)
            for idx, (_, _, _, _, discrepancy) in enumerate(context):
                anomaly_mask[idx] = discrepancy >= discrepancy_threshold

        discrepancy_threshold = _as_float(discrepancy_t.get("discrepancy_threshold"), 1.3)

        for idx, is_anomalous in enumerate(anomaly_mask):
            if not is_anomalous:
                continue
            warehouse_id, warehouse_name, stock_val, release_val, discrepancy = context[idx]
            discrepancy_pass = discrepancy >= discrepancy_threshold
            iforest_flag = bool(used_iforest)
            iforest_boost = (
                _as_float(discrepancy_t.get("iforest_boost"), 0.2) * _as_float(isolation_strengths[idx])
                if iforest_flag
                else 0.0
            )

            base_score = _as_float(discrepancy_t.get("base_score"), 0.45)
            discrepancy_boost = max(0.0, discrepancy) * _as_float(discrepancy_t.get("discrepancy_weight"), 0.18)
            score = _score_cap(base_score + discrepancy_boost + iforest_boost)

            metrics = {
                "threshold_config_version": discrepancy_cfg["version"],
                "thresholds": {
                    "discrepancy_threshold": _round(discrepancy_threshold),
                    "iforest_contamination": _round(contamination),
                },
                "rule_contributions": [
                    _rule_contribution(
                        component="zscore_discrepancy",
                        value=discrepancy,
                        threshold=discrepancy_threshold,
                        operator=">=",
                        passed=discrepancy_pass,
                        weight=0.7,
                    ),
                    {
                        "component": "isolation_forest_outlier",
                        "value": bool(iforest_flag),
                        "threshold": True,
                        "operator": "==",
                        "passed": bool(iforest_flag),
                        "weight": 0.3,
                    },
                ],
                "score_contributions": [
                    _score_component(component="base_score", value=base_score),
                    _score_component(component="discrepancy_boost", value=discrepancy_boost),
                    _score_component(
                        component="iforest_outlier_boost",
                        value=iforest_boost,
                        note="Applied only when isolation forest is available and marks row as anomalous",
                    ),
                ],
                "inputs": {
                    "stock_tons": _round(stock_val),
                    "release_tons": _round(release_val),
                    "discrepancy": _round(discrepancy),
                    "iforest_used": iforest_flag,
                    "iforest_strength": _round(isolation_strengths[idx]),
                },
                "final_score": _round(score),
                "explanation": "Stock-vs-release behavior deviates from peer pattern based on z-score and optional isolation-forest signal.",
            }

            events.append(
                _insert_event(
                    db,
                    reporting_month=reporting_month,
                    anomaly_type="stock_movement_discrepancy",
                    scope_type="warehouse",
                    warehouse_id=warehouse_id,
                    summary=f"{warehouse_name} reported stock and movement diverges from peer pattern.",
                    score=score,
                    metrics=metrics,
                )
            )

    return events

def list_anomalies(db: Session) -> list[AnomalyEvent]:
    return list(db.scalars(select(AnomalyEvent).order_by(AnomalyEvent.detected_at.desc())))


def get_anomaly(db: Session, anomaly_id: int) -> AnomalyEvent | None:
    return db.scalar(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id))
