"""add job run correlation id for traceability

Revision ID: 20260306_0007
Revises: 20260306_0006
Create Date: 2026-03-06 13:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260306_0007"
down_revision = "20260306_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("job_runs") as batch_op:
        batch_op.add_column(sa.Column("correlation_id", sa.String(length=120), nullable=True))
        batch_op.create_index("ix_job_runs_correlation_id", ["correlation_id"])


def downgrade() -> None:
    with op.batch_alter_table("job_runs") as batch_op:
        batch_op.drop_index("ix_job_runs_correlation_id")
        batch_op.drop_column("correlation_id")
