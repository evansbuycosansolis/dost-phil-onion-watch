from typing import Annotated
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.schemas.auth import CurrentUser
from app.schemas.audit import AuditEventDTO, AuditEventDiffDTO
from app.services.audit_service import (
    build_structured_diff,
    event_to_dict,
    export_events_as_csv,
    export_events_as_json,
    get_audit_event,
    list_audit_events,
    summarize_diff,
)

router = APIRouter(prefix="/audit", tags=["audit"], responses=router_default_responses("audit"))


@router.get("/events", response_model=list[AuditEventDTO])
def audit_events(
    limit: int = Query(default=200, ge=1, le=2000),
    actor_user_id: int | None = Query(default=None),
    action_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    start_timestamp: datetime | None = Query(default=None),
    end_timestamp: datetime | None = Query(default=None),
    db: Annotated[Session, Depends(get_db)] = None,
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "auditor", "provincial_admin"))] = None,
):
    rows = list_audit_events(
        db,
        limit=limit,
        actor_user_id=actor_user_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
    )
    return [event_to_dict(row) for row in rows]


@router.get("/events/{event_id}/diff", response_model=AuditEventDiffDTO)
def audit_event_diff(
    event_id: int,
    db: Annotated[Session, Depends(get_db)] = None,
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "auditor", "provincial_admin"))] = None,
):
    event = get_audit_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Audit event not found")
    changes = build_structured_diff(event.before_payload, event.after_payload)
    summary = summarize_diff(changes)
    return {
        "event": event_to_dict(event),
        "summary": summary,
        "changes": changes,
    }


@router.get("/events/export")
def export_audit_events(
    format: Literal["csv", "json"] = Query(default="csv"),
    limit: int = Query(default=500, ge=1, le=5000),
    actor_user_id: int | None = Query(default=None),
    action_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    start_timestamp: datetime | None = Query(default=None),
    end_timestamp: datetime | None = Query(default=None),
    db: Annotated[Session, Depends(get_db)] = None,
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "auditor", "provincial_admin"))] = None,
):
    events = list_audit_events(
        db,
        limit=limit,
        actor_user_id=actor_user_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    if format == "csv":
        content = export_events_as_csv(events)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="audit_slice_{stamp}.csv"'},
        )
    payload = export_events_as_json(events)
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"Content-Disposition": f'attachment; filename="audit_slice_{stamp}.json"'},
    )
