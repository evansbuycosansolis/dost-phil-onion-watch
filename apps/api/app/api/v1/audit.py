from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import AuditLog
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/audit", tags=["audit"], responses=router_default_responses("audit"))


@router.get("/events")
def audit_events(
    limit: int = 200,
    db: Annotated[Session, Depends(get_db)] = None,
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "auditor", "provincial_admin"))] = None,
):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "actor_user_id": row.actor_user_id,
            "action_type": row.action_type,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "timestamp": row.timestamp,
            "before_payload": row.before_payload,
            "after_payload": row.after_payload,
            "correlation_id": row.correlation_id,
            "metadata": row.metadata_json,
        }
        for row in rows
    ]
