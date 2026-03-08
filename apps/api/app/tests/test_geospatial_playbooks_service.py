from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import (
    Alert,
    AlertAcknowledgement,
    ApprovalWorkflow,
    AnomalyEvent,
    AuditLog,
    InterventionAction,
    Municipality,
    JobRun,
    ReportDeliveryLog,
    ReportRecipientGroup,
    ReportRecord,
    SatellitePipelineRun,
)
from app.services.geospatial_playbooks_service import (
    build_monthly_kpi_metrics,
    compute_kpi_statuses,
    run_monthly_kpi_scorecard_generation,
)


def test_compute_kpi_statuses_assigns_expected_traffic_lights():
    overall, statuses, thresholds = compute_kpi_statuses(
        {
            "GEO-KPI-001": 0.81,
            "GEO-KPI-002": 30.0,
            "GEO-KPI-003": 101.0,
        },
        {
            "GEO-KPI-001": {"direction": "higher", "green": 0.75, "amber": 0.65},
            "GEO-KPI-002": {"direction": "lower", "green": 24.0, "amber": 36.0},
            "GEO-KPI-003": {"direction": "lower", "green": 72.0, "amber": 96.0},
        },
    )

    assert overall == "red"
    assert statuses["GEO-KPI-001"] == "green"
    assert statuses["GEO-KPI-002"] == "yellow"
    assert statuses["GEO-KPI-003"] == "red"
    assert "GEO-KPI-001" in thresholds


def test_compute_kpi_statuses_handles_missing_or_invalid_metrics():
    overall, statuses, _ = compute_kpi_statuses(
        {"GEO-KPI-001": "not-a-number"},
        {"GEO-KPI-001": {"direction": "higher", "green": 0.75, "amber": 0.65}, "GEO-KPI-002": {"direction": "higher", "green": 0.8, "amber": 0.6}},
    )

    assert overall == "red"
    assert statuses["GEO-KPI-001"] == "red"
    assert statuses["GEO-KPI-002"] == "yellow"


