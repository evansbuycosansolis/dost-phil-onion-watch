from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ConnectorDecisionAction = Literal["approve", "reject"]


class ConnectorIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=100, ge=1, le=2000)
    dry_run: bool = False


class ConnectorDefinitionDTO(BaseModel):
    key: str
    source_name: str
    display_name: str
    description: str
    submission_types: list[str]
    adapter_version: str


class ConnectorIngestionItemResultDTO(BaseModel):
    external_id: str
    status: str
    submission_type: str | None = None
    source_submission_id: int | None = None
    approval_workflow_id: int | None = None
    reason: str | None = None


class ConnectorIngestionResponseDTO(BaseModel):
    connector_key: str
    sync_batch_id: str
    dry_run: bool
    fetched_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    conflict_count: int
    pending_approval_count: int
    workflow_created_count: int
    results: list[ConnectorIngestionItemResultDTO]


class ConnectorSubmissionDTO(BaseModel):
    id: int
    connector_key: str
    source_name: str
    submission_type: str
    status: str
    idempotency_key: str | None = None
    target_entity_type: str | None = None
    target_entity_id: str | None = None
    conflict_reason: str | None = None
    submitted_by: int | None = None
    submitted_at: datetime
    approval_workflow_id: int | None = None
    approval_status: str | None = None
    provenance: dict[str, Any] | None = None


class ConnectorApprovalWorkflowDTO(BaseModel):
    workflow_id: int
    status: str
    requested_by: int | None = None
    reviewed_by: int | None = None
    requested_at: datetime
    reviewed_at: datetime | None = None
    notes: str | None = None
    source_submission_id: int
    connector_key: str
    submission_type: str
    source_submission_status: str
    source_submission_conflict_reason: str | None = None


class ConnectorApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(default=None, max_length=2000)


class ConnectorApprovalDecisionResponse(BaseModel):
    workflow_id: int
    status: str
    source_submission_id: int
    source_submission_status: str
    target_entity_type: str | None = None
    target_entity_id: str | None = None
    reviewed_at: datetime
