"""geospatial playbook operational tables

Revision ID: 20260308_0011
Revises: 20260307_0010
Create Date: 2026-03-08

"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "20260308_0011"
down_revision = "20260307_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geospatial_rollout_waves",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("wave_number", sa.Integer(), nullable=False),
        sa.Column("region_scope", sa.String(length=180), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewer_ids_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("gate_status", sa.String(length=40), nullable=False, server_default="draft"),
        sa.Column("gate_notes", sa.Text(), nullable=True),
        sa.Column("pass_fail_criteria_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("wave_number", "region_scope", name="uq_geospatial_rollout_waves_number_region"),
    )
    op.create_index("ix_geospatial_rollout_waves_gate_status", "geospatial_rollout_waves", ["gate_status"], unique=False)
    op.create_index("ix_geospatial_rollout_waves_owner", "geospatial_rollout_waves", ["owner_user_id"], unique=False)
    op.create_index("ix_geospatial_rollout_waves_dates", "geospatial_rollout_waves", ["start_date", "end_date"], unique=False)

    op.create_table(
        "geospatial_kpi_scorecards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("region_scope", sa.String(length=180), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("thresholds_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("computed_status", sa.String(length=20), nullable=False, server_default="yellow"),
        sa.Column("source_pointers_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("period_month", "region_scope", name="uq_geospatial_kpi_scorecards_period_scope"),
    )
    op.create_index("ix_geospatial_kpi_scorecards_period", "geospatial_kpi_scorecards", ["period_month"], unique=False)
    op.create_index("ix_geospatial_kpi_scorecards_status", "geospatial_kpi_scorecards", ["computed_status"], unique=False)

    op.create_table(
        "geospatial_incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_key", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="SEV3"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("mitigated_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("impact", sa.Text(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("corrective_actions_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("evidence_pack_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("comms_log_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_to_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("slo_target_minutes", sa.Integer(), nullable=False, server_default="240"),
        sa.Column("postmortem_completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("incident_key", name="uq_geospatial_incidents_incident_key"),
    )
    op.create_index("ix_geospatial_incidents_severity", "geospatial_incidents", ["severity"], unique=False)
    op.create_index("ix_geospatial_incidents_status", "geospatial_incidents", ["status"], unique=False)
    op.create_index("ix_geospatial_incidents_started_at", "geospatial_incidents", ["started_at"], unique=False)
    op.create_index("ix_geospatial_incidents_assigned_to", "geospatial_incidents", ["assigned_to_user_id"], unique=False)
    op.create_index("ix_geospatial_incidents_created_by_user_id", "geospatial_incidents", ["created_by_user_id"], unique=False)

    op.create_table(
        "geospatial_validation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_key", sa.String(length=80), nullable=False),
        sa.Column("scope", sa.String(length=180), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=True),
        sa.Column("threshold_set_version", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="planned"),
        sa.Column("executed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("signoff_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("results_summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("evidence_links_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("run_key", name="uq_geospatial_validation_runs_run_key"),
    )
    op.create_index("ix_geospatial_validation_runs_status", "geospatial_validation_runs", ["status"], unique=False)
    op.create_index("ix_geospatial_validation_runs_scope", "geospatial_validation_runs", ["scope"], unique=False)
    op.create_index("ix_geospatial_validation_runs_signoff", "geospatial_validation_runs", ["signoff_at"], unique=False)
    op.create_index("ix_geospatial_validation_runs_executed_by_user_id", "geospatial_validation_runs", ["executed_by_user_id"], unique=False)
    op.create_index("ix_geospatial_validation_runs_reviewed_by_user_id", "geospatial_validation_runs", ["reviewed_by_user_id"], unique=False)

    op.create_table(
        "geospatial_validation_testcases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("expected", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("code", name="uq_geospatial_validation_testcases_code"),
    )
    op.create_index(
        "ix_geospatial_validation_testcases_category",
        "geospatial_validation_testcases",
        ["category"],
        unique=False,
    )
    op.create_index(
        "ix_geospatial_validation_testcases_active",
        "geospatial_validation_testcases",
        ["is_active"],
        unique=False,
    )

    op.create_table(
        "geospatial_validation_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("geospatial_validation_runs.id"), nullable=False),
        sa.Column("testcase_id", sa.Integer(), sa.ForeignKey("geospatial_validation_testcases.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="skip"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("executed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("run_id", "testcase_id", name="uq_geospatial_validation_results_run_case"),
    )
    op.create_index(
        "ix_geospatial_validation_results_status",
        "geospatial_validation_results",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_geospatial_validation_results_run_id",
        "geospatial_validation_results",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_geospatial_validation_results_testcase_id",
        "geospatial_validation_results",
        ["testcase_id"],
        unique=False,
    )

    op.create_table(
        "geospatial_risk_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("risk_key", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("likelihood", sa.Integer(), nullable=False),
        sa.Column("impact", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=True),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("next_review_date", sa.Date(), nullable=True),
        sa.Column("target_close_date", sa.Date(), nullable=True),
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("board_notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("risk_key", name="uq_geospatial_risk_items_risk_key"),
    )
    op.create_index("ix_geospatial_risk_items_status", "geospatial_risk_items", ["status"], unique=False)
    op.create_index("ix_geospatial_risk_items_owner", "geospatial_risk_items", ["owner_user_id"], unique=False)
    op.create_index("ix_geospatial_risk_items_next_review", "geospatial_risk_items", ["next_review_date"], unique=False)
    op.create_index("ix_geospatial_risk_items_target_close", "geospatial_risk_items", ["target_close_date"], unique=False)
    op.create_index("ix_geospatial_risk_items_escalation", "geospatial_risk_items", ["escalation_level"], unique=False)

    op.create_table(
        "geospatial_ops_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("assigned_to_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("related_entity_type", sa.String(length=80), nullable=True),
        sa.Column("related_entity_id", sa.String(length=120), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("notification_sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_geospatial_ops_tasks_status_due",
        "geospatial_ops_tasks",
        ["status", "due_at"],
        unique=False,
    )
    op.create_index("ix_geospatial_ops_tasks_type", "geospatial_ops_tasks", ["task_type"], unique=False)
    op.create_index("ix_geospatial_ops_tasks_assignee", "geospatial_ops_tasks", ["assigned_to_user_id"], unique=False)
    op.create_index(
        "ix_geospatial_ops_tasks_related",
        "geospatial_ops_tasks",
        ["related_entity_type", "related_entity_id"],
        unique=False,
    )

    now = datetime.utcnow()
    testcase_table = sa.table(
        "geospatial_validation_testcases",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("expected", sa.Text),
        sa.column("severity", sa.String),
        sa.column("category", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        testcase_table,
        [
            {
                "code": "VA-T01",
                "name": "Geospatial route smoke checks",
                "description": "Validate critical geospatial routes respond successfully with authorized access.",
                "expected": "Critical routes return successful response payloads.",
                "severity": "high",
                "category": "api",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "code": "VA-T02",
                "name": "Scheduled worker execution and retries",
                "description": "Validate worker jobs execute and retry policy is applied for transient failures.",
                "expected": "No critical worker class remains stuck or fails without retries.",
                "severity": "high",
                "category": "worker",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "code": "VA-T03",
                "name": "Source freshness and completeness",
                "description": "Validate input source freshness/completeness against configured thresholds.",
                "expected": "Source compliance remains above configured minimums.",
                "severity": "high",
                "category": "data_quality",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "code": "VA-T04",
                "name": "Run and artifact lineage traceability",
                "description": "Validate sampled run lineage and artifact provenance chain is present.",
                "expected": "Input to output lineage is available for sampled runs.",
                "severity": "high",
                "category": "lineage",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "code": "VA-T05",
                "name": "Review and approval SLA flow",
                "description": "Validate analyst to supervisor workflow SLA and mandatory fields.",
                "expected": "Review and approval workflow meets SLA with required evidence.",
                "severity": "medium",
                "category": "workflow",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "code": "VA-T06",
                "name": "Field verification quality",
                "description": "Validate field verification closure quality and evidence completeness.",
                "expected": "Field verification closure includes complete evidence package.",
                "severity": "medium",
                "category": "field",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "code": "VA-T07",
                "name": "RBAC and audit control checks",
                "description": "Validate unauthorized access is blocked and audit events are complete.",
                "expected": "No unauthorized access and full audit coverage for controlled actions.",
                "severity": "critical",
                "category": "governance",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "code": "VA-T08",
                "name": "Export safety and signed package checks",
                "description": "Validate export redaction, signing, and policy-safe output controls.",
                "expected": "All sampled exports satisfy policy and signing requirements.",
                "severity": "critical",
                "category": "export",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "code": "VA-T09",
                "name": "KPI reproducibility",
                "description": "Validate KPI values are reproducible from authoritative API/table sources.",
                "expected": "Published KPI values match recomputed snapshots.",
                "severity": "high",
                "category": "kpi",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "code": "VA-T10",
                "name": "Source and model drift checks",
                "description": "Validate source/model drift remains within approved bounds.",
                "expected": "No uncontrolled drift beyond approved limits.",
                "severity": "high",
                "category": "drift",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_geospatial_ops_tasks_related", table_name="geospatial_ops_tasks")
    op.drop_index("ix_geospatial_ops_tasks_assignee", table_name="geospatial_ops_tasks")
    op.drop_index("ix_geospatial_ops_tasks_type", table_name="geospatial_ops_tasks")
    op.drop_index("ix_geospatial_ops_tasks_status_due", table_name="geospatial_ops_tasks")
    op.drop_table("geospatial_ops_tasks")

    op.drop_index("ix_geospatial_risk_items_escalation", table_name="geospatial_risk_items")
    op.drop_index("ix_geospatial_risk_items_target_close", table_name="geospatial_risk_items")
    op.drop_index("ix_geospatial_risk_items_next_review", table_name="geospatial_risk_items")
    op.drop_index("ix_geospatial_risk_items_owner", table_name="geospatial_risk_items")
    op.drop_index("ix_geospatial_risk_items_status", table_name="geospatial_risk_items")
    op.drop_table("geospatial_risk_items")

    op.drop_index("ix_geospatial_validation_results_testcase_id", table_name="geospatial_validation_results")
    op.drop_index("ix_geospatial_validation_results_run_id", table_name="geospatial_validation_results")
    op.drop_index("ix_geospatial_validation_results_status", table_name="geospatial_validation_results")
    op.drop_table("geospatial_validation_results")

    op.drop_index("ix_geospatial_validation_testcases_active", table_name="geospatial_validation_testcases")
    op.drop_index("ix_geospatial_validation_testcases_category", table_name="geospatial_validation_testcases")
    op.drop_table("geospatial_validation_testcases")

    op.drop_index("ix_geospatial_validation_runs_reviewed_by_user_id", table_name="geospatial_validation_runs")
    op.drop_index("ix_geospatial_validation_runs_executed_by_user_id", table_name="geospatial_validation_runs")
    op.drop_index("ix_geospatial_validation_runs_signoff", table_name="geospatial_validation_runs")
    op.drop_index("ix_geospatial_validation_runs_scope", table_name="geospatial_validation_runs")
    op.drop_index("ix_geospatial_validation_runs_status", table_name="geospatial_validation_runs")
    op.drop_table("geospatial_validation_runs")

    op.drop_index("ix_geospatial_incidents_created_by_user_id", table_name="geospatial_incidents")
    op.drop_index("ix_geospatial_incidents_assigned_to", table_name="geospatial_incidents")
    op.drop_index("ix_geospatial_incidents_started_at", table_name="geospatial_incidents")
    op.drop_index("ix_geospatial_incidents_status", table_name="geospatial_incidents")
    op.drop_index("ix_geospatial_incidents_severity", table_name="geospatial_incidents")
    op.drop_table("geospatial_incidents")

    op.drop_index("ix_geospatial_kpi_scorecards_status", table_name="geospatial_kpi_scorecards")
    op.drop_index("ix_geospatial_kpi_scorecards_period", table_name="geospatial_kpi_scorecards")
    op.drop_table("geospatial_kpi_scorecards")

    op.drop_index("ix_geospatial_rollout_waves_dates", table_name="geospatial_rollout_waves")
    op.drop_index("ix_geospatial_rollout_waves_owner", table_name="geospatial_rollout_waves")
    op.drop_index("ix_geospatial_rollout_waves_gate_status", table_name="geospatial_rollout_waves")
    op.drop_table("geospatial_rollout_waves")
