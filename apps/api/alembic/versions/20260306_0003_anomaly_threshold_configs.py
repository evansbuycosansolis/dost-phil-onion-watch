"""anomaly threshold configs and version history

Revision ID: 20260306_0003
Revises: 20260306_0002
Create Date: 2026-03-06 01:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260306_0003"
down_revision = "20260306_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anomaly_threshold_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("anomaly_type", sa.String(length=80), nullable=False),
        sa.Column("thresholds_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("anomaly_type", name="uq_anomaly_threshold_configs_anomaly_type"),
    )
    op.create_index("ix_anomaly_threshold_configs_type", "anomaly_threshold_configs", ["anomaly_type"])
    op.create_index("ix_anomaly_threshold_configs_active", "anomaly_threshold_configs", ["is_active"])
    op.create_index("ix_anomaly_threshold_configs_last_changed_by", "anomaly_threshold_configs", ["last_changed_by"])

    op.create_table(
        "anomaly_threshold_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("config_id", sa.Integer(), sa.ForeignKey("anomaly_threshold_configs.id"), nullable=False),
        sa.Column("anomaly_type", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("thresholds_json", sa.JSON(), nullable=False),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("config_id", "version", name="uq_anomaly_threshold_versions_config_version"),
    )
    op.create_index("ix_anomaly_threshold_versions_type", "anomaly_threshold_versions", ["anomaly_type"])
    op.create_index("ix_anomaly_threshold_versions_changed_at", "anomaly_threshold_versions", ["changed_at"])
    op.create_index("ix_anomaly_threshold_versions_config_id", "anomaly_threshold_versions", ["config_id"])
    op.create_index("ix_anomaly_threshold_versions_changed_by", "anomaly_threshold_versions", ["changed_by"])


def downgrade() -> None:
    op.drop_index("ix_anomaly_threshold_versions_changed_by", table_name="anomaly_threshold_versions")
    op.drop_index("ix_anomaly_threshold_versions_config_id", table_name="anomaly_threshold_versions")
    op.drop_index("ix_anomaly_threshold_versions_changed_at", table_name="anomaly_threshold_versions")
    op.drop_index("ix_anomaly_threshold_versions_type", table_name="anomaly_threshold_versions")
    op.drop_table("anomaly_threshold_versions")

    op.drop_index("ix_anomaly_threshold_configs_last_changed_by", table_name="anomaly_threshold_configs")
    op.drop_index("ix_anomaly_threshold_configs_active", table_name="anomaly_threshold_configs")
    op.drop_index("ix_anomaly_threshold_configs_type", table_name="anomaly_threshold_configs")
    op.drop_table("anomaly_threshold_configs")
