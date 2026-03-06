from __future__ import annotations

from datetime import date
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    AnomalyEvent,
    ColdStorageStockReport,
    FarmgatePriceReport,
    ForecastOutput,
    ForecastRun,
    HarvestReport,
    ImportRecord,
    JobRun,
    Municipality,
    ReportRecord,
    Role,
    StockReleaseLog,
    User,
    Warehouse,
    WarehouseStockReport,
    WholesalePriceReport,
    RetailPriceReport,
)
from app.schemas.auth import CurrentUser


READONLY_GLOBAL_ROLES = {"super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"}


def _is_scoped_user(user: CurrentUser) -> bool:
    return "municipal_encoder" in user.roles or "warehouse_operator" in user.roles


def _municipality_filter(user: CurrentUser):
    if _is_scoped_user(user) and user.municipality_id:
        return user.municipality_id
    return None


def provincial_overview(db: Session, current_user: CurrentUser) -> dict:
    municipality_scope = _municipality_filter(current_user)

    reporting_month = db.scalar(select(func.max(HarvestReport.reporting_month))) or date.today().replace(day=1)

    harvest_stmt = select(func.coalesce(func.sum(HarvestReport.volume_tons), 0.0)).where(HarvestReport.reporting_month == reporting_month)
    stock_stmt = select(func.coalesce(func.sum(WarehouseStockReport.current_stock_tons), 0.0)).where(
        WarehouseStockReport.reporting_month == reporting_month
    )
    cold_stmt = select(func.coalesce(func.avg(ColdStorageStockReport.utilization_pct), 0.0)).where(
        ColdStorageStockReport.reporting_month == reporting_month
    )
    release_stmt = select(func.coalesce(func.sum(StockReleaseLog.volume_tons), 0.0)).where(
        StockReleaseLog.reporting_month == reporting_month
    )

    if municipality_scope:
        harvest_stmt = harvest_stmt.where(HarvestReport.municipality_id == municipality_scope)
        stock_stmt = stock_stmt.where(WarehouseStockReport.municipality_id == municipality_scope)
        cold_stmt = cold_stmt.where(ColdStorageStockReport.municipality_id == municipality_scope)

    total_harvest = float(db.scalar(harvest_stmt) or 0.0)
    current_stock = float(db.scalar(stock_stmt) or 0.0)
    cold_util = float(db.scalar(cold_stmt) or 0.0)
    release_volume = float(db.scalar(release_stmt) or 0.0)

    latest_run_id = db.scalar(select(func.max(ForecastRun.id)))
    forecast_sum_stmt = select(func.coalesce(func.sum(ForecastOutput.next_month_supply_tons), 0.0))
    if latest_run_id:
        forecast_sum_stmt = forecast_sum_stmt.where(ForecastOutput.forecast_run_id == latest_run_id)
    if municipality_scope:
        forecast_sum_stmt = forecast_sum_stmt.where(ForecastOutput.municipality_id == municipality_scope)
    forecast_supply = float(db.scalar(forecast_sum_stmt) or 0.0)

    active_alerts_stmt = select(func.count(Alert.id)).where(Alert.status.in_(["open", "acknowledged"]))
    if municipality_scope:
        active_alerts_stmt = active_alerts_stmt.where(Alert.municipality_id == municipality_scope)
    active_alerts = int(db.scalar(active_alerts_stmt) or 0)

    anomaly_stmt = (
        select(Municipality.name, func.count(AnomalyEvent.id).label("count"))
        .join(Municipality, Municipality.id == AnomalyEvent.municipality_id, isouter=True)
        .where(AnomalyEvent.reporting_month == reporting_month)
        .group_by(Municipality.name)
        .order_by(func.count(AnomalyEvent.id).desc())
        .limit(5)
    )
    if municipality_scope:
        anomaly_stmt = anomaly_stmt.where(AnomalyEvent.municipality_id == municipality_scope)
    anomaly_hotspots = [row[0] for row in db.execute(anomaly_stmt).all() if row[0]]

    muni_stmt = select(Municipality.id, Municipality.name).order_by(Municipality.name)
    if municipality_scope:
        muni_stmt = muni_stmt.where(Municipality.id == municipality_scope)

    municipality_cards = []
    for muni_id, muni_name in db.execute(muni_stmt).all():
        production = float(
            db.scalar(
                select(func.coalesce(func.sum(HarvestReport.volume_tons), 0.0)).where(
                    HarvestReport.municipality_id == muni_id,
                    HarvestReport.reporting_month == reporting_month,
                )
            )
            or 0.0
        )
        stock = float(
            db.scalar(
                select(func.coalesce(func.sum(WarehouseStockReport.current_stock_tons), 0.0)).where(
                    WarehouseStockReport.municipality_id == muni_id,
                    WarehouseStockReport.reporting_month == reporting_month,
                )
            )
            or 0.0
        )
        avg_price = float(
            db.scalar(
                select(func.coalesce(func.avg(FarmgatePriceReport.price_per_kg), 0.0)).where(
                    FarmgatePriceReport.municipality_id == muni_id,
                    FarmgatePriceReport.reporting_month == reporting_month,
                )
            )
            or 0.0
        )
        municipality_cards.append(
            {
                "municipality_id": muni_id,
                "municipality_name": muni_name,
                "production_tons": production,
                "stock_tons": stock,
                "avg_farmgate_price": round(avg_price, 2),
            }
        )

    return {
        "reporting_month": reporting_month,
        "total_harvest_volume_tons": round(total_harvest, 2),
        "current_warehouse_stock_tons": round(current_stock, 2),
        "cold_storage_utilization_pct": round(cold_util, 2),
        "stock_release_volume_tons": round(release_volume, 2),
        "forecast_next_month_supply_tons": round(forecast_supply, 2),
        "active_alerts": active_alerts,
        "anomaly_hotspots": anomaly_hotspots,
        "municipality_cards": municipality_cards,
    }


