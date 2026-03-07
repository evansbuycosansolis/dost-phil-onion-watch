"""geospatial backlog expansion tables

Revision ID: 20260307_0010
Revises: 20260306_0009
Create Date: 2026-03-07

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260307_0010"
down_revision = "20260306_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("satellite_pipeline_runs", sa.Column("operator_notes", sa.Text(), nullable=True))
    op.add_column("satellite_pipeline_runs", sa.Column("cancel_reason", sa.Text(), nullable=True))
    op.add_column(
        "satellite_pipeline_runs",
        sa.Column("retry_strategy", sa.String(length=40), nullable=False, server_default="standard"),
    )
    op.add_column(
        "satellite_pipeline_runs",
        sa.Column("queue_priority", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column("satellite_pipeline_runs", sa.Column("parent_run_id", sa.Integer(), nullable=True))
    op.add_column("satellite_pipeline_runs", sa.Column("scheduled_for", sa.DateTime(), nullable=True))
    op.add_column("satellite_pipeline_runs", sa.Column("sla_target_minutes", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_satellite_pipeline_runs_parent_run",
        "satellite_pipeline_runs",
        "satellite_pipeline_runs",
        ["parent_run_id"],
        ["id"],
    )
    op.create_index("ix_satellite_pipeline_runs_parent_run_id", "satellite_pipeline_runs", ["parent_run_id"], unique=False)

    op.create_table(
        "geospatial_aoi_metadata",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("aoi_id", sa.Integer(), sa.ForeignKey("geospatial_aois.id"), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("labels_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("watchlist_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("public_share_token", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("aoi_id", name="uq_geospatial_aoi_metadata_aoi_id"),
    )
    op.create_index("ix_geospatial_aoi_metadata_aoi_id", "geospatial_aoi_metadata", ["aoi_id"], unique=False)
    op.create_index("ix_geospatial_aoi_metadata_owner", "geospatial_aoi_metadata", ["owner_user_id"], unique=False)
    op.create_index("ix_geospatial_aoi_metadata_watchlist", "geospatial_aoi_metadata", ["watchlist_flag"], unique=False)
    op.create_index("ix_geospatial_aoi_metadata_public_token", "geospatial_aoi_metadata", ["public_share_token"], unique=False)

    op.create_table(
        "geospatial_aoi_favorites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("aoi_id", sa.Integer(), sa.ForeignKey("geospatial_aois.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("pinned_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("aoi_id", "user_id", name="uq_geospatial_aoi_favorites_aoi_user"),
    )
    op.create_index("ix_geospatial_aoi_favorites_aoi", "geospatial_aoi_favorites", ["aoi_id"], unique=False)
    op.create_index("ix_geospatial_aoi_favorites_user", "geospatial_aoi_favorites", ["user_id"], unique=False)
    op.create_index("ix_geospatial_aoi_favorites_pinned", "geospatial_aoi_favorites", ["is_pinned"], unique=False)

    op.create_table(
        "geospatial_aoi_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("aoi_id", sa.Integer(), sa.ForeignKey("geospatial_aois.id"), nullable=False),
        sa.Column("parent_note_id", sa.Integer(), sa.ForeignKey("geospatial_aoi_notes.id"), nullable=True),
        sa.Column("note_type", sa.String(length=40), nullable=False, server_default="note"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("mentions_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("assigned_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_geospatial_aoi_notes_aoi", "geospatial_aoi_notes", ["aoi_id"], unique=False)
    op.create_index("ix_geospatial_aoi_notes_type", "geospatial_aoi_notes", ["note_type"], unique=False)
    op.create_index("ix_geospatial_aoi_notes_parent", "geospatial_aoi_notes", ["parent_note_id"], unique=False)
    op.create_index("ix_geospatial_aoi_notes_assigned", "geospatial_aoi_notes", ["assigned_user_id"], unique=False)

    op.create_table(
        "geospatial_aoi_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("aoi_id", sa.Integer(), sa.ForeignKey("geospatial_aois.id"), nullable=False),
        sa.Column("asset_type", sa.String(length=40), nullable=False, server_default="photo"),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_geospatial_aoi_attachments_aoi", "geospatial_aoi_attachments", ["aoi_id"], unique=False)
    op.create_index("ix_geospatial_aoi_attachments_type", "geospatial_aoi_attachments", ["asset_type"], unique=False)

    op.create_table(
        "geospatial_aoi_document_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("aoi_id", sa.Integer(), sa.ForeignKey("geospatial_aois.id"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_geospatial_aoi_document_links_aoi", "geospatial_aoi_document_links", ["aoi_id"], unique=False)
    op.create_index("ix_geospatial_aoi_document_links_document", "geospatial_aoi_document_links", ["document_id"], unique=False)

    op.create_table(
        "geospatial_run_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("satellite_pipeline_runs.id"), nullable=False),
        sa.Column("phase", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("logged_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_geospatial_run_events_run", "geospatial_run_events", ["run_id"], unique=False)
    op.create_index("ix_geospatial_run_events_phase", "geospatial_run_events", ["phase"], unique=False)
    op.create_index("ix_geospatial_run_events_logged_at", "geospatial_run_events", ["logged_at"], unique=False)

    op.create_table(
        "geospatial_run_presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("run_type", sa.String(length=60), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sources_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("parameters_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("retry_strategy", sa.String(length=40), nullable=False, server_default="standard"),
        sa.Column("queue_priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("name", "created_by", name="uq_geospatial_run_presets_name_owner"),
    )
    op.create_index("ix_geospatial_run_presets_run_type", "geospatial_run_presets", ["run_type"], unique=False)

    op.create_table(
        "geospatial_run_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("run_type", sa.String(length=60), nullable=False),
        sa.Column("aoi_id", sa.Integer(), sa.ForeignKey("geospatial_aois.id"), nullable=True),
        sa.Column("cron_expression", sa.String(length=80), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="Asia/Manila"),
        sa.Column("recurrence_template", sa.String(length=80), nullable=True),
        sa.Column("retry_strategy", sa.String(length=40), nullable=False, server_default="standard"),
        sa.Column("queue_priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_status", sa.String(length=40), nullable=True),
        sa.Column("sources_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("parameters_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("notify_channels_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_geospatial_run_schedules_active", "geospatial_run_schedules", ["is_active"], unique=False)
    op.create_index("ix_geospatial_run_schedules_next_run", "geospatial_run_schedules", ["next_run_at"], unique=False)
    op.create_index("ix_geospatial_run_schedules_run_type", "geospatial_run_schedules", ["run_type"], unique=False)
    op.create_index("ix_geospatial_run_schedules_aoi_id", "geospatial_run_schedules", ["aoi_id"], unique=False)

    op.create_table(
        "geospatial_filter_presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("preset_type", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("user_id", "preset_type", "name", name="uq_geospatial_filter_presets_user_type_name"),
    )
    op.create_index("ix_geospatial_filter_presets_user", "geospatial_filter_presets", ["user_id"], unique=False)
    op.create_index("ix_geospatial_filter_presets_type", "geospatial_filter_presets", ["preset_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_geospatial_filter_presets_type", table_name="geospatial_filter_presets")
    op.drop_index("ix_geospatial_filter_presets_user", table_name="geospatial_filter_presets")
    op.drop_table("geospatial_filter_presets")

    op.drop_index("ix_geospatial_run_schedules_aoi_id", table_name="geospatial_run_schedules")
    op.drop_index("ix_geospatial_run_schedules_run_type", table_name="geospatial_run_schedules")
    op.drop_index("ix_geospatial_run_schedules_next_run", table_name="geospatial_run_schedules")
    op.drop_index("ix_geospatial_run_schedules_active", table_name="geospatial_run_schedules")
    op.drop_table("geospatial_run_schedules")

    op.drop_index("ix_geospatial_run_presets_run_type", table_name="geospatial_run_presets")
    op.drop_table("geospatial_run_presets")

    op.drop_index("ix_geospatial_run_events_logged_at", table_name="geospatial_run_events")
    op.drop_index("ix_geospatial_run_events_phase", table_name="geospatial_run_events")
    op.drop_index("ix_geospatial_run_events_run", table_name="geospatial_run_events")
    op.drop_table("geospatial_run_events")

    op.drop_index("ix_geospatial_aoi_document_links_document", table_name="geospatial_aoi_document_links")
    op.drop_index("ix_geospatial_aoi_document_links_aoi", table_name="geospatial_aoi_document_links")
    op.drop_table("geospatial_aoi_document_links")

    op.drop_index("ix_geospatial_aoi_attachments_type", table_name="geospatial_aoi_attachments")
    op.drop_index("ix_geospatial_aoi_attachments_aoi", table_name="geospatial_aoi_attachments")
    op.drop_table("geospatial_aoi_attachments")

    op.drop_index("ix_geospatial_aoi_notes_assigned", table_name="geospatial_aoi_notes")
    op.drop_index("ix_geospatial_aoi_notes_parent", table_name="geospatial_aoi_notes")
    op.drop_index("ix_geospatial_aoi_notes_type", table_name="geospatial_aoi_notes")
    op.drop_index("ix_geospatial_aoi_notes_aoi", table_name="geospatial_aoi_notes")
    op.drop_table("geospatial_aoi_notes")

    op.drop_index("ix_geospatial_aoi_favorites_pinned", table_name="geospatial_aoi_favorites")
    op.drop_index("ix_geospatial_aoi_favorites_user", table_name="geospatial_aoi_favorites")
    op.drop_index("ix_geospatial_aoi_favorites_aoi", table_name="geospatial_aoi_favorites")
    op.drop_table("geospatial_aoi_favorites")

    op.drop_index("ix_geospatial_aoi_metadata_public_token", table_name="geospatial_aoi_metadata")
    op.drop_index("ix_geospatial_aoi_metadata_watchlist", table_name="geospatial_aoi_metadata")
    op.drop_index("ix_geospatial_aoi_metadata_owner", table_name="geospatial_aoi_metadata")
    op.drop_index("ix_geospatial_aoi_metadata_aoi_id", table_name="geospatial_aoi_metadata")
    op.drop_table("geospatial_aoi_metadata")

    op.drop_index("ix_satellite_pipeline_runs_parent_run_id", table_name="satellite_pipeline_runs")
    op.drop_constraint("fk_satellite_pipeline_runs_parent_run", "satellite_pipeline_runs", type_="foreignkey")
    op.drop_column("satellite_pipeline_runs", "sla_target_minutes")
    op.drop_column("satellite_pipeline_runs", "scheduled_for")
    op.drop_column("satellite_pipeline_runs", "parent_run_id")
    op.drop_column("satellite_pipeline_runs", "queue_priority")
    op.drop_column("satellite_pipeline_runs", "retry_strategy")
    op.drop_column("satellite_pipeline_runs", "cancel_reason")
    op.drop_column("satellite_pipeline_runs", "operator_notes")
