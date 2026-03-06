from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import FarmerProfile
from app.schemas.auth import CurrentUser
from app.schemas.domain import FarmerCreate
from app.services.audit_service import emit_audit_event

router = APIRouter(prefix="/farmers", tags=["farmers"], responses=router_default_responses("farmers"))


@router.get("/")
def list_farmers(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "municipal_encoder", "auditor"))],
):
    stmt = select(FarmerProfile).order_by(FarmerProfile.full_name)
    if "municipal_encoder" in current_user.roles and current_user.municipality_id:
        stmt = stmt.where(FarmerProfile.municipality_id == current_user.municipality_id)
    farmers = db.scalars(stmt).all()
    return [
        {
            "id": f.id,
            "farmer_code": f.farmer_code,
            "full_name": f.full_name,
            "municipality_id": f.municipality_id,
            "phone_number": f.phone_number,
        }
        for f in farmers
    ]


@router.post("/")
def create_farmer(
    payload: FarmerCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "municipal_encoder"))],
):
    farmer = FarmerProfile(
        farmer_code=payload.farmer_code,
        full_name=payload.full_name,
        municipality_id=payload.municipality_id,
        barangay_id=payload.barangay_id,
        phone_number=payload.phone_number,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(farmer)
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="farmer.create",
        entity_type="farmer_profile",
        entity_id=str(farmer.id),
        after_payload={"farmer_code": farmer.farmer_code, "municipality_id": farmer.municipality_id},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"id": farmer.id, "farmer_code": farmer.farmer_code}