def test_build_monthly_kpi_metrics_uses_real_table_derivations():
    month = date(2099, 1, 1)
    period_start = datetime(2099, 1, 1, 8, 0, 0)

    with SessionLocal() as db:
        municipality = db.scalar(select(Municipality).limit(1))
        assert municipality is not None

        db.add_all(
            [
                AnomalyEvent(
                    detected_at=period_start,
                    reporting_month=month,
                    anomaly_type="geo-risk",
                    scope_type="municipality",
                    municipality_id=municipality.id,
                    severity="high",
                    summary="Reviewed anomaly",
                    status="acknowledged",
                ),
                AnomalyEvent(
                    detected_at=period_start + timedelta(hours=1),
                    reporting_month=month,
                    anomaly_type="geo-risk",
                    scope_type="municipality",
                    municipality_id=municipality.id,
                    severity="high",
                    summary="Resolved anomaly",
                    status="resolved",
                ),
                ApprovalWorkflow(
                    entity_type="geospatial_run",
                    entity_id="run-209901",
                    status="approved",
                    requested_at=period_start,
                    reviewed_at=period_start + timedelta(hours=24),
                ),
                AuditLog(
                    actor_user_id=1,
                    action_type="geospatial.aoi.field_visit.update",
                    entity_type="geospatial_aoi",
                    entity_id="209901",
                    timestamp=period_start + timedelta(days=2),
                    after_payload={
                        "action": "complete",
                        "field_visit": {
                            "status": "completed",
                            "requested_at": period_start.isoformat(),
                            "captured_at": (period_start + timedelta(hours=48)).isoformat(),
                        },
                    },
                ),
                InterventionAction(
                    action_type="deploy_team",
                    municipality_id=municipality.id,
                    action_date=month,
                    description="Completed intervention",
                    status="completed",
                ),
                InterventionAction(
                    action_type="inspection",
                    municipality_id=municipality.id,
                    action_date=month,
                    description="Pending intervention",
                    status="pending",
                ),
                ReportRecord(
                    category="alert_digest",
                    title="Geospatial report usage test",
                    reporting_month=month,
                    status="generated",
                    generated_at=period_start,
                ),
                ReportRecipientGroup(
                    name="Geo KPI Test Group",
                    report_category="alert_digest",
                    role_name="executive_viewer",
                    delivery_channel="file_drop",
                    export_format="pdf",
                    max_attempts=3,
                    retry_backoff_seconds=300,
                    notify_on_failure=True,
                    is_active=True,
                ),
                Alert(
                    opened_at=period_start,
                    alert_type="geospatial_watch",
                    severity="high",
                    status="acknowledged",
                    title="Executive follow-through alert",
                    scope_type="municipality",
                    municipality_id=municipality.id,
                    summary="Alert summary",
                    recommended_action="Review and respond",
                ),
                SatellitePipelineRun(
                    run_type="ingest",
                    status="completed",
                    started_at=period_start + timedelta(minutes=20),
                    finished_at=period_start + timedelta(minutes=50),
                    scheduled_for=period_start,
                    sla_target_minutes=60,
                    aoi_id=None,
                ),
                SatellitePipelineRun(
                    run_type="feature_refresh",
                    status="failed",
                    started_at=period_start + timedelta(hours=2),
                    finished_at=period_start + timedelta(hours=3),
                    scheduled_for=period_start + timedelta(hours=2),
                    sla_target_minutes=30,
                    aoi_id=None,
                ),
                JobRun(
                    job_name="geo_job_success",
                    status="completed",
                    started_at=period_start,
                    finished_at=period_start + timedelta(minutes=5),
                ),
                JobRun(
                    job_name="geo_job_failure",
                    status="failed",
                    started_at=period_start + timedelta(hours=1),
                    finished_at=period_start + timedelta(hours=1, minutes=5),
                ),
            ]
        )
        db.flush()

        report = db.scalar(select(ReportRecord).where(ReportRecord.title == "Geospatial report usage test"))
        group = db.scalar(select(ReportRecipientGroup).where(ReportRecipientGroup.name == "Geo KPI Test Group"))
        alert = db.scalar(select(Alert).where(Alert.title == "Executive follow-through alert"))
        workflow = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.entity_id == "run-209901"))
        assert report is not None and group is not None and alert is not None and workflow is not None

        db.add_all(
            [
                ReportDeliveryLog(
                    report_id=report.id,
                    recipient_group_id=group.id,
                    recipient_user_id=1,
                    recipient_email="exec@example.test",
                    recipient_role="executive_viewer",
                    delivery_channel="file_drop",
                    export_format="pdf",
                    status="sent",
                    attempt_count=1,
                    max_attempts=3,
                    dispatched_at=period_start,
                    delivered_at=period_start + timedelta(minutes=10),
                ),
                AuditLog(
                    actor_user_id=1,
                    action_type="report.export.download",
                    entity_type="report_record",
                    entity_id=str(report.id),
                    timestamp=period_start + timedelta(minutes=30),
                ),
                AlertAcknowledgement(
                    alert_id=alert.id,
                    user_id=1,
                    action="acknowledged",
                    action_at=period_start + timedelta(minutes=15),
                ),
                AuditLog(
                    actor_user_id=1,
                    action_type="geospatial.run.approval_gate.update",
                    entity_type="satellite_pipeline_run",
                    entity_id=workflow.entity_id,
                    timestamp=period_start + timedelta(hours=24),
                ),
                AuditLog(
                    actor_user_id=1,
                    action_type="report.distribution.sent",
                    entity_type="report_delivery_log",
                    entity_id="1",
                    timestamp=period_start + timedelta(minutes=10),
                ),
            ]
        )
        db.commit()

        metrics = build_monthly_kpi_metrics(db, month)

    assert metrics["GEO-KPI-001"] == 0.5
    assert metrics["GEO-KPI-002"] == 24.0
    assert metrics["GEO-KPI-003"] == 48.0
    assert metrics["GEO-KPI-004"] == 0.5
    assert metrics["GEO-KPI-005"] == 1.0
    assert metrics["GEO-KPI-006"] == 1.0
    assert metrics["GEO-KPI-008"] == 0.5
    assert metrics["GEO-KPI-009"] == 0.5
    assert metrics["GEO-KPI-010"] == 1.0
    assert metrics["meta"]["approval_workflows_reviewed"] >= 1
    assert metrics["meta"]["field_visit_completions"] >= 1


def test_kpi_missing_denominator_returns_none_and_yellow_status():
    month = date(2099, 2, 1)

    with SessionLocal() as db:
        metrics = build_monthly_kpi_metrics(db, month)
        overall, statuses, _ = compute_kpi_statuses(metrics)

    assert metrics["GEO-KPI-005"] is None
    assert metrics["GEO-KPI-008"] is None
    assert metrics["GEO-KPI-009"] is None
    assert metrics["GEO-KPI-010"] is None
    assert statuses["GEO-KPI-005"] == "yellow"
    assert statuses["GEO-KPI-008"] == "yellow"
    assert statuses["GEO-KPI-009"] == "yellow"
    assert statuses["GEO-KPI-010"] == "yellow"
    assert overall in {"yellow", "red"}


