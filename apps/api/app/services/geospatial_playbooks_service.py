from __future__ import annotations

import csv
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Alert,
    AlertAcknowledgement,
    ApprovalWorkflow,
    AnomalyEvent,
    AuditLog,
    GeospatialIncident,
    GeospatialKpiScorecard,
    GeospatialOpsTask,
    GeospatialRiskItem,
    GeospatialValidationResult,
    GeospatialValidationRun,
    GeospatialValidationTestcase,
    InterventionAction,
    JobRun,
    Municipality,
    ReportDeliveryLog,
    SatellitePipelineRun,
)
from app.services.notification_service import notify_observability_alert


DEFAULT_VALIDATION_TESTCASES: list[dict[str, str]] = [
    {
        "code": "VA-T01",
        "name": "Geospatial route smoke checks",
        "description": "Validate critical geospatial routes respond successfully with authorized access.",
        "expected": "Critical routes return successful response payloads.",
        "severity": "high",
        "category": "api",
    },
    {
        "code": "VA-T02",
        "name": "Scheduled worker execution and retries",
        "description": "Validate worker jobs execute and retry policy is applied for transient failures.",
        "expected": "No critical worker class remains stuck or fails without retries.",
        "severity": "high",
        "category": "worker",
    },
    {
        "code": "VA-T03",
        "name": "Source freshness and completeness",
        "description": "Validate input source freshness/completeness against configured thresholds.",
        "expected": "Source compliance remains above configured minimums.",
        "severity": "high",
        "category": "data_quality",
    },
    {
        "code": "VA-T04",
        "name": "Run and artifact lineage traceability",
        "description": "Validate sampled run lineage and artifact provenance chain is present.",
        "expected": "Input to output lineage is available for sampled runs.",
        "severity": "high",
        "category": "lineage",
    },
    {
        "code": "VA-T05",
        "name": "Review and approval SLA flow",
        "description": "Validate analyst to supervisor workflow SLA and mandatory fields.",
        "expected": "Review and approval workflow meets SLA with required evidence.",
        "severity": "medium",
        "category": "workflow",
    },
    {
        "code": "VA-T06",
        "name": "Field verification quality",
        "description": "Validate field verification closure quality and evidence completeness.",
        "expected": "Field verification closure includes complete evidence package.",
        "severity": "medium",
        "category": "field",
    },
    {
        "code": "VA-T07",
        "name": "RBAC and audit control checks",
        "description": "Validate unauthorized access is blocked and audit events are complete.",
        "expected": "No unauthorized access and full audit coverage for controlled actions.",
        "severity": "critical",
        "category": "governance",
    },
    {
        "code": "VA-T08",
        "name": "Export safety and signed package checks",
        "description": "Validate export redaction, signing, and policy-safe output controls.",
        "expected": "All sampled exports satisfy policy and signing requirements.",
        "severity": "critical",
        "category": "export",
    },
    {
        "code": "VA-T09",
        "name": "KPI reproducibility",
        "description": "Validate KPI values are reproducible from authoritative API/table sources.",
        "expected": "Published KPI values match recomputed snapshots.",
        "severity": "high",
        "category": "kpi",
    },
    {
        "code": "VA-T10",
        "name": "Source and model drift checks",
        "description": "Validate source/model drift remains within approved bounds.",
        "expected": "No uncontrolled drift beyond approved limits.",
        "severity": "high",
        "category": "drift",
    },
]


DEFAULT_KPI_THRESHOLDS: dict[str, dict[str, Any]] = {
    "GEO-KPI-001": {"direction": "higher", "green": 0.75, "amber": 0.65},
    "GEO-KPI-002": {"direction": "lower", "green": 24.0, "amber": 36.0},
    "GEO-KPI-003": {"direction": "lower", "green": 72.0, "amber": 96.0},
    "GEO-KPI-004": {"direction": "higher", "green": 0.85, "amber": 0.70},
    "GEO-KPI-005": {"direction": "higher", "green": 0.60, "amber": 0.40},
    "GEO-KPI-006": {"direction": "higher", "green": 0.80, "amber": 0.60},
    "GEO-KPI-007": {"direction": "higher", "green": 0.90, "amber": 0.75},
    "GEO-KPI-008": {"direction": "higher", "green": 0.95, "amber": 0.90},
    "GEO-KPI-009": {"direction": "higher", "green": 0.98, "amber": 0.95},
    "GEO-KPI-010": {"direction": "higher", "green": 1.00, "amber": 0.98},
}

