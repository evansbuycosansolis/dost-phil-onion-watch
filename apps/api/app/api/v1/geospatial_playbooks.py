from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import (
    GeospatialIncident,
    GeospatialKpiScorecard,
    GeospatialOpsTask,
    GeospatialRiskItem,
    GeospatialRolloutWave,
    GeospatialValidationResult,
    GeospatialValidationRun,
    GeospatialValidationTestcase,
)
from app.schemas.auth import CurrentUser
from app.schemas.geospatial_playbooks import (
    IncidentCreateRequest,
    IncidentDTO,
    IncidentPostmortemRequest,
    IncidentResolveRequest,
    IncidentUpdateRequest,
    KpiScorecardComputeRequest,
    KpiScorecardCreateRequest,
    KpiScorecardDTO,
    OpsTaskDTO,
    RiskCloseRequest,
    RiskEscalateRequest,
    RiskItemCreateRequest,
    RiskItemDTO,
    RiskItemUpdateRequest,
    RolloutGateEvaluateRequest,
    RolloutWaveCreateRequest,
    RolloutWaveDTO,
    RolloutWaveUpdateRequest,
    ValidationResultDTO,
    ValidationResultsUpsertRequest,
    ValidationRunCreateRequest,
    ValidationRunDTO,
    ValidationTestcaseDTO,
)
from app.services.audit_service import emit_audit_event
from app.services.geospatial_playbooks_service import (
    append_incident_comms_entry,
    compute_kpi_statuses,
    compute_risk_rating,
    create_ops_task,
    default_incident_slo_target_minutes,
    ensure_default_validation_testcases,
    evaluate_wave_gate_status,
    merge_gate_criteria,
    recalculate_validation_run_summary,
    run_incident_slo_checks,
    run_monthly_kpi_scorecard_generation,
    run_risk_review_reminders,
)

router = APIRouter(prefix="/geospatial", tags=["geospatial"], responses=router_default_responses("geospatial"))

READ_ROLES = (
    "super_admin",
    "provincial_admin",
    "municipal_encoder",
    "warehouse_operator",
    "market_analyst",
    "policy_reviewer",
    "executive_viewer",
    "auditor",
)
ADMIN_ROLES = ("super_admin", "provincial_admin")
ROLLOUT_WRITE_ROLES = (*ADMIN_ROLES, "policy_reviewer")
KPI_WRITE_ROLES = (*ADMIN_ROLES, "market_analyst", "policy_reviewer")
INCIDENT_WRITE_ROLES = (*ADMIN_ROLES, "municipal_encoder", "warehouse_operator", "market_analyst", "policy_reviewer")
VALIDATION_WRITE_ROLES = (*ADMIN_ROLES, "market_analyst", "policy_reviewer")
RISK_WRITE_ROLES = (*ADMIN_ROLES, "market_analyst", "policy_reviewer")

DbSession = Annotated[Session, Depends(get_db)]


