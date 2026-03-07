from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
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


def list_audit_events(
    db: Session,
    *,
    limit: int = 200,
    actor_user_id: int | None = None,
    action_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    correlation_id: str | None = None,
    start_timestamp: datetime | None = None,
    end_timestamp: datetime | None = None,
) -> list[AuditLog]:
    stmt = select(AuditLog)
    if actor_user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if action_type:
        stmt = stmt.where(AuditLog.action_type == action_type)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if correlation_id:
        stmt = stmt.where(AuditLog.correlation_id == correlation_id)
    if start_timestamp:
        stmt = stmt.where(AuditLog.timestamp >= start_timestamp)
    if end_timestamp:
        stmt = stmt.where(AuditLog.timestamp <= end_timestamp)
    stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def get_audit_event(db: Session, event_id: int) -> AuditLog | None:
    return db.get(AuditLog, event_id)


def _path_join(base: str, key: str) -> str:
    if not base:
        return key
    if key.startswith("["):
        return f"{base}{key}"
    return f"{base}.{key}"


def _append_change(
    out: list[dict[str, Any]],
    *,
    path: str,
    change_type: str,
    before_value: Any = None,
    after_value: Any = None,
) -> None:
    out.append(
        {
            "path": path or "$",
            "change_type": change_type,
            "before_value": before_value,
            "after_value": after_value,
        }
    )


def _diff_values(before_value: Any, after_value: Any, *, path: str, out: list[dict[str, Any]]) -> None:
    if isinstance(before_value, dict) and isinstance(after_value, dict):
        keys = sorted(set(before_value.keys()) | set(after_value.keys()))
        for key in keys:
            has_before = key in before_value
            has_after = key in after_value
            child_path = _path_join(path, key)
            if has_before and not has_after:
                _append_change(out, path=child_path, change_type="removed", before_value=before_value[key], after_value=None)
                continue
            if has_after and not has_before:
                _append_change(out, path=child_path, change_type="added", before_value=None, after_value=after_value[key])
                continue
            _diff_values(before_value[key], after_value[key], path=child_path, out=out)
        return

    if isinstance(before_value, list) and isinstance(after_value, list):
        max_len = max(len(before_value), len(after_value))
        for index in range(max_len):
            child_path = _path_join(path, f"[{index}]")
            has_before = index < len(before_value)
            has_after = index < len(after_value)
            if has_before and not has_after:
                _append_change(out, path=child_path, change_type="removed", before_value=before_value[index], after_value=None)
                continue
            if has_after and not has_before:
                _append_change(out, path=child_path, change_type="added", before_value=None, after_value=after_value[index])
                continue
            _diff_values(before_value[index], after_value[index], path=child_path, out=out)
        return

    if before_value != after_value:
        _append_change(out, path=path, change_type="modified", before_value=before_value, after_value=after_value)


def build_structured_diff(before_payload: Any, after_payload: Any) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    _diff_values(before_payload, after_payload, path="", out=changes)
    return changes


def summarize_diff(changes: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"total_changes": len(changes), "added": 0, "removed": 0, "modified": 0}
    for change in changes:
        kind = str(change.get("change_type") or "")
        if kind in {"added", "removed", "modified"}:
            summary[kind] += 1
    return summary


def event_to_dict(event: AuditLog) -> dict[str, Any]:
    return {
        "id": event.id,
        "actor_user_id": event.actor_user_id,
        "action_type": event.action_type,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "timestamp": event.timestamp,
        "before_payload": event.before_payload,
        "after_payload": event.after_payload,
        "correlation_id": event.correlation_id,
        "metadata": event.metadata_json,
    }


def export_events_as_csv(events: list[AuditLog]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "timestamp",
            "actor_user_id",
            "action_type",
            "entity_type",
            "entity_id",
            "correlation_id",
            "change_count",
            "changed_paths",
            "before_payload",
            "after_payload",
            "metadata",
        ],
    )
    writer.writeheader()
    for event in events:
        changes = build_structured_diff(event.before_payload, event.after_payload)
        writer.writerow(
            {
                "id": event.id,
                "timestamp": event.timestamp.isoformat(),
                "actor_user_id": event.actor_user_id,
                "action_type": event.action_type,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "correlation_id": event.correlation_id or "",
                "change_count": len(changes),
                "changed_paths": "|".join(change["path"] for change in changes),
                "before_payload": json.dumps(event.before_payload or {}, ensure_ascii=False),
                "after_payload": json.dumps(event.after_payload or {}, ensure_ascii=False),
                "metadata": json.dumps(event.metadata_json or {}, ensure_ascii=False),
            }
        )
    return output.getvalue()


def export_events_as_json(events: list[AuditLog]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        changes = build_structured_diff(event.before_payload, event.after_payload)
        rows.append(
            {
                **event_to_dict(event),
                "diff_summary": summarize_diff(changes),
                "changed_paths": [change["path"] for change in changes],
            }
        )
    return rows