REVIEW_WORKFLOW_ENTITY_TYPES = (
    "geospatial_run",
    "geospatial_run_release_gate",
    "source_submission",
)

REVIEW_WORKFLOW_AUDIT_ACTIONS = (
    "geospatial.run.approval_gate.update",
    "connector.approval.approve",
    "connector.approval.reject",
)

CONTROLLED_REPORT_DELIVERY_STATUSES = ("sent", "retrying", "failed")
COMPLETED_INTERVENTION_STATUSES = {"completed", "done", "successful", "resolved", "closed"}
COMPLETED_ALERT_ACTIONS = {"acknowledged", "resolved"}
KPI_METRIC_IDS = tuple(DEFAULT_KPI_THRESHOLDS.keys())

KPI_ACTION_GUIDANCE = {
    "green": "Maintain controls and continue standard monitoring cadence.",
    "yellow": "Investigate yellow metrics within 48 hours and capture remediation owners.",
    "red": "Trigger immediate operations/governance review and open an incident if service risk is confirmed.",
}


def _month_window(period_month: date) -> tuple[datetime, datetime]:
    period_start = datetime.combine(period_month, datetime.min.time())
    next_month = (period_month.replace(day=28) + timedelta(days=4)).replace(day=1)
    period_end = datetime.combine(next_month, datetime.min.time())
    return period_start, period_end