def municipal_overview(db: Session, municipality_id: int, current_user: CurrentUser) -> dict:
    municipality_scope = _municipality_filter(current_user)
    if municipality_scope and municipality_scope != municipality_id:
        return {"error": "Forbidden"}

    reporting_month = db.scalar(select(func.max(HarvestReport.reporting_month))) or date.today().replace(day=1)

    production = float(
        db.scalar(
            select(func.coalesce(func.sum(HarvestReport.volume_tons), 0.0)).where(
                HarvestReport.municipality_id == municipality_id,
                HarvestReport.reporting_month == reporting_month,
            )
        )
        or 0.0
    )
    stock = float(
        db.scalar(
            select(func.coalesce(func.sum(WarehouseStockReport.current_stock_tons), 0.0)).where(
                WarehouseStockReport.municipality_id == municipality_id,
                WarehouseStockReport.reporting_month == reporting_month,
            )
        )
        or 0.0
    )

    prices = db.execute(
        select(FarmgatePriceReport.report_date, FarmgatePriceReport.price_per_kg)
        .where(FarmgatePriceReport.municipality_id == municipality_id)
        .order_by(FarmgatePriceReport.report_date.desc())
        .limit(6)
    ).all()

    alerts = db.execute(
        select(Alert.id, Alert.title, Alert.severity, Alert.status)
        .where(Alert.municipality_id == municipality_id)
        .order_by(Alert.opened_at.desc())
        .limit(8)
    ).all()

    compliance_reports = int(
        db.scalar(
            select(func.count(HarvestReport.id)).where(
                HarvestReport.municipality_id == municipality_id,
                HarvestReport.reporting_month == reporting_month,
            )
        )
        or 0
    )

    return {
        "municipality_id": municipality_id,
        "reporting_month": reporting_month,
        "production_tons": round(production, 2),
        "stock_tons": round(stock, 2),
        "recent_price_reports": [{"report_date": d, "price_per_kg": p} for d, p in prices],
        "local_alerts": [{"id": i, "title": t, "severity": s, "status": st} for i, t, s, st in alerts],
        "recent_submissions": compliance_reports,
        "reporting_compliance_pct": min(100.0, compliance_reports * 20.0),
    }


