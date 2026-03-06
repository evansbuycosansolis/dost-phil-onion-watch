from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import HarvestReport
from app.schemas.auth import CurrentUser
from app.schemas.domain import HarvestReportCreate
from app.services.audit_service import emit_audit_event
from app.services.production_service import create_harvest_report, list_harvest_reports

router = APIRouter(prefix="/production", tags=["production"], responses=router_default_responses("production"))


@router.get("/harvest-reports")
def get_harvest_reports(
    municipality_id: int | None = None,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "municipal_encoder", "executive_viewer", "auditor", "market_analyst"))] = None,
):
    scoped = municipality_id
    if "municipal_encoder" in current_user.roles and current_user.municipality_id:
        scoped = current_user.municipality_id
    rows = list_harvest_reports(db, scoped)
    return [
        {
            "id": r.id,
            "municipality_id": r.municipality_id,
            "reporting_month": r.reporting_month,
            "harvest_date": r.harvest_date,
            "volume_tons": r.volume_tons,
            "quality_grade": r.quality_grade,
        }
        for r in rows
    ]


@router.post("/harvest-reports")
def create_harvest(
    payload: HarvestReportCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "municipal_encoder"))],
):
    report = HarvestReport(
        municipality_id=payload.municipality_id,
        farmer_id=payload.farmer_id,
        reporting_month=payload.reporting_month,
        harvest_date=payload.harvest_date,
        volume_tons=payload.volume_tons,
        quality_grade=payload.quality_grade,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    create_harvest_report(db, report)

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="production.harvest.create",
        entity_type="harvest_report",
        entity_id=str(report.id),
        after_payload={"municipality_id": report.municipality_id, "volume_tons": report.volume_tons},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"id": report.id, "message": "Harvest report recorded"}