def _rollout_to_dto(row: GeospatialRolloutWave) -> RolloutWaveDTO:
    return RolloutWaveDTO(
        id=row.id,
        name=row.name,
        wave_number=row.wave_number,
        region_scope=row.region_scope,
        start_date=row.start_date,
        end_date=row.end_date,
        owner_user_id=row.owner_user_id,
        reviewer_ids=list(row.reviewer_ids_json or []),
        gate_status=row.gate_status,
        gate_notes=row.gate_notes,
        pass_fail_criteria=dict(row.pass_fail_criteria_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _kpi_to_dto(row: GeospatialKpiScorecard) -> KpiScorecardDTO:
    return KpiScorecardDTO(
        id=row.id,
        period_month=row.period_month,
        region_scope=row.region_scope,
        metrics=dict(row.metrics_json or {}),
        thresholds=dict(row.thresholds_json or {}),
        computed_status=row.computed_status,
        source_pointers=dict(row.source_pointers_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _incident_to_dto(row: GeospatialIncident) -> IncidentDTO:
    return IncidentDTO(
        id=row.id,
        incident_key=row.incident_key,
        severity=row.severity,
        status=row.status,
        started_at=row.started_at,
        mitigated_at=row.mitigated_at,
        resolved_at=row.resolved_at,
        summary=row.summary,
        impact=row.impact,
        root_cause=row.root_cause,
        corrective_actions=list(row.corrective_actions_json or []),
        evidence_pack=dict(row.evidence_pack_json or {}),
        comms_log=list(row.comms_log_json or []),
        created_by_user_id=row.created_by_user_id,
        assigned_to_user_id=row.assigned_to_user_id,
        slo_target_minutes=row.slo_target_minutes,
        postmortem_completed_at=row.postmortem_completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _validation_run_to_dto(row: GeospatialValidationRun) -> ValidationRunDTO:
    return ValidationRunDTO(
        id=row.id,
        run_key=row.run_key,
        scope=row.scope,
        model_version=row.model_version,
        threshold_set_version=row.threshold_set_version,
        status=row.status,
        executed_by_user_id=row.executed_by_user_id,
        reviewed_by_user_id=row.reviewed_by_user_id,
        signoff_at=row.signoff_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        results_summary=dict(row.results_summary_json or {}),
        evidence_links=list(row.evidence_links_json or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _validation_result_to_dto(
    row: GeospatialValidationResult,
    testcase_lookup: dict[int, GeospatialValidationTestcase],
) -> ValidationResultDTO:
    testcase = testcase_lookup.get(row.testcase_id)
    return ValidationResultDTO(
        id=row.id,
        run_id=row.run_id,
        testcase_id=row.testcase_id,
        testcase_code=testcase.code if testcase else str(row.testcase_id),
        status=row.status,
        notes=row.notes,
        evidence=dict(row.evidence_json or {}),
        executed_at=row.executed_at,
    )


def _testcase_to_dto(row: GeospatialValidationTestcase) -> ValidationTestcaseDTO:
    return ValidationTestcaseDTO(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        expected=row.expected,
        severity=row.severity,
        category=row.category,
        is_active=bool(row.is_active),
    )


def _risk_to_dto(row: GeospatialRiskItem) -> RiskItemDTO:
    return RiskItemDTO(
        id=row.id,
        risk_key=row.risk_key,
        title=row.title,
        description=row.description,
        likelihood=row.likelihood,
        impact=row.impact,
        rating=row.rating,
        trigger=row.trigger,
        mitigation=row.mitigation,
        owner_user_id=row.owner_user_id,
        status=row.status,
        next_review_date=row.next_review_date,
        target_close_date=row.target_close_date,
        escalation_level=row.escalation_level,
        board_notes=row.board_notes,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _task_to_dto(row: GeospatialOpsTask) -> OpsTaskDTO:
    return OpsTaskDTO(
        id=row.id,
        task_type=row.task_type,
        title=row.title,
        description=row.description,
        status=row.status,
        priority=row.priority,
        due_at=row.due_at,
        assigned_to_user_id=row.assigned_to_user_id,
        related_entity_type=row.related_entity_type,
        related_entity_id=row.related_entity_id,
        payload=dict(row.payload_json or {}),
        completed_at=row.completed_at,
        notification_sent_at=row.notification_sent_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _entity_snapshot_rollout(row: GeospatialRolloutWave) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "wave_number": row.wave_number,
        "region_scope": row.region_scope,
        "gate_status": row.gate_status,
        "gate_notes": row.gate_notes,
        "pass_fail_criteria": dict(row.pass_fail_criteria_json or {}),
        "reviewer_ids": list(row.reviewer_ids_json or []),
    }


def _entity_snapshot_kpi(row: GeospatialKpiScorecard) -> dict:
    return {
        "id": row.id,
        "period_month": row.period_month.isoformat(),
        "region_scope": row.region_scope,
        "computed_status": row.computed_status,
        "metrics": dict(row.metrics_json or {}),
        "thresholds": dict(row.thresholds_json or {}),
        "source_pointers": dict(row.source_pointers_json or {}),
    }


def _entity_snapshot_incident(row: GeospatialIncident) -> dict:
    return {
        "id": row.id,
        "incident_key": row.incident_key,
        "severity": row.severity,
        "status": row.status,
        "started_at": row.started_at.isoformat(),
        "mitigated_at": row.mitigated_at.isoformat() if row.mitigated_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "summary": row.summary,
        "impact": row.impact,
        "root_cause": row.root_cause,
        "corrective_actions": list(row.corrective_actions_json or []),
        "assigned_to_user_id": row.assigned_to_user_id,
        "slo_target_minutes": row.slo_target_minutes,
    }


def _entity_snapshot_validation_run(row: GeospatialValidationRun) -> dict:
    return {
        "id": row.id,
        "run_key": row.run_key,
        "scope": row.scope,
        "status": row.status,
        "model_version": row.model_version,
        "threshold_set_version": row.threshold_set_version,
        "results_summary": dict(row.results_summary_json or {}),
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "signoff_at": row.signoff_at.isoformat() if row.signoff_at else None,
    }


def _entity_snapshot_risk(row: GeospatialRiskItem) -> dict:
    return {
        "id": row.id,
        "risk_key": row.risk_key,
        "title": row.title,
        "likelihood": row.likelihood,
        "impact": row.impact,
        "rating": row.rating,
        "status": row.status,
        "owner_user_id": row.owner_user_id,
        "escalation_level": row.escalation_level,
        "next_review_date": row.next_review_date.isoformat() if row.next_review_date else None,
        "target_close_date": row.target_close_date.isoformat() if row.target_close_date else None,
        "board_notes": row.board_notes,
        "metadata": dict(row.metadata_json or {}),
    }


def _generate_incident_key(db: Session) -> str:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    count = int(
        db.scalar(
            select(func.count(GeospatialIncident.id)).where(
                GeospatialIncident.started_at >= day_start,
                GeospatialIncident.started_at < day_end,
            )
        )
        or 0
    )
    candidate = f"GEO-INC-{now.strftime('%Y%m%d')}-{max(1, count + 1):03d}"
    if db.scalar(select(GeospatialIncident.id).where(GeospatialIncident.incident_key == candidate)) is None:
        return candidate
    for idx in range(1, 100):
        retry = f"GEO-INC-{now.strftime('%Y%m%d%H%M%S')}-{idx:02d}"
        if db.scalar(select(GeospatialIncident.id).where(GeospatialIncident.incident_key == retry)) is None:
            return retry
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not generate incident key")


def _generate_validation_run_key(db: Session) -> str:
    base = datetime.now(timezone.utc).strftime("VA-RUN-%Y%m%d-%H%M%S")
    if db.scalar(select(GeospatialValidationRun.id).where(GeospatialValidationRun.run_key == base)) is None:
        return base
    for idx in range(1, 100):
        candidate = f"{base}-{idx:02d}"
        if db.scalar(select(GeospatialValidationRun.id).where(GeospatialValidationRun.run_key == candidate)) is None:
            return candidate
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not generate validation run key")


@router.post("/waves", response_model=RolloutWaveDTO, status_code=status.HTTP_201_CREATED)
def create_rollout_wave(
    payload: RolloutWaveCreateRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*ROLLOUT_WRITE_ROLES))],
) -> RolloutWaveDTO:
    duplicate = db.scalar(
        select(GeospatialRolloutWave).where(
            GeospatialRolloutWave.wave_number == payload.wave_number,
            GeospatialRolloutWave.region_scope == payload.region_scope,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Wave number already exists for region")

    row = GeospatialRolloutWave(
        name=payload.name,
        wave_number=payload.wave_number,
        region_scope=payload.region_scope,
        start_date=payload.start_date,
        end_date=payload.end_date,
        owner_user_id=payload.owner_user_id or current_user.id,
        reviewer_ids_json=sorted(set(payload.reviewer_ids)),
        gate_status="draft",
        gate_notes=payload.gate_notes,
        pass_fail_criteria_json=payload.pass_fail_criteria,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(row)
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.wave.create",
        entity_type="geospatial_rollout_wave",
        entity_id=str(row.id),
        before_payload=None,
        after_payload=_entity_snapshot_rollout(row),
    )
    db.commit()
    db.refresh(row)
    return _rollout_to_dto(row)


@router.get("/waves", response_model=list[RolloutWaveDTO])
def list_rollout_waves(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    gate_status: str | None = Query(default=None),
    region_scope: str | None = Query(default=None),
    owner_user_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
) -> list[RolloutWaveDTO]:
    stmt = select(GeospatialRolloutWave)
    if gate_status:
        stmt = stmt.where(GeospatialRolloutWave.gate_status == gate_status)
    if region_scope:
        stmt = stmt.where(GeospatialRolloutWave.region_scope == region_scope)
    if owner_user_id is not None:
        stmt = stmt.where(GeospatialRolloutWave.owner_user_id == owner_user_id)
    rows = list(db.scalars(stmt.order_by(GeospatialRolloutWave.wave_number.desc(), GeospatialRolloutWave.id.desc()).limit(limit)))
    return [_rollout_to_dto(row) for row in rows]


@router.get("/waves/{wave_id}", response_model=RolloutWaveDTO)
def get_rollout_wave(
    wave_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
) -> RolloutWaveDTO:
    row = db.get(GeospatialRolloutWave, wave_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wave not found")
    return _rollout_to_dto(row)


@router.patch("/waves/{wave_id}", response_model=RolloutWaveDTO)
def update_rollout_wave(
    wave_id: int,
    payload: RolloutWaveUpdateRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*ROLLOUT_WRITE_ROLES))],
) -> RolloutWaveDTO:
    row = db.get(GeospatialRolloutWave, wave_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wave not found")

    before = _entity_snapshot_rollout(row)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "reviewer_ids":
            row.reviewer_ids_json = sorted(set(value or []))
        elif key == "pass_fail_criteria":
            row.pass_fail_criteria_json = value or {}
        else:
            setattr(row, key, value)

    row.updated_by = current_user.id
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.wave.update",
        entity_type="geospatial_rollout_wave",
        entity_id=str(row.id),
        before_payload=before,
        after_payload=_entity_snapshot_rollout(row),
    )
    db.commit()
    db.refresh(row)
    return _rollout_to_dto(row)


@router.post("/waves/{wave_id}/gate-evaluate", response_model=RolloutWaveDTO)
def evaluate_rollout_wave_gate(
    wave_id: int,
    payload: RolloutGateEvaluateRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*ROLLOUT_WRITE_ROLES))],
) -> RolloutWaveDTO:
    row = db.get(GeospatialRolloutWave, wave_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wave not found")

    before = _entity_snapshot_rollout(row)
    merged = merge_gate_criteria(dict(row.pass_fail_criteria_json or {}), payload.pass_fail_criteria)
    row.pass_fail_criteria_json = merged
    row.gate_status = evaluate_wave_gate_status(merged)
    if payload.gate_notes is not None:
        row.gate_notes = payload.gate_notes
    row.updated_by = current_user.id
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.wave.gate_evaluate",
        entity_type="geospatial_rollout_wave",
        entity_id=str(row.id),
        before_payload=before,
        after_payload=_entity_snapshot_rollout(row),
    )
    db.commit()
    db.refresh(row)
    return _rollout_to_dto(row)


@router.post("/kpi/scorecards", response_model=KpiScorecardDTO, status_code=status.HTTP_201_CREATED)
def create_kpi_scorecard(
    payload: KpiScorecardCreateRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*KPI_WRITE_ROLES))],
) -> KpiScorecardDTO:
    duplicate = db.scalar(
        select(GeospatialKpiScorecard).where(
            GeospatialKpiScorecard.period_month == payload.period_month,
            GeospatialKpiScorecard.region_scope == payload.region_scope,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scorecard already exists for period and scope")

    overall_status, metric_statuses, thresholds = compute_kpi_statuses(payload.metrics, payload.thresholds)
    row = GeospatialKpiScorecard(
        period_month=payload.period_month,
        region_scope=payload.region_scope,
        metrics_json=payload.metrics,
        thresholds_json=thresholds,
        computed_status=overall_status,
        source_pointers_json={
            **payload.source_pointers,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "metric_statuses": metric_statuses,
        },
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(row)
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.kpi.create",
        entity_type="geospatial_kpi_scorecard",
        entity_id=str(row.id),
        before_payload=None,
        after_payload=_entity_snapshot_kpi(row),
    )
    db.commit()
    db.refresh(row)
    return _kpi_to_dto(row)


@router.get("/kpi/scorecards", response_model=list[KpiScorecardDTO])
def list_kpi_scorecards(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    period_month: date | None = Query(default=None),
    region_scope: str | None = Query(default=None),
    computed_status: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=300),
) -> list[KpiScorecardDTO]:
    stmt = select(GeospatialKpiScorecard)
    if period_month is not None:
        stmt = stmt.where(GeospatialKpiScorecard.period_month == period_month)
    if region_scope:
        stmt = stmt.where(GeospatialKpiScorecard.region_scope == region_scope)
    if computed_status:
        stmt = stmt.where(GeospatialKpiScorecard.computed_status == computed_status)
    rows = list(db.scalars(stmt.order_by(GeospatialKpiScorecard.period_month.desc(), GeospatialKpiScorecard.id.desc()).limit(limit)))
    return [_kpi_to_dto(row) for row in rows]


@router.get("/kpi/scorecards/{scorecard_id}", response_model=KpiScorecardDTO)
def get_kpi_scorecard(
    scorecard_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
) -> KpiScorecardDTO:
    row = db.get(GeospatialKpiScorecard, scorecard_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scorecard not found")
    return _kpi_to_dto(row)


@router.post("/kpi/scorecards/{scorecard_id}/compute", response_model=KpiScorecardDTO)
def compute_kpi_scorecard(
    scorecard_id: int,
    payload: KpiScorecardComputeRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*KPI_WRITE_ROLES))],
) -> KpiScorecardDTO:
    row = db.get(GeospatialKpiScorecard, scorecard_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scorecard not found")

    before = _entity_snapshot_kpi(row)
    thresholds = payload.thresholds or dict(row.thresholds_json or {})
    overall_status, metric_statuses, merged_thresholds = compute_kpi_statuses(dict(row.metrics_json or {}), thresholds)
    row.thresholds_json = merged_thresholds
    row.computed_status = overall_status
    row.source_pointers_json = {
        **(row.source_pointers_json or {}),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "metric_statuses": metric_statuses,
    }
    row.updated_by = current_user.id
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.kpi.compute",
        entity_type="geospatial_kpi_scorecard",
        entity_id=str(row.id),
        before_payload=before,
        after_payload=_entity_snapshot_kpi(row),
    )
    db.commit()
    db.refresh(row)
    return _kpi_to_dto(row)


