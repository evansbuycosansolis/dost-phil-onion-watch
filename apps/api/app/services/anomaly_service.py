from __future__ import annotations

from datetime import date

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AnomalyEvent,
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
    metrics: dict | None = None,
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
        score=round(score, 4),
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


def run_anomaly_detection(db: Session, reporting_month: date) -> list[AnomalyEvent]:
    events: list[AnomalyEvent] = []
    previous_month = _latest_previous_month(reporting_month)

    # Rule 1: high stock but low releases by warehouse.
    warehouse_rows = db.execute(
        select(Warehouse.id, Warehouse.name, func.coalesce(func.sum(WarehouseStockReport.current_stock_tons), 0.0), func.coalesce(func.sum(StockReleaseLog.volume_tons), 0.0))
        .join(WarehouseStockReport, WarehouseStockReport.warehouse_id == Warehouse.id)
        .join(StockReleaseLog, StockReleaseLog.warehouse_id == Warehouse.id, isouter=True)
        .where(WarehouseStockReport.reporting_month == reporting_month)
        .group_by(Warehouse.id, Warehouse.name)
    ).all()

    stocks = [float(row[2]) for row in warehouse_rows]
    releases = [float(row[3]) for row in warehouse_rows]
    stock_threshold = float(np.percentile(stocks, 75)) if stocks else 0.0
    release_threshold = float(np.percentile(releases, 25)) if releases else 0.0

    for warehouse_id, warehouse_name, stock, release in warehouse_rows:
        stock = float(stock)
        release = float(release)
        if stock > stock_threshold and release <= release_threshold:
            score = min(1.0, 0.55 + (stock / (stock_threshold + 1e-6)) * 0.2)
            events.append(
                _insert_event(
                    db,
                    reporting_month=reporting_month,
                    anomaly_type="stock_release_mismatch",
                    scope_type="warehouse",
                    warehouse_id=warehouse_id,
                    summary=f"{warehouse_name} has elevated stock with unusually low releases.",
                    score=score,
                    metrics={"stock_tons": stock, "release_tons": release, "stock_threshold": stock_threshold, "release_threshold": release_threshold},
                )
            )

    # Rule 2: price rise despite adequate stock by municipality.
    muni_rows = db.execute(select(Municipality.id, Municipality.name)).all()
    for municipality_id, municipality_name in muni_rows:
        stock = float(
            db.scalar(
                select(func.coalesce(func.sum(WarehouseStockReport.current_stock_tons), 0.0)).where(
                    WarehouseStockReport.municipality_id == municipality_id,
                    WarehouseStockReport.reporting_month == reporting_month,
                )
            )
            or 0.0
        )
        retail_now = float(
            db.scalar(
                select(func.coalesce(func.avg(RetailPriceReport.price_per_kg), 0.0)).where(
                    RetailPriceReport.municipality_id == municipality_id,
                    RetailPriceReport.reporting_month == reporting_month,
                )
            )
            or 0.0
        )
        retail_prev = float(
            db.scalar(
                select(func.coalesce(func.avg(RetailPriceReport.price_per_kg), 0.0)).where(
                    RetailPriceReport.municipality_id == municipality_id,
                    RetailPriceReport.reporting_month == previous_month,
                )
            )
            or 0.0
        )

        if retail_prev > 0 and stock > 100:
            delta_pct = (retail_now - retail_prev) / retail_prev
            if delta_pct > 0.2:
                score = min(1.0, 0.5 + delta_pct)
                events.append(
                    _insert_event(
                        db,
                        reporting_month=reporting_month,
                        anomaly_type="price_stock_conflict",
                        scope_type="municipality",
                        municipality_id=municipality_id,
                        summary=f"{municipality_name} retail prices surged despite adequate reported stock.",
                        score=score,
                        metrics={"retail_now": retail_now, "retail_prev": retail_prev, "stock_tons": stock, "delta_pct": delta_pct},
                    )
                )

    # Rule 3: price crash during high harvest and import overlap.
    harvest_by_month = float(db.scalar(select(func.coalesce(func.sum(HarvestReport.volume_tons), 0.0)).where(HarvestReport.reporting_month == reporting_month)) or 0.0)
    imports_by_month = float(db.scalar(select(func.coalesce(func.sum(ImportRecord.volume_tons), 0.0)).where(ImportRecord.reporting_month == reporting_month)) or 0.0)
    retail_now_global = float(db.scalar(select(func.coalesce(func.avg(RetailPriceReport.price_per_kg), 0.0)).where(RetailPriceReport.reporting_month == reporting_month)) or 0.0)
    retail_prev_global = float(db.scalar(select(func.coalesce(func.avg(RetailPriceReport.price_per_kg), 0.0)).where(RetailPriceReport.reporting_month == previous_month)) or 0.0)

    if harvest_by_month > 800 and imports_by_month > 250 and retail_prev_global > 0:
        drop_pct = (retail_prev_global - retail_now_global) / retail_prev_global
        if drop_pct > 0.12:
            score = min(1.0, 0.45 + drop_pct)
            events.append(
                _insert_event(
                    db,
                    reporting_month=reporting_month,
                    anomaly_type="import_harvest_collision",
                    scope_type="provincial",
                    summary="Retail prices dropped materially during high harvest and significant import arrivals.",
                    score=score,
                    metrics={
                        "harvest_tons": harvest_by_month,
                        "imports_tons": imports_by_month,
                        "retail_drop_pct": drop_pct,
                    },
                )
            )

    # Rule 4: abnormal spread by municipality.
    for municipality_id, municipality_name in muni_rows:
        farm = float(
            db.scalar(
                select(func.coalesce(func.avg(FarmgatePriceReport.price_per_kg), 0.0)).where(
                    FarmgatePriceReport.municipality_id == municipality_id,
                    FarmgatePriceReport.reporting_month == reporting_month,
                )
            )
            or 0.0
        )
        wholesale = float(
            db.scalar(
                select(func.coalesce(func.avg(WholesalePriceReport.price_per_kg), 0.0)).where(
                    WholesalePriceReport.municipality_id == municipality_id,
                    WholesalePriceReport.reporting_month == reporting_month,
                )
            )
            or 0.0
        )
        retail = float(
            db.scalar(
                select(func.coalesce(func.avg(RetailPriceReport.price_per_kg), 0.0)).where(
                    RetailPriceReport.municipality_id == municipality_id,
                    RetailPriceReport.reporting_month == reporting_month,
                )
            )
            or 0.0
        )
        spread = retail - farm
        if farm > 0 and spread > 28:
            score = min(1.0, 0.4 + spread / 100)
            events.append(
                _insert_event(
                    db,
                    reporting_month=reporting_month,
                    anomaly_type="price_spread_outlier",
                    scope_type="municipality",
                    municipality_id=municipality_id,
                    summary=f"{municipality_name} shows abnormal farmgate-to-retail spread.",
                    score=score,
                    metrics={"farmgate": farm, "wholesale": wholesale, "retail": retail, "spread": spread},
                )
            )

    # Rule 5: z-score/unsupervised discrepancy on stock vs releases.
    features = []
    context = []
    for warehouse_id, _, stock, release in warehouse_rows:
        stock_val = float(stock)
        release_val = float(release)
        z_stock = _compute_z(stock_val, stocks)
        z_release = _compute_z(release_val, releases)
        discrepancy = z_stock - z_release
        features.append([stock_val, release_val, discrepancy])
        context.append((warehouse_id, stock_val, release_val, discrepancy))

    if features:
        matrix = np.array(features, dtype=float)
        anomaly_mask = np.zeros(len(features), dtype=bool)

        if IsolationForest is not None and len(features) >= 5:
            clf = IsolationForest(contamination=0.2, random_state=42)
            preds = clf.fit_predict(matrix)
            anomaly_mask = preds == -1
        else:
            for idx, (_, _, _, discrepancy) in enumerate(context):
                anomaly_mask[idx] = discrepancy > 1.3

        for idx, is_anomalous in enumerate(anomaly_mask):
            if not is_anomalous:
                continue
            warehouse_id, stock_val, release_val, discrepancy = context[idx]
            score = min(1.0, 0.45 + max(discrepancy, 0) * 0.2)
            events.append(
                _insert_event(
                    db,
                    reporting_month=reporting_month,
                    anomaly_type="stock_movement_discrepancy",
                    scope_type="warehouse",
                    warehouse_id=warehouse_id,
                    summary="Reported stock and movement behavior diverges from peer pattern.",
                    score=score,
                    metrics={"stock_tons": stock_val, "release_tons": release_val, "discrepancy": discrepancy},
                )
            )

    return events


def list_anomalies(db: Session) -> list[AnomalyEvent]:
    return list(db.scalars(select(AnomalyEvent).order_by(AnomalyEvent.detected_at.desc())))


def get_anomaly(db: Session, anomaly_id: int) -> AnomalyEvent | None:
    return db.scalar(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id))
