from datetime import date, datetime
from pydantic import BaseModel


class AnomalyRunRequest(BaseModel):
    reporting_month: date | None = None


class AnomalyDTO(BaseModel):
    id: int
    detected_at: datetime
    reporting_month: date
    anomaly_type: str
    scope_type: str
    severity: str
    summary: str
    municipality_id: int | None
    warehouse_id: int | None
    market_id: int | None