@router.post("/incidents", response_model=IncidentDTO, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreateRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*INCIDENT_WRITE_ROLES))],
) -> IncidentDTO:
    key = payload.incident_key or _generate_incident_key(db)
    if db.scalar(select(GeospatialIncident.id).where(GeospatialIncident.incident_key == key)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Incident key already exists")

    started_at = payload.started_at or datetime.now(timezone.utc)
    row = GeospatialIncident(
        incident_key=key,
        severity=payload.severity,
        status="open",
        started_at=started_at,
        summary=payload.summary,
        impact=payload.impact,
        root_cause=payload.root_cause,
        corrective_actions_json=payload.corrective_actions,
        evidence_pack_json=payload.evidence_pack,
        comms_log_json=payload.comms_log,
        created_by_user_id=current_user.id,
        assigned_to_user_id=payload.assigned_to_user_id,
        slo_target_minutes=payload.slo_target_minutes or default_incident_slo_target_minutes(payload.severity),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(row)
    db.flush()

    append_incident_comms_entry(
        row,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "created",
            "actor_user_id": current_user.id,
            "summary": payload.summary,
        },
    )

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.incident.create",
        entity_type="geospatial_incident",
        entity_id=str(row.id),
        before_payload=None,
        after_payload=_entity_snapshot_incident(row),
    )
    db.commit()
    db.refresh(row)
    return _incident_to_dto(row)


