"""report distribution groups and delivery logs

Revision ID: 20260306_0005
Revises: 20260306_0004
Create Date: 2026-03-06 06:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260306_0005"
down_revision = "20260306_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_recipient_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("report_category", sa.String(length=80), nullable=True),
        sa.Column("role_name", sa.String(length=64), nullable=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("stakeholder_organizations.id"), nullable=True),
        sa.Column("delivery_channel", sa.String(length=40), nullable=False, server_default="file_drop"),
        sa.Column("export_format", sa.String(length=10), nullable=False, server_default="pdf"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("retry_backoff_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("notify_on_failure", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_report_recipient_groups_active", "report_recipient_groups", ["is_active"])
    op.create_index("ix_report_recipient_groups_category", "report_recipient_groups", ["report_category"])
    op.create_index("ix_report_recipient_groups_role", "report_recipient_groups", ["role_name"])
    op.create_index("ix_report_recipient_groups_organization", "report_recipient_groups", ["organization_id"])

    op.create_table(
        "report_delivery_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("report_records.id"), nullable=False),
        sa.Column("recipient_group_id", sa.Integer(), sa.ForeignKey("report_recipient_groups.id"), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_email", sa.String(length=120), nullable=False),
        sa.Column("recipient_role", sa.String(length=64), nullable=True),
        sa.Column("recipient_organization_id", sa.Integer(), sa.ForeignKey("stakeholder_organizations.id"), nullable=True),
        sa.Column("delivery_channel", sa.String(length=40), nullable=False),
        sa.Column("export_format", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("notification_sent_at", sa.DateTime(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint(
            "report_id",
            "recipient_group_id",
            "recipient_user_id",
            "export_format",
            name="uq_report_delivery_logs_report_group_user_format",
        ),
    )
    op.create_index("ix_report_delivery_logs_report", "report_delivery_logs", ["report_id"])
    op.create_index("ix_report_delivery_logs_recipient_user", "report_delivery_logs", ["recipient_user_id"])
    op.create_index("ix_report_delivery_logs_dispatched_at", "report_delivery_logs", ["dispatched_at"])
    op.create_index("ix_report_delivery_logs_status_next_attempt", "report_delivery_logs", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_report_delivery_logs_status_next_attempt", table_name="report_delivery_logs")
    op.drop_index("ix_report_delivery_logs_dispatched_at", table_name="report_delivery_logs")
    op.drop_index("ix_report_delivery_logs_recipient_user", table_name="report_delivery_logs")
    op.drop_index("ix_report_delivery_logs_report", table_name="report_delivery_logs")
    op.drop_table("report_delivery_logs")

    op.drop_index("ix_report_recipient_groups_organization", table_name="report_recipient_groups")
    op.drop_index("ix_report_recipient_groups_role", table_name="report_recipient_groups")
    op.drop_index("ix_report_recipient_groups_category", table_name="report_recipient_groups")
    op.drop_index("ix_report_recipient_groups_active", table_name="report_recipient_groups")
    op.drop_table("report_recipient_groups")