def _safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    if denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def _average_hours(pairs: Iterable[tuple[datetime | None, datetime | None]]) -> float | None:
    values: list[float] = []
    for started_at, finished_at in pairs:
        if started_at is None or finished_at is None:
            continue
        delta = (finished_at - started_at).total_seconds() / 3600.0
        if delta < 0:
            continue
        values.append(delta)
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def _slugify_scope(scope: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", (scope or "").strip().lower())
    return normalized.strip("-") or "global"


def _kpi_records_dir(period_month: date, region_scope: str) -> Path:
    month_key = period_month.strftime("%Y-%m")
    folder = Path(settings.reports_path) / "records" / "geospatial-kpi" / month_key / _slugify_scope(region_scope)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _extract_traceability_source_counts(meta: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, value in (meta or {}).items():
        if key.startswith("supporting_"):
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            counts[key] = value
    return counts


def _build_traceability_links(meta: dict[str, Any]) -> dict[str, list[str]]:
    incident_ids = [int(row) for row in (meta.get("supporting_incident_ids") or []) if isinstance(row, int)]
    workflow_ids = [int(row) for row in (meta.get("supporting_workflow_ids") or []) if isinstance(row, int)]
    delivery_ids = [int(row) for row in (meta.get("supporting_delivery_log_ids") or []) if isinstance(row, int)]
    audit_ids = [int(row) for row in (meta.get("supporting_audit_log_ids") or []) if isinstance(row, int)]
    report_ids = [int(row) for row in (meta.get("supporting_report_ids") or []) if isinstance(row, int)]

    return {
        "incidents": [f"/api/v1/geospatial/incidents/{incident_id}" for incident_id in incident_ids],
        "workflows": [f"/api/v1/audit/events?entity_type=approval_workflow&entity_id={workflow_id}" for workflow_id in workflow_ids],
        "deliveries": [f"/api/v1/audit/events?entity_type=report_delivery_log&entity_id={delivery_id}" for delivery_id in delivery_ids],
        "reports": [f"/api/v1/reports/{report_id}" for report_id in report_ids],
        "audit": [f"/api/v1/audit/events/{audit_id}" for audit_id in audit_ids],
    }


def write_monthly_kpi_artifacts(
    *,
    period_month: date,
    region_scope: str,
    metrics: dict[str, Any],
    statuses: dict[str, str],
    thresholds: dict[str, Any],
    overall_status: str,
) -> dict[str, str]:
    records_dir = _kpi_records_dir(period_month, region_scope)
    csv_path = records_dir / "scorecard.csv"
    variance_notes_path = records_dir / "variance-notes.md"
    action_summary_path = records_dir / "action-summary.md"

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["kpi_id", "value", "status", "direction", "green_threshold", "amber_threshold"])
        for kpi_id in KPI_METRIC_IDS:
            config = thresholds.get(kpi_id) if isinstance(thresholds.get(kpi_id), dict) else {}
            writer.writerow(
                [
                    kpi_id,
                    metrics.get(kpi_id),
                    statuses.get(kpi_id, "unknown"),
                    config.get("direction", "higher"),
                    config.get("green"),
                    config.get("amber"),
                ]
            )

    variance_lines = [
        f"# KPI Variance Notes ({period_month.isoformat()} - {region_scope})",
        "",
    ]
    flagged = False
    for kpi_id in KPI_METRIC_IDS:
        status = statuses.get(kpi_id, "unknown")
        value = metrics.get(kpi_id)
        if status == "green":
            continue
        flagged = True
        if value is None:
            variance_lines.append(f"- {kpi_id}: `{status}` because denominator data is unavailable for this period.")
        else:
            variance_lines.append(f"- {kpi_id}: `{status}` with measured value `{value}`.")
    if not flagged:
        variance_lines.append("- No variance flags. All KPI metrics are green.")
    variance_notes_path.write_text("\n".join(variance_lines).strip() + "\n", encoding="utf-8")

    action_summary_lines = [
        f"# KPI Action Summary ({period_month.isoformat()} - {region_scope})",
        "",
        f"- Overall status: `{overall_status}`",
        f"- Recommendation: {KPI_ACTION_GUIDANCE.get(overall_status, KPI_ACTION_GUIDANCE['yellow'])}",
        "- Next review owner: geospatial operations governance board.",
    ]
    action_summary_path.write_text("\n".join(action_summary_lines).strip() + "\n", encoding="utf-8")

    return {
        "records_dir": str(records_dir),
        "scorecard_csv": str(csv_path),
        "variance_notes": str(variance_notes_path),
        "action_summary": str(action_summary_path),
    }


def ensure_default_validation_testcases(db: Session) -> list[GeospatialValidationTestcase]:
    existing = {
        row.code: row
        for row in db.scalars(select(GeospatialValidationTestcase)).all()
    }
    for payload in DEFAULT_VALIDATION_TESTCASES:
        row = existing.get(payload["code"])
        if row is not None:
            row.name = payload["name"]
            row.description = payload["description"]
            row.expected = payload["expected"]
            row.severity = payload["severity"]
            row.category = payload["category"]
            row.is_active = True
            continue
        db.add(
            GeospatialValidationTestcase(
                code=payload["code"],
                name=payload["name"],
                description=payload["description"],
                expected=payload["expected"],
                severity=payload["severity"],
                category=payload["category"],
                is_active=True,
            )
        )
    db.flush()
    return list(db.scalars(select(GeospatialValidationTestcase).order_by(GeospatialValidationTestcase.code)))


def evaluate_wave_gate_status(criteria: dict[str, Any]) -> str:
    if not criteria:
        return "ready"
    bool_values: list[bool] = []
    for _, value in criteria.items():
        if isinstance(value, bool):
            bool_values.append(value)
            continue
        if isinstance(value, dict):
            nested_bool = [v for v in value.values() if isinstance(v, bool)]
            bool_values.extend(bool(v) for v in nested_bool)
    if not bool_values:
        return "ready"
    return "passed" if all(bool_values) else "failed"


def merge_gate_criteria(current: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current or {})
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**(merged.get(key) or {}), **value}
        else:
            merged[key] = value
    return merged


def _metric_status(metric_value: float, config: dict[str, Any]) -> str:
    direction = str(config.get("direction", "higher"))
    green = float(config.get("green", 0))
    amber = float(config.get("amber", green))
    if direction == "lower":
        if metric_value <= green:
            return "green"
        if metric_value <= amber:
            return "yellow"
        return "red"

    if metric_value >= green:
        return "green"
    if metric_value >= amber:
        return "yellow"
    return "red"


