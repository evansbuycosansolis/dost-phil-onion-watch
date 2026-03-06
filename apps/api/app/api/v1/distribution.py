from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import DistributionLog, StockReleaseLog, TransportLog
from app.schemas.auth import CurrentUser
from app.services.audit_service import emit_audit_event

router = APIRouter(prefix="/distribution", tags=["distribution"], responses=router_default_responses("distribution"))


@router.get("/stock-releases")
def list_stock_releases(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "warehouse_operator", "market_analyst", "auditor", "executive_viewer"))],
):
    rows = db.scalars(select(StockReleaseLog).order_by(StockReleaseLog.release_date.desc()).limit(100)).all()
    return [
        {
            "id": r.id,
            "warehouse_id": r.warehouse_id,
            "release_date": r.release_date,
            "reporting_month": r.reporting_month,
            "volume_tons": r.volume_tons,
            "destination_market_id": r.destination_market_id,
        }
        for r in rows
    ]


@router.post("/stock-releases")
def create_stock_release(
    payload: dict,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "warehouse_operator"))],
):
    record = StockReleaseLog(
        warehouse_id=payload["warehouse_id"],
        release_date=payload["release_date"],
        reporting_month=payload["reporting_month"],
        volume_tons=payload["volume_tons"],
        destination_market_id=payload.get("destination_market_id"),
        notes=payload.get("notes"),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(record)
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="distribution.stock_release.create",
        entity_type="stock_release_log",
        entity_id=str(record.id),
        after_payload={"warehouse_id": record.warehouse_id, "volume_tons": record.volume_tons},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"id": record.id}


@router.get("/transport-logs")
def list_transport_logs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "warehouse_operator", "market_analyst", "auditor"))],
):
    rows = db.scalars(select(TransportLog).order_by(TransportLog.transport_date.desc()).limit(100)).all()
    return [
        {
            "id": t.id,
            "origin_warehouse_id": t.origin_warehouse_id,
            "destination_market_id": t.destination_market_id,
            "transport_date": t.transport_date,
            "volume_tons": t.volume_tons,
            "vehicle_plate": t.vehicle_plate,
        }
        for t in rows
    ]


@router.get("/logs")
def list_distribution_logs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "warehouse_operator", "market_analyst", "auditor", "executive_viewer"))],
):
    rows = db.scalars(select(DistributionLog).order_by(DistributionLog.distribution_date.desc()).limit(100)).all()
    return [
        {
            "id": d.id,
            "municipality_id": d.municipality_id,
            "market_id": d.market_id,
            "distribution_date": d.distribution_date,
            "volume_tons": d.volume_tons,
        }
        for d in rows
    ]
