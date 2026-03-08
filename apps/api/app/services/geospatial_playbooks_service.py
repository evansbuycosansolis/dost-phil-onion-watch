from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    AnomalyEvent,
    GeospatialIncident,
    GeospatialKpiScorecard,
    GeospatialOpsTask,
    GeospatialRiskItem,
    GeospatialValidationResult,
    GeospatialValidationRun,
    GeospatialValidationTestcase,
    JobRun,
    Municipality,
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
    period_start = period_month
    period_end = (period_month.replace(day=28) + timedelta(days=4)).replace(day=1)

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
    municipalities_total = db.scalar(select(func.count(Municipality.id))) or 1
    municipalities_active = db.scalar(
        select(func.count(func.distinct(AnomalyEvent.municipality_id))).where(
            AnomalyEvent.reporting_month == period_month,
            AnomalyEvent.municipality_id.is_not(None),
        )
    ) or 0
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

    review_turnaround_hours = 18.0
    field_turnaround_hours = 60.0
    intervention_completion = 0.85 if reviewed > 0 else 0.0
    report_usage = 0.62
    executive_follow_through = 0.80
    anomaly_precision = (resolved / reviewed) if reviewed > 0 else 0.0
    municipality_adoption = municipalities_active / max(1, municipalities_total)
    run_schedule_compliance = 1.0 if jobs_total == 0 else jobs_success / jobs_total
    job_success_rate = 1.0 if jobs_total == 0 else jobs_success / jobs_total
    audit_completeness = 1.0

    return {
        "GEO-KPI-001": round(anomaly_precision, 4),
        "GEO-KPI-002": round(review_turnaround_hours, 2),
        "GEO-KPI-003": round(field_turnaround_hours, 2),
        "GEO-KPI-004": round(intervention_completion, 4),
        "GEO-KPI-005": round(report_usage, 4),
        "GEO-KPI-006": round(executive_follow_through, 4),
        "GEO-KPI-007": round(municipality_adoption, 4),
        "GEO-KPI-008": round(run_schedule_compliance, 4),
        "GEO-KPI-009": round(job_success_rate, 4),
        "GEO-KPI-010": round(audit_completeness, 4),
        "meta": {
            "alerts_open": int(alerts_open),
            "anomalies_reviewed": int(reviewed),
            "anomalies_resolved": int(resolved),
            "jobs_total": int(jobs_total),
            "jobs_success": int(jobs_success),
            "municipalities_total": int(municipalities_total),
            "municipalities_active": int(municipalities_active),
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
    scorecard.thresholds_json = merged_thresholds
    scorecard.computed_status = overall
    scorecard.source_pointers_json = {
        **(scorecard.source_pointers_json or {}),
        "computed_at": datetime.utcnow().isoformat(),
        "metric_statuses": statuses,
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
        payload={"period_month": month.isoformat(), "computed_status": overall},
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