@router.get("/incidents", response_model=list[IncidentDTO])
def list_incidents(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    assigned_to_user_id: int | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=400),
) -> list[IncidentDTO]:
    stmt = select(GeospatialIncident)
    if status_filter:
        stmt = stmt.where(GeospatialIncident.status == status_filter)
    if severity:
        stmt = stmt.where(GeospatialIncident.severity == severity)
    if assigned_to_user_id is not None:
        stmt = stmt.where(GeospatialIncident.assigned_to_user_id == assigned_to_user_id)
    rows = list(db.scalars(stmt.order_by(GeospatialIncident.started_at.desc(), GeospatialIncident.id.desc()).limit(limit)))
    return [_incident_to_dto(row) for row in rows]


@router.get("/incidents/{incident_id}", response_model=IncidentDTO)
def get_incident(
    incident_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
) -> IncidentDTO:
    row = db.get(GeospatialIncident, incident_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return _incident_to_dto(row)


@router.patch("/incidents/{incident_id}", response_model=IncidentDTO)
def update_incident(
    incident_id: int,
    payload: IncidentUpdateRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*INCIDENT_WRITE_ROLES))],
) -> IncidentDTO:
    row = db.get(GeospatialIncident, incident_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    before = _entity_snapshot_incident(row)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "corrective_actions":
            row.corrective_actions_json = value or []
        elif key == "evidence_pack":
            row.evidence_pack_json = value or {}
        elif key == "comms_log":
            row.comms_log_json = value or []
        else:
            setattr(row, key, value)

    if "severity" in updates and "slo_target_minutes" not in updates:
        row.slo_target_minutes = default_incident_slo_target_minutes(row.severity)

    if row.status == "mitigating" and row.mitigated_at is None:
        row.mitigated_at = datetime.now(timezone.utc)
    if row.status == "resolved" and row.resolved_at is None:
        row.resolved_at = datetime.now(timezone.utc)

    append_incident_comms_entry(
        row,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "updated",
            "actor_user_id": current_user.id,
            "changes": list(updates.keys()),
        },
    )
    row.updated_by = current_user.id
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.incident.update",
        entity_type="geospatial_incident",
        entity_id=str(row.id),
        before_payload=before,
        after_payload=_entity_snapshot_incident(row),
    )
    db.commit()
    db.refresh(row)
    return _incident_to_dto(row)


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentDTO)
def resolve_incident(
    incident_id: int,
    payload: IncidentResolveRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*INCIDENT_WRITE_ROLES))],
) -> IncidentDTO:
    row = db.get(GeospatialIncident, incident_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    before = _entity_snapshot_incident(row)
    row.status = "resolved"
    row.resolved_at = datetime.now(timezone.utc)
    if payload.root_cause:
        row.root_cause = payload.root_cause
    if payload.corrective_actions:
        row.corrective_actions_json = payload.corrective_actions
    if payload.evidence_pack:
        merged = dict(row.evidence_pack_json or {})
        merged.update(payload.evidence_pack)
        row.evidence_pack_json = merged

    append_incident_comms_entry(
        row,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "resolved",
            "actor_user_id": current_user.id,
            "resolution_note": payload.resolution_note,
        },
    )

    row.updated_by = current_user.id
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.incident.resolve",
        entity_type="geospatial_incident",
        entity_id=str(row.id),
        before_payload=before,
        after_payload=_entity_snapshot_incident(row),
    )
    db.commit()
    db.refresh(row)
    return _incident_to_dto(row)


