"""repair missing job_runs table for worker bootstrap

Revision ID: 20260309_0012
Revises: 20260308_0011
Create Date: 2026-03-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260309_0012"
down_revision = "20260308_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "job_runs" not in table_names:
        op.create_table(
            "job_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("job_name", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("correlation_id", sa.String(length=120), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("details_json", sa.JSON(), nullable=True),
            sa.Column("triggered_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
        )

    inspector = sa.inspect(bind)
    index_names = {idx["name"] for idx in inspector.get_indexes("job_runs")}
    if "ix_job_runs_correlation_id" not in index_names:
        op.create_index("ix_job_runs_correlation_id", "job_runs", ["correlation_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "job_runs" not in table_names:
        return

    index_names = {idx["name"] for idx in inspector.get_indexes("job_runs")}
    if "ix_job_runs_correlation_id" in index_names:
        op.drop_index("ix_job_runs_correlation_id", table_name="job_runs")
    op.drop_table("job_runs")
