"""forecast model registry and selection diagnostics

Revision ID: 20260306_0002
Revises: 20260306_0001
Create Date: 2026-03-06 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260306_0002"
down_revision = "20260306_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_model_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("forecast_run_id", sa.Integer(), sa.ForeignKey("forecast_runs.id"), nullable=False),
        sa.Column("municipality_id", sa.Integer(), sa.ForeignKey("municipalities.id"), nullable=False),
        sa.Column("model_name", sa.String(length=80), nullable=False),
        sa.Column("model_family", sa.String(length=40), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("prediction_next_month", sa.Float(), nullable=True),
        sa.Column("holdout_actual", sa.Float(), nullable=True),
        sa.Column("holdout_prediction", sa.Float(), nullable=True),
        sa.Column("holdout_mae", sa.Float(), nullable=True),
        sa.Column("holdout_mape", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("fallback_rank", sa.Integer(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_forecast_model_metrics_run_muni", "forecast_model_metrics", ["forecast_run_id", "municipality_id"])
    op.create_index("ix_forecast_model_metrics_model_name", "forecast_model_metrics", ["model_name"])
    op.create_index("ix_forecast_model_metrics_selected", "forecast_model_metrics", ["selected"])
    op.create_index("ix_forecast_model_metrics_forecast_run_id", "forecast_model_metrics", ["forecast_run_id"])
    op.create_index("ix_forecast_model_metrics_municipality_id", "forecast_model_metrics", ["municipality_id"])

    with op.batch_alter_table("forecast_outputs") as batch_op:
        batch_op.add_column(sa.Column("selected_model", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("selected_model_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("fallback_order_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("selection_metadata_json", sa.JSON(), nullable=True))
        batch_op.create_index("ix_forecast_outputs_selected_model", ["selected_model"])


def downgrade() -> None:
    with op.batch_alter_table("forecast_outputs") as batch_op:
        batch_op.drop_index("ix_forecast_outputs_selected_model")
        batch_op.drop_column("selection_metadata_json")
        batch_op.drop_column("fallback_order_json")
        batch_op.drop_column("selected_model_score")
        batch_op.drop_column("selected_model")

    op.drop_index("ix_forecast_model_metrics_municipality_id", table_name="forecast_model_metrics")
    op.drop_index("ix_forecast_model_metrics_forecast_run_id", table_name="forecast_model_metrics")
    op.drop_index("ix_forecast_model_metrics_selected", table_name="forecast_model_metrics")
    op.drop_index("ix_forecast_model_metrics_model_name", table_name="forecast_model_metrics")
    op.drop_index("ix_forecast_model_metrics_run_muni", table_name="forecast_model_metrics")
    op.drop_table("forecast_model_metrics")