@router.post("/incidents/{incident_id}/postmortem", response_model=IncidentDTO)
def postmortem_incident(
    incident_id: int,
    payload: IncidentPostmortemRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*INCIDENT_WRITE_ROLES))],
) -> IncidentDTO:
    row = db.get(GeospatialIncident, incident_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    before = _entity_snapshot_incident(row)
    row.status = "postmortem"
    if row.resolved_at is None:
        row.resolved_at = datetime.now(timezone.utc)
    row.root_cause = payload.root_cause
    if payload.corrective_actions:
        row.corrective_actions_json = payload.corrective_actions
    if payload.evidence_pack:
        merged = dict(row.evidence_pack_json or {})
        merged.update(payload.evidence_pack)
        row.evidence_pack_json = merged

    lessons_payload = {"lessons_learned": payload.lessons_learned} if payload.lessons_learned else {}
    append_incident_comms_entry(
        row,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "postmortem_completed",
            "actor_user_id": current_user.id,
            **lessons_payload,
        },
    )

    row.postmortem_completed_at = datetime.now(timezone.utc)
    row.updated_by = current_user.id
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.incident.postmortem",
        entity_type="geospatial_incident",
        entity_id=str(row.id),
        before_payload=before,
        after_payload=_entity_snapshot_incident(row),
    )
    db.commit()
    db.refresh(row)
    return _incident_to_dto(row)


