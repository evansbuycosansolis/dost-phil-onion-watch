from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


MobileSubmissionType = Literal["harvest_report", "warehouse_stock_report", "farmgate_price_report"]
MobileSubmissionStatus = Literal["accepted", "updated", "duplicate", "conflict", "rejected"]


class MobileSubmissionProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_channel: str = "mobile_app"
    client_id: str
    device_id: str
    app_version: str | None = None
    submitted_at: datetime | None = None


class MobileSubmissionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=120)
    submission_type: MobileSubmissionType
    observed_server_updated_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class MobileSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(default="1.0", min_length=1, max_length=16)
    sync_batch_id: str = Field(min_length=8, max_length=120)
    provenance: MobileSubmissionProvenance
    submissions: list[MobileSubmissionItem] = Field(min_length=1, max_length=200)


class MobileSubmissionResult(BaseModel):
    idempotency_key: str
    submission_type: MobileSubmissionType
    status: MobileSubmissionStatus
    source_submission_id: int | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    server_updated_at: datetime | None = None
    conflict_reason: str | None = None
    message: str | None = None


class MobileSyncResponse(BaseModel):
    sync_batch_id: str
    processed_at: datetime
    summary: dict[str, int]
    results: list[MobileSubmissionResult]


class MobileSubmissionRecord(BaseModel):
    id: int
    sync_batch_id: str | None = None
    submission_type: str
    source_channel: str
    source_name: str
    client_id: str | None = None
    device_id: str | None = None
    app_version: str | None = None
    idempotency_key: str | None = None
    status: str
    target_entity_type: str | None = None
    target_entity_id: str | None = None
    conflict_reason: str | None = None
    submitted_by: int | None = None
    submitted_at: datetime
    created_at: datetime
    updated_at: datetime
    provenance: dict[str, Any] | None = None