def test_kpi_report_usage_handles_mixed_delivery_statuses():
    month = date(2099, 3, 1)
    period_start = datetime(2099, 3, 1, 8, 0, 0)

    with SessionLocal() as db:
        report = ReportRecord(
            category="alert_digest",
            title="Mixed delivery status KPI test",
            reporting_month=month,
            status="generated",
            generated_at=period_start,
        )
        group = ReportRecipientGroup(
            name="Mixed delivery status group",
            report_category="alert_digest",
            role_name="executive_viewer",
            delivery_channel="file_drop",
            export_format="pdf",
            max_attempts=3,
            retry_backoff_seconds=300,
            notify_on_failure=True,
            is_active=True,
        )
        db.add_all([report, group])
        db.flush()

        db.add_all(
            [
                ReportDeliveryLog(
                    report_id=report.id,
                    recipient_group_id=group.id,
                    recipient_user_id=1,
                    recipient_email="exec1@example.test",
                    recipient_role="executive_viewer",
                    delivery_channel="file_drop",
                    export_format="pdf",
                    status="sent",
                    attempt_count=1,
                    max_attempts=3,
                    dispatched_at=period_start,
                ),
                ReportDeliveryLog(
                    report_id=report.id,
                    recipient_group_id=group.id,
                    recipient_user_id=2,
                    recipient_email="exec2@example.test",
                    recipient_role="executive_viewer",
                    delivery_channel="file_drop",
                    export_format="pdf",
                    status="failed",
                    attempt_count=2,
                    max_attempts=3,
                    dispatched_at=period_start + timedelta(minutes=5),
                ),
                AuditLog(
                    actor_user_id=1,
                    action_type="report.export.download",
                    entity_type="report_record",
                    entity_id=str(report.id),
                    timestamp=period_start + timedelta(minutes=15),
                ),
            ]
        )
        db.commit()

        metrics = build_monthly_kpi_metrics(db, month)

    assert metrics["GEO-KPI-005"] == 0.5
    assert metrics["meta"]["targeted_recipients"] == 2
    assert metrics["meta"]["active_report_readers"] == 1


def test_kpi_audit_completeness_drops_when_audit_coverage_missing():
    month = date(2099, 4, 1)
    period_start = datetime(2099, 4, 1, 9, 0, 0)

    with SessionLocal() as db:
        report = ReportRecord(
            category="alert_digest",
            title="Audit completeness KPI test",
            reporting_month=month,
            status="generated",
            generated_at=period_start,
        )
        group = ReportRecipientGroup(
            name="Audit completeness group",
            report_category="alert_digest",
            role_name="executive_viewer",
            delivery_channel="file_drop",
            export_format="pdf",
            max_attempts=3,
            retry_backoff_seconds=300,
            notify_on_failure=True,
            is_active=True,
        )
        workflow = ApprovalWorkflow(
            entity_type="geospatial_run",
            entity_id="run-audit-gap-209904",
            status="approved",
            requested_at=period_start,
            reviewed_at=period_start + timedelta(hours=2),
        )
        db.add_all([report, group, workflow])
        db.flush()

        delivery = ReportDeliveryLog(
            report_id=report.id,
            recipient_group_id=group.id,
            recipient_user_id=1,
            recipient_email="exec.audit@example.test",
            recipient_role="executive_viewer",
            delivery_channel="file_drop",
            export_format="pdf",
            status="sent",
            attempt_count=1,
            max_attempts=3,
            dispatched_at=period_start + timedelta(minutes=15),
            delivered_at=period_start + timedelta(minutes=35),
        )
        delivery.updated_at = period_start + timedelta(minutes=35)
        db.add(delivery)
        db.commit()

        metrics = build_monthly_kpi_metrics(db, month)

    assert metrics["meta"]["controlled_actions_total"] >= 2
    assert metrics["meta"]["audited_actions_total"] == 0
    assert metrics["GEO-KPI-010"] == 0.0


def test_kpi_schedule_compliance_drops_for_overdue_pipeline_runs():
    month = date(2099, 5, 1)
    period_start = datetime(2099, 5, 1, 7, 0, 0)

    with SessionLocal() as db:
        db.add_all(
            [
                SatellitePipelineRun(
                    run_type="ingest",
                    status="completed",
                    started_at=period_start + timedelta(minutes=3),
                    finished_at=period_start + timedelta(minutes=20),
                    scheduled_for=period_start,
                    sla_target_minutes=30,
                    aoi_id=None,
                ),
                SatellitePipelineRun(
                    run_type="feature_refresh",
                    status="completed",
                    started_at=period_start + timedelta(hours=1),
                    finished_at=period_start + timedelta(hours=2, minutes=15),
                    scheduled_for=period_start + timedelta(hours=1),
                    sla_target_minutes=30,
                    aoi_id=None,
                ),
            ]
        )
        db.commit()

        metrics = build_monthly_kpi_metrics(db, month)

    assert metrics["meta"]["pipeline_runs_total"] == 2
    assert metrics["meta"]["pipeline_runs_compliant"] == 1
    assert metrics["GEO-KPI-008"] == 0.5


def test_monthly_kpi_automation_writes_artifact_files(tmp_path, monkeypatch):
    month = date(2099, 6, 1)
    monkeypatch.setattr(settings, "reports_path", str(tmp_path), raising=False)

    with SessionLocal() as db:
        row = run_monthly_kpi_scorecard_generation(db, reporting_month=month, actor_user_id=1)
        db.commit()
        db.refresh(row)

        pointers = row.source_pointers_json or {}
        artifacts = pointers.get("artifacts") or {}

    assert artifacts["records_dir"]
    assert artifacts["scorecard_csv"]
    assert artifacts["variance_notes"]
    assert artifacts["action_summary"]
    assert Path(artifacts["scorecard_csv"]).exists()
    assert Path(artifacts["variance_notes"]).exists()
    assert Path(artifacts["action_summary"]).exists()