@router.post("/validation/runs", response_model=ValidationRunDTO, status_code=status.HTTP_201_CREATED)
def create_validation_run(
    payload: ValidationRunCreateRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*VALIDATION_WRITE_ROLES))],
) -> ValidationRunDTO:
    ensure_default_validation_testcases(db)
    run_key = payload.run_key or _generate_validation_run_key(db)
    if db.scalar(select(GeospatialValidationRun.id).where(GeospatialValidationRun.run_key == run_key)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Validation run key already exists")

    row = GeospatialValidationRun(
        run_key=run_key,
        scope=payload.scope,
        model_version=payload.model_version,
        threshold_set_version=payload.threshold_set_version,
        status="planned",
        executed_by_user_id=current_user.id,
        reviewed_by_user_id=None,
        signoff_at=None,
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        results_summary_json={"total": 0, "pass": 0, "fail": 0, "skip": 0, "pass_rate": 0.0},
        evidence_links_json=payload.evidence_links,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(row)
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.validation_run.create",
        entity_type="geospatial_validation_run",
        entity_id=str(row.id),
        before_payload=None,
        after_payload=_entity_snapshot_validation_run(row),
    )
    db.commit()
    db.refresh(row)
    return _validation_run_to_dto(row)


@router.get("/validation/runs", response_model=list[ValidationRunDTO])
def list_validation_runs(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    status_filter: str | None = Query(default=None, alias="status"),
    scope: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=300),
) -> list[ValidationRunDTO]:
    ensure_default_validation_testcases(db)
    stmt = select(GeospatialValidationRun)
    if status_filter:
        stmt = stmt.where(GeospatialValidationRun.status == status_filter)
    if scope:
        stmt = stmt.where(GeospatialValidationRun.scope == scope)
    rows = list(db.scalars(stmt.order_by(GeospatialValidationRun.started_at.desc(), GeospatialValidationRun.id.desc()).limit(limit)))
    return [_validation_run_to_dto(row) for row in rows]


@router.get("/validation/runs/{run_id}", response_model=ValidationRunDTO)
def get_validation_run(
    run_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
) -> ValidationRunDTO:
    row = db.get(GeospatialValidationRun, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation run not found")
    return _validation_run_to_dto(row)


@router.get("/validation/runs/{run_id}/results", response_model=list[ValidationResultDTO])
def list_validation_results(
    run_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
) -> list[ValidationResultDTO]:
    run = db.get(GeospatialValidationRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation run not found")
    testcases = {row.id: row for row in db.scalars(select(GeospatialValidationTestcase)).all()}
    rows = list(
        db.scalars(
            select(GeospatialValidationResult)
            .where(GeospatialValidationResult.run_id == run.id)
            .order_by(GeospatialValidationResult.id)
        )
    )
    return [_validation_result_to_dto(row, testcases) for row in rows]


@router.post("/validation/runs/{run_id}/results", response_model=list[ValidationResultDTO])
def upsert_validation_results(
    run_id: int,
    payload: ValidationResultsUpsertRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*VALIDATION_WRITE_ROLES))],
) -> list[ValidationResultDTO]:
    ensure_default_validation_testcases(db)
    run = db.get(GeospatialValidationRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation run not found")

    before = _entity_snapshot_validation_run(run)
    testcases = list(db.scalars(select(GeospatialValidationTestcase).where(GeospatialValidationTestcase.is_active == True)))  # noqa: E712
    testcase_by_id = {row.id: row for row in testcases}
    testcase_by_code = {row.code: row for row in testcases}

    upserted: list[GeospatialValidationResult] = []
    for item in payload.results:
        testcase = None
        if item.testcase_id is not None:
            testcase = testcase_by_id.get(item.testcase_id)
        if testcase is None and item.testcase_code:
            testcase = testcase_by_code.get(item.testcase_code)
        if testcase is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown validation testcase")

        existing = db.scalar(
            select(GeospatialValidationResult).where(
                GeospatialValidationResult.run_id == run.id,
                GeospatialValidationResult.testcase_id == testcase.id,
            )
        )
        if existing is None:
            existing = GeospatialValidationResult(
                run_id=run.id,
                testcase_id=testcase.id,
                status=item.status,
                notes=item.notes,
                evidence_json=item.evidence,
                executed_at=datetime.now(timezone.utc),
                created_by=current_user.id,
                updated_by=current_user.id,
            )
            db.add(existing)
        else:
            existing.status = item.status
            existing.notes = item.notes
            existing.evidence_json = item.evidence
            existing.executed_at = datetime.now(timezone.utc)
            existing.updated_by = current_user.id
        db.flush()
        upserted.append(existing)

    if payload.reviewed_by_user_id is not None:
        run.reviewed_by_user_id = payload.reviewed_by_user_id
    else:
        run.reviewed_by_user_id = current_user.id

    summary = recalculate_validation_run_summary(db, run)
    if payload.signoff:
        run.signoff_at = datetime.now(timezone.utc)
    run.updated_by = current_user.id
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.validation_run.results_upsert",
        entity_type="geospatial_validation_run",
        entity_id=str(run.id),
        before_payload=before,
        after_payload={**_entity_snapshot_validation_run(run), "summary": summary, "results_upserted": len(upserted)},
    )
    db.commit()

    refreshed_testcases = {row.id: row for row in db.scalars(select(GeospatialValidationTestcase)).all()}
    result_rows = list(
        db.scalars(
            select(GeospatialValidationResult)
            .where(GeospatialValidationResult.run_id == run.id)
            .order_by(GeospatialValidationResult.id)
        )
    )
    return [_validation_result_to_dto(row, refreshed_testcases) for row in result_rows]


