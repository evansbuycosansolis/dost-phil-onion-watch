from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class AuditEventDTO(BaseModel):
    id: int
    actor_user_id: int | None
    action_type: str
    entity_type: str
    entity_id: str
    timestamp: datetime
    before_payload: dict[str, Any] | None
    after_payload: dict[str, Any] | None
    correlation_id: str | None
    metadata: dict[str, Any] | None


class AuditDiffEntryDTO(BaseModel):
    path: str
    change_type: Literal["added", "removed", "modified"]
    before_value: Any | None = None
    after_value: Any | None = None


class AuditDiffSummaryDTO(BaseModel):
    total_changes: int
    added: int
    removed: int
    modified: int


class AuditEventDiffDTO(BaseModel):
    event: AuditEventDTO
    summary: AuditDiffSummaryDTO
    changes: list[AuditDiffEntryDTO]