def warehouses_overview(db: Session, current_user: CurrentUser) -> list[dict]:
    municipality_scope = _municipality_filter(current_user)

    wh_stmt = select(Warehouse.id, Warehouse.name, Warehouse.location, Warehouse.capacity_tons, Municipality.name, Warehouse.municipality_id).join(
        Municipality, Municipality.id == Warehouse.municipality_id
    )
    if municipality_scope:
        wh_stmt = wh_stmt.where(Warehouse.municipality_id == municipality_scope)

    rows = []
    for warehouse_id, name, location, capacity, municipality_name, municipality_id in db.execute(wh_stmt).all():
        latest_report = db.execute(
            select(WarehouseStockReport.report_date, WarehouseStockReport.current_stock_tons)
            .where(WarehouseStockReport.warehouse_id == warehouse_id)
            .order_by(WarehouseStockReport.report_date.desc())
            .limit(1)
        ).first()
        release_trend = float(
            db.scalar(select(func.coalesce(func.sum(StockReleaseLog.volume_tons), 0.0)).where(StockReleaseLog.warehouse_id == warehouse_id))
            or 0.0
        )
        anomaly_flag = (
            db.scalar(
                select(func.count(AnomalyEvent.id)).where(
                    AnomalyEvent.warehouse_id == warehouse_id,
                    AnomalyEvent.status == "open",
                )
            )
            or 0
        ) > 0

        stock = float(latest_report[1]) if latest_report else 0.0
        utilization = (stock / capacity * 100.0) if capacity else 0.0
        rows.append(
            {
                "warehouse_id": warehouse_id,
                "warehouse_name": name,
                "municipality_name": municipality_name,
                "location": location,
                "capacity_tons": float(capacity),
                "current_stock_tons": round(stock, 2),
                "utilization_pct": round(utilization, 2),
                "last_update": latest_report[0] if latest_report else None,
                "release_trend_tons": round(release_trend, 2),
                "anomaly_flag": anomaly_flag,
                "municipality_id": municipality_id,
            }
        )

    return rows


def prices_overview(db: Session, current_user: CurrentUser) -> dict:
    municipality_scope = _municipality_filter(current_user)

    farmgate_stmt = select(FarmgatePriceReport.report_date, FarmgatePriceReport.price_per_kg, FarmgatePriceReport.municipality_id).order_by(
        FarmgatePriceReport.report_date
    )
    wholesale_stmt = select(WholesalePriceReport.report_date, WholesalePriceReport.price_per_kg, WholesalePriceReport.municipality_id).order_by(
        WholesalePriceReport.report_date
    )
    retail_stmt = select(RetailPriceReport.report_date, RetailPriceReport.price_per_kg, RetailPriceReport.municipality_id).order_by(
        RetailPriceReport.report_date
    )

    if municipality_scope:
        farmgate_stmt = farmgate_stmt.where(FarmgatePriceReport.municipality_id == municipality_scope)
        wholesale_stmt = wholesale_stmt.where(WholesalePriceReport.municipality_id == municipality_scope)
        retail_stmt = retail_stmt.where(RetailPriceReport.municipality_id == municipality_scope)

    farmgate = [{"date": d, "price": p, "municipality_id": m} for d, p, m in db.execute(farmgate_stmt).all()]
    wholesale = [{"date": d, "price": p, "municipality_id": m} for d, p, m in db.execute(wholesale_stmt).all()]
    retail = [{"date": d, "price": p, "municipality_id": m} for d, p, m in db.execute(retail_stmt).all()]

    spreads = []
    for index in range(min(len(retail), len(farmgate))):
        spreads.append(
            {
                "date": retail[index]["date"],
                "spread": round(retail[index]["price"] - farmgate[index]["price"], 2),
            }
        )

    muni_prices = db.execute(
        select(Municipality.name, func.avg(FarmgatePriceReport.price_per_kg), func.avg(WholesalePriceReport.price_per_kg), func.avg(RetailPriceReport.price_per_kg))
        .join(FarmgatePriceReport, FarmgatePriceReport.municipality_id == Municipality.id, isouter=True)
        .join(WholesalePriceReport, WholesalePriceReport.municipality_id == Municipality.id, isouter=True)
        .join(RetailPriceReport, RetailPriceReport.municipality_id == Municipality.id, isouter=True)
        .group_by(Municipality.name)
        .order_by(Municipality.name)
    ).all()

    pressure_warnings = []
    for name, fg, wh, rt in muni_prices:
        fg_val = float(fg or 0)
        rt_val = float(rt or 0)
        if fg_val > 0 and (rt_val - fg_val) > 25:
            pressure_warnings.append(f"{name}: elevated farmgate-retail spread")

    return {
        "farmgate_trend": farmgate,
        "wholesale_trend": wholesale,
        "retail_trend": retail,
        "price_spread": spreads,
        "municipality_comparison": [
            {
                "municipality": name,
                "avg_farmgate": round(float(fg or 0), 2),
                "avg_wholesale": round(float(wh or 0), 2),
                "avg_retail": round(float(rt or 0), 2),
            }
            for name, fg, wh, rt in muni_prices
        ],
        "price_pressure_warnings": pressure_warnings,
    }