@router.get("/validation/testcases", response_model=list[ValidationTestcaseDTO])
def list_validation_testcases(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
) -> list[ValidationTestcaseDTO]:
    rows = ensure_default_validation_testcases(db)
    db.commit()
    return [_testcase_to_dto(row) for row in rows]


@router.post("/risks", response_model=RiskItemDTO, status_code=status.HTTP_201_CREATED)
def create_risk_item(
    payload: RiskItemCreateRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*RISK_WRITE_ROLES))],
) -> RiskItemDTO:
    if db.scalar(select(GeospatialRiskItem.id).where(GeospatialRiskItem.risk_key == payload.risk_key)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Risk key already exists")

    row = GeospatialRiskItem(
        risk_key=payload.risk_key,
        title=payload.title,
        description=payload.description,
        likelihood=payload.likelihood,
        impact=payload.impact,
        rating=compute_risk_rating(payload.likelihood, payload.impact),
        trigger=payload.trigger,
        mitigation=payload.mitigation,
        owner_user_id=payload.owner_user_id,
        status=payload.status,
        next_review_date=payload.next_review_date,
        target_close_date=payload.target_close_date,
        escalation_level=payload.escalation_level,
        board_notes=payload.board_notes,
        metadata_json=payload.metadata,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(row)
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.risk.create",
        entity_type="geospatial_risk_item",
        entity_id=str(row.id),
        before_payload=None,
        after_payload=_entity_snapshot_risk(row),
    )
    db.commit()
    db.refresh(row)
    return _risk_to_dto(row)


@router.get("/risks", response_model=list[RiskItemDTO])
def list_risk_items(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    status_filter: str | None = Query(default=None, alias="status"),
    owner_user_id: int | None = Query(default=None),
    escalation_level: int | None = Query(default=None, ge=0, le=5),
    limit: int = Query(default=120, ge=1, le=300),
) -> list[RiskItemDTO]:
    stmt = select(GeospatialRiskItem)
    if status_filter:
        stmt = stmt.where(GeospatialRiskItem.status == status_filter)
    if owner_user_id is not None:
        stmt = stmt.where(GeospatialRiskItem.owner_user_id == owner_user_id)
    if escalation_level is not None:
        stmt = stmt.where(GeospatialRiskItem.escalation_level >= escalation_level)
    rows = list(db.scalars(stmt.order_by(GeospatialRiskItem.rating.desc(), GeospatialRiskItem.id.desc()).limit(limit)))
    return [_risk_to_dto(row) for row in rows]


@router.get("/risks/{risk_id}", response_model=RiskItemDTO)
def get_risk_item(
    risk_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
) -> RiskItemDTO:
    row = db.get(GeospatialRiskItem, risk_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk item not found")
    return _risk_to_dto(row)


@router.patch("/risks/{risk_id}", response_model=RiskItemDTO)
def update_risk_item(
    risk_id: int,
    payload: RiskItemUpdateRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*RISK_WRITE_ROLES))],
) -> RiskItemDTO:
    row = db.get(GeospatialRiskItem, risk_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk item not found")

    before = _entity_snapshot_risk(row)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "metadata":
            row.metadata_json = value or {}
        else:
            setattr(row, key, value)

    if "likelihood" in updates or "impact" in updates:
        row.rating = compute_risk_rating(row.likelihood, row.impact)

    row.updated_by = current_user.id
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.risk.update",
        entity_type="geospatial_risk_item",
        entity_id=str(row.id),
        before_payload=before,
        after_payload=_entity_snapshot_risk(row),
    )
    db.commit()
    db.refresh(row)
    return _risk_to_dto(row)


