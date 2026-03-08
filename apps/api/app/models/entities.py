from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class StakeholderOrganization(Base, TimestampMixin):
    __tablename__ = "stakeholder_organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_type: Mapped[str] = mapped_column(String(80), nullable=False)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True, index=True)


class Municipality(Base, TimestampMixin):
    __tablename__ = "municipalities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    province: Mapped[str] = mapped_column(String(120), default="Occidental Mindoro", nullable=False)
    region: Mapped[str] = mapped_column(String(120), default="MIMAROPA", nullable=False)


class Barangay(Base, TimestampMixin):
    __tablename__ = "barangays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class Market(Base, TimestampMixin):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    market_type: Mapped[str] = mapped_column(String(40), nullable=False)


class GeospatialAOI(Base, TimestampMixin):
    __tablename__ = "geospatial_aois"
    __table_args__ = (
        UniqueConstraint("code", name="uq_geospatial_aois_code"),
        Index("ix_geospatial_aois_scope_type", "scope_type"),
        Index("ix_geospatial_aois_municipality_id", "municipality_id"),
        Index("ix_geospatial_aois_warehouse_id", "warehouse_id"),
        Index("ix_geospatial_aois_market_id", "market_id"),
        Index("ix_geospatial_aois_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_type: Mapped[str] = mapped_column(String(60), default="custom", nullable=False)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True)
    srid: Mapped[int] = mapped_column(Integer, default=4326, nullable=False)
    boundary_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    boundary_wkt: Mapped[str | None] = mapped_column(Text, nullable=True)
    bbox_min_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_min_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_max_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_max_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class GeospatialAOIVersion(Base, TimestampMixin):
    __tablename__ = "geospatial_aoi_versions"
    __table_args__ = (
        UniqueConstraint("aoi_id", "version", name="uq_geospatial_aoi_versions_aoi_version"),
        Index("ix_geospatial_aoi_versions_aoi_id", "aoi_id"),
        Index("ix_geospatial_aoi_versions_changed_at", "changed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aoi_id: Mapped[int] = mapped_column(ForeignKey("geospatial_aois.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    change_type: Mapped[str] = mapped_column(String(40), default="create", nullable=False)
    boundary_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    boundary_wkt: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GeospatialAOIMetadata(Base, TimestampMixin):
    __tablename__ = "geospatial_aoi_metadata"
    __table_args__ = (
        UniqueConstraint("aoi_id", name="uq_geospatial_aoi_metadata_aoi_id"),
        Index("ix_geospatial_aoi_metadata_owner", "owner_user_id"),
        Index("ix_geospatial_aoi_metadata_watchlist", "watchlist_flag"),
        Index("ix_geospatial_aoi_metadata_public_token", "public_share_token"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aoi_id: Mapped[int] = mapped_column(ForeignKey("geospatial_aois.id"), nullable=False, index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    labels_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    watchlist_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    public_share_token: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class GeospatialAOIFavorite(Base, TimestampMixin):
    __tablename__ = "geospatial_aoi_favorites"
    __table_args__ = (
        UniqueConstraint("aoi_id", "user_id", name="uq_geospatial_aoi_favorites_aoi_user"),
        Index("ix_geospatial_aoi_favorites_user", "user_id"),
        Index("ix_geospatial_aoi_favorites_aoi", "aoi_id"),
        Index("ix_geospatial_aoi_favorites_pinned", "is_pinned"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aoi_id: Mapped[int] = mapped_column(ForeignKey("geospatial_aois.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pinned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GeospatialAOINote(Base, TimestampMixin):
    __tablename__ = "geospatial_aoi_notes"
    __table_args__ = (
        Index("ix_geospatial_aoi_notes_aoi", "aoi_id"),
        Index("ix_geospatial_aoi_notes_type", "note_type"),
        Index("ix_geospatial_aoi_notes_parent", "parent_note_id"),
        Index("ix_geospatial_aoi_notes_assigned", "assigned_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aoi_id: Mapped[int] = mapped_column(ForeignKey("geospatial_aois.id"), nullable=False, index=True)
    parent_note_id: Mapped[int | None] = mapped_column(ForeignKey("geospatial_aoi_notes.id"), nullable=True, index=True)
    note_type: Mapped[str] = mapped_column(String(40), default="note", nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class GeospatialAOIAttachment(Base, TimestampMixin):
    __tablename__ = "geospatial_aoi_attachments"
    __table_args__ = (
        Index("ix_geospatial_aoi_attachments_aoi", "aoi_id"),
        Index("ix_geospatial_aoi_attachments_type", "asset_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aoi_id: Mapped[int] = mapped_column(ForeignKey("geospatial_aois.id"), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(40), default="photo", nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class GeospatialAOIDocumentLink(Base, TimestampMixin):
    __tablename__ = "geospatial_aoi_document_links"
    __table_args__ = (
        Index("ix_geospatial_aoi_document_links_aoi", "aoi_id"),
        Index("ix_geospatial_aoi_document_links_document", "document_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aoi_id: Mapped[int] = mapped_column(ForeignKey("geospatial_aois.id"), nullable=False, index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SatellitePipelineRun(Base, TimestampMixin):
    __tablename__ = "satellite_pipeline_runs"
    __table_args__ = (
        Index("ix_satellite_pipeline_runs_started_at", "started_at"),
        Index("ix_satellite_pipeline_runs_status", "status"),
        Index("ix_satellite_pipeline_runs_run_type", "run_type"),
        Index("ix_satellite_pipeline_runs_aoi_id", "aoi_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_type: Mapped[str] = mapped_column(String(60), nullable=False)
    backend: Mapped[str] = mapped_column(String(40), default="gee", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    algorithm_version: Mapped[str] = mapped_column(String(40), default="1.0", nullable=False)
    aoi_id: Mapped[int | None] = mapped_column(ForeignKey("geospatial_aois.id"), nullable=True)
    sources_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    results_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_strategy: Mapped[str] = mapped_column(String(40), default="standard", nullable=False)
    queue_priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    parent_run_id: Mapped[int | None] = mapped_column(ForeignKey("satellite_pipeline_runs.id"), nullable=True, index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sla_target_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SatelliteScene(Base, TimestampMixin):
    __tablename__ = "satellite_scenes"
    __table_args__ = (
        UniqueConstraint("source", "scene_id", name="uq_satellite_scenes_source_scene_id"),
        Index("ix_satellite_scenes_acquired_at", "acquired_at"),
        Index("ix_satellite_scenes_aoi_id", "aoi_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    scene_id: Mapped[str] = mapped_column(String(180), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    aoi_id: Mapped[int | None] = mapped_column(ForeignKey("geospatial_aois.id"), nullable=True)
    cloud_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    spatial_resolution_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bands_available: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    footprint_geojson: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(40), default="discovered", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class GeospatialFeature(Base, TimestampMixin):
    __tablename__ = "geospatial_features"
    __table_args__ = (
        Index("ix_geospatial_features_aoi_date", "aoi_id", "observation_date"),
        Index("ix_geospatial_features_reporting_month", "reporting_month"),
        Index("ix_geospatial_features_source", "source"),
        Index("ix_geospatial_features_processing_run_id", "processing_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aoi_id: Mapped[int] = mapped_column(ForeignKey("geospatial_aois.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    cloud_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    ndvi_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    evi_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndwi_mean: Mapped[float | None] = mapped_column(Float, nullable=True)

    radar_backscatter_vv: Mapped[float | None] = mapped_column(Float, nullable=True)
    radar_backscatter_vh: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    vegetation_vigor_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_activity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    observation_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    processing_run_id: Mapped[int | None] = mapped_column(ForeignKey("satellite_pipeline_runs.id"), nullable=True)
    features_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    quality_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class GeospatialRunEvent(Base, TimestampMixin):
    __tablename__ = "geospatial_run_events"
    __table_args__ = (
        Index("ix_geospatial_run_events_run", "run_id"),
        Index("ix_geospatial_run_events_phase", "phase"),
        Index("ix_geospatial_run_events_logged_at", "logged_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("satellite_pipeline_runs.id"), nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GeospatialRunPreset(Base, TimestampMixin):
    __tablename__ = "geospatial_run_presets"
    __table_args__ = (
        UniqueConstraint("name", "created_by", name="uq_geospatial_run_presets_name_owner"),
        Index("ix_geospatial_run_presets_run_type", "run_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    run_type: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    retry_strategy: Mapped[str] = mapped_column(String(40), default="standard", nullable=False)
    queue_priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)


class GeospatialRunSchedule(Base, TimestampMixin):
    __tablename__ = "geospatial_run_schedules"
    __table_args__ = (
        Index("ix_geospatial_run_schedules_active", "is_active"),
        Index("ix_geospatial_run_schedules_next_run", "next_run_at"),
        Index("ix_geospatial_run_schedules_run_type", "run_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    run_type: Mapped[str] = mapped_column(String(60), nullable=False)
    aoi_id: Mapped[int | None] = mapped_column(ForeignKey("geospatial_aois.id"), nullable=True, index=True)
    cron_expression: Mapped[str] = mapped_column(String(80), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Manila", nullable=False)
    recurrence_template: Mapped[str | None] = mapped_column(String(80), nullable=True)
    retry_strategy: Mapped[str] = mapped_column(String(40), default="standard", nullable=False)
    queue_priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sources_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    notify_channels_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class GeospatialFilterPreset(Base, TimestampMixin):
    __tablename__ = "geospatial_filter_presets"
    __table_args__ = (
        UniqueConstraint("user_id", "preset_type", "name", name="uq_geospatial_filter_presets_user_type_name"),
        Index("ix_geospatial_filter_presets_user", "user_id"),
        Index("ix_geospatial_filter_presets_type", "preset_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    preset_type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    filters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class GeospatialRolloutWave(Base, TimestampMixin):
    __tablename__ = "geospatial_rollout_waves"
    __table_args__ = (
        UniqueConstraint("wave_number", "region_scope", name="uq_geospatial_rollout_waves_number_region"),
        Index("ix_geospatial_rollout_waves_gate_status", "gate_status"),
        Index("ix_geospatial_rollout_waves_owner", "owner_user_id"),
        Index("ix_geospatial_rollout_waves_dates", "start_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    wave_number: Mapped[int] = mapped_column(Integer, nullable=False)
    region_scope: Mapped[str] = mapped_column(String(180), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reviewer_ids_json: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    gate_status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    gate_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pass_fail_criteria_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class GeospatialKpiScorecard(Base, TimestampMixin):
    __tablename__ = "geospatial_kpi_scorecards"
    __table_args__ = (
        UniqueConstraint("period_month", "region_scope", name="uq_geospatial_kpi_scorecards_period_scope"),
        Index("ix_geospatial_kpi_scorecards_period", "period_month"),
        Index("ix_geospatial_kpi_scorecards_status", "computed_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    region_scope: Mapped[str] = mapped_column(String(180), nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    thresholds_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    computed_status: Mapped[str] = mapped_column(String(20), default="yellow", nullable=False)
    source_pointers_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class GeospatialIncident(Base, TimestampMixin):
    __tablename__ = "geospatial_incidents"
    __table_args__ = (
        UniqueConstraint("incident_key", name="uq_geospatial_incidents_incident_key"),
        Index("ix_geospatial_incidents_severity", "severity"),
        Index("ix_geospatial_incidents_status", "status"),
        Index("ix_geospatial_incidents_started_at", "started_at"),
        Index("ix_geospatial_incidents_assigned_to", "assigned_to_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_key: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="SEV3", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    mitigated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_actions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    evidence_pack_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    comms_log_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    slo_target_minutes: Mapped[int] = mapped_column(Integer, default=240, nullable=False)
    postmortem_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class GeospatialValidationRun(Base, TimestampMixin):
    __tablename__ = "geospatial_validation_runs"
    __table_args__ = (
        UniqueConstraint("run_key", name="uq_geospatial_validation_runs_run_key"),
        Index("ix_geospatial_validation_runs_status", "status"),
        Index("ix_geospatial_validation_runs_scope", "scope"),
        Index("ix_geospatial_validation_runs_signoff", "signoff_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(180), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    threshold_set_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="planned", nullable=False)
    executed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    signoff_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    results_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_links_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class GeospatialValidationTestcase(Base, TimestampMixin):
    __tablename__ = "geospatial_validation_testcases"
    __table_args__ = (
        UniqueConstraint("code", name="uq_geospatial_validation_testcases_code"),
        Index("ix_geospatial_validation_testcases_category", "category"),
        Index("ix_geospatial_validation_testcases_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class GeospatialValidationResult(Base, TimestampMixin):
    __tablename__ = "geospatial_validation_results"
    __table_args__ = (
        UniqueConstraint("run_id", "testcase_id", name="uq_geospatial_validation_results_run_case"),
        Index("ix_geospatial_validation_results_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("geospatial_validation_runs.id"), nullable=False, index=True)
    testcase_id: Mapped[int] = mapped_column(ForeignKey("geospatial_validation_testcases.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="skip", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GeospatialRiskItem(Base, TimestampMixin):
    __tablename__ = "geospatial_risk_items"
    __table_args__ = (
        UniqueConstraint("risk_key", name="uq_geospatial_risk_items_risk_key"),
        Index("ix_geospatial_risk_items_status", "status"),
        Index("ix_geospatial_risk_items_owner", "owner_user_id"),
        Index("ix_geospatial_risk_items_next_review", "next_review_date"),
        Index("ix_geospatial_risk_items_target_close", "target_close_date"),
        Index("ix_geospatial_risk_items_escalation", "escalation_level"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    risk_key: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    likelihood: Mapped[int] = mapped_column(Integer, nullable=False)
    impact: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[str | None] = mapped_column(Text, nullable=True)
    mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    board_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class GeospatialOpsTask(Base, TimestampMixin):
    __tablename__ = "geospatial_ops_tasks"
    __table_args__ = (
        Index("ix_geospatial_ops_tasks_status_due", "status", "due_at"),
        Index("ix_geospatial_ops_tasks_type", "task_type"),
        Index("ix_geospatial_ops_tasks_assignee", "assigned_to_user_id"),
        Index("ix_geospatial_ops_tasks_related", "related_entity_type", "related_entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    related_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    related_entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notification_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Warehouse(Base, TimestampMixin):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    capacity_tons: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ColdStorageFacility(Base, TimestampMixin):
    __tablename__ = "cold_storage_facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    capacity_tons: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(40), default="local", nullable=False)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    last_mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("stakeholder_organizations.id"), nullable=True, index=True)


class UserRole(Base, TimestampMixin):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)


class FarmerProfile(Base, TimestampMixin):
    __tablename__ = "farmer_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    barangay_id: Mapped[int | None] = mapped_column(ForeignKey("barangays.id"), nullable=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("stakeholder_organizations.id"), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(40), nullable=True)


class FarmLocation(Base, TimestampMixin):
    __tablename__ = "farm_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmer_profiles.id"), nullable=False, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    barangay_id: Mapped[int | None] = mapped_column(ForeignKey("barangays.id"), nullable=True)
    area_hectares: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)


class PlantingRecord(Base, TimestampMixin):
    __tablename__ = "planting_records"
    __table_args__ = (Index("ix_planting_records_expected_harvest_month", "expected_harvest_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmer_profiles.id"), nullable=False, index=True)
    farm_location_id: Mapped[int] = mapped_column(ForeignKey("farm_locations.id"), nullable=False, index=True)
    planting_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_harvest_month: Mapped[date] = mapped_column(Date, nullable=False)
    variety: Mapped[str] = mapped_column(String(80), nullable=False)
    area_hectares: Mapped[float] = mapped_column(Float, nullable=False)


class HarvestReport(Base, TimestampMixin):
    __tablename__ = "harvest_reports"
    __table_args__ = (
        Index("ix_harvest_reports_reporting_month", "reporting_month"),
        Index("ix_harvest_reports_municipality_reporting", "municipality_id", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int | None] = mapped_column(ForeignKey("farmer_profiles.id"), nullable=True, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    harvest_date: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    quality_grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="submitted", nullable=False)


class YieldEstimate(Base, TimestampMixin):
    __tablename__ = "yield_estimates"
    __table_args__ = (
        Index("ix_yield_estimates_reporting_month", "reporting_month"),
        Index("ix_yield_estimates_municipality_reporting", "municipality_id", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    estimated_yield_tons: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class WarehouseStockReport(Base, TimestampMixin):
    __tablename__ = "warehouse_stock_reports"
    __table_args__ = (
        Index("ix_warehouse_stock_reports_reporting_month", "reporting_month"),
        Index("ix_warehouse_stock_reports_warehouse_reporting", "warehouse_id", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_stock_tons: Mapped[float] = mapped_column(Float, nullable=False)
    inflow_tons: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    outflow_tons: Mapped[float] = mapped_column(Float, default=0, nullable=False)


class ColdStorageStockReport(Base, TimestampMixin):
    __tablename__ = "cold_storage_stock_reports"
    __table_args__ = (
        Index("ix_cold_storage_stock_reports_reporting_month", "reporting_month"),
        Index("ix_cold_storage_stock_reports_facility_reporting", "cold_storage_facility_id", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cold_storage_facility_id: Mapped[int] = mapped_column(ForeignKey("cold_storage_facilities.id"), nullable=False, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_stock_tons: Mapped[float] = mapped_column(Float, nullable=False)
    utilization_pct: Mapped[float] = mapped_column(Float, nullable=False)


class StockReleaseLog(Base, TimestampMixin):
    __tablename__ = "stock_release_logs"
    __table_args__ = (Index("ix_stock_release_logs_reporting_month", "reporting_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False, index=True)
    release_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    destination_market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TransportLog(Base, TimestampMixin):
    __tablename__ = "transport_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False, index=True)
    destination_market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    transport_date: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    vehicle_plate: Mapped[str | None] = mapped_column(String(40), nullable=True)


class DistributionLog(Base, TimestampMixin):
    __tablename__ = "distribution_logs"
    __table_args__ = (Index("ix_distribution_logs_reporting_month", "reporting_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    distribution_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)


class FarmgatePriceReport(Base, TimestampMixin):
    __tablename__ = "farmgate_price_reports"
    __table_args__ = (
        Index("ix_farmgate_price_reports_report_date", "report_date"),
        Index("ix_farmgate_price_reports_reporting_month", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    price_per_kg: Mapped[float] = mapped_column(Float, nullable=False)


class WholesalePriceReport(Base, TimestampMixin):
    __tablename__ = "wholesale_price_reports"
    __table_args__ = (
        Index("ix_wholesale_price_reports_report_date", "report_date"),
        Index("ix_wholesale_price_reports_reporting_month", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    price_per_kg: Mapped[float] = mapped_column(Float, nullable=False)


class RetailPriceReport(Base, TimestampMixin):
    __tablename__ = "retail_price_reports"
    __table_args__ = (
        Index("ix_retail_price_reports_report_date", "report_date"),
        Index("ix_retail_price_reports_reporting_month", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    price_per_kg: Mapped[float] = mapped_column(Float, nullable=False)


class DemandEstimate(Base, TimestampMixin):
    __tablename__ = "demand_estimates"
    __table_args__ = (Index("ix_demand_estimates_reporting_month", "reporting_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    demand_tons: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(80), nullable=False)


class ImportRecord(Base, TimestampMixin):
    __tablename__ = "import_records"
    __table_args__ = (
        Index("ix_import_records_arrival_date", "arrival_date"),
        Index("ix_import_records_reporting_month", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_reference: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    origin_country: Mapped[str] = mapped_column(String(80), nullable=False)
    arrival_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)


class ShipmentArrival(Base, TimestampMixin):
    __tablename__ = "shipment_arrivals"
    __table_args__ = (Index("ix_shipment_arrivals_arrival_date", "arrival_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_record_id: Mapped[int] = mapped_column(ForeignKey("import_records.id"), nullable=False, index=True)
    port_name: Mapped[str] = mapped_column(String(120), nullable=False)
    arrival_date: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    inspection_status: Mapped[str] = mapped_column(String(40), nullable=False)


class InspectionNote(Base, TimestampMixin):
    __tablename__ = "inspection_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_arrival_id: Mapped[int] = mapped_column(ForeignKey("shipment_arrivals.id"), nullable=False, index=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)


class InterventionAction(Base, TimestampMixin):
    __tablename__ = "intervention_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True, index=True)
    action_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)


class ForecastRun(Base, TimestampMixin):
    __tablename__ = "forecast_runs"
    __table_args__ = (Index("ix_forecast_runs_run_month", "run_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    run_month: Mapped[date] = mapped_column(Date, nullable=False)
    model_used: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ForecastOutput(Base, TimestampMixin):
    __tablename__ = "forecast_outputs"
    __table_args__ = (
        Index("ix_forecast_outputs_period_start", "period_start"),
        Index("ix_forecast_outputs_municipality_period", "municipality_id", "period_start"),
        Index("ix_forecast_outputs_selected_model", "selected_model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    forecast_run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"), nullable=False, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    next_month_supply_tons: Mapped[float] = mapped_column(Float, nullable=False)
    next_quarter_trend: Mapped[float] = mapped_column(Float, nullable=False)
    shortage_probability: Mapped[float] = mapped_column(Float, nullable=False)
    oversupply_probability: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    error_mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    selected_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    selected_model_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fallback_order_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    selection_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ForecastModelMetric(Base, TimestampMixin):
    __tablename__ = "forecast_model_metrics"
    __table_args__ = (
        Index("ix_forecast_model_metrics_run_muni", "forecast_run_id", "municipality_id"),
        Index("ix_forecast_model_metrics_model_name", "model_name"),
        Index("ix_forecast_model_metrics_selected", "selected"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    forecast_run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"), nullable=False, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_family: Mapped[str] = mapped_column(String(40), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    prediction_next_month: Mapped[float | None] = mapped_column(Float, nullable=True)
    holdout_actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    holdout_prediction: Mapped[float | None] = mapped_column(Float, nullable=True)
    holdout_mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    holdout_mape: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fallback_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AnomalyEvent(Base, TimestampMixin):
    __tablename__ = "anomaly_events"
    __table_args__ = (
        Index("ix_anomaly_events_reporting_month", "reporting_month"),
        Index("ix_anomaly_events_severity", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True, index=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)


class AnomalyThresholdConfig(Base, TimestampMixin):
    __tablename__ = "anomaly_threshold_configs"
    __table_args__ = (
        UniqueConstraint("anomaly_type", name="uq_anomaly_threshold_configs_anomaly_type"),
        Index("ix_anomaly_threshold_configs_type", "anomaly_type"),
        Index("ix_anomaly_threshold_configs_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anomaly_type: Mapped[str] = mapped_column(String(80), nullable=False)
    thresholds_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class AnomalyThresholdVersion(Base, TimestampMixin):
    __tablename__ = "anomaly_threshold_versions"
    __table_args__ = (
        UniqueConstraint("config_id", "version", name="uq_anomaly_threshold_versions_config_version"),
        Index("ix_anomaly_threshold_versions_type", "anomaly_type"),
        Index("ix_anomaly_threshold_versions_changed_at", "changed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("anomaly_threshold_configs.id"), nullable=False, index=True)
    anomaly_type: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    thresholds_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class RiskScore(Base, TimestampMixin):
    __tablename__ = "risk_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anomaly_event_id: Mapped[int | None] = mapped_column(ForeignKey("anomaly_events.id"), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(60), nullable=False)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True, index=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    linked_forecast_id: Mapped[int | None] = mapped_column(ForeignKey("forecast_outputs.id"), nullable=True)
    linked_anomaly_id: Mapped[int | None] = mapped_column(ForeignKey("anomaly_events.id"), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AlertAcknowledgement(Base, TimestampMixin):
    __tablename__ = "alert_acknowledgements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_action_type", "action_type"),
        Index("ix_audit_logs_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    before_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class DataCorrection(Base, TimestampMixin):
    __tablename__ = "data_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_name: Mapped[str] = mapped_column(String(120), nullable=False)
    record_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    old_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class SourceSubmission(Base, TimestampMixin):
    __tablename__ = "source_submissions"
    __table_args__ = (
        UniqueConstraint("source_name", "idempotency_key", name="uq_source_submissions_source_idempotency"),
        Index("ix_source_submissions_status", "status"),
        Index("ix_source_submissions_sync_batch_id", "sync_batch_id"),
        Index("ix_source_submissions_device_id", "device_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_channel: Mapped[str] = mapped_column(String(40), default="api", nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sync_batch_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_entity_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    conflict_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ApprovalWorkflow(Base, TimestampMixin):
    __tablename__ = "approval_workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_status", "status"),
        Index("ix_documents_index_status", "index_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="uploaded", nullable=False)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    index_status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentChunk(Base, TimestampMixin):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_chunk_index"),
        Index("ix_document_chunks_status", "status"),
        Index("ix_document_chunks_document_status", "document_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_vector: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class DocumentIndexRun(Base, TimestampMixin):
    __tablename__ = "document_index_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    num_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class DocumentIngestionJob(Base, TimestampMixin):
    __tablename__ = "document_ingestion_jobs"
    __table_args__ = (
        Index("ix_document_ingestion_jobs_status", "status"),
        Index("ix_document_ingestion_jobs_document", "document_id"),
        Index("ix_document_ingestion_jobs_queued_at", "queued_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class JobRun(Base, TimestampMixin):
    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_correlation_id", "correlation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ReportRecord(Base, TimestampMixin):
    __tablename__ = "report_records"
    __table_args__ = (Index("ix_report_records_reporting_month", "reporting_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="generated", nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ReportRecipientGroup(Base, TimestampMixin):
    __tablename__ = "report_recipient_groups"
    __table_args__ = (
        Index("ix_report_recipient_groups_active", "is_active"),
        Index("ix_report_recipient_groups_category", "report_category"),
        Index("ix_report_recipient_groups_role", "role_name"),
        Index("ix_report_recipient_groups_organization", "organization_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    role_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("stakeholder_organizations.id"), nullable=True, index=True)
    delivery_channel: Mapped[str] = mapped_column(String(40), default="file_drop", nullable=False)
    export_format: Mapped[str] = mapped_column(String(10), default="pdf", nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    retry_backoff_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    notify_on_failure: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ReportDeliveryLog(Base, TimestampMixin):
    __tablename__ = "report_delivery_logs"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "recipient_group_id",
            "recipient_user_id",
            "export_format",
            name="uq_report_delivery_logs_report_group_user_format",
        ),
        Index("ix_report_delivery_logs_status_next_attempt", "status", "next_attempt_at"),
        Index("ix_report_delivery_logs_report", "report_id"),
        Index("ix_report_delivery_logs_recipient_user", "recipient_user_id"),
        Index("ix_report_delivery_logs_dispatched_at", "dispatched_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report_records.id"), nullable=False, index=True)
    recipient_group_id: Mapped[int] = mapped_column(ForeignKey("report_recipient_groups.id"), nullable=False, index=True)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    recipient_email: Mapped[str] = mapped_column(String(120), nullable=False)
    recipient_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recipient_organization_id: Mapped[int | None] = mapped_column(ForeignKey("stakeholder_organizations.id"), nullable=True, index=True)
    delivery_channel: Mapped[str] = mapped_column(String(40), nullable=False)
    export_format: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    notification_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