def imports_overview(db: Session, current_user: CurrentUser) -> dict:
    imports = db.execute(
        select(
            ImportRecord.id,
            ImportRecord.import_reference,
            ImportRecord.arrival_date,
            ImportRecord.volume_tons,
            ImportRecord.origin_country,
            ImportRecord.status,
        ).order_by(ImportRecord.arrival_date.desc())
    ).all()

    high_harvest_months = {
        row[0]
        for row in db.execute(
            select(HarvestReport.reporting_month).group_by(HarvestReport.reporting_month).having(func.sum(HarvestReport.volume_tons) > 500)
        ).all()
    }

    records = []
    risks = []
    for rec_id, ref, arrival, volume, origin, status in imports:
        overlap = arrival.replace(day=1) in high_harvest_months
        timing_risk = "high" if overlap and volume > 300 else "medium" if overlap else "low"
        records.append(
            {
                "id": rec_id,
                "import_reference": ref,
                "arrival_date": arrival,
                "volume_tons": volume,
                "origin": origin,
                "status": status,
                "overlap_with_harvest_window": overlap,
                "timing_risk": timing_risk,
            }
        )
        if timing_risk in {"high", "medium"}:
            risks.append(f"{ref}: {timing_risk} import timing risk")

    return {"imports": records, "risk_assessment": risks}


def alerts_overview(db: Session, current_user: CurrentUser) -> dict:
    municipality_scope = _municipality_filter(current_user)
    alert_stmt = select(Alert)
    if municipality_scope:
        alert_stmt = alert_stmt.where(Alert.municipality_id == municipality_scope)
    alerts = list(db.scalars(alert_stmt))

    by_severity: dict[str, int] = {}
    for alert in alerts:
        by_severity[alert.severity] = by_severity.get(alert.severity, 0) + 1

    return {
        "active_alerts": [
            {
                "id": a.id,
                "title": a.title,
                "severity": a.severity,
                "type": a.alert_type,
                "status": a.status,
                "scope_type": a.scope_type,
                "municipality_id": a.municipality_id,
                "warehouse_id": a.warehouse_id,
            }
            for a in alerts
            if a.status in {"open", "acknowledged"}
        ],
        "severity_counts": by_severity,
        "open_count": sum(1 for a in alerts if a.status == "open"),
    }


def reports_overview(db: Session, current_user: CurrentUser) -> dict:
    reports = db.execute(
        select(ReportRecord.id, ReportRecord.category, ReportRecord.title, ReportRecord.reporting_month, ReportRecord.status, ReportRecord.file_path)
        .order_by(ReportRecord.generated_at.desc())
        .limit(24)
    ).all()

    monthly_counts = db.execute(
        select(ReportRecord.reporting_month, func.count(ReportRecord.id)).group_by(ReportRecord.reporting_month).order_by(ReportRecord.reporting_month.desc())
    ).all()

    return {
        "reports": [
            {
                "id": rid,
                "category": category,
                "title": title,
                "reporting_month": month,
                "status": status,
                "file_path": path,
            }
            for rid, category, title, month, status, path in reports
        ],
        "monthly_summary": [{"reporting_month": month, "count": count} for month, count in monthly_counts],
    }


def admin_overview(db: Session, current_user: CurrentUser) -> dict:
    users_count = int(db.scalar(select(func.count(User.id))) or 0)
    roles_count = int(db.scalar(select(func.count(Role.id))) or 0)
    docs_count = int(db.scalar(select(func.count()).select_from(Alert)) or 0)
    job_runs = db.execute(select(JobRun.job_name, JobRun.status, JobRun.started_at).order_by(JobRun.started_at.desc()).limit(20)).all()

    return {
        "users_count": users_count,
        "roles_count": roles_count,
        "active_alerts": docs_count,
        "job_status": [{"job_name": j, "status": s, "started_at": dt} for j, s, dt in job_runs],
        "pipeline_runs": [{"job_name": j, "status": s, "started_at": dt} for j, s, dt in job_runs],
        "system_settings": {"environment": "development", "feature_flags": {"knowledge_center": True}},
    }