def compute_kpi_statuses(
    metrics: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    merged_thresholds = {**DEFAULT_KPI_THRESHOLDS, **(thresholds or {})}
    statuses: dict[str, str] = {}
    overall = "green"
    for kpi_id, config in merged_thresholds.items():
        value = metrics.get(kpi_id)
        if value is None:
            statuses[kpi_id] = "yellow"
            if overall == "green":
                overall = "yellow"
            continue
        try:
            metric_value = float(value)
        except (TypeError, ValueError):
            statuses[kpi_id] = "red"
            overall = "red"
            continue
        status = _metric_status(metric_value, config)
        statuses[kpi_id] = status
        if status == "red":
            overall = "red"
        elif status == "yellow" and overall == "green":
            overall = "yellow"
    return overall, statuses, merged_thresholds


def default_incident_slo_target_minutes(severity: str) -> int:
    mapping = {
        "SEV0": 60,
        "SEV1": 240,
        "SEV2": 1440,
        "SEV3": 7200,
    }
    return mapping.get(severity, 240)


def incident_due_at(incident: GeospatialIncident) -> datetime:
    return incident.started_at + timedelta(minutes=max(1, incident.slo_target_minutes))


def append_incident_comms_entry(incident: GeospatialIncident, entry: dict[str, Any]) -> None:
    rows = list(incident.comms_log_json or [])
    rows.append(entry)
    incident.comms_log_json = rows


def recalculate_validation_run_summary(db: Session, run: GeospatialValidationRun) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(GeospatialValidationResult).where(GeospatialValidationResult.run_id == run.id)
        )
    )
    pass_count = sum(1 for row in rows if row.status == "pass")
    fail_count = sum(1 for row in rows if row.status == "fail")
    skip_count = sum(1 for row in rows if row.status == "skip")
    total = len(rows)
    summary = {
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "skip": skip_count,
        "pass_rate": (pass_count / total) if total > 0 else 0.0,
    }
    run.results_summary_json = summary
    if total == 0:
        run.status = "planned"
    elif fail_count > 0:
        run.status = "failed"
    elif pass_count > 0:
        run.status = "passed"
    else:
        run.status = "running"
    run.finished_at = datetime.utcnow()
    db.flush()
    return summary


def compute_risk_rating(likelihood: int, impact: int) -> int:
    return max(1, int(likelihood)) * max(1, int(impact))


