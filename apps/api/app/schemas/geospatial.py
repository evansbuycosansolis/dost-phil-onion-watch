from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AOICreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=180)
    description: str | None = None
    scope_type: str = Field(default="custom", max_length=60)
    municipality_id: int | None = None
    warehouse_id: int | None = None
    market_id: int | None = None
    boundary_geojson: dict[str, Any]
    boundary_wkt: str | None = None
    source: str = Field(default="manual", max_length=80)
    change_reason: str | None = None


class AOIUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=80)
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = None
    scope_type: str | None = Field(default=None, max_length=60)
    municipality_id: int | None = None
    warehouse_id: int | None = None
    market_id: int | None = None
    boundary_geojson: dict[str, Any] | None = None
    boundary_wkt: str | None = None
    source: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None
    change_reason: str | None = None


class AOIDTO(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    scope_type: str
    municipality_id: int | None
    warehouse_id: int | None
    market_id: int | None
    srid: int
    boundary_geojson: dict[str, Any]
    boundary_wkt: str | None
    bbox_min_lng: float | None
    bbox_min_lat: float | None
    bbox_max_lng: float | None
    bbox_max_lat: float | None
    centroid_lng: float | None
    centroid_lat: float | None
    source: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AOIVersionDTO(BaseModel):
    id: int
    aoi_id: int
    version: int
    change_type: str
    boundary_geojson: dict[str, Any]
    boundary_wkt: str | None
    changed_by: int | None
    change_reason: str | None
    changed_at: datetime


class AOIMetadataDTO(BaseModel):
    aoi_id: int
    owner_user_id: int | None
    tags: list[str]
    labels: list[str]
    watchlist_flag: bool
    public_share_token: str | None
    metadata: dict[str, Any]


class AOIMetadataUpdateRequest(BaseModel):
    owner_user_id: int | None = None
    tags: list[str] | None = None
    labels: list[str] | None = None
    watchlist_flag: bool | None = None
    metadata: dict[str, Any] | None = None


class AOIFavoriteRequest(BaseModel):
    is_pinned: bool = True


class AOIBulkStatusRequest(BaseModel):
    aoi_ids: list[int] = Field(default_factory=list)
    is_active: bool
    change_reason: str | None = None


class AOIBulkImportRequest(BaseModel):
    feature_collection: dict[str, Any]
    default_scope_type: str = "custom"
    default_source: str = "bulk_import"


class AOINoteCreateRequest(BaseModel):
    note_type: Literal["note", "comment"] = "note"
    body: str = Field(min_length=1, max_length=5000)
    parent_note_id: int | None = None
    mentions: list[str] = Field(default_factory=list)
    assigned_user_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AOIAttachmentCreateRequest(BaseModel):
    asset_type: str = Field(default="photo", max_length=40)
    title: str = Field(min_length=2, max_length=180)
    url: str = Field(min_length=3, max_length=512)
    notes: str | None = None


class AOIDocumentLinkCreateRequest(BaseModel):
    document_id: int | None = None
    title: str = Field(min_length=2, max_length=180)
    url: str | None = Field(default=None, max_length=512)
    notes: str | None = None


class AOIVersionDiffResponse(BaseModel):
    aoi_id: int
    from_version: int
    to_version: int
    changes: list[dict[str, Any]]


class AOIAnalyticsResponse(BaseModel):
    aoi_id: int
    risk_score: float
    seasonality_summary: list[dict[str, Any]]
    cloud_coverage_trend: list[dict[str, Any]]
    vegetation_vigor_trend: list[dict[str, Any]]
    crop_activity_trend: list[dict[str, Any]]
    anomaly_sparkline: list[float]
    confidence_trend: list[dict[str, Any]]


class RunPriorityUpdateRequest(BaseModel):
    queue_priority: int = Field(ge=1, le=1000)


class RunNotesUpdateRequest(BaseModel):
    operator_notes: str = Field(min_length=1, max_length=5000)


class RunCloneRequest(BaseModel):
    notes: str | None = None
    queue_priority: int | None = Field(default=None, ge=1, le=1000)
    retry_strategy: str | None = Field(default=None, max_length=40)


class RunPresetCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    run_type: str = Field(min_length=2, max_length=60)
    description: str | None = None
    sources: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    retry_strategy: str = Field(default="standard", max_length=40)
    queue_priority: int = Field(default=100, ge=1, le=1000)


class RunPresetDTO(BaseModel):
    id: int
    name: str
    run_type: str
    description: str | None
    sources: list[str]
    parameters: dict[str, Any]
    retry_strategy: str
    queue_priority: int
    created_at: datetime


class RunScheduleCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    run_type: str = Field(min_length=2, max_length=60)
    aoi_id: int | None = None
    cron_expression: str = Field(min_length=3, max_length=80)
    timezone: str = Field(default="Asia/Manila", max_length=80)
    recurrence_template: str | None = Field(default=None, max_length=80)
    retry_strategy: str = Field(default="standard", max_length=40)
    queue_priority: int = Field(default=100, ge=1, le=1000)
    is_active: bool = True
    sources: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    notify_channels: list[str] = Field(default_factory=list)
    notes: str | None = None


class RunScheduleDTO(BaseModel):
    id: int
    name: str
    run_type: str
    aoi_id: int | None
    cron_expression: str
    timezone: str
    recurrence_template: str | None
    retry_strategy: str
    queue_priority: int
    is_active: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_run_status: str | None
    sources: list[str]
    parameters: dict[str, Any]
    notify_channels: list[str]
    notes: str | None


class FilterPresetCreateRequest(BaseModel):
    preset_type: Literal["scene", "feature"]
    name: str = Field(min_length=2, max_length=120)
    filters: dict[str, Any] = Field(default_factory=dict)


class FilterPresetDTO(BaseModel):
    id: int
    preset_type: str
    name: str
    filters: dict[str, Any]
    created_at: datetime


class RunCompareRequest(BaseModel):
    left_run_id: int
    right_run_id: int


class RunCompareResponse(BaseModel):
    left_run_id: int
    right_run_id: int
    metrics_summary: dict[str, Any]
    provenance_diff: dict[str, Any]
    scene_overlap_matrix: dict[str, Any]
    feature_overlap_matrix: dict[str, Any]
    parameter_delta: dict[str, Any]
    diff: dict[str, Any]


class GeospatialStatusDTO(BaseModel):
    postgis_enabled: bool
    postgis_version: str | None
    srid_default: int
    aoi_count: int
    active_aoi_count: int


class RunLineageResponse(BaseModel):
    root_run_id: int
    upstream_depth: int
    downstream_count: int
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class RunArtifactManifestResponse(BaseModel):
    run_id: int
    generated_at: str
    artifacts: list[dict[str, Any]]


class RunArtifactDownloadCenterResponse(BaseModel):
    run_id: int
    generated_at: str
    artifact_count: int
    total_size_bytes: int
    artifacts: list[dict[str, Any]]


class RunDependencyGraphResponse(BaseModel):
    root_run_id: int
    direction: Literal["upstream", "downstream"]
    depth: int
    node_count: int
    edge_count: int
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class RunReproducibilityResponse(BaseModel):
    run_id: int
    reference_run_id: int | None
    reference_reason: str | None
    badge: Literal["high", "medium", "low"]
    score: float
    diagnostics: list[dict[str, Any]]
    summary: dict[str, Any]


class GeospatialExecutiveDashboardResponse(BaseModel):
    as_of: str
    totals: dict[str, Any]
    monthly_run_trend: list[dict[str, Any]]
    top_anomaly_aois: list[dict[str, Any]]
    source_reliability: list[dict[str, Any]]
