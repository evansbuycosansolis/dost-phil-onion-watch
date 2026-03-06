from datetime import datetime
from pydantic import BaseModel


class AlertDTO(BaseModel):
    id: int
    title: str
    severity: str
    alert_type: str
    scope_type: str
    status: str
    summary: str
    recommended_action: str
    municipality_id: int | None
    warehouse_id: int | None
    market_id: int | None
    opened_at: datetime


class AlertActionRequest(BaseModel):
    notes: str | None = None
