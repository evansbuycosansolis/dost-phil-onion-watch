"""mobile sync idempotency and provenance columns on source submissions

Revision ID: 20260306_0008
Revises: 20260306_0007
Create Date: 2026-03-06 16:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260306_0008"
down_revision = "20260306_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("source_submissions") as batch_op:
        batch_op.add_column(sa.Column("source_channel", sa.String(length=40), nullable=False, server_default="api"))
        batch_op.add_column(sa.Column("client_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("device_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("app_version", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("sync_batch_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("payload_hash", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("target_entity_type", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("target_entity_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("conflict_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("provenance_json", sa.JSON(), nullable=True))
        batch_op.create_index("ix_source_submissions_status", ["status"])
        batch_op.create_index("ix_source_submissions_sync_batch_id", ["sync_batch_id"])
        batch_op.create_index("ix_source_submissions_device_id", ["device_id"])
        batch_op.create_unique_constraint(
            "uq_source_submissions_source_idempotency",
            ["source_name", "idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("source_submissions") as batch_op:
        batch_op.drop_constraint("uq_source_submissions_source_idempotency", type_="unique")
        batch_op.drop_index("ix_source_submissions_device_id")
        batch_op.drop_index("ix_source_submissions_sync_batch_id")
        batch_op.drop_index("ix_source_submissions_status")
        batch_op.drop_column("provenance_json")
        batch_op.drop_column("conflict_reason")
        batch_op.drop_column("target_entity_id")
        batch_op.drop_column("target_entity_type")
        batch_op.drop_column("payload_hash")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("sync_batch_id")
        batch_op.drop_column("app_version")
        batch_op.drop_column("device_id")
        batch_op.drop_column("client_id")
        batch_op.drop_column("source_channel")
