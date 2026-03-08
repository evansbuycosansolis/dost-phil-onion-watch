from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


RolloutGateStatus = Literal["draft", "ready", "passed", "failed"]
KpiStatus = Literal["green", "yellow", "red"]
IncidentSeverity = Literal["SEV0", "SEV1", "SEV2", "SEV3"]
IncidentStatus = Literal["open", "mitigating", "resolved", "postmortem"]
ValidationRunStatus = Literal["planned", "running", "passed", "failed"]
ValidationResultStatus = Literal["pass", "fail", "skip"]
RiskStatus = Literal["open", "mitigating", "accepted", "closed"]


class RolloutWaveCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    wave_number: int = Field(ge=0, le=100)
    region_scope: str = Field(min_length=2, max_length=180)
    start_date: date | None = None
    end_date: date | None = None
    owner_user_id: int | None = None
    reviewer_ids: list[int] = Field(default_factory=list)
    gate_notes: str | None = None
    pass_fail_criteria: dict[str, Any] = Field(default_factory=dict)


class RolloutWaveUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    wave_number: int | None = Field(default=None, ge=0, le=100)
    region_scope: str | None = Field(default=None, min_length=2, max_length=180)
    start_date: date | None = None
    end_date: date | None = None
    owner_user_id: int | None = None
    reviewer_ids: list[int] | None = None
    gate_status: RolloutGateStatus | None = None
    gate_notes: str | None = None
    pass_fail_criteria: dict[str, Any] | None = None


class RolloutGateEvaluateRequest(BaseModel):
    gate_notes: str | None = None
    pass_fail_criteria: dict[str, Any] = Field(default_factory=dict)


class RolloutWaveDTO(BaseModel):
    id: int
    name: str
    wave_number: int
    region_scope: str
    start_date: date | None
    end_date: date | None
    owner_user_id: int | None
    reviewer_ids: list[int]
    gate_status: RolloutGateStatus
    gate_notes: str | None
    pass_fail_criteria: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class KpiScorecardCreateRequest(BaseModel):
    period_month: date
    region_scope: str = Field(min_length=2, max_length=180)
    metrics: dict[str, Any] = Field(default_factory=dict)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    source_pointers: dict[str, Any] = Field(default_factory=dict)


class KpiScorecardComputeRequest(BaseModel):
    thresholds: dict[str, Any] | None = None


class KpiScorecardDTO(BaseModel):
    id: int
    period_month: date
    region_scope: str
    metrics: dict[str, Any]
    thresholds: dict[str, Any]
    computed_status: KpiStatus
    source_pointers: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class IncidentCreateRequest(BaseModel):
    incident_key: str | None = Field(default=None, min_length=3, max_length=80)
    severity: IncidentSeverity = "SEV3"
    summary: str = Field(min_length=5)
    impact: str | None = None
    root_cause: str | None = None
    corrective_actions: list[dict[str, Any]] = Field(default_factory=list)
    evidence_pack: dict[str, Any] = Field(default_factory=dict)
    comms_log: list[dict[str, Any]] = Field(default_factory=list)
    assigned_to_user_id: int | None = None
    slo_target_minutes: int | None = Field(default=None, ge=1, le=10080)
    started_at: datetime | None = None


class IncidentUpdateRequest(BaseModel):
    severity: IncidentSeverity | None = None
    status: IncidentStatus | None = None
    summary: str | None = None
    impact: str | None = None
    root_cause: str | None = None
    corrective_actions: list[dict[str, Any]] | None = None
    evidence_pack: dict[str, Any] | None = None
    comms_log: list[dict[str, Any]] | None = None
    assigned_to_user_id: int | None = None
    mitigated_at: datetime | None = None
    resolved_at: datetime | None = None
    slo_target_minutes: int | None = Field(default=None, ge=1, le=10080)


class IncidentResolveRequest(BaseModel):
    root_cause: str | None = None
    corrective_actions: list[dict[str, Any]] = Field(default_factory=list)
    evidence_pack: dict[str, Any] = Field(default_factory=dict)
    resolution_note: str | None = None


