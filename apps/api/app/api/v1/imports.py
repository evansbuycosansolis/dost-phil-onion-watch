from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import ImportRecord
from app.schemas.auth import CurrentUser
from app.schemas.domain import ImportRecordCreate
from app.services.audit_service import emit_audit_event
from app.services.import_service import create_import_record, list_import_records, list_shipments

router = APIRouter(prefix="/imports", tags=["imports"], responses=router_default_responses("imports"))


@router.get("/")
def get_imports(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    rows = list_import_records(db)
    return [
        {
            "id": r.id,
            "import_reference": r.import_reference,
            "origin_country": r.origin_country,
            "arrival_date": r.arrival_date,
            "reporting_month": r.reporting_month,
            "volume_tons": r.volume_tons,
            "status": r.status,
        }
        for r in rows
    ]


@router.post("/")
def create_import(
    payload: ImportRecordCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer"))],
):
    record = ImportRecord(
        import_reference=payload.import_reference,
        origin_country=payload.origin_country,
        arrival_date=payload.arrival_date,
        reporting_month=payload.reporting_month,
        volume_tons=payload.volume_tons,
        status=payload.status,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    create_import_record(db, record)

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="imports.create",
        entity_type="import_record",
        entity_id=str(record.id),
        after_payload={"import_reference": record.import_reference, "volume_tons": record.volume_tons},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"id": record.id}


@router.get("/shipments")
def get_shipments(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer", "market_analyst", "auditor"))],
):
    shipments = list_shipments(db)
    return [
        {
            "id": s.id,
            "import_record_id": s.import_record_id,
            "port_name": s.port_name,
            "arrival_date": s.arrival_date,
            "volume_tons": s.volume_tons,
            "inspection_status": s.inspection_status,
        }
        for s in shipments
    ]
