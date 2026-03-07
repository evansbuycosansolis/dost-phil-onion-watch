"""document ingestion queue, progress tracking, and chunk retries

Revision ID: 20260306_0004
Revises: 20260306_0003
Create Date: 2026-03-06 02:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260306_0004"
down_revision = "20260306_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("processed_chunks", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("failed_chunks", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("failure_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("index_status", sa.String(length=40), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("last_processed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("last_indexed_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_documents_status", ["status"])
        batch_op.create_index("ix_documents_index_status", ["index_status"])

    with op.batch_alter_table("document_chunks") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"))
        batch_op.add_column(sa.Column("failure_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_attempt_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("processed_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_document_chunks_status", ["status"])
        batch_op.create_index("ix_document_chunks_document_status", ["document_id", "status"])
        batch_op.create_unique_constraint("uq_document_chunks_document_chunk_index", ["document_id", "chunk_index"])

    op.create_table(
        "document_ingestion_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("queued_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_document_ingestion_jobs_status", "document_ingestion_jobs", ["status"])
    op.create_index("ix_document_ingestion_jobs_document", "document_ingestion_jobs", ["document_id"])
    op.create_index("ix_document_ingestion_jobs_queued_at", "document_ingestion_jobs", ["queued_at"])
    op.create_index("ix_document_ingestion_jobs_requested_by", "document_ingestion_jobs", ["requested_by"])


def downgrade() -> None:
    op.drop_index("ix_document_ingestion_jobs_requested_by", table_name="document_ingestion_jobs")
    op.drop_index("ix_document_ingestion_jobs_queued_at", table_name="document_ingestion_jobs")
    op.drop_index("ix_document_ingestion_jobs_document", table_name="document_ingestion_jobs")
    op.drop_index("ix_document_ingestion_jobs_status", table_name="document_ingestion_jobs")
    op.drop_table("document_ingestion_jobs")

    with op.batch_alter_table("document_chunks") as batch_op:
        batch_op.drop_constraint("uq_document_chunks_document_chunk_index", type_="unique")
        batch_op.drop_index("ix_document_chunks_document_status")
        batch_op.drop_index("ix_document_chunks_status")
        batch_op.drop_column("processed_at")
        batch_op.drop_column("last_attempt_at")
        batch_op.drop_column("failure_reason")
        batch_op.drop_column("max_retries")
        batch_op.drop_column("retry_count")
        batch_op.drop_column("status")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_index("ix_documents_index_status")
        batch_op.drop_index("ix_documents_status")
        batch_op.drop_column("last_indexed_at")
        batch_op.drop_column("last_processed_at")
        batch_op.drop_column("index_status")
        batch_op.drop_column("failure_reason")
        batch_op.drop_column("failed_chunks")
        batch_op.drop_column("processed_chunks")
        batch_op.drop_column("total_chunks")
        batch_op.drop_column("progress_pct")
