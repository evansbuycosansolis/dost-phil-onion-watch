from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    AlertAcknowledgement,
    AnomalyEvent,
    ForecastOutput,
    ForecastRun,
    HarvestReport,
    ImportRecord,
    Municipality,
)


def list_alerts(db: Session, status: str | None = None) -> list[Alert]:
    stmt = select(Alert).order_by(Alert.opened_at.desc())
    if status:
        stmt = stmt.where(Alert.status == status)
    return list(db.scalars(stmt))


def get_alert(db: Session, alert_id: int) -> Alert | None:
    return db.scalar(select(Alert).where(Alert.id == alert_id))


def append_alert_action(db: Session, ack: AlertAcknowledgement) -> AlertAcknowledgement:
    db.add(ack)
    db.flush()
    return ack


def _alert_exists(
    db: Session,
    *,
    alert_type: str,
    municipality_id: int | None = None,
    warehouse_id: int | None = None,
    linked_forecast_id: int | None = None,
    linked_anomaly_id: int | None = None,
) -> bool:
    stmt = select(func.count(Alert.id)).where(Alert.alert_type == alert_type, Alert.status.in_(["open", "acknowledged"]))
    if municipality_id is not None:
        stmt = stmt.where(Alert.municipality_id == municipality_id)
    if warehouse_id is not None:
        stmt = stmt.where(Alert.warehouse_id == warehouse_id)
    if linked_forecast_id is not None:
        stmt = stmt.where(Alert.linked_forecast_id == linked_forecast_id)
    if linked_anomaly_id is not None:
        stmt = stmt.where(Alert.linked_anomaly_id == linked_anomaly_id)
    return int(db.scalar(stmt) or 0) > 0


def generate_alerts_from_signals(db: Session, reporting_month: date) -> list[Alert]:
    created: list[Alert] = []

    latest_run = db.scalar(select(ForecastRun).order_by(ForecastRun.id.desc()).limit(1))
    if latest_run:
        outputs = db.scalars(select(ForecastOutput).where(ForecastOutput.forecast_run_id == latest_run.id)).all()
        for output in outputs:
            if output.shortage_probability >= 0.6 and not _alert_exists(
                db,
                alert_type="shortage_risk",
                municipality_id=output.municipality_id,
                linked_forecast_id=output.id,
            ):
                alert = Alert(
                    alert_type="shortage_risk",
                    severity="high" if output.shortage_probability > 0.75 else "medium",
                    title="Projected supply shortage risk",
                    scope_type="municipality",
                    municipality_id=output.municipality_id,
                    summary="Forecast indicates potential supply shortfall next month.",
                    recommended_action="Coordinate staged stock releases and monitor local market inflows.",
                    linked_forecast_id=output.id,
                    status="open",
                )
                db.add(alert)
                db.flush()
                created.append(alert)

            if output.oversupply_probability >= 0.6 and not _alert_exists(
                db,
                alert_type="oversupply_risk",
                municipality_id=output.municipality_id,
                linked_forecast_id=output.id,
            ):
                alert = Alert(
                    alert_type="oversupply_risk",
                    severity="medium",
                    title="Projected oversupply risk",
                    scope_type="municipality",
                    municipality_id=output.municipality_id,
                    summary="Forecast indicates potential oversupply pressure next month.",
                    recommended_action="Review pacing of imports and storage turnover plans.",
                    linked_forecast_id=output.id,
                    status="open",
                )
                db.add(alert)
                db.flush()
                created.append(alert)

    anomaly_events = db.scalars(
        select(AnomalyEvent).where(AnomalyEvent.reporting_month == reporting_month, AnomalyEvent.status == "open")
    ).all()
    for event in anomaly_events:
        mapping = {
            "stock_release_mismatch": ("stock_retention_anomaly_risk", "high", "Stock retention anomaly"),
            "price_stock_conflict": ("price_pressure_risk", "high", "Price pressure despite stock"),
            "import_harvest_collision": ("import_timing_risk", "medium", "Import timing overlap risk"),
            "price_spread_outlier": ("price_pressure_risk", "medium", "Abnormal price spread"),
            "stock_movement_discrepancy": ("stock_retention_anomaly_risk", "high", "Stock movement discrepancy"),
        }
        alert_type, severity, title = mapping.get(event.anomaly_type, ("price_pressure_risk", "medium", "Market anomaly"))

        if _alert_exists(db, alert_type=alert_type, municipality_id=event.municipality_id, warehouse_id=event.warehouse_id, linked_anomaly_id=event.id):
            continue

        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            title=title,
            scope_type=event.scope_type,
            municipality_id=event.municipality_id,
            warehouse_id=event.warehouse_id,
            market_id=event.market_id,
            summary=event.summary,
            recommended_action="Validate records, coordinate field checks, and issue corrective operational directive if confirmed.",
            linked_anomaly_id=event.id,
            status="open",
        )
        db.add(alert)
        db.flush()
        created.append(alert)

    # Compliance risk: municipalities with no harvest submission this month.
    municipalities = db.scalars(select(Municipality)).all()
    for municipality in municipalities:
        report_count = int(
            db.scalar(
                select(func.count(HarvestReport.id)).where(
                    HarvestReport.municipality_id == municipality.id,
                    HarvestReport.reporting_month == reporting_month,
                )
            )
            or 0
        )
        if report_count == 0 and not _alert_exists(db, alert_type="reporting_compliance_risk", municipality_id=municipality.id):
            alert = Alert(
                alert_type="reporting_compliance_risk",
                severity="medium",
                title="Missing monthly production submission",
                scope_type="municipality",
                municipality_id=municipality.id,
                summary=f"{municipality.name} has no harvest report for the reporting month.",
                recommended_action="Notify municipal encoder and enforce submission SLA.",
                status="open",
            )
            db.add(alert)
            db.flush()
            created.append(alert)

    # Import timing risk when large imports coincide with month.
    import_volume = float(
        db.scalar(select(func.coalesce(func.sum(ImportRecord.volume_tons), 0.0)).where(ImportRecord.reporting_month == reporting_month))
        or 0.0
    )
    if import_volume > 350 and not _alert_exists(db, alert_type="import_timing_risk"):
        alert = Alert(
            alert_type="import_timing_risk",
            severity="medium",
            title="High import volume timing risk",
            scope_type="provincial",
            summary="Import arrivals are elevated for the current reporting month.",
            recommended_action="Review release and procurement timing against local harvest windows.",
            status="open",
        )
        db.add(alert)
        db.flush()
        created.append(alert)

    return created


def acknowledge_alert(db: Session, alert: Alert, user_id: int, notes: str | None = None) -> Alert:
    alert.status = "acknowledged"
    append_alert_action(
        db,
        AlertAcknowledgement(alert_id=alert.id, user_id=user_id, action="acknowledged", notes=notes),
    )
    db.flush()
    return alert


def resolve_alert(db: Session, alert: Alert, user_id: int, notes: str | None = None) -> Alert:
    alert.status = "resolved"
    append_alert_action(
        db,
        AlertAcknowledgement(alert_id=alert.id, user_id=user_id, action="resolved", notes=notes),
    )
    db.flush()
    return alert
