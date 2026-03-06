from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.core.security import hash_password
from app.models import Role, User, UserRole
from app.schemas.auth import CurrentUser, UserSummary
from app.services.audit_service import emit_audit_event
from app.services.auth_service import get_user_roles

router = APIRouter(prefix="/users", tags=["users"], responses=router_default_responses("users"))


@router.get("/", response_model=list[UserSummary])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor"))],
) -> list[UserSummary]:
    users = list(db.scalars(select(User).order_by(User.full_name)))
    result = []
    for user in users:
        roles = get_user_roles(db, user.id)
        result.append(UserSummary(id=user.id, email=user.email, full_name=user.full_name, roles=roles, is_active=user.is_active))
    return result


@router.post("/", response_model=UserSummary)
def create_user(
    payload: dict,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
) -> UserSummary:
    email = payload.get("email")
    full_name = payload.get("full_name")
    roles = payload.get("roles", [])
    municipality_id = payload.get("municipality_id")

    if not email or not full_name or not roles:
        raise HTTPException(status_code=400, detail="email, full_name, and roles are required")

    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(payload.get("password", "ChangeMe123!")),
        municipality_id=municipality_id,
    )
    db.add(user)
    db.flush()

    assigned = []
    for role_name in roles:
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role:
            db.add(UserRole(user_id=user.id, role_id=role.id))
            assigned.append(role_name)
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="user.create",
        entity_type="user",
        entity_id=str(user.id),
        after_payload={"email": user.email, "roles": assigned},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return UserSummary(id=user.id, email=user.email, full_name=user.full_name, roles=assigned, is_active=user.is_active)
