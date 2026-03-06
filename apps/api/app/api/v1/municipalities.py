from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import Municipality
from app.schemas.auth import CurrentUser
from app.schemas.domain import MunicipalityCreate
from app.services.audit_service import emit_audit_event

router = APIRouter(prefix="/municipalities", tags=["municipalities"], responses=router_default_responses("municipalities"))


@router.get("/")
def list_municipalities(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "municipal_encoder", "warehouse_operator", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    rows = db.scalars(select(Municipality).order_by(Municipality.name)).all()
    return [
        {"id": row.id, "code": row.code, "name": row.name, "province": row.province, "region": row.region}
        for row in rows
    ]


@router.post("/")
def create_municipality(
    payload: MunicipalityCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
):
    if db.scalar(select(Municipality).where(Municipality.code == payload.code)):
        raise HTTPException(status_code=409, detail="Municipality code exists")

    municipality = Municipality(code=payload.code, name=payload.name, province=payload.province, region=payload.region)
    db.add(municipality)
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="municipality.create",
        entity_type="municipality",
        entity_id=str(municipality.id),
        after_payload={"code": municipality.code, "name": municipality.name},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"id": municipality.id, "code": municipality.code, "name": municipality.name}
