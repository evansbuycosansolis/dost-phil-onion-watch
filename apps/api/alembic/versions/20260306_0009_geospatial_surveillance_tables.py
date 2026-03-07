"""geospatial surveillance tables

Revision ID: 20260306_0009
Revises: 20260306_0008
Create Date: 2026-03-06

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260306_0009"
down_revision = "20260306_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "satellite_pipeline_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_type", sa.String(length=60), nullable=False),
        sa.Column("backend", sa.String(length=40), nullable=False, server_default="gee"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("triggered_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("correlation_id", sa.String(length=80), nullable=True),
        sa.Column("algorithm_version", sa.String(length=40), nullable=False, server_default="1.0"),
        sa.Column("aoi_id", sa.Integer(), sa.ForeignKey("geospatial_aois.id"), nullable=True),
        sa.Column("sources_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("parameters_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("results_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_satellite_pipeline_runs_started_at", "satellite_pipeline_runs", ["started_at"], unique=False)
    op.create_index("ix_satellite_pipeline_runs_status", "satellite_pipeline_runs", ["status"], unique=False)
    op.create_index("ix_satellite_pipeline_runs_run_type", "satellite_pipeline_runs", ["run_type"], unique=False)
    op.create_index("ix_satellite_pipeline_runs_aoi_id", "satellite_pipeline_runs", ["aoi_id"], unique=False)
    op.create_index("ix_satellite_pipeline_runs_triggered_by", "satellite_pipeline_runs", ["triggered_by"], unique=False)
    op.create_index("ix_satellite_pipeline_runs_correlation_id", "satellite_pipeline_runs", ["correlation_id"], unique=False)

    op.create_table(
        "satellite_scenes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("scene_id", sa.String(length=180), nullable=False),
        sa.Column("acquired_at", sa.DateTime(), nullable=False),
        sa.Column("aoi_id", sa.Integer(), sa.ForeignKey("geospatial_aois.id"), nullable=True),
        sa.Column("cloud_score", sa.Float(), nullable=True),
        sa.Column("spatial_resolution_m", sa.Integer(), nullable=True),
        sa.Column("bands_available", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("footprint_geojson", sa.JSON(), nullable=True),
        sa.Column("processing_status", sa.String(length=40), nullable=False, server_default="discovered"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("source", "scene_id", name="uq_satellite_scenes_source_scene_id"),
    )
    op.create_index("ix_satellite_scenes_acquired_at", "satellite_scenes", ["acquired_at"], unique=False)
    op.create_index("ix_satellite_scenes_aoi_id", "satellite_scenes", ["aoi_id"], unique=False)

    op.create_table(
        "geospatial_features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("aoi_id", sa.Integer(), sa.ForeignKey("geospatial_aois.id"), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("reporting_month", sa.Date(), nullable=True),
        sa.Column("cloud_score", sa.Float(), nullable=True),
        sa.Column("ndvi_mean", sa.Float(), nullable=True),
        sa.Column("evi_mean", sa.Float(), nullable=True),
        sa.Column("ndwi_mean", sa.Float(), nullable=True),
        sa.Column("radar_backscatter_vv", sa.Float(), nullable=True),
        sa.Column("radar_backscatter_vh", sa.Float(), nullable=True),
        sa.Column("change_score", sa.Float(), nullable=True),
        sa.Column("vegetation_vigor_score", sa.Float(), nullable=True),
        sa.Column("crop_activity_score", sa.Float(), nullable=True),
        sa.Column("observation_confidence_score", sa.Float(), nullable=True),
        sa.Column("processing_run_id", sa.Integer(), sa.ForeignKey("satellite_pipeline_runs.id"), nullable=True),
        sa.Column("features_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("quality_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_geospatial_features_aoi_date", "geospatial_features", ["aoi_id", "observation_date"], unique=False)
    op.create_index("ix_geospatial_features_reporting_month", "geospatial_features", ["reporting_month"], unique=False)
    op.create_index("ix_geospatial_features_source", "geospatial_features", ["source"], unique=False)
    op.create_index("ix_geospatial_features_processing_run_id", "geospatial_features", ["processing_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_geospatial_features_processing_run_id", table_name="geospatial_features")
    op.drop_index("ix_geospatial_features_source", table_name="geospatial_features")
    op.drop_index("ix_geospatial_features_reporting_month", table_name="geospatial_features")
    op.drop_index("ix_geospatial_features_aoi_date", table_name="geospatial_features")
    op.drop_table("geospatial_features")

    op.drop_index("ix_satellite_scenes_aoi_id", table_name="satellite_scenes")
    op.drop_index("ix_satellite_scenes_acquired_at", table_name="satellite_scenes")
    op.drop_table("satellite_scenes")

    op.drop_index("ix_satellite_pipeline_runs_correlation_id", table_name="satellite_pipeline_runs")
    op.drop_index("ix_satellite_pipeline_runs_triggered_by", table_name="satellite_pipeline_runs")
    op.drop_index("ix_satellite_pipeline_runs_aoi_id", table_name="satellite_pipeline_runs")
    op.drop_index("ix_satellite_pipeline_runs_run_type", table_name="satellite_pipeline_runs")
    op.drop_index("ix_satellite_pipeline_runs_status", table_name="satellite_pipeline_runs")
    op.drop_index("ix_satellite_pipeline_runs_started_at", table_name="satellite_pipeline_runs")
    op.drop_table("satellite_pipeline_runs")
