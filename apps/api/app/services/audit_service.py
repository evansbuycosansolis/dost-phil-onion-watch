from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def emit_audit_event(
    db: Session,
    *,
    actor_user_id: int | None,
    action_type: str,
    entity_type: str,
    entity_id: str,
    before_payload: dict[str, Any] | None = None,
    after_payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    event = AuditLog(
        actor_user_id=actor_user_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        before_payload=before_payload,
        after_payload=after_payload,
        correlation_id=correlation_id,
        metadata_json=metadata,
    )
    db.add(event)
    db.flush()
    return event