class IncidentPostmortemRequest(BaseModel):
    root_cause: str = Field(min_length=3)
    corrective_actions: list[dict[str, Any]] = Field(default_factory=list)
    lessons_learned: str | None = None
    evidence_pack: dict[str, Any] = Field(default_factory=dict)


class IncidentDTO(BaseModel):
    id: int
    incident_key: str
    severity: IncidentSeverity
    status: IncidentStatus
    started_at: datetime
    mitigated_at: datetime | None
    resolved_at: datetime | None
    summary: str
    impact: str | None
    root_cause: str | None
    corrective_actions: list[dict[str, Any]]
    evidence_pack: dict[str, Any]
    comms_log: list[dict[str, Any]]
    created_by_user_id: int | None
    assigned_to_user_id: int | None
    slo_target_minutes: int
    postmortem_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ValidationRunCreateRequest(BaseModel):
    run_key: str | None = Field(default=None, min_length=3, max_length=80)
    scope: str = Field(min_length=2, max_length=180)
    model_version: str | None = Field(default=None, max_length=80)
    threshold_set_version: str | None = Field(default=None, max_length=80)
    evidence_links: list[str] = Field(default_factory=list)


class ValidationRunDTO(BaseModel):
    id: int
    run_key: str
    scope: str
    model_version: str | None
    threshold_set_version: str | None
    status: ValidationRunStatus
    executed_by_user_id: int | None
    reviewed_by_user_id: int | None
    signoff_at: datetime | None
    started_at: datetime
    finished_at: datetime | None
    results_summary: dict[str, Any]
    evidence_links: list[str]
    created_at: datetime
    updated_at: datetime


class ValidationTestcaseDTO(BaseModel):
    id: int
    code: str
    name: str
    description: str
    expected: str
    severity: str
    category: str
    is_active: bool


class ValidationResultItemRequest(BaseModel):
    testcase_id: int | None = None
    testcase_code: str | None = None
    status: ValidationResultStatus
    notes: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class ValidationResultsUpsertRequest(BaseModel):
    results: list[ValidationResultItemRequest] = Field(default_factory=list)
    reviewed_by_user_id: int | None = None
    signoff: bool = False


class ValidationResultDTO(BaseModel):
    id: int
    run_id: int
    testcase_id: int
    testcase_code: str
    status: ValidationResultStatus
    notes: str | None
    evidence: dict[str, Any]
    executed_at: datetime


class RiskItemCreateRequest(BaseModel):
    risk_key: str = Field(min_length=3, max_length=40)
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=5)
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    trigger: str | None = None
    mitigation: str | None = None
    owner_user_id: int | None = None
    status: RiskStatus = "open"
    next_review_date: date | None = None
    target_close_date: date | None = None
    escalation_level: int = Field(default=0, ge=0, le=5)
    board_notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskItemUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=180)
    description: str | None = None
    likelihood: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    trigger: str | None = None
    mitigation: str | None = None
    owner_user_id: int | None = None
    status: RiskStatus | None = None
    next_review_date: date | None = None
    target_close_date: date | None = None
    escalation_level: int | None = Field(default=None, ge=0, le=5)
    board_notes: str | None = None
    metadata: dict[str, Any] | None = None


class RiskEscalateRequest(BaseModel):
    escalation_level: int | None = Field(default=None, ge=1, le=5)
    board_notes: str | None = None


class RiskCloseRequest(BaseModel):
    board_notes: str | None = None
    resolution: str | None = None


class RiskItemDTO(BaseModel):
    id: int
    risk_key: str
    title: str
    description: str
    likelihood: int
    impact: int
    rating: int
    trigger: str | None
    mitigation: str | None
    owner_user_id: int | None
    status: RiskStatus
    next_review_date: date | None
    target_close_date: date | None
    escalation_level: int
    board_notes: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class OpsTaskDTO(BaseModel):
    id: int
    task_type: str
    title: str
    description: str
    status: str
    priority: str
    due_at: datetime | None
    assigned_to_user_id: int | None
    related_entity_type: str | None
    related_entity_id: str | None
    payload: dict[str, Any]
    completed_at: datetime | None
    notification_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
