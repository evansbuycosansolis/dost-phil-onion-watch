from datetime import datetime
from pydantic import BaseModel


class AuditEventDTO(BaseModel):
    id: int
    actor_user_id: int | None
    action_type: str
    entity_type: str
    entity_id: str
    timestamp: datetime
    correlation_id: str | None