def create_ops_task(
    db: Session,
    *,
    task_type: str,
    title: str,
    description: str,
    due_at: datetime | None = None,
    assigned_to_user_id: int | None = None,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
    priority: str = "medium",
    created_by: int | None = None,
) -> GeospatialOpsTask:
    task = GeospatialOpsTask(
        task_type=task_type,
        title=title,
        description=description,
        status="open",
        priority=priority,
        due_at=due_at,
        assigned_to_user_id=assigned_to_user_id,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        payload_json=payload or {},
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(task)
    db.flush()
    return task


def build_monthly_kpi_metrics(db: Session, period_month: date) -> dict[str, Any]:
    period_start, period_end = _month_window(period_month)

    reviewed = db.scalar(
        select(func.count(AnomalyEvent.id)).where(
            AnomalyEvent.reporting_month == period_month,
            AnomalyEvent.status.in_(["acknowledged", "resolved"]),
        )
    ) or 0
    resolved = db.scalar(
        select(func.count(AnomalyEvent.id)).where(
            AnomalyEvent.reporting_month == period_month,
            AnomalyEvent.status == "resolved",
        )
    ) or 0
    alerts_open = db.scalar(
        select(func.count(Alert.id)).where(
            Alert.status == "open",
            Alert.opened_at >= period_start,
            Alert.opened_at < period_end,
        )
    ) or 0
    approval_workflows_reviewed = list(
        db.execute(
            select(ApprovalWorkflow.requested_at, ApprovalWorkflow.reviewed_at).where(
                ApprovalWorkflow.entity_type.in_(REVIEW_WORKFLOW_ENTITY_TYPES),
                ApprovalWorkflow.requested_at.is_not(None),
                ApprovalWorkflow.reviewed_at.is_not(None),
                ApprovalWorkflow.reviewed_at >= period_start,
                ApprovalWorkflow.reviewed_at < period_end,
            )
        ).all()
    )
    approval_workflow_ids = [
        int(row)
        for row in db.scalars(
            select(ApprovalWorkflow.id).where(
                ApprovalWorkflow.entity_type.in_(REVIEW_WORKFLOW_ENTITY_TYPES),
                ApprovalWorkflow.reviewed_at.is_not(None),
                ApprovalWorkflow.reviewed_at >= period_start,
                ApprovalWorkflow.reviewed_at < period_end,
            )
        ).all()
    ]
    field_visit_logs = list(
        db.scalars(
            select(AuditLog).where(
                AuditLog.action_type == "geospatial.aoi.field_visit.update",
                AuditLog.timestamp >= period_start,
                AuditLog.timestamp < period_end,
            )
        )
    )
    field_visit_audit_ids = [int(row.id) for row in field_visit_logs]
    intervention_actions = list(
        db.scalars(
            select(InterventionAction).where(
                InterventionAction.action_date >= period_month,
                InterventionAction.action_date < period_end.date(),
            )
        )
    )
    report_delivery_rows = list(
        db.execute(
            select(ReportDeliveryLog.id, ReportDeliveryLog.report_id).where(
                ReportDeliveryLog.dispatched_at >= period_start,
                ReportDeliveryLog.dispatched_at < period_end,
            )
        ).all()
    )
    report_delivery_log_ids = [int(row.id) for row in report_delivery_rows]
    supporting_report_ids = sorted({int(row.report_id) for row in report_delivery_rows if row.report_id is not None})
    targeted_recipients = db.scalar(
        select(func.count(func.distinct(ReportDeliveryLog.recipient_user_id))).where(
            ReportDeliveryLog.dispatched_at >= period_start,
            ReportDeliveryLog.dispatched_at < period_end,
            ReportDeliveryLog.recipient_user_id.is_not(None),
        )
    ) or 0
    active_report_readers = db.scalar(
        select(func.count(func.distinct(AuditLog.actor_user_id))).where(
            AuditLog.action_type == "report.export.download",
            AuditLog.timestamp >= period_start,
            AuditLog.timestamp < period_end,
            AuditLog.actor_user_id.is_not(None),
        )
    ) or 0
    alerts_opened = db.scalar(
        select(func.count(Alert.id)).where(
            Alert.opened_at >= period_start,
            Alert.opened_at < period_end,
        )
    ) or 0
    supporting_incident_ids = [
        int(row)
        for row in db.scalars(
            select(GeospatialIncident.id).where(
                GeospatialIncident.started_at >= period_start,
                GeospatialIncident.started_at < period_end,
            )
        ).all()
    ]
    completed_alert_actions = db.scalar(
        select(func.count(func.distinct(AlertAcknowledgement.alert_id))).where(
            AlertAcknowledgement.action_at >= period_start,
            AlertAcknowledgement.action_at < period_end,
            AlertAcknowledgement.action.in_(tuple(COMPLETED_ALERT_ACTIONS)),
        )
    ) or 0
    workflows_requested = db.scalar(
        select(func.count(ApprovalWorkflow.id)).where(
            ApprovalWorkflow.entity_type.in_(REVIEW_WORKFLOW_ENTITY_TYPES),
            ApprovalWorkflow.requested_at >= period_start,
            ApprovalWorkflow.requested_at < period_end,
        )
    ) or 0
    workflows_completed = db.scalar(
        select(func.count(ApprovalWorkflow.id)).where(
            ApprovalWorkflow.entity_type.in_(REVIEW_WORKFLOW_ENTITY_TYPES),
            ApprovalWorkflow.reviewed_at.is_not(None),
            ApprovalWorkflow.reviewed_at >= period_start,
            ApprovalWorkflow.reviewed_at < period_end,
        )
    ) or 0
    municipalities_total = db.scalar(select(func.count(Municipality.id))) or 1
    municipalities_active = db.scalar(
        select(func.count(func.distinct(AnomalyEvent.municipality_id))).where(
            AnomalyEvent.reporting_month == period_month,
            AnomalyEvent.municipality_id.is_not(None),
        )
    ) or 0
    pipeline_runs = list(
        db.scalars(
            select(SatellitePipelineRun).where(
                func.coalesce(SatellitePipelineRun.scheduled_for, SatellitePipelineRun.started_at) >= period_start,
                func.coalesce(SatellitePipelineRun.scheduled_for, SatellitePipelineRun.started_at) < period_end,
            )
        )
    )
    jobs_total = db.scalar(
        select(func.count(JobRun.id)).where(
            JobRun.started_at >= period_start,
            JobRun.started_at < period_end,
        )
    ) or 0
    jobs_success = db.scalar(
        select(func.count(JobRun.id)).where(
            JobRun.status == "completed",
            JobRun.started_at >= period_start,
            JobRun.started_at < period_end,
        )
    ) or 0

    field_turnaround_pairs: list[tuple[datetime | None, datetime | None]] = []
    for row in field_visit_logs:
        payload = row.after_payload if isinstance(row.after_payload, dict) else {}
        field_visit = payload.get("field_visit") if isinstance(payload.get("field_visit"), dict) else {}
        action = str(payload.get("action") or "").lower()
        status = str(field_visit.get("status") or "").lower()
        requested_at = _parse_iso_datetime(field_visit.get("requested_at"))
        captured_at = _parse_iso_datetime(field_visit.get("captured_at"))
        if requested_at is None or captured_at is None:
            continue
        if action == "complete" or status == "completed":
            field_turnaround_pairs.append((requested_at, captured_at))

    intervention_total = len(intervention_actions)
    intervention_completed = sum(1 for row in intervention_actions if str(row.status).lower() in COMPLETED_INTERVENTION_STATUSES)

    compliant_runs = 0
    for run in pipeline_runs:
        if str(run.status).lower() != "completed":
            continue
        reference_time = run.finished_at or run.started_at
        if run.scheduled_for is None:
            compliant_runs += 1
            continue
        deadline = run.scheduled_for + timedelta(minutes=max(1, run.sla_target_minutes or 60))
        if reference_time is not None and reference_time <= deadline:
            compliant_runs += 1

    reviewed_workflow_count = workflows_completed
    reviewed_workflow_audit_count = db.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.action_type.in_(REVIEW_WORKFLOW_AUDIT_ACTIONS),
            AuditLog.timestamp >= period_start,
            AuditLog.timestamp < period_end,
        )
    ) or 0
    controlled_report_delivery_count = db.scalar(
        select(func.count(func.distinct(ReportDeliveryLog.id))).where(
            ReportDeliveryLog.updated_at >= period_start,
            ReportDeliveryLog.updated_at < period_end,
            ReportDeliveryLog.status.in_(CONTROLLED_REPORT_DELIVERY_STATUSES),
        )
    ) or 0
    audited_report_delivery_count = db.scalar(
        select(func.count(func.distinct(AuditLog.entity_id))).where(
            AuditLog.entity_type == "report_delivery_log",
            AuditLog.timestamp >= period_start,
            AuditLog.timestamp < period_end,
        )
    ) or 0
    supporting_audit_log_ids = [
        int(row)
        for row in db.scalars(
            select(AuditLog.id).where(
                AuditLog.timestamp >= period_start,
                AuditLog.timestamp < period_end,
                AuditLog.action_type.in_(
                    (
                        *REVIEW_WORKFLOW_AUDIT_ACTIONS,
                        "report.export.download",
                        "report.distribution.queued",
                        "report.distribution.sent",
                        "report.distribution.failed",
                        "geospatial.aoi.field_visit.update",
                    )
                ),
            )
        ).all()
    ]

    anomaly_precision = _safe_ratio(resolved, reviewed)
    review_turnaround_hours = _average_hours(approval_workflows_reviewed)
    field_turnaround_hours = _average_hours(field_turnaround_pairs)
    intervention_completion = _safe_ratio(intervention_completed, intervention_total)
    report_usage = _safe_ratio(active_report_readers, targeted_recipients)
    executive_follow_through = _safe_ratio(completed_alert_actions + workflows_completed, alerts_opened + workflows_requested)
    municipality_adoption = _safe_ratio(municipalities_active, municipalities_total)
    run_schedule_compliance = _safe_ratio(compliant_runs, len(pipeline_runs))
    job_success_rate = _safe_ratio(jobs_success, jobs_total)
    controlled_actions = reviewed_workflow_count + controlled_report_delivery_count
    audited_actions = min(reviewed_workflow_count, reviewed_workflow_audit_count) + min(controlled_report_delivery_count, audited_report_delivery_count)
    audit_completeness = _safe_ratio(audited_actions, controlled_actions)

    return {
        "GEO-KPI-001": round(anomaly_precision, 4) if anomaly_precision is not None else None,
        "GEO-KPI-002": round(review_turnaround_hours, 2) if review_turnaround_hours is not None else None,
        "GEO-KPI-003": round(field_turnaround_hours, 2) if field_turnaround_hours is not None else None,
        "GEO-KPI-004": round(intervention_completion, 4) if intervention_completion is not None else None,
        "GEO-KPI-005": round(report_usage, 4) if report_usage is not None else None,
        "GEO-KPI-006": round(executive_follow_through, 4) if executive_follow_through is not None else None,
        "GEO-KPI-007": round(municipality_adoption, 4) if municipality_adoption is not None else None,
        "GEO-KPI-008": round(run_schedule_compliance, 4) if run_schedule_compliance is not None else None,
        "GEO-KPI-009": round(job_success_rate, 4) if job_success_rate is not None else None,
        "GEO-KPI-010": round(audit_completeness, 4) if audit_completeness is not None else None,
        "meta": {
            "alerts_open": int(alerts_open),
            "anomalies_reviewed": int(reviewed),
            "anomalies_resolved": int(resolved),
            "approval_workflows_reviewed": int(reviewed_workflow_count),
            "field_visit_completions": len(field_turnaround_pairs),
            "intervention_actions_total": intervention_total,
            "intervention_actions_completed": intervention_completed,
            "targeted_recipients": int(targeted_recipients),
            "active_report_readers": int(active_report_readers),
            "alerts_opened": int(alerts_opened),
            "alerts_actioned": int(completed_alert_actions),
            "approval_workflows_requested": int(workflows_requested),
            "pipeline_runs_total": len(pipeline_runs),
            "pipeline_runs_compliant": compliant_runs,
            "jobs_total": int(jobs_total),
            "jobs_success": int(jobs_success),
            "municipalities_total": int(municipalities_total),
            "municipalities_active": int(municipalities_active),
            "controlled_actions_total": int(controlled_actions),
            "audited_actions_total": int(audited_actions),
            "supporting_incident_ids": sorted(set(supporting_incident_ids))[:25],
            "supporting_workflow_ids": sorted(set(approval_workflow_ids))[:25],
            "supporting_delivery_log_ids": sorted(set(report_delivery_log_ids))[:25],
            "supporting_report_ids": supporting_report_ids[:25],
            "supporting_audit_log_ids": sorted(set([*field_visit_audit_ids, *supporting_audit_log_ids]))[:50],
        },
    }


