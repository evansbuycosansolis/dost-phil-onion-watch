from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


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
    metrics: dict[str, Any] = Field(default_factory=dict)


class AnomalyRunResponse(BaseModel):
    created: int
    reporting_month: date


class AnomalyThresholdConfigDTO(BaseModel):
    id: int
    anomaly_type: str
    version: int
    thresholds: dict[str, Any]
    is_active: bool
    change_reason: str | None = None
    last_changed_by: int | None = None
    updated_at: datetime


class AnomalyThresholdVersionDTO(BaseModel):
    id: int
    anomaly_type: str
    version: int
    thresholds: dict[str, Any]
    changed_by: int | None = None
    change_reason: str | None = None
    changed_at: datetime


class AnomalyThresholdUpdateRequest(BaseModel):
    thresholds: dict[str, float | int | bool]
    reason: str = "manual_threshold_update"