@router.post("/risks/{risk_id}/escalate", response_model=RiskItemDTO)
def escalate_risk_item(
    risk_id: int,
    payload: RiskEscalateRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*RISK_WRITE_ROLES))],
) -> RiskItemDTO:
    row = db.get(GeospatialRiskItem, risk_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk item not found")

    before = _entity_snapshot_risk(row)
    if payload.escalation_level is not None:
        row.escalation_level = max(row.escalation_level, payload.escalation_level)
    else:
        row.escalation_level = min(5, row.escalation_level + 1)
    row.status = "mitigating"
    if payload.board_notes:
        row.board_notes = payload.board_notes

    task = create_ops_task(
        db,
        task_type="risk_escalation",
        title=f"Escalated risk {row.risk_key}",
        description=f"Risk {row.risk_key} escalated to level {row.escalation_level}.",
        due_at=datetime.now(timezone.utc) + timedelta(days=1),
        assigned_to_user_id=row.owner_user_id,
        related_entity_type="geospatial_risk_item",
        related_entity_id=str(row.id),
        payload={"risk_key": row.risk_key, "escalation_level": row.escalation_level},
        priority="high" if row.escalation_level >= 3 else "medium",
        created_by=current_user.id,
    )

    row.updated_by = current_user.id
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.risk.escalate",
        entity_type="geospatial_risk_item",
        entity_id=str(row.id),
        before_payload=before,
        after_payload={**_entity_snapshot_risk(row), "ops_task_id": task.id},
    )
    db.commit()
    db.refresh(row)
    return _risk_to_dto(row)


@router.post("/risks/{risk_id}/close", response_model=RiskItemDTO)
def close_risk_item(
    risk_id: int,
    payload: RiskCloseRequest,
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*RISK_WRITE_ROLES))],
) -> RiskItemDTO:
    row = db.get(GeospatialRiskItem, risk_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk item not found")

    before = _entity_snapshot_risk(row)
    row.status = "closed"
    if payload.board_notes:
        row.board_notes = payload.board_notes

    metadata = dict(row.metadata_json or {})
    metadata["resolution"] = payload.resolution
    metadata["closed_at"] = datetime.now(timezone.utc).isoformat()
    metadata["closed_by_user_id"] = current_user.id
    row.metadata_json = metadata
    row.updated_by = current_user.id
    db.flush()

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.risk.close",
        entity_type="geospatial_risk_item",
        entity_id=str(row.id),
        before_payload=before,
        after_payload=_entity_snapshot_risk(row),
    )
    db.commit()
    db.refresh(row)
    return _risk_to_dto(row)


@router.get("/ops/tasks", response_model=list[OpsTaskDTO])
def list_geospatial_ops_tasks(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    status_filter: str | None = Query(default=None, alias="status"),
    task_type: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
) -> list[OpsTaskDTO]:
    stmt = select(GeospatialOpsTask)
    if status_filter:
        stmt = stmt.where(GeospatialOpsTask.status == status_filter)
    if task_type:
        stmt = stmt.where(GeospatialOpsTask.task_type == task_type)
    rows = list(db.scalars(stmt.order_by(GeospatialOpsTask.created_at.desc(), GeospatialOpsTask.id.desc()).limit(limit)))
    return [_task_to_dto(row) for row in rows]


@router.post("/automation/monthly-kpi", response_model=KpiScorecardDTO)
def run_monthly_kpi_automation(
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
    reporting_month: date | None = Query(default=None),
) -> KpiScorecardDTO:
    row = run_monthly_kpi_scorecard_generation(db, reporting_month=reporting_month, actor_user_id=current_user.id)
    db.flush()
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.automation.monthly_kpi",
        entity_type="geospatial_kpi_scorecard",
        entity_id=str(row.id),
        before_payload=None,
        after_payload=_entity_snapshot_kpi(row),
    )
    db.commit()
    db.refresh(row)
    return _kpi_to_dto(row)


@router.post("/automation/risk-review-reminders", response_model=list[OpsTaskDTO])
def run_risk_review_automation(
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
) -> list[OpsTaskDTO]:
    tasks = run_risk_review_reminders(db, actor_user_id=current_user.id)
    db.flush()
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.automation.risk_review",
        entity_type="geospatial_ops_task",
        entity_id=",".join(str(row.id) for row in tasks) if tasks else "none",
        before_payload=None,
        after_payload={"tasks_created": [row.id for row in tasks]},
    )
    db.commit()
    return [_task_to_dto(row) for row in tasks]


@router.post("/automation/incident-slo-checks", response_model=list[OpsTaskDTO])
def run_incident_slo_automation(
    db: DbSession,
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
) -> list[OpsTaskDTO]:
    tasks = run_incident_slo_checks(db, actor_user_id=current_user.id)
    db.flush()
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.playbooks.automation.incident_slo",
        entity_type="geospatial_ops_task",
        entity_id=",".join(str(row.id) for row in tasks) if tasks else "none",
        before_payload=None,
        after_payload={"tasks_created": [row.id for row in tasks]},
    )
    db.commit()
    return [_task_to_dto(row) for row in tasks]