def run_monthly_kpi_scorecard_generation(
    db: Session,
    *,
    reporting_month: date | None = None,
    actor_user_id: int | None = None,
) -> GeospatialKpiScorecard:
    month = (reporting_month or date.today()).replace(day=1)
    scorecard = db.scalar(
        select(GeospatialKpiScorecard).where(
            GeospatialKpiScorecard.period_month == month,
            GeospatialKpiScorecard.region_scope == "Occidental Mindoro",
        )
    )
    metrics = build_monthly_kpi_metrics(db, month)
    if scorecard is None:
        scorecard = GeospatialKpiScorecard(
            period_month=month,
            region_scope="Occidental Mindoro",
            metrics_json=metrics,
            thresholds_json=DEFAULT_KPI_THRESHOLDS,
            source_pointers_json={
                "api": [
                    "/api/v1/geospatial/dashboard/executive",
                    "/api/v1/admin/jobs",
                    "/api/v1/audit/events",
                    "/api/v1/geospatial/ops/tasks",
                ]
            },
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        db.add(scorecard)
        db.flush()
    else:
        scorecard.metrics_json = metrics
        scorecard.updated_by = actor_user_id

    overall, statuses, merged_thresholds = compute_kpi_statuses(
        scorecard.metrics_json or {},
        scorecard.thresholds_json or DEFAULT_KPI_THRESHOLDS,
    )
    source_meta = (
        dict(scorecard.metrics_json.get("meta") or {})
        if isinstance(scorecard.metrics_json, dict)
        else {}
    )
    traceability = {
        "source_counts": _extract_traceability_source_counts(source_meta),
        "supporting_links": _build_traceability_links(source_meta),
    }
    artifacts = write_monthly_kpi_artifacts(
        period_month=month,
        region_scope=scorecard.region_scope,
        metrics=dict(scorecard.metrics_json or {}),
        statuses=statuses,
        thresholds=merged_thresholds,
        overall_status=overall,
    )
    scorecard.thresholds_json = merged_thresholds
    scorecard.computed_status = overall
    scorecard.source_pointers_json = {
        **(scorecard.source_pointers_json or {}),
        "computed_at": datetime.utcnow().isoformat(),
        "metric_statuses": statuses,
        "traceability": traceability,
        "artifacts": artifacts,
    }
    db.flush()

    create_ops_task(
        db,
        task_type="kpi_scorecard_review",
        title=f"Review geospatial KPI scorecard for {month.isoformat()}",
        description="Monthly KPI scorecard was generated and requires operations/governance review.",
        due_at=datetime.utcnow() + timedelta(days=2),
        related_entity_type="geospatial_kpi_scorecard",
        related_entity_id=str(scorecard.id),
        payload={
            "period_month": month.isoformat(),
            "computed_status": overall,
            "artifact_paths": artifacts,
        },
        priority="high" if overall == "red" else "medium",
        created_by=actor_user_id,
    )
    return scorecard


def run_risk_review_reminders(db: Session, *, actor_user_id: int | None = None) -> list[GeospatialOpsTask]:
    today = date.today()
    rows = list(
        db.scalars(
            select(GeospatialRiskItem).where(
                GeospatialRiskItem.status.in_(["open", "mitigating", "accepted"]),
                GeospatialRiskItem.next_review_date.is_not(None),
                GeospatialRiskItem.next_review_date <= today,
            )
        )
    )
    tasks: list[GeospatialOpsTask] = []
    for risk in rows:
        duplicate = db.scalar(
            select(GeospatialOpsTask).where(
                GeospatialOpsTask.task_type == "risk_review_reminder",
                GeospatialOpsTask.related_entity_type == "geospatial_risk_item",
                GeospatialOpsTask.related_entity_id == str(risk.id),
                GeospatialOpsTask.status == "open",
            )
        )
        if duplicate:
            continue
        tasks.append(
            create_ops_task(
                db,
                task_type="risk_review_reminder",
                title=f"Risk review due: {risk.risk_key}",
                description=f"Risk item {risk.risk_key} requires review.",
                due_at=datetime.utcnow() + timedelta(hours=12),
                assigned_to_user_id=risk.owner_user_id,
                related_entity_type="geospatial_risk_item",
                related_entity_id=str(risk.id),
                payload={"risk_key": risk.risk_key, "next_review_date": str(risk.next_review_date)},
                priority="high" if risk.rating >= 16 else "medium",
                created_by=actor_user_id,
            )
        )
    return tasks


def run_incident_slo_checks(db: Session, *, actor_user_id: int | None = None) -> list[GeospatialOpsTask]:
    now = datetime.utcnow()
    rows = list(
        db.scalars(
            select(GeospatialIncident).where(GeospatialIncident.status.in_(["open", "mitigating"]))
        )
    )
    tasks: list[GeospatialOpsTask] = []
    for incident in rows:
        if incident_due_at(incident) > now:
            continue
        duplicate = db.scalar(
            select(GeospatialOpsTask).where(
                GeospatialOpsTask.task_type == "incident_slo_breach",
                GeospatialOpsTask.related_entity_type == "geospatial_incident",
                GeospatialOpsTask.related_entity_id == str(incident.id),
                GeospatialOpsTask.status == "open",
            )
        )
        if duplicate:
            continue
        task = create_ops_task(
            db,
            task_type="incident_slo_breach",
            title=f"Incident SLO breach: {incident.incident_key}",
            description=f"Incident {incident.incident_key} exceeded target mitigation window.",
            due_at=now,
            assigned_to_user_id=incident.assigned_to_user_id,
            related_entity_type="geospatial_incident",
            related_entity_id=str(incident.id),
            payload={
                "incident_key": incident.incident_key,
                "severity": incident.severity,
                "started_at": incident.started_at.isoformat(),
                "slo_target_minutes": incident.slo_target_minutes,
            },
            priority="critical" if incident.severity in {"SEV0", "SEV1"} else "high",
            created_by=actor_user_id,
        )
        append_incident_comms_entry(
            incident,
            {
                "timestamp": now.isoformat(),
                "message": "Automatic SLO breach task generated.",
                "task_id": task.id,
                "event": "slo_breach",
            },
        )
        notify_observability_alert(
            alert_type="geospatial_incident_slo_breach",
            severity="critical" if incident.severity in {"SEV0", "SEV1"} else "high",
            summary=f"Incident {incident.incident_key} exceeded SLO target.",
            metrics={
                "incident_id": incident.id,
                "severity": incident.severity,
                "started_at": incident.started_at.isoformat(),
                "slo_target_minutes": incident.slo_target_minutes,
            },
        )
        tasks.append(task)
    return tasks
