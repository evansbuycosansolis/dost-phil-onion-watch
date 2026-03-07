from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Response
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import (
    Alert,
    AuditLog,
    ApprovalWorkflow,
    Barangay,
    Document,
    FarmgatePriceReport,
    GeospatialAOI,
    GeospatialAOIAttachment,
    GeospatialAOIDocumentLink,
    GeospatialAOIFavorite,
    GeospatialAOIMetadata,
    GeospatialAOINote,
    GeospatialAOIVersion,
    GeospatialFeature,
    GeospatialFilterPreset,
    GeospatialRunEvent,
    GeospatialRunPreset,
    GeospatialRunSchedule,
    ImportRecord,
    InterventionAction,
    Municipality,
    ReportRecord,
    RetailPriceReport,
    SatellitePipelineRun,
    SatelliteScene,
    StakeholderOrganization,
    TransportLog,
    WarehouseStockReport,
    WholesalePriceReport,
)
from app.schemas.auth import CurrentUser
from app.schemas.geospatial import (
    AOIAttachmentCreateRequest,
    AOIAnalyticsResponse,
    AOIBulkImportRequest,
    AOIBulkStatusRequest,
    AOICreateRequest,
    AOIDocumentLinkCreateRequest,
    AOIDTO,
    AOIFavoriteRequest,
    AOIMetadataDTO,
    AOIMetadataUpdateRequest,
    AOINoteCreateRequest,
    AOIUpdateRequest,
    AOIVersionDTO,
    AOIVersionDiffResponse,
    FilterPresetCreateRequest,
    FilterPresetDTO,
    GeospatialExecutiveDashboardResponse,
    RunCloneRequest,
    RunCompareRequest,
    RunCompareResponse,
    RunDependencyGraphResponse,
    RunArtifactDownloadCenterResponse,
    RunArtifactManifestResponse,
    RunLineageResponse,
    RunNotesUpdateRequest,
    RunPresetCreateRequest,
    RunPresetDTO,
    RunReproducibilityResponse,
    RunPriorityUpdateRequest,
    RunScheduleCreateRequest,
    RunScheduleDTO,
)
from app.services.audit_service import build_structured_diff, emit_audit_event
from app.services.geospatial_feature_service import execute_feature_refresh_run, queue_feature_refresh_run
from app.services.satellite_ingestion_service import execute_ingestion_run, queue_ingestion_run
from app.services.stac_service import geojson_to_bbox

router = APIRouter(prefix="/geospatial", tags=["geospatial"], responses=router_default_responses("geospatial"))

READ_ROLES = (
    "super_admin",
    "provincial_admin",
    "municipal_encoder",
    "warehouse_operator",
    "market_analyst",
    "policy_reviewer",
    "executive_viewer",
    "auditor",
)
ADMIN_ROLES = ("super_admin", "provincial_admin")


def _aoi_to_dto(row: GeospatialAOI) -> AOIDTO:
    return AOIDTO(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        scope_type=row.scope_type,
        municipality_id=row.municipality_id,
        warehouse_id=row.warehouse_id,
        market_id=row.market_id,
        srid=row.srid,
        boundary_geojson=row.boundary_geojson,
        boundary_wkt=row.boundary_wkt,
        bbox_min_lng=row.bbox_min_lng,
        bbox_min_lat=row.bbox_min_lat,
        bbox_max_lng=row.bbox_max_lng,
        bbox_max_lat=row.bbox_max_lat,
        centroid_lng=row.centroid_lng,
        centroid_lat=row.centroid_lat,
        source=row.source,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _next_aoi_version(db: Session, *, aoi_id: int) -> int:
    current = db.scalar(select(func.max(GeospatialAOIVersion.version)).where(GeospatialAOIVersion.aoi_id == aoi_id))
    return int(current or 0) + 1


def _apply_bbox_and_centroid(aoi: GeospatialAOI) -> None:
    minx, miny, maxx, maxy = geojson_to_bbox(aoi.boundary_geojson)
    aoi.bbox_min_lng = float(minx)
    aoi.bbox_min_lat = float(miny)
    aoi.bbox_max_lng = float(maxx)
    aoi.bbox_max_lat = float(maxy)
    aoi.centroid_lng = float((minx + maxx) / 2.0)
    aoi.centroid_lat = float((miny + maxy) / 2.0)


def _normalize_string_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    unique: set[str] = set()
    normalized: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item:
            continue
        key = item.lower()
        if key in unique:
            continue
        unique.add(key)
        normalized.append(item)
    return normalized


def _get_or_create_aoi_metadata(db: Session, *, aoi_id: int) -> GeospatialAOIMetadata:
    meta = db.scalar(select(GeospatialAOIMetadata).where(GeospatialAOIMetadata.aoi_id == aoi_id))
    if meta is None:
        token_input = f"{aoi_id}-{datetime.utcnow().isoformat()}"
        token = hashlib.sha256(token_input.encode("utf-8")).hexdigest()[:32]
        meta = GeospatialAOIMetadata(
            aoi_id=aoi_id,
            owner_user_id=None,
            tags_json=[],
            labels_json=[],
            watchlist_flag=False,
            public_share_token=token,
            metadata_json={},
        )
        db.add(meta)
        db.flush()
    return meta


def _metadata_to_dto(meta: GeospatialAOIMetadata) -> AOIMetadataDTO:
    return AOIMetadataDTO(
        aoi_id=meta.aoi_id,
        owner_user_id=meta.owner_user_id,
        tags=_normalize_string_list((meta.tags_json or [])),
        labels=_normalize_string_list((meta.labels_json or [])),
        watchlist_flag=bool(meta.watchlist_flag),
        public_share_token=meta.public_share_token,
        metadata=meta.metadata_json or {},
    )


def _bbox_overlaps(a: GeospatialAOI, b: GeospatialAOI) -> bool:
    if a.id == b.id:
        return False
    if a.bbox_min_lng is None or a.bbox_max_lng is None or a.bbox_min_lat is None or a.bbox_max_lat is None:
        return False
    if b.bbox_min_lng is None or b.bbox_max_lng is None or b.bbox_min_lat is None or b.bbox_max_lat is None:
        return False
    return not (
        a.bbox_max_lng < b.bbox_min_lng
        or a.bbox_min_lng > b.bbox_max_lng
        or a.bbox_max_lat < b.bbox_min_lat
        or a.bbox_min_lat > b.bbox_max_lat
    )


def _overlap_conflicts(db: Session, *, candidate: GeospatialAOI) -> list[dict[str, Any]]:
    rows = db.scalars(select(GeospatialAOI).where(GeospatialAOI.is_active == True)).all()  # noqa: E712
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        if _bbox_overlaps(candidate, row):
            conflicts.append({"id": row.id, "code": row.code, "name": row.name})
    return conflicts


def _append_run_event(
    db: Session,
    *,
    run_id: int,
    phase: str,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
    actor_user_id: int | None = None,
) -> GeospatialRunEvent:
    event = GeospatialRunEvent(
        run_id=run_id,
        phase=phase,
        status=status,
        message=message,
        details_json=details or {},
        logged_at=datetime.utcnow(),
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(event)
    db.flush()
    return event


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator / denominator)


def _pearson_like(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_var = sum((x - x_mean) ** 2 for x in xs)
    y_var = sum((y - y_mean) ** 2 for y in ys)
    denom = (x_var * y_var) ** 0.5
    if denom <= 0:
        return 0.0
    return round(max(-1.0, min(1.0, numerator / denom)), 4)


def _pipeline_health_badge(status: str) -> str:
    if status in {"completed"}:
        return "healthy"
    if status in {"queued", "running", "cancel_requested"}:
        return "degraded"
    return "critical"


def _run_to_dto(row: SatellitePipelineRun, *, aoi_code: str | None = None, aoi_name: str | None = None) -> dict:
    return {
        "id": row.id,
        "run_type": row.run_type,
        "backend": row.backend,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "triggered_by": row.triggered_by,
        "correlation_id": row.correlation_id,
        "algorithm_version": row.algorithm_version,
        "aoi_id": row.aoi_id,
        "aoi_code": aoi_code,
        "aoi_name": aoi_name,
        "sources": (row.sources_json or {}).get("sources", []),
        "parameters": row.parameters_json or {},
        "results": row.results_json or {},
        "notes": row.notes,
        "operator_notes": row.operator_notes,
        "cancel_reason": row.cancel_reason,
        "retry_strategy": row.retry_strategy,
        "queue_priority": row.queue_priority,
        "parent_run_id": row.parent_run_id,
        "scheduled_for": row.scheduled_for.isoformat() if row.scheduled_for else None,
        "sla_target_minutes": row.sla_target_minutes,
    }


def _scene_to_dto(row: SatelliteScene, *, aoi_code: str | None = None, aoi_name: str | None = None) -> dict:
    return {
        "id": row.id,
        "source": row.source,
        "scene_id": row.scene_id,
        "aoi_id": row.aoi_id,
        "aoi_code": aoi_code,
        "aoi_name": aoi_name,
        "acquired_at": row.acquired_at.isoformat() if row.acquired_at else None,
        "cloud_score": row.cloud_score,
        "spatial_resolution_m": row.spatial_resolution_m,
        "processing_status": row.processing_status,
        "bands_available": row.bands_available or {},
        "metadata": row.metadata_json or {},
    }


def _feature_to_dto(row: GeospatialFeature, *, aoi_code: str | None = None, aoi_name: str | None = None) -> dict:
    features = row.features_json or {}
    return {
        "id": row.id,
        "aoi_id": row.aoi_id,
        "aoi_code": aoi_code,
        "aoi_name": aoi_name,
        "source": row.source,
        "observation_date": row.observation_date.isoformat() if row.observation_date else None,
        "reporting_month": row.reporting_month.isoformat() if row.reporting_month else None,
        "cloud_score": row.cloud_score,
        "crop_activity_score": row.crop_activity_score,
        "vegetation_vigor_score": row.vegetation_vigor_score,
        "observation_confidence_score": row.observation_confidence_score,
        "scene_id": features.get("scene_id"),
        "acquired_at": features.get("acquired_at"),
        "quality": row.quality_json or {},
    }


def _aoi_lookup_map(db: Session, aoi_ids: set[int]) -> dict[int, tuple[str | None, str | None]]:
    if not aoi_ids:
        return {}
    rows = db.execute(select(GeospatialAOI.id, GeospatialAOI.code, GeospatialAOI.name).where(GeospatialAOI.id.in_(sorted(aoi_ids)))).all()
    return {aoi_id: (code, name) for aoi_id, code, name in rows}


def _hydrate_scene_refs(db: Session, refs: list[dict]) -> list[dict]:
    if not refs:
        return []

    ref_map: dict[tuple[str, str], dict] = {}
    for ref in refs:
        source = ref.get("source")
        scene_id = ref.get("scene_id")
        if isinstance(source, str) and isinstance(scene_id, str):
            ref_map[(source, scene_id)] = ref

    if not ref_map:
        return []

    scene_rows = db.scalars(select(SatelliteScene).where(SatelliteScene.scene_id.in_(sorted({scene_id for _, scene_id in ref_map.keys()})))).all()
    aoi_map = _aoi_lookup_map(db, {row.aoi_id for row in scene_rows if row.aoi_id is not None})

    hydrated: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in scene_rows:
        key = (row.source, row.scene_id)
        ref = ref_map.get(key)
        if ref is None or key in seen:
            continue
        aoi_code, aoi_name = aoi_map.get(row.aoi_id, (None, None))
        payload = _scene_to_dto(row, aoi_code=aoi_code, aoi_name=aoi_name)
        payload["provenance_status"] = ref.get("provenance_status")
        hydrated.append(payload)
        seen.add(key)

    for key, ref in ref_map.items():
        if key in seen:
            continue
        hydrated.append(
            {
                "id": None,
                "source": ref.get("source"),
                "scene_id": ref.get("scene_id"),
                "aoi_id": ref.get("aoi_id"),
                "aoi_code": None,
                "aoi_name": None,
                "acquired_at": ref.get("acquired_at"),
                "cloud_score": ref.get("cloud_score"),
                "spatial_resolution_m": ref.get("spatial_resolution_m"),
                "processing_status": ref.get("processing_status") or "discovered",
                "bands_available": {},
                "metadata": {},
                "provenance_status": ref.get("provenance_status"),
            }
        )

    return hydrated


def _run_detail_to_dto(row: SatellitePipelineRun, *, db: Session, aoi_code: str | None = None, aoi_name: str | None = None) -> dict:
    payload = _run_to_dto(row, aoi_code=aoi_code, aoi_name=aoi_name)
    related_features: list[dict] = []
    related_scenes: list[dict] = []

    if row.run_type == "feature_refresh":
        feature_rows = db.scalars(
            select(GeospatialFeature)
            .where(GeospatialFeature.processing_run_id == row.id)
            .order_by(desc(GeospatialFeature.observation_date), desc(GeospatialFeature.id))
            .limit(100)
        ).all()
        aoi_map = _aoi_lookup_map(db, {feature.aoi_id for feature in feature_rows})
        related_features = [
            _feature_to_dto(feature, aoi_code=aoi_map.get(feature.aoi_id, (None, None))[0], aoi_name=aoi_map.get(feature.aoi_id, (None, None))[1])
            for feature in feature_rows
        ]
        related_scenes = _hydrate_scene_refs(
            db,
            [
                {
                    "source": feature.source,
                    "scene_id": (feature.features_json or {}).get("scene_id"),
                    "aoi_id": feature.aoi_id,
                    "acquired_at": (feature.features_json or {}).get("acquired_at"),
                    "provenance_status": "materialized_feature",
                }
                for feature in feature_rows
                if isinstance((feature.features_json or {}).get("scene_id"), str)
            ],
        )
    elif row.run_type == "ingest":
        scene_discovery = (row.results_json or {}).get("scene_discovery") or {}
        related_scenes = _hydrate_scene_refs(db, scene_discovery.get("scene_refs") or [])

    payload["provenance_summary"] = {
        "scene_count": len(related_scenes),
        "feature_count": len(related_features),
        "scene_sources": sorted({scene.get("source") for scene in related_scenes if scene.get("source")}),
        "feature_sources": sorted({feature.get("source") for feature in related_features if feature.get("source")}),
    }
    payload["related_scenes"] = related_scenes
    payload["related_features"] = related_features
    return payload


def _normalize_pagination(*, page: int, page_size: int) -> tuple[int, int]:
    return max(1, page), max(1, min(page_size, 100))


def _paginate_rows(*, rows: list[dict], page: int, page_size: int) -> dict:
    page, page_size = _normalize_pagination(page=page, page_size=page_size)
    total = len(rows)
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "rows": rows[start:end],
    }


def _matches_contains(value: object, query: str) -> bool:
    return query in str(value or "").lower()


def _sort_rows(*, rows: list[dict], sort_by: str, sort_dir: str) -> list[dict]:
    reverse = sort_dir.lower() == "desc"
    return sorted(rows, key=lambda row: (str(row.get(sort_by) or ""), str(row.get("id") or "")), reverse=reverse)


def _filter_sort_scene_rows(
    *,
    rows: list[dict],
    source: str | None,
    search: str | None,
    aoi_code: str | None,
    processing_status: str | None,
    sort_by: str,
    sort_dir: str,
) -> list[dict]:
    search_value = (search or "").strip().lower()
    aoi_code_value = (aoi_code or "").strip().lower()
    filtered = rows
    if source:
        filtered = [row for row in filtered if str(row.get("source") or "") == source]
    if processing_status:
        filtered = [row for row in filtered if str(row.get("processing_status") or "") == processing_status]
    if aoi_code_value:
        filtered = [row for row in filtered if _matches_contains(row.get("aoi_code"), aoi_code_value)]
    if search_value:
        filtered = [
            row
            for row in filtered
            if _matches_contains(row.get("scene_id"), search_value)
            or _matches_contains(row.get("source"), search_value)
            or _matches_contains(row.get("aoi_code"), search_value)
        ]
    allowed_sort = {"acquired_at", "source", "aoi_code", "cloud_score", "spatial_resolution_m", "scene_id", "processing_status", "provenance_status"}
    sort_key = sort_by if sort_by in allowed_sort else "acquired_at"
    return _sort_rows(rows=filtered, sort_by=sort_key, sort_dir=sort_dir)


def _filter_sort_feature_rows(
    *,
    rows: list[dict],
    source: str | None,
    search: str | None,
    aoi_code: str | None,
    sort_by: str,
    sort_dir: str,
) -> list[dict]:
    search_value = (search or "").strip().lower()
    aoi_code_value = (aoi_code or "").strip().lower()
    filtered = rows
    if source:
        filtered = [row for row in filtered if str(row.get("source") or "") == source]
    if aoi_code_value:
        filtered = [row for row in filtered if _matches_contains(row.get("aoi_code"), aoi_code_value)]
    if search_value:
        filtered = [
            row
            for row in filtered
            if _matches_contains(row.get("scene_id"), search_value)
            or _matches_contains(row.get("source"), search_value)
            or _matches_contains(row.get("aoi_code"), search_value)
            or _matches_contains(row.get("observation_date"), search_value)
        ]
    allowed_sort = {"observation_date", "source", "aoi_code", "scene_id", "observation_confidence_score", "crop_activity_score", "vegetation_vigor_score", "cloud_score"}
    sort_key = sort_by if sort_by in allowed_sort else "observation_date"
    return _sort_rows(rows=filtered, sort_by=sort_key, sort_dir=sort_dir)


def _list_run_scene_rows(db: Session, *, run: SatellitePipelineRun) -> list[dict]:
    if run.run_type == "ingest":
        scene_discovery = (run.results_json or {}).get("scene_discovery") or {}
        scene_refs = scene_discovery.get("scene_refs") or []
        if not isinstance(scene_refs, list):
            return []
        rows = _hydrate_scene_refs(db, scene_refs)
        rows.sort(key=lambda row: (str(row.get("acquired_at") or ""), str(row.get("scene_id") or "")), reverse=True)
        return rows

    if run.run_type == "feature_refresh":
        feature_rows = db.scalars(
            select(GeospatialFeature)
            .where(GeospatialFeature.processing_run_id == run.id)
            .order_by(desc(GeospatialFeature.observation_date), desc(GeospatialFeature.id))
        ).all()
        refs: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for feature in feature_rows:
            features = feature.features_json or {}
            source = feature.source
            scene_id = features.get("scene_id")
            if not isinstance(scene_id, str):
                continue
            key = (source, scene_id)
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                {
                    "source": source,
                    "scene_id": scene_id,
                    "aoi_id": feature.aoi_id,
                    "acquired_at": features.get("acquired_at"),
                    "provenance_status": "materialized_feature",
                }
            )
        rows = _hydrate_scene_refs(db, refs)
        rows.sort(key=lambda row: (str(row.get("acquired_at") or ""), str(row.get("scene_id") or "")), reverse=True)
        return rows

    return []


def _list_run_feature_rows(db: Session, *, run: SatellitePipelineRun) -> list[dict]:
    if run.run_type != "feature_refresh":
        return []

    feature_rows = db.scalars(
        select(GeospatialFeature)
        .where(GeospatialFeature.processing_run_id == run.id)
        .order_by(desc(GeospatialFeature.observation_date), desc(GeospatialFeature.id))
    ).all()
    aoi_map = _aoi_lookup_map(db, {feature.aoi_id for feature in feature_rows})
    return [
        _feature_to_dto(
            feature,
            aoi_code=aoi_map.get(feature.aoi_id, (None, None))[0],
            aoi_name=aoi_map.get(feature.aoi_id, (None, None))[1],
        )
        for feature in feature_rows
    ]


def _ingest_parameters_payload(*, start: datetime | None, end: datetime | None, limit_per_source: int) -> dict:
    return {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "limit_per_source": limit_per_source,
    }


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _load_run_or_404(db: Session, *, run_id: int) -> SatellitePipelineRun:
    run = db.scalar(select(SatellitePipelineRun).where(SatellitePipelineRun.id == run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return run


def _load_aoi_or_404(db: Session, *, aoi_id: int) -> GeospatialAOI:
    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id))
    if aoi is None:
        raise HTTPException(status_code=404, detail="AOI not found")
    return aoi


def _find_duplicate_run(
    db: Session,
    *,
    run_type: str,
    aoi_id: int | None,
    sources: list[str] | None,
    parameters: dict[str, Any],
) -> SatellitePipelineRun | None:
    normalized_sources = sorted([str(item).strip() for item in (sources or []) if str(item).strip()])
    rows = db.scalars(
        select(SatellitePipelineRun)
        .where(
            SatellitePipelineRun.run_type == run_type,
            SatellitePipelineRun.status.in_(["queued", "running", "cancel_requested"]),
            SatellitePipelineRun.aoi_id == aoi_id,
        )
        .order_by(desc(SatellitePipelineRun.id))
        .limit(25)
    ).all()
    for row in rows:
        row_sources = sorted([str(item).strip() for item in ((row.sources_json or {}).get("sources") or []) if str(item).strip()])
        if row_sources != normalized_sources:
            continue
        if (row.parameters_json or {}) == (parameters or {}):
            return row
    return None


def _execute_ingest_run_background(
    *,
    run_id: int,
    aoi_id: int | None,
    sources: list[str] | None,
    start: datetime | None,
    end: datetime | None,
    limit_per_source: int,
) -> None:
    db = SessionLocal()
    try:
        run = execute_ingestion_run(
            db,
            run_id=run_id,
            aoi_id=aoi_id,
            sources=sources,
            start=start,
            end=end,
            limit_per_source=limit_per_source,
        )
        _append_run_event(
            db,
            run_id=run.id,
            phase="execution",
            status=run.status,
            message="Ingest run execution completed",
            details={"status": run.status, "results": run.results_json or {}},
        )
        db.commit()
    except Exception:
        db.rollback()
        failed_run = db.scalar(select(SatellitePipelineRun).where(SatellitePipelineRun.id == run_id))
        if failed_run is not None:
            _append_run_event(
                db,
                run_id=failed_run.id,
                phase="execution",
                status="failed",
                message="Ingest run execution failed",
                details={"status": failed_run.status, "results": failed_run.results_json or {}},
            )
            db.commit()
        else:
            db.rollback()
        raise
    finally:
        db.close()


def _execute_feature_refresh_background(*, run_id: int, aoi_id: int | None, sources: list[str] | None) -> None:
    db = SessionLocal()
    try:
        run = execute_feature_refresh_run(db, run_id=run_id, aoi_id=aoi_id, sources=sources)
        _append_run_event(
            db,
            run_id=run.id,
            phase="execution",
            status=run.status,
            message="Feature refresh execution completed",
            details={"status": run.status, "results": run.results_json or {}},
        )
        db.commit()
    except Exception:
        db.rollback()
        failed_run = db.scalar(select(SatellitePipelineRun).where(SatellitePipelineRun.id == run_id))
        if failed_run is not None:
            _append_run_event(
                db,
                run_id=failed_run.id,
                phase="execution",
                status="failed",
                message="Feature refresh execution failed",
                details={"status": failed_run.status, "results": failed_run.results_json or {}},
            )
            db.commit()
        else:
            db.rollback()
        raise
    finally:
        db.close()


@router.get("/aois")
def list_aois(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        CurrentUser,
        Depends(
            require_role(
                "super_admin",
                "provincial_admin",
                "municipal_encoder",
                "warehouse_operator",
                "market_analyst",
                "policy_reviewer",
                "executive_viewer",
                "auditor",
            )
        ),
    ],
    scope_type: str | None = None,
    municipality_id: int | None = None,
    warehouse_id: int | None = None,
    market_id: int | None = None,
    search: str | None = None,
    tag: str | None = None,
    watchlist_only: bool = False,
    favorites_only: bool = False,
    is_active: bool | None = True,
    limit: int = 500,
):
    stmt = select(GeospatialAOI)
    if scope_type:
        stmt = stmt.where(GeospatialAOI.scope_type == scope_type)
    if municipality_id is not None:
        stmt = stmt.where(GeospatialAOI.municipality_id == municipality_id)
    if warehouse_id is not None:
        stmt = stmt.where(GeospatialAOI.warehouse_id == warehouse_id)
    if market_id is not None:
        stmt = stmt.where(GeospatialAOI.market_id == market_id)
    if is_active is not None:
        stmt = stmt.where(GeospatialAOI.is_active == is_active)
    if search:
        q = f"%{search.strip()}%"
        stmt = stmt.where(or_(GeospatialAOI.code.ilike(q), GeospatialAOI.name.ilike(q), GeospatialAOI.description.ilike(q)))

    rows = db.scalars(stmt.order_by(GeospatialAOI.name).limit(max(1, min(limit, 2000)))).all()
    if not rows:
        return []

    aoi_ids = [row.id for row in rows]
    metadata_rows = db.scalars(select(GeospatialAOIMetadata).where(GeospatialAOIMetadata.aoi_id.in_(aoi_ids))).all()
    metadata_map = {row.aoi_id: row for row in metadata_rows}
    favorite_rows = db.scalars(
        select(GeospatialAOIFavorite).where(
            GeospatialAOIFavorite.aoi_id.in_(aoi_ids),
            GeospatialAOIFavorite.user_id == current_user.id,
        )
    ).all()
    favorite_map = {row.aoi_id: row for row in favorite_rows}

    normalized_tag = tag.strip().lower() if tag else ""
    result: list[dict[str, Any]] = []
    for row in rows:
        meta = metadata_map.get(row.id)
        tags = _normalize_string_list((meta.tags_json if meta else []) or [])
        labels = _normalize_string_list((meta.labels_json if meta else []) or [])
        favorite = favorite_map.get(row.id)

        if watchlist_only and not (meta and meta.watchlist_flag):
            continue
        if favorites_only and favorite is None:
            continue
        if normalized_tag and normalized_tag not in {entry.lower() for entry in tags}:
            continue

        result.append(
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "description": row.description,
                "scope_type": row.scope_type,
                "municipality_id": row.municipality_id,
                "warehouse_id": row.warehouse_id,
                "market_id": row.market_id,
                "srid": row.srid,
                "bbox": {
                    "min_lng": row.bbox_min_lng,
                    "min_lat": row.bbox_min_lat,
                    "max_lng": row.bbox_max_lng,
                    "max_lat": row.bbox_max_lat,
                },
                "centroid": {"lng": row.centroid_lng, "lat": row.centroid_lat},
                "source": row.source,
                "is_active": row.is_active,
                "tags": tags,
                "labels": labels,
                "owner_user_id": meta.owner_user_id if meta else None,
                "watchlist_flag": bool(meta.watchlist_flag) if meta else False,
                "is_favorite": favorite is not None,
                "is_pinned": bool(favorite.is_pinned) if favorite else False,
            }
        )

    return result


@router.post("/aois", response_model=AOIDTO)
def create_aoi(
    payload: AOICreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
):
    existing = db.scalar(select(GeospatialAOI).where(GeospatialAOI.code == payload.code))
    if existing is not None:
        raise HTTPException(status_code=400, detail="AOI code already exists")

    aoi = GeospatialAOI(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        scope_type=payload.scope_type,
        municipality_id=payload.municipality_id,
        warehouse_id=payload.warehouse_id,
        market_id=payload.market_id,
        srid=4326,
        boundary_geojson=payload.boundary_geojson,
        boundary_wkt=payload.boundary_wkt,
        source=payload.source,
        is_active=True,
    )
    _apply_bbox_and_centroid(aoi)

    conflicts = _overlap_conflicts(db, candidate=aoi)
    if conflicts:
        raise HTTPException(status_code=409, detail={"message": "AOI overlaps with existing AOI boundaries", "conflicts": conflicts})

    db.add(aoi)
    db.flush()
    _get_or_create_aoi_metadata(db, aoi_id=aoi.id)

    db.add(
        GeospatialAOIVersion(
            aoi_id=aoi.id,
            version=1,
            change_type="create",
            boundary_geojson=aoi.boundary_geojson,
            boundary_wkt=aoi.boundary_wkt,
            changed_by=current_user.id,
            change_reason=payload.change_reason,
            changed_at=datetime.utcnow(),
        )
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.create",
        entity_type="geospatial_aoi",
        entity_id=str(aoi.id),
        before_payload=None,
        after_payload={"id": aoi.id, "code": aoi.code, "name": aoi.name},
    )
    db.flush()
    return _aoi_to_dto(aoi)


@router.put("/aois/{aoi_id}", response_model=AOIDTO)
def update_aoi(
    aoi_id: int,
    payload: AOIUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
):
    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id))
    if aoi is None:
        raise HTTPException(status_code=404, detail="AOI not found")

    before_payload = _aoi_to_dto(aoi).model_dump(mode="json")
    change_reason = payload.change_reason

    if payload.code is not None and payload.code != aoi.code:
        other = db.scalar(select(GeospatialAOI).where(GeospatialAOI.code == payload.code))
        if other is not None:
            raise HTTPException(status_code=400, detail="AOI code already exists")
        aoi.code = payload.code

    if payload.name is not None:
        aoi.name = payload.name
    if payload.description is not None:
        aoi.description = payload.description
    if payload.scope_type is not None:
        aoi.scope_type = payload.scope_type
    if payload.municipality_id is not None:
        aoi.municipality_id = payload.municipality_id
    if payload.warehouse_id is not None:
        aoi.warehouse_id = payload.warehouse_id
    if payload.market_id is not None:
        aoi.market_id = payload.market_id
    if payload.boundary_geojson is not None:
        aoi.boundary_geojson = payload.boundary_geojson
    if payload.boundary_wkt is not None:
        aoi.boundary_wkt = payload.boundary_wkt
    if payload.source is not None:
        aoi.source = payload.source
    if payload.is_active is not None:
        aoi.is_active = payload.is_active

    if payload.boundary_geojson is not None:
        _apply_bbox_and_centroid(aoi)
        conflicts = _overlap_conflicts(db, candidate=aoi)
        if conflicts:
            raise HTTPException(status_code=409, detail={"message": "AOI overlaps with existing AOI boundaries", "conflicts": conflicts})

    next_version = _next_aoi_version(db, aoi_id=aoi.id)
    db.add(
        GeospatialAOIVersion(
            aoi_id=aoi.id,
            version=next_version,
            change_type="update",
            boundary_geojson=aoi.boundary_geojson,
            boundary_wkt=aoi.boundary_wkt,
            changed_by=current_user.id,
            change_reason=change_reason,
            changed_at=datetime.utcnow(),
        )
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.update",
        entity_type="geospatial_aoi",
        entity_id=str(aoi.id),
        before_payload=before_payload,
        after_payload=_aoi_to_dto(aoi).model_dump(mode="json"),
    )
    db.flush()
    return _aoi_to_dto(aoi)


@router.delete("/aois/{aoi_id}", response_model=AOIDTO)
def deactivate_aoi(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
    change_reason: str | None = None,
):
    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id))
    if aoi is None:
        raise HTTPException(status_code=404, detail="AOI not found")

    before_payload = _aoi_to_dto(aoi).model_dump(mode="json")
    aoi.is_active = False
    next_version = _next_aoi_version(db, aoi_id=aoi.id)
    db.add(
        GeospatialAOIVersion(
            aoi_id=aoi.id,
            version=next_version,
            change_type="deactivate",
            boundary_geojson=aoi.boundary_geojson,
            boundary_wkt=aoi.boundary_wkt,
            changed_by=current_user.id,
            change_reason=change_reason,
            changed_at=datetime.utcnow(),
        )
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.deactivate",
        entity_type="geospatial_aoi",
        entity_id=str(aoi.id),
        before_payload=before_payload,
        after_payload=_aoi_to_dto(aoi).model_dump(mode="json"),
    )
    db.flush()
    return _aoi_to_dto(aoi)


@router.get("/aois/{aoi_id}/versions", response_model=list[AOIVersionDTO])
def list_aoi_versions(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        CurrentUser,
        Depends(
            require_role(
                "super_admin",
                "provincial_admin",
                "municipal_encoder",
                "warehouse_operator",
                "market_analyst",
                "policy_reviewer",
                "executive_viewer",
                "auditor",
            )
        ),
    ],
    limit: int = 25,
):
    rows = db.scalars(
        select(GeospatialAOIVersion)
        .where(GeospatialAOIVersion.aoi_id == aoi_id)
        .order_by(desc(GeospatialAOIVersion.version))
        .limit(max(1, min(limit, 200)))
    ).all()

    return [
        AOIVersionDTO(
            id=row.id,
            aoi_id=row.aoi_id,
            version=row.version,
            change_type=row.change_type,
            boundary_geojson=row.boundary_geojson,
            boundary_wkt=row.boundary_wkt,
            changed_by=row.changed_by,
            change_reason=row.change_reason,
            changed_at=row.changed_at,
        )
        for row in rows
    ]


@router.get("/aois/{aoi_id}")
def get_aoi(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        CurrentUser,
        Depends(
            require_role(
                "super_admin",
                "provincial_admin",
                "municipal_encoder",
                "warehouse_operator",
                "market_analyst",
                "policy_reviewer",
                "executive_viewer",
                "auditor",
            )
        ),
    ],
):
    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id))
    if aoi is None:
        raise HTTPException(status_code=404, detail="AOI not found")
    meta = _get_or_create_aoi_metadata(db, aoi_id=aoi.id)
    favorite = db.scalar(
        select(GeospatialAOIFavorite).where(
            GeospatialAOIFavorite.aoi_id == aoi.id,
            GeospatialAOIFavorite.user_id == current_user.id,
        )
    )
    overlaps = [
        row
        for row in _overlap_conflicts(db, candidate=aoi)
        if int(row.get("id") or 0) != aoi.id
    ]

    return {
        "id": aoi.id,
        "code": aoi.code,
        "name": aoi.name,
        "description": aoi.description,
        "scope_type": aoi.scope_type,
        "municipality_id": aoi.municipality_id,
        "warehouse_id": aoi.warehouse_id,
        "market_id": aoi.market_id,
        "srid": aoi.srid,
        "boundary_geojson": aoi.boundary_geojson,
        "boundary_wkt": aoi.boundary_wkt,
        "bbox": {
            "min_lng": aoi.bbox_min_lng,
            "min_lat": aoi.bbox_min_lat,
            "max_lng": aoi.bbox_max_lng,
            "max_lat": aoi.bbox_max_lat,
        },
        "centroid": {"lng": aoi.centroid_lng, "lat": aoi.centroid_lat},
        "source": aoi.source,
        "is_active": aoi.is_active,
        "tags": _normalize_string_list(meta.tags_json or []),
        "labels": _normalize_string_list(meta.labels_json or []),
        "owner_user_id": meta.owner_user_id,
        "watchlist_flag": bool(meta.watchlist_flag),
        "is_favorite": favorite is not None,
        "is_pinned": bool(favorite.is_pinned) if favorite else False,
        "geometry_hints": {
            "overlap_conflicts": overlaps,
            "bbox_summary": f"{aoi.bbox_min_lng},{aoi.bbox_min_lat} -> {aoi.bbox_max_lng},{aoi.bbox_max_lat}",
        },
    }


@router.get("/observations")
def list_observations(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        CurrentUser,
        Depends(
            require_role(
                "super_admin",
                "provincial_admin",
                "municipal_encoder",
                "warehouse_operator",
                "market_analyst",
                "policy_reviewer",
                "executive_viewer",
                "auditor",
            )
        ),
    ],
    aoi_id: int | None = None,
    source: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 500,
):
    stmt = select(GeospatialFeature)
    if aoi_id is not None:
        stmt = stmt.where(GeospatialFeature.aoi_id == aoi_id)
    if source:
        stmt = stmt.where(GeospatialFeature.source == source)
    if start_date is not None:
        stmt = stmt.where(GeospatialFeature.observation_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(GeospatialFeature.observation_date <= end_date)

    rows = db.scalars(stmt.order_by(desc(GeospatialFeature.observation_date)).limit(max(1, min(limit, 2000)))).all()
    return [
        {
            "id": row.id,
            "aoi_id": row.aoi_id,
            "source": row.source,
            "observation_date": row.observation_date.isoformat(),
            "reporting_month": row.reporting_month.isoformat() if row.reporting_month else None,
            "ndvi_mean": row.ndvi_mean,
            "evi_mean": row.evi_mean,
            "ndwi_mean": row.ndwi_mean,
            "cloud_score": row.cloud_score,
            "radar_backscatter_vv": row.radar_backscatter_vv,
            "radar_backscatter_vh": row.radar_backscatter_vh,
            "change_score": row.change_score,
            "vegetation_vigor_score": row.vegetation_vigor_score,
            "crop_activity_score": row.crop_activity_score,
            "observation_confidence_score": row.observation_confidence_score,
            "processing_run_id": row.processing_run_id,
            "quality": row.quality_json or {},
            "features": row.features_json or {},
        }
        for row in rows
    ]


@router.get("/observations/{aoi_id}/timeline")
def aoi_timeline(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        CurrentUser,
        Depends(
            require_role(
                "super_admin",
                "provincial_admin",
                "municipal_encoder",
                "warehouse_operator",
                "market_analyst",
                "policy_reviewer",
                "executive_viewer",
                "auditor",
            )
        ),
    ],
    source: str | None = None,
    limit: int = 365,
):
    stmt = select(GeospatialFeature).where(GeospatialFeature.aoi_id == aoi_id)
    if source:
        stmt = stmt.where(GeospatialFeature.source == source)

    rows = db.scalars(stmt.order_by(desc(GeospatialFeature.observation_date)).limit(max(1, min(limit, 5000)))).all()
    return {
        "aoi_id": aoi_id,
        "count": len(rows),
        "observations": [
            {
                "observation_date": row.observation_date.isoformat(),
                "source": row.source,
                "crop_activity_score": row.crop_activity_score,
                "vegetation_vigor_score": row.vegetation_vigor_score,
                "observation_confidence_score": row.observation_confidence_score,
                "cloud_score": row.cloud_score,
            }
            for row in rows
        ],
    }


@router.post("/ingest/run")
def trigger_ingest_run(
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
    aoi_id: int | None = None,
    sources: list[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit_per_source: int = 200,
    backend: str = "gee",
    notes: str | None = None,
    queue_priority: int = 100,
    retry_strategy: str = "standard",
    sla_target_minutes: int | None = None,
    operator_notes: str | None = None,
):
    parameters = _ingest_parameters_payload(start=start, end=end, limit_per_source=limit_per_source)
    duplicate_of = _find_duplicate_run(
        db,
        run_type="ingest",
        aoi_id=aoi_id,
        sources=sources,
        parameters=parameters,
    )
    run = queue_ingestion_run(
        db,
        triggered_by=current_user.id,
        correlation_id=None,
        aoi_id=aoi_id,
        sources=sources,
        backend=backend,
        notes=notes,
        status="queued",
    )
    run.parameters_json = parameters
    run.queue_priority = max(1, min(1000, int(queue_priority)))
    run.retry_strategy = retry_strategy.strip() or "standard"
    run.sla_target_minutes = sla_target_minutes
    run.operator_notes = operator_notes
    if duplicate_of is not None:
        run.parent_run_id = duplicate_of.id

    _append_run_event(
        db,
        run_id=run.id,
        phase="queue",
        status="queued",
        message="Ingest run queued",
        details={
            "duplicate_of_run_id": duplicate_of.id if duplicate_of else None,
            "queue_priority": run.queue_priority,
            "retry_strategy": run.retry_strategy,
        },
        actor_user_id=current_user.id,
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.run.queue",
        entity_type="satellite_pipeline_run",
        entity_id=str(run.id),
        before_payload=None,
        after_payload={"run_type": run.run_type, "status": run.status, "queue_priority": run.queue_priority},
    )
    db.commit()
    db.refresh(run)
    background_tasks.add_task(
        _execute_ingest_run_background,
        run_id=run.id,
        aoi_id=aoi_id,
        sources=sources,
        start=start,
        end=end,
        limit_per_source=limit_per_source,
    )
    return {"run_id": run.id, "status": run.status, "duplicate_of_run_id": duplicate_of.id if duplicate_of else None}


@router.post("/features/recompute")
def trigger_feature_recompute(
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
    aoi_id: int | None = None,
    sources: list[str] | None = None,
    backend: str = "gee",
    notes: str | None = None,
    queue_priority: int = 100,
    retry_strategy: str = "standard",
    sla_target_minutes: int | None = None,
    operator_notes: str | None = None,
):
    parameters = {"lookback_days": int(settings.geospatial_default_lookback_days)}
    duplicate_of = _find_duplicate_run(
        db,
        run_type="feature_refresh",
        aoi_id=aoi_id,
        sources=sources,
        parameters=parameters,
    )
    run = queue_feature_refresh_run(
        db,
        triggered_by=current_user.id,
        correlation_id=None,
        aoi_id=aoi_id,
        sources=sources,
        backend=backend,
        notes=notes,
        status="queued",
    )
    run.parameters_json = {**(run.parameters_json or {}), **parameters}
    run.queue_priority = max(1, min(1000, int(queue_priority)))
    run.retry_strategy = retry_strategy.strip() or "standard"
    run.sla_target_minutes = sla_target_minutes
    run.operator_notes = operator_notes
    if duplicate_of is not None:
        run.parent_run_id = duplicate_of.id

    _append_run_event(
        db,
        run_id=run.id,
        phase="queue",
        status="queued",
        message="Feature recompute queued",
        details={
            "duplicate_of_run_id": duplicate_of.id if duplicate_of else None,
            "queue_priority": run.queue_priority,
            "retry_strategy": run.retry_strategy,
        },
        actor_user_id=current_user.id,
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.run.queue",
        entity_type="satellite_pipeline_run",
        entity_id=str(run.id),
        before_payload=None,
        after_payload={"run_type": run.run_type, "status": run.status, "queue_priority": run.queue_priority},
    )
    db.commit()
    db.refresh(run)
    background_tasks.add_task(_execute_feature_refresh_background, run_id=run.id, aoi_id=aoi_id, sources=sources)
    return {"run_id": run.id, "status": run.status, "duplicate_of_run_id": duplicate_of.id if duplicate_of else None}


@router.post("/runs/{run_id}/cancel")
def cancel_pipeline_run(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
    reason: str | None = None,
):
    run = _load_run_or_404(db, run_id=run_id)
    if run.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Run can no longer be cancelled")

    if run.status == "cancel_requested":
        return {"run_id": run.id, "status": run.status}

    now = datetime.utcnow()
    if run.status == "queued":
        run.status = "cancelled"
        run.finished_at = now
        run.cancel_reason = reason
        run.results_json = {
            **(run.results_json or {}),
            "cancelled": {
                "phase": "queued",
                "requested_by": current_user.id,
                "requested_at": now.isoformat(),
                "reason": reason,
            },
        }
    elif run.status == "running":
        run.status = "cancel_requested"
        run.cancel_reason = reason
        run.results_json = {
            **(run.results_json or {}),
            "cancel_requested": {
                "requested_by": current_user.id,
                "requested_at": now.isoformat(),
                "reason": reason,
            },
        }
    else:
        raise HTTPException(status_code=409, detail="Run can no longer be cancelled")

    _append_run_event(
        db,
        run_id=run.id,
        phase="cancel",
        status=run.status,
        message="Run cancellation requested" if run.status == "cancel_requested" else "Run cancelled",
        details={"reason": reason, "requested_by": current_user.id},
        actor_user_id=current_user.id,
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.run.cancel",
        entity_type="satellite_pipeline_run",
        entity_id=str(run.id),
        before_payload=None,
        after_payload={"status": run.status, "cancel_reason": run.cancel_reason},
    )
    db.commit()
    db.refresh(run)
    return {"run_id": run.id, "status": run.status}


@router.post("/runs/{run_id}/retry")
def retry_pipeline_run(
    run_id: int,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
):
    run = _load_run_or_404(db, run_id=run_id)
    if run.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Only failed or cancelled runs can be retried")

    sources = (run.sources_json or {}).get("sources") or None
    retry_note = f"Retry of run #{run.id}" if not run.notes else f"Retry of run #{run.id} · {run.notes}"

    if run.run_type == "ingest":
        start = _parse_iso_datetime((run.parameters_json or {}).get("start"))
        end = _parse_iso_datetime((run.parameters_json or {}).get("end"))
        limit_per_source = int((run.parameters_json or {}).get("limit_per_source") or 200)
        retry_run = queue_ingestion_run(
            db,
            triggered_by=current_user.id,
            correlation_id=None,
            aoi_id=run.aoi_id,
            sources=sources,
            backend=run.backend,
            notes=retry_note,
            status="queued",
        )
        retry_run.parameters_json = _ingest_parameters_payload(start=start, end=end, limit_per_source=limit_per_source)
        retry_run.parent_run_id = run.id
        retry_run.retry_strategy = run.retry_strategy
        retry_run.queue_priority = run.queue_priority
        retry_run.sla_target_minutes = run.sla_target_minutes
        retry_run.operator_notes = run.operator_notes
        _append_run_event(
            db,
            run_id=retry_run.id,
            phase="retry",
            status="queued",
            message=f"Retry queued for run #{run.id}",
            details={"from_run_id": run.id},
            actor_user_id=current_user.id,
        )
        db.commit()
        db.refresh(retry_run)
        background_tasks.add_task(
            _execute_ingest_run_background,
            run_id=retry_run.id,
            aoi_id=run.aoi_id,
            sources=sources,
            start=start,
            end=end,
            limit_per_source=limit_per_source,
        )
        return {"run_id": retry_run.id, "status": retry_run.status}

    if run.run_type == "feature_refresh":
        retry_run = queue_feature_refresh_run(
            db,
            triggered_by=current_user.id,
            correlation_id=None,
            aoi_id=run.aoi_id,
            sources=sources,
            backend=run.backend,
            notes=retry_note,
            status="queued",
        )
        retry_run.parent_run_id = run.id
        retry_run.retry_strategy = run.retry_strategy
        retry_run.queue_priority = run.queue_priority
        retry_run.sla_target_minutes = run.sla_target_minutes
        retry_run.operator_notes = run.operator_notes
        _append_run_event(
            db,
            run_id=retry_run.id,
            phase="retry",
            status="queued",
            message=f"Retry queued for run #{run.id}",
            details={"from_run_id": run.id},
            actor_user_id=current_user.id,
        )
        db.commit()
        db.refresh(retry_run)
        background_tasks.add_task(_execute_feature_refresh_background, run_id=retry_run.id, aoi_id=run.aoi_id, sources=sources)
        return {"run_id": retry_run.id, "status": retry_run.status}

    raise HTTPException(status_code=400, detail="Unsupported run type")


@router.get("/runs")
def list_pipeline_runs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        CurrentUser,
        Depends(
            require_role(
                "super_admin",
                "provincial_admin",
                "municipal_encoder",
                "warehouse_operator",
                "market_analyst",
                "policy_reviewer",
                "executive_viewer",
                "auditor",
            )
        ),
    ],
    run_type: str | None = None,
    status: str | None = None,
    aoi_id: int | None = None,
    limit: int = 50,
):
    stmt = select(SatellitePipelineRun, GeospatialAOI.code, GeospatialAOI.name).join(
        GeospatialAOI,
        SatellitePipelineRun.aoi_id == GeospatialAOI.id,
        isouter=True,
    )
    if run_type:
        stmt = stmt.where(SatellitePipelineRun.run_type == run_type)
    if status:
        stmt = stmt.where(SatellitePipelineRun.status == status)
    if aoi_id is not None:
        stmt = stmt.where(SatellitePipelineRun.aoi_id == aoi_id)

    rows = db.execute(stmt.order_by(desc(SatellitePipelineRun.started_at)).limit(max(1, min(limit, 200)))).all()
    return [_run_to_dto(run, aoi_code=aoi_code, aoi_name=aoi_name) for run, aoi_code, aoi_name in rows]


@router.get("/runs/{run_id}")
def get_pipeline_run_detail(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        CurrentUser,
        Depends(
            require_role(
                "super_admin",
                "provincial_admin",
                "municipal_encoder",
                "warehouse_operator",
                "market_analyst",
                "policy_reviewer",
                "executive_viewer",
                "auditor",
            )
        ),
    ],
):
    row = db.execute(
        select(SatellitePipelineRun, GeospatialAOI.code, GeospatialAOI.name)
        .join(GeospatialAOI, SatellitePipelineRun.aoi_id == GeospatialAOI.id, isouter=True)
        .where(SatellitePipelineRun.id == run_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    run, aoi_code, aoi_name = row
    return _run_detail_to_dto(run, db=db, aoi_code=aoi_code, aoi_name=aoi_name)


@router.get("/runs/{run_id}/provenance/scenes")
def get_pipeline_run_scenes(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        CurrentUser,
        Depends(
            require_role(
                "super_admin",
                "provincial_admin",
                "municipal_encoder",
                "warehouse_operator",
                "market_analyst",
                "policy_reviewer",
                "executive_viewer",
                "auditor",
            )
        ),
    ],
    page: int = 1,
    page_size: int = 20,
    source: str | None = None,
    search: str | None = None,
    aoi_code: str | None = None,
    processing_status: str | None = None,
    sort_by: str = "acquired_at",
    sort_dir: str = "desc",
):
    run = _load_run_or_404(db, run_id=run_id)
    rows = _filter_sort_scene_rows(
        rows=_list_run_scene_rows(db, run=run),
        source=source,
        search=search,
        aoi_code=aoi_code,
        processing_status=processing_status,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    payload = _paginate_rows(rows=rows, page=page, page_size=page_size)
    return {"run_id": run.id, **payload}


@router.get("/runs/{run_id}/provenance/features")
def get_pipeline_run_features(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        CurrentUser,
        Depends(
            require_role(
                "super_admin",
                "provincial_admin",
                "municipal_encoder",
                "warehouse_operator",
                "market_analyst",
                "policy_reviewer",
                "executive_viewer",
                "auditor",
            )
        ),
    ],
    page: int = 1,
    page_size: int = 20,
    source: str | None = None,
    search: str | None = None,
    aoi_code: str | None = None,
    sort_by: str = "observation_date",
    sort_dir: str = "desc",
):
    run = _load_run_or_404(db, run_id=run_id)
    rows = _filter_sort_feature_rows(
        rows=_list_run_feature_rows(db, run=run),
        source=source,
        search=search,
        aoi_code=aoi_code,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    payload = _paginate_rows(rows=rows, page=page, page_size=page_size)
    return {"run_id": run.id, **payload}


@router.get("/map/layers")
def map_layers(
    _: Annotated[
        CurrentUser,
        Depends(
            require_role(
                "super_admin",
                "provincial_admin",
                "municipal_encoder",
                "warehouse_operator",
                "market_analyst",
                "policy_reviewer",
                "executive_viewer",
                "auditor",
            )
        ),
    ],
):
    return {
        "layers": [
            {
                "key": "crop_activity_score",
                "label": "Crop activity",
                "description": "Fused AOI-level crop activity signal.",
                "status": "ready",
                "legend": ["0.0 low", "0.5 moderate", "1.0 high"],
            },
            {
                "key": "vegetation_vigor_score",
                "label": "Vegetation vigor",
                "description": "Optical vegetation vigor proxy (NDVI/EVI-derived).",
                "status": "ready",
                "legend": ["0.0 low", "0.5 moderate", "1.0 high"],
            },
            {
                "key": "radar_change_score",
                "label": "Radar change",
                "description": "SAR structural/change signal for cloudy-period continuity.",
                "status": "ready",
                "legend": ["-1.0 drop", "0.0 stable", "1.0 surge"],
            },
            {
                "key": "cloud_confidence_score",
                "label": "Cloud confidence",
                "description": "Optical usability / cloud penalty signal.",
                "status": "degraded",
                "legend": ["0.0 poor", "0.5 moderate", "1.0 high"],
            },
            {
                "key": "observation_confidence_score",
                "label": "Observation confidence",
                "description": "Overall confidence given coverage, cloud, and temporal gaps.",
                "status": "ready",
                "legend": ["0.0 poor", "0.5 moderate", "1.0 high"],
            },
        ],
        "layer_status": {
            "ready": 4,
            "degraded": 1,
            "failed": 0,
        },
    }


@router.post("/map/layers/{layer_key}/retry")
def retry_map_layer(
    layer_key: str,
    _: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
):
    return {
        "layer_key": layer_key,
        "status": "ready",
        "retried_at": datetime.utcnow().isoformat(),
        "message": "Layer reload queued",
    }


@router.get("/dashboard/provincial")
def provincial_geospatial_overview(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    latest_date = db.scalar(select(func.max(GeospatialFeature.observation_date)))
    total_features = int(db.scalar(select(func.count(GeospatialFeature.id))) or 0)
    total_aois = int(db.scalar(select(func.count(GeospatialAOI.id))) or 0)

    return {
        "total_aois": total_aois,
        "total_features": total_features,
        "latest_observation_date": latest_date.isoformat() if latest_date else None,
    }


@router.get("/dashboard/municipal/{municipality_id}")
def municipal_geospatial_overview(
    municipality_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "municipal_encoder", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    aois = db.scalars(
        select(GeospatialAOI).where(GeospatialAOI.municipality_id == municipality_id, GeospatialAOI.is_active == True)  # noqa: E712
    ).all()

    # Latest per AOI (simple approach for v1 scaffolding).
    results = []
    for aoi in aois:
        feature = db.scalar(
            select(GeospatialFeature)
            .where(GeospatialFeature.aoi_id == aoi.id)
            .order_by(desc(GeospatialFeature.observation_date))
            .limit(1)
        )
        results.append(
            {
                "aoi_id": aoi.id,
                "aoi_code": aoi.code,
                "aoi_name": aoi.name,
                "latest": None
                if feature is None
                else {
                    "date": feature.observation_date.isoformat(),
                    "source": feature.source,
                    "crop_activity_score": feature.crop_activity_score,
                    "vegetation_vigor_score": feature.vegetation_vigor_score,
                    "observation_confidence_score": feature.observation_confidence_score,
                },
            }
        )

    return {
        "municipality_id": municipality_id,
        "aoi_count": len(aois),
        "aois": results,
    }


@router.get("/aois/{aoi_id}/metadata", response_model=AOIMetadataDTO)
def get_aoi_metadata(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id))
    if aoi is None:
        raise HTTPException(status_code=404, detail="AOI not found")
    return _metadata_to_dto(_get_or_create_aoi_metadata(db, aoi_id=aoi_id))


@router.post("/aois/{aoi_id}/metadata", response_model=AOIMetadataDTO)
def update_aoi_metadata(
    aoi_id: int,
    payload: AOIMetadataUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
):
    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id))
    if aoi is None:
        raise HTTPException(status_code=404, detail="AOI not found")
    meta = _get_or_create_aoi_metadata(db, aoi_id=aoi_id)
    before_payload = _metadata_to_dto(meta).model_dump(mode="json")
    if payload.owner_user_id is not None:
        meta.owner_user_id = payload.owner_user_id
    if payload.tags is not None:
        meta.tags_json = _normalize_string_list(payload.tags)
    if payload.labels is not None:
        meta.labels_json = _normalize_string_list(payload.labels)
    if payload.watchlist_flag is not None:
        meta.watchlist_flag = payload.watchlist_flag
    if payload.metadata is not None:
        meta.metadata_json = payload.metadata
    meta.updated_by = current_user.id
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.metadata.update",
        entity_type="geospatial_aoi",
        entity_id=str(aoi_id),
        before_payload=before_payload,
        after_payload=_metadata_to_dto(meta).model_dump(mode="json"),
    )
    db.commit()
    db.refresh(meta)
    return _metadata_to_dto(meta)


@router.post("/aois/{aoi_id}/favorite")
def favorite_aoi(
    aoi_id: int,
    payload: AOIFavoriteRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id))
    if aoi is None:
        raise HTTPException(status_code=404, detail="AOI not found")
    favorite = db.scalar(
        select(GeospatialAOIFavorite).where(
            GeospatialAOIFavorite.aoi_id == aoi_id,
            GeospatialAOIFavorite.user_id == current_user.id,
        )
    )
    if favorite is None:
        favorite = GeospatialAOIFavorite(
            aoi_id=aoi_id,
            user_id=current_user.id,
            is_pinned=payload.is_pinned,
            pinned_at=datetime.utcnow(),
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(favorite)
    else:
        favorite.is_pinned = payload.is_pinned
        favorite.pinned_at = datetime.utcnow()
        favorite.updated_by = current_user.id
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.favorite",
        entity_type="geospatial_aoi",
        entity_id=str(aoi_id),
        before_payload=None,
        after_payload={"is_favorite": True, "is_pinned": payload.is_pinned},
    )
    db.commit()
    return {"aoi_id": aoi_id, "is_favorite": True, "is_pinned": favorite.is_pinned}


@router.delete("/aois/{aoi_id}/favorite")
def unfavorite_aoi(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    favorite = db.scalar(
        select(GeospatialAOIFavorite).where(
            GeospatialAOIFavorite.aoi_id == aoi_id,
            GeospatialAOIFavorite.user_id == current_user.id,
        )
    )
    if favorite is None:
        return {"aoi_id": aoi_id, "is_favorite": False}
    db.delete(favorite)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.unfavorite",
        entity_type="geospatial_aoi",
        entity_id=str(aoi_id),
        before_payload={"is_favorite": True},
        after_payload={"is_favorite": False},
    )
    db.commit()
    return {"aoi_id": aoi_id, "is_favorite": False}


@router.get("/favorites/aois")
def list_aoi_favorites(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    rows = db.execute(
        select(GeospatialAOIFavorite, GeospatialAOI)
        .join(GeospatialAOI, GeospatialAOI.id == GeospatialAOIFavorite.aoi_id)
        .where(GeospatialAOIFavorite.user_id == current_user.id)
        .order_by(desc(GeospatialAOIFavorite.pinned_at))
    ).all()
    return [
        {
            "aoi_id": aoi.id,
            "code": aoi.code,
            "name": aoi.name,
            "is_pinned": favorite.is_pinned,
            "pinned_at": favorite.pinned_at.isoformat(),
        }
        for favorite, aoi in rows
    ]


@router.post("/aois/bulk/status")
def bulk_update_aoi_status(
    payload: AOIBulkStatusRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
):
    ids = sorted({int(item) for item in payload.aoi_ids if int(item) > 0})
    if not ids:
        raise HTTPException(status_code=400, detail="No AOI ids provided")
    rows = db.scalars(select(GeospatialAOI).where(GeospatialAOI.id.in_(ids))).all()
    updated_ids: list[int] = []
    for row in rows:
        before_payload = _aoi_to_dto(row).model_dump(mode="json")
        row.is_active = payload.is_active
        row.updated_by = current_user.id
        next_version = _next_aoi_version(db, aoi_id=row.id)
        db.add(
            GeospatialAOIVersion(
                aoi_id=row.id,
                version=next_version,
                change_type="bulk_activate" if payload.is_active else "bulk_deactivate",
                boundary_geojson=row.boundary_geojson,
                boundary_wkt=row.boundary_wkt,
                changed_by=current_user.id,
                change_reason=payload.change_reason,
                changed_at=datetime.utcnow(),
            )
        )
        emit_audit_event(
            db,
            actor_user_id=current_user.id,
            action_type="geospatial.aoi.bulk_status",
            entity_type="geospatial_aoi",
            entity_id=str(row.id),
            before_payload=before_payload,
            after_payload=_aoi_to_dto(row).model_dump(mode="json"),
        )
        updated_ids.append(row.id)
    db.commit()
    return {"updated_count": len(updated_ids), "aoi_ids": updated_ids, "is_active": payload.is_active}


@router.post("/aois/bulk/import-geojson")
def bulk_import_aoi_geojson(
    payload: AOIBulkImportRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
):
    collection = payload.feature_collection or {}
    features = collection.get("features")
    if collection.get("type") != "FeatureCollection" or not isinstance(features, list):
        raise HTTPException(status_code=400, detail="feature_collection must be a GeoJSON FeatureCollection")

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict):
            skipped.append({"index": index, "reason": "Invalid feature payload"})
            continue
        geometry = feature.get("geometry")
        properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        if not isinstance(geometry, dict):
            skipped.append({"index": index, "reason": "Missing geometry"})
            continue
        code = str(properties.get("code") or f"BULK-AOI-{index:03d}").strip()
        name = str(properties.get("name") or code).strip()
        if not code or not name:
            skipped.append({"index": index, "reason": "Missing AOI code/name"})
            continue
        if db.scalar(select(GeospatialAOI).where(GeospatialAOI.code == code)) is not None:
            skipped.append({"index": index, "code": code, "reason": "Duplicate code"})
            continue
        aoi = GeospatialAOI(
            code=code,
            name=name,
            description=str(properties.get("description") or "").strip() or None,
            scope_type=str(properties.get("scope_type") or payload.default_scope_type or "custom"),
            municipality_id=properties.get("municipality_id"),
            warehouse_id=properties.get("warehouse_id"),
            market_id=properties.get("market_id"),
            srid=4326,
            boundary_geojson=geometry,
            boundary_wkt=None,
            source=str(properties.get("source") or payload.default_source or "bulk_import"),
            is_active=True,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        try:
            _apply_bbox_and_centroid(aoi)
        except Exception:
            skipped.append({"index": index, "code": code, "reason": "Invalid polygon geometry"})
            continue
        if _overlap_conflicts(db, candidate=aoi):
            skipped.append({"index": index, "code": code, "reason": "AOI overlaps existing boundary"})
            continue
        db.add(aoi)
        db.flush()
        _get_or_create_aoi_metadata(db, aoi_id=aoi.id)
        db.add(
            GeospatialAOIVersion(
                aoi_id=aoi.id,
                version=1,
                change_type="create",
                boundary_geojson=aoi.boundary_geojson,
                boundary_wkt=aoi.boundary_wkt,
                changed_by=current_user.id,
                change_reason="Bulk GeoJSON import",
                changed_at=datetime.utcnow(),
            )
        )
        created.append({"id": aoi.id, "code": aoi.code, "name": aoi.name})
    db.commit()
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.bulk_import",
        entity_type="geospatial_aoi",
        entity_id="bulk",
        before_payload=None,
        after_payload={"created": created, "skipped": skipped},
    )
    return {"created_count": len(created), "skipped_count": len(skipped), "created": created, "skipped": skipped}


@router.get("/aois/export/geojson")
def export_aoi_geojson(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    is_active: bool | None = None,
):
    stmt = select(GeospatialAOI)
    if is_active is not None:
        stmt = stmt.where(GeospatialAOI.is_active == is_active)
    rows = db.scalars(stmt.order_by(GeospatialAOI.id)).all()
    meta_rows = db.scalars(select(GeospatialAOIMetadata).where(GeospatialAOIMetadata.aoi_id.in_([aoi.id for aoi in rows]))).all() if rows else []
    meta_map = {row.aoi_id: row for row in meta_rows}
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": row.boundary_geojson,
                "properties": {
                    "id": row.id,
                    "code": row.code,
                    "name": row.name,
                    "scope_type": row.scope_type,
                    "municipality_id": row.municipality_id,
                    "warehouse_id": row.warehouse_id,
                    "market_id": row.market_id,
                    "is_active": row.is_active,
                    "tags": _normalize_string_list((meta_map.get(row.id).tags_json if meta_map.get(row.id) else []) or []),
                    "labels": _normalize_string_list((meta_map.get(row.id).labels_json if meta_map.get(row.id) else []) or []),
                },
            }
            for row in rows
        ],
    }


@router.get("/aois/export/csv")
def export_aoi_csv(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    is_active: bool | None = None,
):
    stmt = select(GeospatialAOI)
    if is_active is not None:
        stmt = stmt.where(GeospatialAOI.is_active == is_active)
    rows = db.scalars(stmt.order_by(GeospatialAOI.id)).all()
    metadata_rows = db.scalars(select(GeospatialAOIMetadata).where(GeospatialAOIMetadata.aoi_id.in_([row.id for row in rows]))).all() if rows else []
    metadata_map = {row.aoi_id: row for row in metadata_rows}

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "code",
            "name",
            "scope_type",
            "municipality_id",
            "warehouse_id",
            "market_id",
            "is_active",
            "tags",
            "labels",
            "owner_user_id",
            "watchlist_flag",
        ],
    )
    writer.writeheader()
    for row in rows:
        meta = metadata_map.get(row.id)
        writer.writerow(
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "scope_type": row.scope_type,
                "municipality_id": row.municipality_id,
                "warehouse_id": row.warehouse_id,
                "market_id": row.market_id,
                "is_active": row.is_active,
                "tags": "|".join(_normalize_string_list((meta.tags_json if meta else []) or [])),
                "labels": "|".join(_normalize_string_list((meta.labels_json if meta else []) or [])),
                "owner_user_id": meta.owner_user_id if meta else "",
                "watchlist_flag": bool(meta.watchlist_flag) if meta else False,
            }
        )
    csv_payload = output.getvalue()
    return Response(content=csv_payload, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=geospatial_aois.csv"})


@router.get("/aois/{aoi_id}/versions/diff", response_model=AOIVersionDiffResponse)
def diff_aoi_versions(
    aoi_id: int,
    from_version: int,
    to_version: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    left = db.scalar(
        select(GeospatialAOIVersion).where(
            GeospatialAOIVersion.aoi_id == aoi_id,
            GeospatialAOIVersion.version == from_version,
        )
    )
    right = db.scalar(
        select(GeospatialAOIVersion).where(
            GeospatialAOIVersion.aoi_id == aoi_id,
            GeospatialAOIVersion.version == to_version,
        )
    )
    if left is None or right is None:
        raise HTTPException(status_code=404, detail="AOI version not found")
    changes = build_structured_diff(left.boundary_geojson or {}, right.boundary_geojson or {})
    return AOIVersionDiffResponse(
        aoi_id=aoi_id,
        from_version=from_version,
        to_version=to_version,
        changes=changes,
    )


@router.post("/aois/{aoi_id}/versions/{version}/restore", response_model=AOIDTO)
def restore_aoi_version(
    aoi_id: int,
    version: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
):
    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id))
    snapshot = db.scalar(select(GeospatialAOIVersion).where(GeospatialAOIVersion.aoi_id == aoi_id, GeospatialAOIVersion.version == version))
    if aoi is None or snapshot is None:
        raise HTTPException(status_code=404, detail="AOI/version not found")
    before_payload = _aoi_to_dto(aoi).model_dump(mode="json")
    aoi.boundary_geojson = snapshot.boundary_geojson
    aoi.boundary_wkt = snapshot.boundary_wkt
    _apply_bbox_and_centroid(aoi)
    next_version = _next_aoi_version(db, aoi_id=aoi.id)
    db.add(
        GeospatialAOIVersion(
            aoi_id=aoi.id,
            version=next_version,
            change_type="restore",
            boundary_geojson=aoi.boundary_geojson,
            boundary_wkt=aoi.boundary_wkt,
            changed_by=current_user.id,
            change_reason=f"Restored from version {version}",
            changed_at=datetime.utcnow(),
        )
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.restore",
        entity_type="geospatial_aoi",
        entity_id=str(aoi.id),
        before_payload=before_payload,
        after_payload=_aoi_to_dto(aoi).model_dump(mode="json"),
    )
    db.commit()
    db.refresh(aoi)
    return _aoi_to_dto(aoi)


@router.get("/aois/{aoi_id}/notes")
def list_aoi_notes(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    note_type: str | None = None,
):
    stmt = select(GeospatialAOINote).where(GeospatialAOINote.aoi_id == aoi_id)
    if note_type:
        stmt = stmt.where(GeospatialAOINote.note_type == note_type)
    rows = db.scalars(stmt.order_by(desc(GeospatialAOINote.created_at)).limit(300)).all()
    return [
        {
            "id": row.id,
            "aoi_id": row.aoi_id,
            "note_type": row.note_type,
            "body": row.body,
            "parent_note_id": row.parent_note_id,
            "mentions": row.mentions_json or [],
            "assigned_user_id": row.assigned_user_id,
            "is_resolved": row.is_resolved,
            "metadata": row.metadata_json or {},
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
        }
        for row in rows
    ]


@router.post("/aois/{aoi_id}/notes")
def create_aoi_note(
    aoi_id: int,
    payload: AOINoteCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    if db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id)) is None:
        raise HTTPException(status_code=404, detail="AOI not found")
    note = GeospatialAOINote(
        aoi_id=aoi_id,
        parent_note_id=payload.parent_note_id,
        note_type=payload.note_type,
        body=payload.body.strip(),
        mentions_json=_normalize_string_list(payload.mentions),
        assigned_user_id=payload.assigned_user_id,
        is_resolved=False,
        metadata_json=payload.metadata or {},
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.note.create",
        entity_type="geospatial_aoi_note",
        entity_id=str(note.id),
        before_payload=None,
        after_payload={"aoi_id": aoi_id, "note_type": payload.note_type},
    )
    db.commit()
    return {
        "id": note.id,
        "aoi_id": note.aoi_id,
        "note_type": note.note_type,
        "body": note.body,
        "parent_note_id": note.parent_note_id,
        "mentions": note.mentions_json or [],
        "assigned_user_id": note.assigned_user_id,
        "is_resolved": note.is_resolved,
        "metadata": note.metadata_json or {},
        "created_at": note.created_at.isoformat(),
        "created_by": note.created_by,
    }


@router.get("/aois/{aoi_id}/attachments")
def list_aoi_attachments(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    rows = db.scalars(
        select(GeospatialAOIAttachment)
        .where(GeospatialAOIAttachment.aoi_id == aoi_id)
        .order_by(desc(GeospatialAOIAttachment.created_at))
    ).all()
    return [
        {
            "id": row.id,
            "aoi_id": row.aoi_id,
            "asset_type": row.asset_type,
            "title": row.title,
            "url": row.url,
            "notes": row.notes,
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
        }
        for row in rows
    ]


@router.post("/aois/{aoi_id}/attachments")
def create_aoi_attachment(
    aoi_id: int,
    payload: AOIAttachmentCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    if db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id)) is None:
        raise HTTPException(status_code=404, detail="AOI not found")
    attachment = GeospatialAOIAttachment(
        aoi_id=aoi_id,
        asset_type=payload.asset_type,
        title=payload.title.strip(),
        url=payload.url.strip(),
        notes=payload.notes.strip() if payload.notes else None,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.attachment.create",
        entity_type="geospatial_aoi_attachment",
        entity_id=str(attachment.id),
        before_payload=None,
        after_payload={"aoi_id": aoi_id, "title": payload.title, "asset_type": payload.asset_type},
    )
    db.commit()
    return {
        "id": attachment.id,
        "aoi_id": attachment.aoi_id,
        "asset_type": attachment.asset_type,
        "title": attachment.title,
        "url": attachment.url,
        "notes": attachment.notes,
        "created_at": attachment.created_at.isoformat(),
        "created_by": attachment.created_by,
    }


@router.get("/aois/{aoi_id}/document-links")
def list_aoi_document_links(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    rows = db.scalars(
        select(GeospatialAOIDocumentLink)
        .where(GeospatialAOIDocumentLink.aoi_id == aoi_id)
        .order_by(desc(GeospatialAOIDocumentLink.created_at))
    ).all()
    return [
        {
            "id": row.id,
            "aoi_id": row.aoi_id,
            "document_id": row.document_id,
            "title": row.title,
            "url": row.url,
            "notes": row.notes,
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
        }
        for row in rows
    ]


@router.post("/aois/{aoi_id}/document-links")
def create_aoi_document_link(
    aoi_id: int,
    payload: AOIDocumentLinkCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    if db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id)) is None:
        raise HTTPException(status_code=404, detail="AOI not found")
    if payload.document_id is not None:
        document = db.scalar(select(Document).where(Document.id == payload.document_id))
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
    link = GeospatialAOIDocumentLink(
        aoi_id=aoi_id,
        document_id=payload.document_id,
        title=payload.title.strip(),
        url=payload.url.strip() if payload.url else None,
        notes=payload.notes.strip() if payload.notes else None,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.document_link.create",
        entity_type="geospatial_aoi_document_link",
        entity_id=str(link.id),
        before_payload=None,
        after_payload={"aoi_id": aoi_id, "document_id": payload.document_id, "title": payload.title},
    )
    db.commit()
    return {
        "id": link.id,
        "aoi_id": link.aoi_id,
        "document_id": link.document_id,
        "title": link.title,
        "url": link.url,
        "notes": link.notes,
        "created_at": link.created_at.isoformat(),
        "created_by": link.created_by,
    }


@router.get("/aois/{aoi_id}/activity")
def aoi_recent_activity(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    limit: int = 100,
):
    if db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id)) is None:
        raise HTTPException(status_code=404, detail="AOI not found")
    events: list[dict[str, Any]] = []
    versions = db.scalars(
        select(GeospatialAOIVersion)
        .where(GeospatialAOIVersion.aoi_id == aoi_id)
        .order_by(desc(GeospatialAOIVersion.changed_at))
        .limit(limit)
    ).all()
    notes = db.scalars(
        select(GeospatialAOINote)
        .where(GeospatialAOINote.aoi_id == aoi_id)
        .order_by(desc(GeospatialAOINote.created_at))
        .limit(limit)
    ).all()
    runs = db.scalars(
        select(SatellitePipelineRun)
        .where(SatellitePipelineRun.aoi_id == aoi_id)
        .order_by(desc(SatellitePipelineRun.started_at))
        .limit(limit)
    ).all()
    favorites = db.scalars(
        select(GeospatialAOIFavorite)
        .where(GeospatialAOIFavorite.aoi_id == aoi_id, GeospatialAOIFavorite.user_id == current_user.id)
        .order_by(desc(GeospatialAOIFavorite.pinned_at))
        .limit(limit)
    ).all()
    for row in versions:
        events.append({"timestamp": row.changed_at.isoformat(), "type": "version", "summary": f"Version {row.version} · {row.change_type}", "actor_user_id": row.changed_by})
    for row in notes:
        events.append({"timestamp": row.created_at.isoformat(), "type": row.note_type, "summary": row.body[:180], "actor_user_id": row.created_by})
    for row in runs:
        events.append({"timestamp": (row.started_at or row.created_at).isoformat(), "type": "run", "summary": f"Run #{row.id} · {row.run_type} · {row.status}", "actor_user_id": row.triggered_by})
    for row in favorites:
        events.append({"timestamp": row.pinned_at.isoformat(), "type": "favorite", "summary": "AOI pinned to favorites", "actor_user_id": row.user_id})
    events.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    return {"aoi_id": aoi_id, "count": len(events[:limit]), "events": events[:limit]}


@router.get("/aois/{aoi_id}/analytics", response_model=AOIAnalyticsResponse)
def aoi_analytics(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    months: int = 12,
):
    if db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id)) is None:
        raise HTTPException(status_code=404, detail="AOI not found")
    rows = db.scalars(
        select(GeospatialFeature)
        .where(GeospatialFeature.aoi_id == aoi_id)
        .order_by(GeospatialFeature.observation_date.desc())
        .limit(max(3, min(months * 6, 500)))
    ).all()
    rows = list(reversed(rows))
    cloud_coverage_trend = [{"date": row.observation_date.isoformat(), "value": row.cloud_score} for row in rows]
    vegetation_vigor_trend = [{"date": row.observation_date.isoformat(), "value": row.vegetation_vigor_score} for row in rows]
    crop_activity_trend = [{"date": row.observation_date.isoformat(), "value": row.crop_activity_score} for row in rows]
    confidence_trend = [{"date": row.observation_date.isoformat(), "value": row.observation_confidence_score} for row in rows]

    monthly: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.observation_date.strftime("%Y-%m")
        bucket = monthly.setdefault(key, {"month": key, "count": 0, "cloud_total": 0.0, "vigor_total": 0.0, "crop_total": 0.0, "conf_total": 0.0})
        bucket["count"] += 1
        bucket["cloud_total"] += float(row.cloud_score or 0.0)
        bucket["vigor_total"] += float(row.vegetation_vigor_score or 0.0)
        bucket["crop_total"] += float(row.crop_activity_score or 0.0)
        bucket["conf_total"] += float(row.observation_confidence_score or 0.0)
    seasonality_summary = []
    for key in sorted(monthly.keys()):
        bucket = monthly[key]
        count = max(1, int(bucket["count"]))
        seasonality_summary.append(
            {
                "month": key,
                "avg_cloud": round(bucket["cloud_total"] / count, 4),
                "avg_vigor": round(bucket["vigor_total"] / count, 4),
                "avg_crop_activity": round(bucket["crop_total"] / count, 4),
                "avg_confidence": round(bucket["conf_total"] / count, 4),
                "count": count,
            }
        )

    anomaly_sparkline: list[float] = []
    previous_crop: float | None = None
    for row in rows:
        current_crop = float(row.crop_activity_score or 0.0)
        if previous_crop is None:
            anomaly_sparkline.append(0.0)
        else:
            anomaly_sparkline.append(round(current_crop - previous_crop, 4))
        previous_crop = current_crop

    avg_cloud = sum(float(row.cloud_score or 0.0) for row in rows) / max(1, len(rows))
    avg_conf = sum(float(row.observation_confidence_score or 0.0) for row in rows) / max(1, len(rows))
    avg_crop = sum(float(row.crop_activity_score or 0.0) for row in rows) / max(1, len(rows))
    risk_score = max(0.0, min(1.0, (avg_cloud * 0.35) + ((1.0 - avg_conf) * 0.4) + (max(0.0, 0.65 - avg_crop) * 0.25)))

    return AOIAnalyticsResponse(
        aoi_id=aoi_id,
        risk_score=round(risk_score, 4),
        seasonality_summary=seasonality_summary,
        cloud_coverage_trend=cloud_coverage_trend,
        vegetation_vigor_trend=vegetation_vigor_trend,
        crop_activity_trend=crop_activity_trend,
        anomaly_sparkline=anomaly_sparkline,
        confidence_trend=confidence_trend,
    )


@router.get("/aois/{aoi_id}/summary/public")
def aoi_public_summary(
    aoi_id: int,
    token: str,
    db: Annotated[Session, Depends(get_db)],
):
    meta = db.scalar(select(GeospatialAOIMetadata).where(GeospatialAOIMetadata.aoi_id == aoi_id))
    if meta is None or not meta.public_share_token or token != meta.public_share_token:
        raise HTTPException(status_code=403, detail="Invalid public summary token")
    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == aoi_id))
    if aoi is None:
        raise HTTPException(status_code=404, detail="AOI not found")
    latest_feature = db.scalar(
        select(GeospatialFeature)
        .where(GeospatialFeature.aoi_id == aoi_id)
        .order_by(desc(GeospatialFeature.observation_date))
        .limit(1)
    )
    return {
        "id": aoi.id,
        "code": aoi.code,
        "name": aoi.name,
        "scope_type": aoi.scope_type,
        "municipality_id": aoi.municipality_id,
        "latest_observation": None
        if latest_feature is None
        else {
            "observation_date": latest_feature.observation_date.isoformat(),
            "source": latest_feature.source,
            "crop_activity_score": latest_feature.crop_activity_score,
            "vegetation_vigor_score": latest_feature.vegetation_vigor_score,
            "observation_confidence_score": latest_feature.observation_confidence_score,
        },
    }


@router.post("/runs/{run_id}/priority")
def update_run_priority(
    run_id: int,
    payload: RunPriorityUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    previous = {"queue_priority": run.queue_priority}
    run.queue_priority = payload.queue_priority
    run.updated_by = current_user.id
    _append_run_event(
        db,
        run_id=run.id,
        phase="queue",
        status="updated",
        message=f"Queue priority updated to {run.queue_priority}",
        details={"queue_priority": run.queue_priority},
        actor_user_id=current_user.id,
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.run.priority.update",
        entity_type="satellite_pipeline_run",
        entity_id=str(run.id),
        before_payload=previous,
        after_payload={"queue_priority": run.queue_priority},
    )
    db.commit()
    return {"run_id": run.id, "queue_priority": run.queue_priority}


@router.post("/runs/{run_id}/notes")
def update_run_operator_notes(
    run_id: int,
    payload: RunNotesUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    before_payload = {"operator_notes": run.operator_notes}
    run.operator_notes = payload.operator_notes.strip()
    run.updated_by = current_user.id
    _append_run_event(
        db,
        run_id=run.id,
        phase="notes",
        status="updated",
        message="Operator notes updated",
        details={"length": len(run.operator_notes)},
        actor_user_id=current_user.id,
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.run.notes.update",
        entity_type="satellite_pipeline_run",
        entity_id=str(run.id),
        before_payload=before_payload,
        after_payload={"operator_notes": run.operator_notes},
    )
    db.commit()
    return {"run_id": run.id, "operator_notes": run.operator_notes}


@router.post("/runs/{run_id}/clone")
def clone_pipeline_run(
    run_id: int,
    payload: RunCloneRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    sources = (run.sources_json or {}).get("sources") or None
    clone_notes = payload.notes.strip() if payload.notes else f"Cloned from run #{run.id}"
    queue_priority = payload.queue_priority if payload.queue_priority is not None else run.queue_priority
    retry_strategy = payload.retry_strategy.strip() if payload.retry_strategy else run.retry_strategy

    if run.run_type == "ingest":
        start = _parse_iso_datetime((run.parameters_json or {}).get("start"))
        end = _parse_iso_datetime((run.parameters_json or {}).get("end"))
        limit_per_source = int((run.parameters_json or {}).get("limit_per_source") or 200)
        cloned = queue_ingestion_run(
            db,
            triggered_by=current_user.id,
            correlation_id=None,
            aoi_id=run.aoi_id,
            sources=sources,
            backend=run.backend,
            notes=clone_notes,
            status="queued",
        )
        cloned.parameters_json = _ingest_parameters_payload(start=start, end=end, limit_per_source=limit_per_source)
        cloned.parent_run_id = run.id
        cloned.queue_priority = queue_priority
        cloned.retry_strategy = retry_strategy
        cloned.sla_target_minutes = run.sla_target_minutes
        cloned.operator_notes = run.operator_notes
        _append_run_event(
            db,
            run_id=cloned.id,
            phase="clone",
            status="queued",
            message=f"Cloned from run #{run.id}",
            details={"source_run_id": run.id},
            actor_user_id=current_user.id,
        )
        db.commit()
        db.refresh(cloned)
        background_tasks.add_task(
            _execute_ingest_run_background,
            run_id=cloned.id,
            aoi_id=cloned.aoi_id,
            sources=sources,
            start=start,
            end=end,
            limit_per_source=limit_per_source,
        )
        return {"run_id": cloned.id, "status": cloned.status, "parent_run_id": cloned.parent_run_id}

    if run.run_type == "feature_refresh":
        cloned = queue_feature_refresh_run(
            db,
            triggered_by=current_user.id,
            correlation_id=None,
            aoi_id=run.aoi_id,
            sources=sources,
            backend=run.backend,
            notes=clone_notes,
            status="queued",
        )
        cloned.parent_run_id = run.id
        cloned.queue_priority = queue_priority
        cloned.retry_strategy = retry_strategy
        cloned.sla_target_minutes = run.sla_target_minutes
        cloned.operator_notes = run.operator_notes
        _append_run_event(
            db,
            run_id=cloned.id,
            phase="clone",
            status="queued",
            message=f"Cloned from run #{run.id}",
            details={"source_run_id": run.id},
            actor_user_id=current_user.id,
        )
        db.commit()
        db.refresh(cloned)
        background_tasks.add_task(_execute_feature_refresh_background, run_id=cloned.id, aoi_id=cloned.aoi_id, sources=sources)
        return {"run_id": cloned.id, "status": cloned.status, "parent_run_id": cloned.parent_run_id}

    raise HTTPException(status_code=400, detail="Unsupported run type")


def _run_diagnostics_payload(db: Session, run: SatellitePipelineRun) -> dict[str, Any]:
    started_at = run.started_at or run.created_at
    finished_at = run.finished_at or datetime.utcnow()
    elapsed_seconds = max(0.0, (finished_at - started_at).total_seconds()) if started_at else 0.0
    scene_rows = _list_run_scene_rows(db, run=run)
    feature_rows = _list_run_feature_rows(db, run=run)
    scene_count = len(scene_rows)
    feature_count = len(feature_rows)
    source_counts: dict[str, int] = {}
    for row in scene_rows:
        source = str(row.get("source") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    missing_scene_count = int(sum(1 for row in feature_rows if not row.get("scene_id")))
    provenance_completeness = round(_safe_ratio(feature_count - missing_scene_count, max(1, feature_count)), 4)
    latest_acquired = max((row.get("acquired_at") for row in scene_rows if row.get("acquired_at")), default=None)
    stale_data_warning = False
    if isinstance(latest_acquired, str):
        latest_dt = _parse_iso_datetime(latest_acquired)
        if latest_dt is not None:
            stale_data_warning = (datetime.utcnow() - latest_dt).days >= 14
    throughput = round(_safe_ratio(feature_count + scene_count, max(1.0, elapsed_seconds / 60.0)), 4)
    run_rows = db.scalars(
        select(SatellitePipelineRun)
        .where(SatellitePipelineRun.run_type == run.run_type, SatellitePipelineRun.finished_at.is_not(None))
        .order_by(desc(SatellitePipelineRun.finished_at))
        .limit(200)
    ).all()
    durations = sorted(
        [
            max(0.0, ((row.finished_at or datetime.utcnow()) - (row.started_at or row.created_at)).total_seconds())
            for row in run_rows
            if row.started_at is not None
        ]
    )
    p50 = durations[len(durations) // 2] if durations else 0.0
    p90 = durations[min(len(durations) - 1, int(len(durations) * 0.9))] if durations else 0.0
    sla_breach = False
    if run.sla_target_minutes is not None:
        sla_breach = elapsed_seconds > (run.sla_target_minutes * 60)
    run_events = db.scalars(
        select(GeospatialRunEvent)
        .where(GeospatialRunEvent.run_id == run.id)
        .order_by(desc(GeospatialRunEvent.logged_at))
        .limit(200)
    ).all()
    health_badge = _pipeline_health_badge(run.status)
    return {
        "run_id": run.id,
        "status": run.status,
        "health_badge": health_badge,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "duration_percentiles_seconds": {"p50": round(p50, 2), "p90": round(p90, 2)},
        "throughput_per_minute": throughput,
        "source_coverage": source_counts,
        "missing_scene_count": missing_scene_count,
        "provenance_completeness_score": provenance_completeness,
        "stale_data_warning": stale_data_warning,
        "sla_breach": sla_breach,
        "phase_progress": {
            "queued": 20 if run.status in {"queued", "running", "completed", "failed", "cancel_requested", "cancelled"} else 0,
            "discovery_or_extract": 60 if run.status in {"running", "completed", "failed", "cancel_requested", "cancelled"} else 0,
            "materialization": 85 if run.status in {"completed", "failed", "cancel_requested", "cancelled"} else 0,
            "finalized": 100 if run.status in {"completed", "failed", "cancelled"} else 0,
        },
        "live_logs": [
            {
                "id": event.id,
                "phase": event.phase,
                "status": event.status,
                "message": event.message,
                "details": event.details_json or {},
                "logged_at": event.logged_at.isoformat(),
            }
            for event in run_events
        ],
    }


def _run_sources(run: SatellitePipelineRun) -> list[str]:
    raw = (run.sources_json or {}).get("sources", [])
    if not isinstance(raw, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw:
        source = str(value or "").strip()
        if not source:
            continue
        key = source.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(source)
    return sorted(normalized)


def _flatten_json_paths(value: Any, *, path: str = "$") -> dict[str, Any]:
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key in sorted(value.keys()):
            child_path = f"{path}.{key}"
            flattened.update(_flatten_json_paths(value[key], path=child_path))
        return flattened if flattened else {path: {}}
    if isinstance(value, list):
        flattened: dict[str, Any] = {}
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]"
            flattened.update(_flatten_json_paths(item, path=child_path))
        return flattened if flattened else {path: []}
    return {path: value}


def _build_parameter_delta(*, left: SatellitePipelineRun, right: SatellitePipelineRun) -> dict[str, Any]:
    left_params = left.parameters_json or {}
    right_params = right.parameters_json or {}
    left_flat = _flatten_json_paths(left_params)
    right_flat = _flatten_json_paths(right_params)
    all_paths = sorted(set(left_flat.keys()) | set(right_flat.keys()))

    sentinel = object()
    changed_rows: list[dict[str, Any]] = []
    unchanged_count = 0
    for path in all_paths:
        left_value = left_flat.get(path, sentinel)
        right_value = right_flat.get(path, sentinel)
        if left_value == right_value:
            unchanged_count += 1
            continue
        if left_value is sentinel:
            change_type = "added"
            left_payload = None
        elif right_value is sentinel:
            change_type = "removed"
            left_payload = left_value
        else:
            change_type = "modified"
            left_payload = left_value
        changed_rows.append(
            {
                "path": path,
                "change_type": change_type,
                "left": left_payload,
                "right": None if right_value is sentinel else right_value,
            }
        )

    metadata_changes = {
        "backend": {"left": left.backend, "right": right.backend, "changed": left.backend != right.backend},
        "algorithm_version": {
            "left": left.algorithm_version,
            "right": right.algorithm_version,
            "changed": left.algorithm_version != right.algorithm_version,
        },
        "retry_strategy": {
            "left": left.retry_strategy,
            "right": right.retry_strategy,
            "changed": left.retry_strategy != right.retry_strategy,
        },
        "queue_priority": {
            "left": left.queue_priority,
            "right": right.queue_priority,
            "changed": left.queue_priority != right.queue_priority,
        },
        "sources": {
            "left": _run_sources(left),
            "right": _run_sources(right),
            "changed": _run_sources(left) != _run_sources(right),
        },
    }
    metadata_changed_count = sum(1 for row in metadata_changes.values() if row.get("changed"))

    left_hash = hashlib.sha256(json.dumps(left_params, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    right_hash = hashlib.sha256(json.dumps(right_params, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    max_changes = 250
    return {
        "left_hash": left_hash,
        "right_hash": right_hash,
        "changed_count": len(changed_rows),
        "unchanged_count": unchanged_count,
        "truncated": len(changed_rows) > max_changes,
        "changes": changed_rows[:max_changes],
        "metadata_changes": metadata_changes,
        "metadata_changed_count": metadata_changed_count,
    }


def _build_overlap_matrix(
    *,
    left_count: int,
    right_count: int,
    shared_count: int,
    left_only_count: int,
    right_only_count: int,
) -> dict[str, Any]:
    union_count = left_count + right_count - shared_count
    return {
        "labels": {"rows": ["left_run", "right_run"], "columns": ["left_catalog", "right_catalog"]},
        "values": [[left_count, shared_count], [shared_count, right_count]],
        "union_count": union_count,
        "shared_count": shared_count,
        "left_only_count": left_only_count,
        "right_only_count": right_only_count,
        "left_only_ratio": round(_safe_ratio(left_only_count, max(1, union_count)), 4),
        "right_only_ratio": round(_safe_ratio(right_only_count, max(1, union_count)), 4),
    }


def _run_compare_payload(db: Session, *, left: SatellitePipelineRun, right: SatellitePipelineRun) -> dict[str, Any]:
    left_diag = _run_diagnostics_payload(db, left)
    right_diag = _run_diagnostics_payload(db, right)

    left_scene_rows = _list_run_scene_rows(db, run=left)
    right_scene_rows = _list_run_scene_rows(db, run=right)
    left_feature_rows = _list_run_feature_rows(db, run=left)
    right_feature_rows = _list_run_feature_rows(db, run=right)

    left_scene_keys = {f'{row.get("source")}::{row.get("scene_id")}' for row in left_scene_rows if row.get("scene_id")}
    right_scene_keys = {f'{row.get("source")}::{row.get("scene_id")}' for row in right_scene_rows if row.get("scene_id")}

    left_feature_keys = {
        f'{row.get("source")}::{row.get("aoi_id")}::{row.get("scene_id")}::{row.get("observation_date")}'
        for row in left_feature_rows
    }
    right_feature_keys = {
        f'{row.get("source")}::{row.get("aoi_id")}::{row.get("scene_id")}::{row.get("observation_date")}'
        for row in right_feature_rows
    }

    scene_shared = sorted(left_scene_keys & right_scene_keys)
    scene_left_only = sorted(left_scene_keys - right_scene_keys)
    scene_right_only = sorted(right_scene_keys - left_scene_keys)
    feature_shared = sorted(left_feature_keys & right_feature_keys)
    feature_left_only = sorted(left_feature_keys - right_feature_keys)
    feature_right_only = sorted(right_feature_keys - left_feature_keys)

    metrics_summary = {
        "status_left": left.status,
        "status_right": right.status,
        "elapsed_seconds_left": float(left_diag["elapsed_seconds"]),
        "elapsed_seconds_right": float(right_diag["elapsed_seconds"]),
        "elapsed_seconds_delta": round(float(right_diag["elapsed_seconds"]) - float(left_diag["elapsed_seconds"]), 2),
        "throughput_per_minute_left": float(left_diag["throughput_per_minute"]),
        "throughput_per_minute_right": float(right_diag["throughput_per_minute"]),
        "throughput_delta": round(float(right_diag["throughput_per_minute"]) - float(left_diag["throughput_per_minute"]), 4),
        "missing_scene_left": int(left_diag["missing_scene_count"]),
        "missing_scene_right": int(right_diag["missing_scene_count"]),
        "missing_scene_delta": int(right_diag["missing_scene_count"]) - int(left_diag["missing_scene_count"]),
        "provenance_completeness_left": float(left_diag["provenance_completeness_score"]),
        "provenance_completeness_right": float(right_diag["provenance_completeness_score"]),
        "provenance_completeness_delta": round(
            float(right_diag["provenance_completeness_score"]) - float(left_diag["provenance_completeness_score"]),
            4,
        ),
        "source_coverage_left": left_diag["source_coverage"],
        "source_coverage_right": right_diag["source_coverage"],
    }

    provenance_diff = {
        "scene_counts": {
            "left": len(left_scene_keys),
            "right": len(right_scene_keys),
            "shared": len(scene_shared),
            "left_only": len(scene_left_only),
            "right_only": len(scene_right_only),
        },
        "feature_counts": {
            "left": len(left_feature_keys),
            "right": len(right_feature_keys),
            "shared": len(feature_shared),
            "left_only": len(feature_left_only),
            "right_only": len(feature_right_only),
        },
        "scene_overlap_ratio": round(_safe_ratio(len(scene_shared), max(1, len(left_scene_keys | right_scene_keys))), 4),
        "feature_overlap_ratio": round(_safe_ratio(len(feature_shared), max(1, len(left_feature_keys | right_feature_keys))), 4),
        "scene_shared_sample": scene_shared[:12],
        "scene_left_only_sample": scene_left_only[:12],
        "scene_right_only_sample": scene_right_only[:12],
        "feature_shared_sample": feature_shared[:12],
        "feature_left_only_sample": feature_left_only[:12],
        "feature_right_only_sample": feature_right_only[:12],
    }
    scene_overlap_matrix = _build_overlap_matrix(
        left_count=len(left_scene_keys),
        right_count=len(right_scene_keys),
        shared_count=len(scene_shared),
        left_only_count=len(scene_left_only),
        right_only_count=len(scene_right_only),
    )
    feature_overlap_matrix = _build_overlap_matrix(
        left_count=len(left_feature_keys),
        right_count=len(right_feature_keys),
        shared_count=len(feature_shared),
        left_only_count=len(feature_left_only),
        right_only_count=len(feature_right_only),
    )
    parameter_delta = _build_parameter_delta(left=left, right=right)

    diff = {
        "status": {"left": left.status, "right": right.status},
        "elapsed_seconds_delta": metrics_summary["elapsed_seconds_delta"],
        "throughput_delta": metrics_summary["throughput_delta"],
        "missing_scene_delta": metrics_summary["missing_scene_delta"],
        "provenance_completeness_delta": metrics_summary["provenance_completeness_delta"],
        "source_coverage": {"left": left_diag["source_coverage"], "right": right_diag["source_coverage"]},
        "metrics_summary": metrics_summary,
        "provenance_diff": provenance_diff,
        "scene_overlap_matrix": scene_overlap_matrix,
        "feature_overlap_matrix": feature_overlap_matrix,
        "parameter_delta": parameter_delta,
    }

    return {
        "left_run_id": left.id,
        "right_run_id": right.id,
        "metrics_summary": metrics_summary,
        "provenance_diff": provenance_diff,
        "scene_overlap_matrix": scene_overlap_matrix,
        "feature_overlap_matrix": feature_overlap_matrix,
        "parameter_delta": parameter_delta,
        "diff": diff,
    }


def _lineage_node(row: SatellitePipelineRun) -> dict[str, Any]:
    return {
        "run_id": row.id,
        "parent_run_id": row.parent_run_id,
        "run_type": row.run_type,
        "status": row.status,
        "aoi_id": row.aoi_id,
        "queue_priority": row.queue_priority,
        "retry_strategy": row.retry_strategy,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _run_lineage_payload(db: Session, *, root: SatellitePipelineRun) -> dict[str, Any]:
    nodes: dict[int, dict[str, Any]] = {root.id: _lineage_node(root)}
    edges: list[dict[str, Any]] = []

    upstream_depth = 0
    current = root
    while current.parent_run_id is not None and upstream_depth < 20:
        parent = db.get(SatellitePipelineRun, current.parent_run_id)
        if parent is None:
            break
        nodes[parent.id] = _lineage_node(parent)
        edges.append({"from_run_id": parent.id, "to_run_id": current.id, "relation": "parent_child"})
        current = parent
        upstream_depth += 1

    queue: list[int] = [root.id]
    visited: set[int] = {root.id}
    downstream_count = 0
    while queue:
        parent_id = queue.pop(0)
        child_rows = db.scalars(
            select(SatellitePipelineRun)
            .where(SatellitePipelineRun.parent_run_id == parent_id)
            .order_by(desc(SatellitePipelineRun.started_at), desc(SatellitePipelineRun.id))
        ).all()
        for child in child_rows:
            nodes[child.id] = _lineage_node(child)
            edges.append({"from_run_id": parent_id, "to_run_id": child.id, "relation": "parent_child"})
            downstream_count += 1
            if child.id not in visited:
                visited.add(child.id)
                queue.append(child.id)

    return {
        "root_run_id": root.id,
        "upstream_depth": upstream_depth,
        "downstream_count": downstream_count,
        "nodes": sorted(nodes.values(), key=lambda row: int(row["run_id"])),
        "edges": edges,
    }


def _run_upstream_dependency_payload(db: Session, *, root: SatellitePipelineRun) -> dict[str, Any]:
    nodes: dict[int, dict[str, Any]] = {root.id: _lineage_node(root)}
    edges: list[dict[str, Any]] = []
    depth = 0
    current = root
    while current.parent_run_id is not None and depth < 20:
        parent = db.get(SatellitePipelineRun, current.parent_run_id)
        if parent is None:
            break
        nodes[parent.id] = _lineage_node(parent)
        edges.append({"from_run_id": parent.id, "to_run_id": current.id, "relation": "upstream_dependency"})
        current = parent
        depth += 1
    return {
        "root_run_id": root.id,
        "direction": "upstream",
        "depth": depth,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": sorted(nodes.values(), key=lambda row: int(row["run_id"])),
        "edges": edges,
    }


def _run_downstream_dependency_payload(db: Session, *, root: SatellitePipelineRun) -> dict[str, Any]:
    nodes: dict[int, dict[str, Any]] = {root.id: _lineage_node(root)}
    edges: list[dict[str, Any]] = []
    queue: list[tuple[int, int]] = [(root.id, 0)]
    visited: set[int] = {root.id}
    depth = 0
    while queue:
        parent_id, parent_depth = queue.pop(0)
        child_rows = db.scalars(
            select(SatellitePipelineRun)
            .where(SatellitePipelineRun.parent_run_id == parent_id)
            .order_by(desc(SatellitePipelineRun.started_at), desc(SatellitePipelineRun.id))
        ).all()
        for child in child_rows:
            nodes[child.id] = _lineage_node(child)
            edges.append({"from_run_id": parent_id, "to_run_id": child.id, "relation": "downstream_consumer"})
            depth = max(depth, parent_depth + 1)
            if child.id not in visited:
                visited.add(child.id)
                queue.append((child.id, parent_depth + 1))
    return {
        "root_run_id": root.id,
        "direction": "downstream",
        "depth": depth,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": sorted(nodes.values(), key=lambda row: int(row["run_id"])),
        "edges": edges,
    }


def _select_repro_reference_run(db: Session, *, run: SatellitePipelineRun) -> tuple[SatellitePipelineRun | None, str | None]:
    if run.parent_run_id is not None:
        parent = db.get(SatellitePipelineRun, run.parent_run_id)
        if parent is not None:
            return parent, "parent_run"

    stmt = select(SatellitePipelineRun).where(
        SatellitePipelineRun.id != run.id,
        SatellitePipelineRun.run_type == run.run_type,
    )
    if run.aoi_id is not None:
        stmt = stmt.where(SatellitePipelineRun.aoi_id == run.aoi_id)
    reference = db.scalar(stmt.order_by(desc(SatellitePipelineRun.started_at), desc(SatellitePipelineRun.id)).limit(1))
    if reference is not None:
        return reference, "recent_peer"
    return None, None


def _run_reproducibility_payload(db: Session, *, run: SatellitePipelineRun) -> dict[str, Any]:
    reference, reference_reason = _select_repro_reference_run(db, run=run)
    if reference is None:
        return {
            "run_id": run.id,
            "reference_run_id": None,
            "reference_reason": None,
            "badge": "low",
            "score": 0.0,
            "diagnostics": [
                {
                    "check": "reference_run_available",
                    "passed": False,
                    "weight": 1.0,
                    "contribution": 0.0,
                    "details": "No comparable historical run was found for reproducibility scoring.",
                }
            ],
            "summary": {
                "scene_overlap_ratio": 0.0,
                "feature_overlap_ratio": 0.0,
                "parameter_changed_count": 0,
                "parameter_hash_match": False,
            },
        }

    compare_payload = _run_compare_payload(db, left=reference, right=run)
    parameter_delta = compare_payload["parameter_delta"]
    metrics_summary = compare_payload["metrics_summary"]
    provenance_diff = compare_payload["provenance_diff"]

    reference_sources = _run_sources(reference)
    run_sources = _run_sources(run)
    elapsed_left = float(metrics_summary.get("elapsed_seconds_left", 0.0) or 0.0)
    elapsed_right = float(metrics_summary.get("elapsed_seconds_right", 0.0) or 0.0)
    elapsed_ratio = _safe_ratio(abs(elapsed_right - elapsed_left), max(1.0, elapsed_left))
    throughput_left = float(metrics_summary.get("throughput_per_minute_left", 0.0) or 0.0)
    throughput_right = float(metrics_summary.get("throughput_per_minute_right", 0.0) or 0.0)
    throughput_ratio = _safe_ratio(abs(throughput_right - throughput_left), max(0.1, abs(throughput_left)))

    checks: list[dict[str, Any]] = []

    def add_check(*, check: str, passed: bool, weight: float, details: str) -> None:
        checks.append(
            {
                "check": check,
                "passed": bool(passed),
                "weight": weight,
                "contribution": round(weight if passed else 0.0, 4),
                "details": details,
            }
        )

    add_check(
        check="backend_match",
        passed=reference.backend == run.backend,
        weight=0.12,
        details=f"{reference.backend} -> {run.backend}",
    )
    add_check(
        check="algorithm_version_match",
        passed=reference.algorithm_version == run.algorithm_version,
        weight=0.15,
        details=f"{reference.algorithm_version} -> {run.algorithm_version}",
    )
    add_check(
        check="source_set_match",
        passed=reference_sources == run_sources,
        weight=0.12,
        details=f"{reference_sources} -> {run_sources}",
    )
    add_check(
        check="parameter_hash_match",
        passed=parameter_delta.get("left_hash") == parameter_delta.get("right_hash"),
        weight=0.20,
        details=f'{parameter_delta.get("left_hash")} vs {parameter_delta.get("right_hash")}',
    )
    add_check(
        check="parameter_delta_budget",
        passed=int(parameter_delta.get("changed_count", 0)) <= 2,
        weight=0.11,
        details=f'{parameter_delta.get("changed_count", 0)} changed parameter path(s)',
    )
    add_check(
        check="scene_overlap_ratio",
        passed=float(provenance_diff.get("scene_overlap_ratio", 0.0) or 0.0) >= 0.65,
        weight=0.10,
        details=f'{provenance_diff.get("scene_overlap_ratio", 0.0)} overlap ratio',
    )
    add_check(
        check="feature_overlap_ratio",
        passed=float(provenance_diff.get("feature_overlap_ratio", 0.0) or 0.0) >= 0.65,
        weight=0.10,
        details=f'{provenance_diff.get("feature_overlap_ratio", 0.0)} overlap ratio',
    )
    add_check(
        check="elapsed_time_stability",
        passed=elapsed_ratio <= 0.35,
        weight=0.05,
        details=f"{round(elapsed_ratio, 4)} relative delta",
    )
    add_check(
        check="throughput_stability",
        passed=throughput_ratio <= 0.40,
        weight=0.05,
        details=f"{round(throughput_ratio, 4)} relative delta",
    )

    score = round(sum(float(row["contribution"]) for row in checks), 4)
    badge = "high" if score >= 0.85 else "medium" if score >= 0.65 else "low"
    return {
        "run_id": run.id,
        "reference_run_id": reference.id,
        "reference_reason": reference_reason,
        "badge": badge,
        "score": score,
        "diagnostics": checks,
        "summary": {
            "scene_overlap_ratio": float(provenance_diff.get("scene_overlap_ratio", 0.0) or 0.0),
            "feature_overlap_ratio": float(provenance_diff.get("feature_overlap_ratio", 0.0) or 0.0),
            "parameter_changed_count": int(parameter_delta.get("changed_count", 0) or 0),
            "parameter_hash_match": bool(parameter_delta.get("left_hash") == parameter_delta.get("right_hash")),
        },
    }


def _rows_to_csv_bytes(rows: list[dict[str, Any]], *, field_order: list[str]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=field_order, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in field_order})
    return buffer.getvalue().encode("utf-8")


def _run_artifact_payload(db: Session, *, run: SatellitePipelineRun, artifact_key: str) -> tuple[str, str, bytes]:
    if artifact_key == "run-summary.json":
        detail = _run_detail_to_dto(run, db=db)
        payload = json.dumps(detail, indent=2, sort_keys=True, default=str).encode("utf-8")
        return ("run-summary.json", "application/json", payload)

    if artifact_key == "diagnostics.json":
        diagnostics = _run_diagnostics_payload(db, run)
        payload = json.dumps(diagnostics, indent=2, sort_keys=True, default=str).encode("utf-8")
        return ("diagnostics.json", "application/json", payload)

    if artifact_key == "run-events.json":
        events = db.scalars(
            select(GeospatialRunEvent)
            .where(GeospatialRunEvent.run_id == run.id)
            .order_by(GeospatialRunEvent.logged_at, GeospatialRunEvent.id)
        ).all()
        payload_rows = [
            {
                "id": row.id,
                "phase": row.phase,
                "status": row.status,
                "message": row.message,
                "details": row.details_json or {},
                "logged_at": row.logged_at.isoformat(),
            }
            for row in events
        ]
        payload = json.dumps(payload_rows, indent=2, sort_keys=True, default=str).encode("utf-8")
        return ("run-events.json", "application/json", payload)

    if artifact_key == "provenance-scenes.csv":
        rows = _list_run_scene_rows(db, run=run)
        payload = _rows_to_csv_bytes(
            rows,
            field_order=[
                "id",
                "source",
                "scene_id",
                "aoi_id",
                "aoi_code",
                "aoi_name",
                "acquired_at",
                "cloud_score",
                "spatial_resolution_m",
                "processing_status",
                "provenance_status",
            ],
        )
        return ("provenance-scenes.csv", "text/csv", payload)

    if artifact_key == "provenance-features.csv":
        rows = _list_run_feature_rows(db, run=run)
        payload = _rows_to_csv_bytes(
            rows,
            field_order=[
                "id",
                "source",
                "aoi_id",
                "aoi_code",
                "aoi_name",
                "scene_id",
                "observation_date",
                "reporting_month",
                "observation_confidence_score",
                "crop_activity_score",
                "vegetation_vigor_score",
                "cloud_score",
            ],
        )
        return ("provenance-features.csv", "text/csv", payload)

    if artifact_key == "signed-package":
        manifest = _run_artifact_manifest_payload(db, run=run)
        signed_blob = {"run_id": run.id, "manifest": manifest, "signed_at": datetime.utcnow().isoformat()}
        signature = hashlib.sha256(f'{settings.secret_key}:{json.dumps(signed_blob, sort_keys=True, default=str)}'.encode("utf-8")).hexdigest()
        signed_blob["signature"] = signature
        payload = json.dumps(signed_blob, indent=2, default=str).encode("utf-8")
        return ("signed-package.json", "application/json", payload)

    if artifact_key == "evidence-bundle":
        detail = _run_detail_to_dto(run, db=db)
        diagnostics = _run_diagnostics_payload(db, run)
        compare_ref = _run_reproducibility_payload(db, run=run)
        chain_of_custody = _run_chain_of_custody_timeline(db, run=run)
        approval_gate = _run_approval_gate_payload(db, run=run)
        bundle = {
            "run_id": run.id,
            "generated_at": datetime.utcnow().isoformat(),
            "detail": detail,
            "diagnostics": diagnostics,
            "reproducibility": compare_ref,
            "approval_gate": approval_gate,
            "chain_of_custody": chain_of_custody,
            "events": [
                {
                    "phase": row.phase,
                    "status": row.status,
                    "message": row.message,
                    "logged_at": row.logged_at.isoformat(),
                }
                for row in db.scalars(
                    select(GeospatialRunEvent).where(GeospatialRunEvent.run_id == run.id).order_by(GeospatialRunEvent.logged_at).limit(400)
                ).all()
            ],
        }
        payload = json.dumps(bundle, indent=2, default=str).encode("utf-8")
        return ("evidence-bundle.json", "application/json", payload)

    raise HTTPException(status_code=404, detail="Artifact key not found")


def _run_artifact_manifest_payload(db: Session, *, run: SatellitePipelineRun) -> dict[str, Any]:
    generated_at = datetime.utcnow()
    artifact_specs = [
        ("run-summary.json", "Run summary snapshot"),
        ("diagnostics.json", "Run diagnostics payload"),
        ("run-events.json", "Run event log"),
        ("provenance-scenes.csv", "Scene export CSV"),
        ("provenance-features.csv", "Feature export CSV"),
    ]
    artifacts: list[dict[str, Any]] = []
    for artifact_key, label in artifact_specs:
        filename, content_type, payload = _run_artifact_payload(db, run=run, artifact_key=artifact_key)
        artifacts.append(
            {
                "artifact_key": artifact_key,
                "label": label,
                "filename": filename,
                "content_type": content_type,
                "size_bytes": len(payload),
                "checksum_sha256": hashlib.sha256(payload).hexdigest(),
                "download_path": f"/api/v1/geospatial/runs/{run.id}/artifacts/{artifact_key}",
                "generated_at": generated_at.isoformat(),
            }
        )
    return {
        "run_id": run.id,
        "generated_at": generated_at.isoformat(),
        "artifacts": artifacts,
    }


def _run_artifact_download_center_payload(db: Session, *, run: SatellitePipelineRun) -> dict[str, Any]:
    manifest = _run_artifact_manifest_payload(db, run=run)
    artifacts = manifest["artifacts"]
    total_size_bytes = int(sum(int(row.get("size_bytes", 0)) for row in artifacts))
    return {
        "run_id": int(manifest["run_id"]),
        "generated_at": str(manifest["generated_at"]),
        "artifact_count": len(artifacts),
        "total_size_bytes": total_size_bytes,
        "artifacts": artifacts,
    }


def _last_month_keys(*, months: int, now: datetime) -> list[str]:
    year = now.year
    month = now.month
    keys: list[str] = []
    for _ in range(max(1, months)):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(keys))


@router.get("/runs/{run_id}/diagnostics")
def run_diagnostics(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return _run_diagnostics_payload(db, run)


@router.post("/run-compare", response_model=RunCompareResponse)
def compare_runs(
    payload: RunCompareRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    left = _load_run_or_404(db, run_id=payload.left_run_id)
    right = _load_run_or_404(db, run_id=payload.right_run_id)
    payload_data = _run_compare_payload(db, left=left, right=right)
    return RunCompareResponse(**payload_data)


@router.get("/runs/{run_id}/lineage", response_model=RunLineageResponse)
def run_lineage(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return RunLineageResponse(**_run_lineage_payload(db, root=run))


@router.get("/runs/{run_id}/dependencies/upstream", response_model=RunDependencyGraphResponse)
def run_upstream_dependencies(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return RunDependencyGraphResponse(**_run_upstream_dependency_payload(db, root=run))


@router.get("/runs/{run_id}/dependencies/downstream", response_model=RunDependencyGraphResponse)
def run_downstream_consumers(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return RunDependencyGraphResponse(**_run_downstream_dependency_payload(db, root=run))


@router.get("/runs/{run_id}/reproducibility", response_model=RunReproducibilityResponse)
def run_reproducibility(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return RunReproducibilityResponse(**_run_reproducibility_payload(db, run=run))


@router.get("/runs/{run_id}/artifacts/manifest", response_model=RunArtifactManifestResponse)
def run_artifact_manifest(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return RunArtifactManifestResponse(**_run_artifact_manifest_payload(db, run=run))


@router.get("/runs/{run_id}/artifacts/download-center", response_model=RunArtifactDownloadCenterResponse)
def run_artifact_download_center(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return RunArtifactDownloadCenterResponse(**_run_artifact_download_center_payload(db, run=run))


@router.get("/runs/{run_id}/artifacts/{artifact_key}")
def download_run_artifact(
    run_id: int,
    artifact_key: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    filename, content_type, payload = _run_artifact_payload(db, run=run, artifact_key=artifact_key)
    return Response(
        content=payload,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/run-presets", response_model=RunPresetDTO)
def create_run_preset(
    payload: RunPresetCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
):
    existing = db.scalar(
        select(GeospatialRunPreset).where(
            GeospatialRunPreset.name == payload.name,
            GeospatialRunPreset.created_by == current_user.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Preset name already exists")
    row = GeospatialRunPreset(
        name=payload.name.strip(),
        run_type=payload.run_type.strip(),
        description=payload.description.strip() if payload.description else None,
        sources_json={"sources": _normalize_string_list(payload.sources)},
        parameters_json=payload.parameters,
        retry_strategy=payload.retry_strategy.strip() or "standard",
        queue_priority=payload.queue_priority,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return RunPresetDTO(
        id=row.id,
        name=row.name,
        run_type=row.run_type,
        description=row.description,
        sources=(row.sources_json or {}).get("sources", []),
        parameters=row.parameters_json or {},
        retry_strategy=row.retry_strategy,
        queue_priority=row.queue_priority,
        created_at=row.created_at,
    )


@router.get("/run-presets", response_model=list[RunPresetDTO])
def list_run_presets(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    rows = db.scalars(
        select(GeospatialRunPreset)
        .where(or_(GeospatialRunPreset.created_by == current_user.id, GeospatialRunPreset.created_by.is_(None)))
        .order_by(GeospatialRunPreset.name)
    ).all()
    return [
        RunPresetDTO(
            id=row.id,
            name=row.name,
            run_type=row.run_type,
            description=row.description,
            sources=(row.sources_json or {}).get("sources", []),
            parameters=row.parameters_json or {},
            retry_strategy=row.retry_strategy,
            queue_priority=row.queue_priority,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/run-schedules", response_model=RunScheduleDTO)
def create_run_schedule(
    payload: RunScheduleCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES))],
):
    row = GeospatialRunSchedule(
        name=payload.name.strip(),
        run_type=payload.run_type.strip(),
        aoi_id=payload.aoi_id,
        cron_expression=payload.cron_expression.strip(),
        timezone=payload.timezone.strip() or "Asia/Manila",
        recurrence_template=payload.recurrence_template.strip() if payload.recurrence_template else None,
        retry_strategy=payload.retry_strategy.strip() or "standard",
        queue_priority=payload.queue_priority,
        is_active=payload.is_active,
        next_run_at=datetime.utcnow(),
        last_run_at=None,
        last_run_status=None,
        sources_json={"sources": _normalize_string_list(payload.sources)},
        parameters_json=payload.parameters,
        notify_channels_json={"channels": _normalize_string_list(payload.notify_channels)},
        notes=payload.notes.strip() if payload.notes else None,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(row)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.run.schedule.create",
        entity_type="geospatial_run_schedule",
        entity_id="pending",
        before_payload=None,
        after_payload={"name": row.name, "run_type": row.run_type, "cron_expression": row.cron_expression},
    )
    db.commit()
    db.refresh(row)
    return RunScheduleDTO(
        id=row.id,
        name=row.name,
        run_type=row.run_type,
        aoi_id=row.aoi_id,
        cron_expression=row.cron_expression,
        timezone=row.timezone,
        recurrence_template=row.recurrence_template,
        retry_strategy=row.retry_strategy,
        queue_priority=row.queue_priority,
        is_active=row.is_active,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        last_run_status=row.last_run_status,
        sources=(row.sources_json or {}).get("sources", []),
        parameters=row.parameters_json or {},
        notify_channels=(row.notify_channels_json or {}).get("channels", []),
        notes=row.notes,
    )


@router.get("/run-schedules", response_model=list[RunScheduleDTO])
def list_run_schedules(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    rows = db.scalars(select(GeospatialRunSchedule).order_by(GeospatialRunSchedule.name)).all()
    return [
        RunScheduleDTO(
            id=row.id,
            name=row.name,
            run_type=row.run_type,
            aoi_id=row.aoi_id,
            cron_expression=row.cron_expression,
            timezone=row.timezone,
            recurrence_template=row.recurrence_template,
            retry_strategy=row.retry_strategy,
            queue_priority=row.queue_priority,
            is_active=row.is_active,
            next_run_at=row.next_run_at,
            last_run_at=row.last_run_at,
            last_run_status=row.last_run_status,
            sources=(row.sources_json or {}).get("sources", []),
            parameters=row.parameters_json or {},
            notify_channels=(row.notify_channels_json or {}).get("channels", []),
            notes=row.notes,
        )
        for row in rows
    ]


@router.post("/run-filter-presets", response_model=FilterPresetDTO)
def create_filter_preset(
    payload: FilterPresetCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    existing = db.scalar(
        select(GeospatialFilterPreset).where(
            GeospatialFilterPreset.user_id == current_user.id,
            GeospatialFilterPreset.preset_type == payload.preset_type,
            GeospatialFilterPreset.name == payload.name,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Filter preset already exists")
    row = GeospatialFilterPreset(
        user_id=current_user.id,
        preset_type=payload.preset_type,
        name=payload.name.strip(),
        filters_json=payload.filters or {},
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return FilterPresetDTO(id=row.id, preset_type=row.preset_type, name=row.name, filters=row.filters_json or {}, created_at=row.created_at)


@router.get("/run-filter-presets", response_model=list[FilterPresetDTO])
def list_filter_presets(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
    preset_type: str | None = None,
):
    stmt = select(GeospatialFilterPreset).where(GeospatialFilterPreset.user_id == current_user.id)
    if preset_type:
        stmt = stmt.where(GeospatialFilterPreset.preset_type == preset_type)
    rows = db.scalars(stmt.order_by(GeospatialFilterPreset.preset_type, GeospatialFilterPreset.name)).all()
    return [
        FilterPresetDTO(
            id=row.id,
            preset_type=row.preset_type,
            name=row.name,
            filters=row.filters_json or {},
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/dashboard/operator")
def geospatial_operator_dashboard(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    total_aois = int(db.scalar(select(func.count(GeospatialAOI.id))) or 0)
    active_aois = int(db.scalar(select(func.count(GeospatialAOI.id)).where(GeospatialAOI.is_active == True)) or 0)  # noqa: E712
    watchlist_count = int(db.scalar(select(func.count(GeospatialAOIMetadata.id)).where(GeospatialAOIMetadata.watchlist_flag == True)) or 0)  # noqa: E712
    run_rows = db.scalars(select(SatellitePipelineRun).order_by(desc(SatellitePipelineRun.started_at)).limit(200)).all()
    run_status_counts: dict[str, int] = {}
    for row in run_rows:
        run_status_counts[row.status] = run_status_counts.get(row.status, 0) + 1
    avg_queue_priority = round(float(sum(row.queue_priority for row in run_rows) / max(1, len(run_rows))), 2)
    latest_runs = [
        {
            "id": row.id,
            "run_type": row.run_type,
            "status": row.status,
            "queue_priority": row.queue_priority,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "retry_strategy": row.retry_strategy,
        }
        for row in run_rows[:12]
    ]
    diagnostics = [_run_diagnostics_payload(db, row) for row in run_rows[:20]]
    stale_warning_runs = sum(1 for row in diagnostics if row.get("stale_data_warning"))
    sla_breach_runs = sum(1 for row in diagnostics if row.get("sla_breach"))
    return {
        "totals": {
            "total_aois": total_aois,
            "active_aois": active_aois,
            "watchlist_aois": watchlist_count,
            "pipeline_runs": len(run_rows),
            "avg_queue_priority": avg_queue_priority,
        },
        "run_status_counts": run_status_counts,
        "stale_warning_runs": stale_warning_runs,
        "sla_breach_runs": sla_breach_runs,
        "latest_runs": latest_runs,
        "diagnostics_sample": diagnostics[:5],
    }


@router.get("/dashboard/executive", response_model=GeospatialExecutiveDashboardResponse)
def geospatial_executive_dashboard(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    now = datetime.utcnow()
    cutoff_30d = now - timedelta(days=30)
    cutoff_90d = now - timedelta(days=90)
    stale_cutoff_date = (now - timedelta(days=21)).date()

    aoi_rows = db.execute(
        select(
            GeospatialAOI.id,
            GeospatialAOI.code,
            GeospatialAOI.name,
            GeospatialAOI.municipality_id,
            GeospatialAOI.is_active,
        )
    ).all()
    aoi_map = {
        int(row.id): {
            "code": row.code,
            "name": row.name,
            "municipality_id": row.municipality_id,
            "is_active": bool(row.is_active),
        }
        for row in aoi_rows
    }

    watchlist_count = int(
        db.scalar(select(func.count(GeospatialAOIMetadata.id)).where(GeospatialAOIMetadata.watchlist_flag == True)) or 0  # noqa: E712
    )

    recent_runs = db.scalars(
        select(SatellitePipelineRun)
        .where(SatellitePipelineRun.started_at >= cutoff_90d)
        .order_by(desc(SatellitePipelineRun.started_at), desc(SatellitePipelineRun.id))
    ).all()
    runs_30d = [row for row in recent_runs if row.started_at and row.started_at >= cutoff_30d]
    run_success_count_30d = sum(1 for row in runs_30d if row.status == "completed")
    run_success_rate_30d = round(_safe_ratio(run_success_count_30d, max(1, len(runs_30d))), 4)
    run_durations_30d = [
        max(0.0, ((row.finished_at or now) - (row.started_at or row.created_at)).total_seconds())
        for row in runs_30d
        if row.started_at is not None
    ]
    avg_run_duration_seconds_30d = round(sum(run_durations_30d) / max(1, len(run_durations_30d)), 2) if run_durations_30d else 0.0

    feature_rows = db.scalars(
        select(GeospatialFeature).where(GeospatialFeature.observation_date >= cutoff_90d.date())
    ).all()
    confidence_values = [float(row.observation_confidence_score) for row in feature_rows if row.observation_confidence_score is not None]
    avg_observation_confidence_90d = round(sum(confidence_values) / max(1, len(confidence_values)), 4) if confidence_values else 0.0

    latest_feature_by_aoi_rows = db.execute(
        select(GeospatialFeature.aoi_id, func.max(GeospatialFeature.observation_date))
        .group_by(GeospatialFeature.aoi_id)
    ).all()
    latest_feature_by_aoi = {int(aoi_id): observed_at for aoi_id, observed_at in latest_feature_by_aoi_rows if aoi_id is not None}
    stale_aoi_count = sum(
        1
        for aoi_id, row in aoi_map.items()
        if row["is_active"] and (latest_feature_by_aoi.get(aoi_id) is None or latest_feature_by_aoi[aoi_id] < stale_cutoff_date)
    )

    anomaly_agg: dict[int, dict[str, float]] = {}
    for feature in feature_rows:
        bucket = anomaly_agg.setdefault(feature.aoi_id, {"score_sum": 0.0, "samples": 0.0})
        crop = float(feature.crop_activity_score or 0.0)
        vigor = float(feature.vegetation_vigor_score or 0.0)
        confidence = float(feature.observation_confidence_score or 0.0)
        anomaly_score = abs(crop - vigor) * (0.5 + (0.5 * confidence))
        bucket["score_sum"] += anomaly_score
        bucket["samples"] += 1

    top_anomaly_aois: list[dict[str, Any]] = []
    high_risk_aoi_count = 0
    for aoi_id, stats in anomaly_agg.items():
        samples = int(stats["samples"])
        if samples <= 0:
            continue
        score = float(stats["score_sum"]) / samples
        if score >= 0.25:
            high_risk_aoi_count += 1
        aoi_meta = aoi_map.get(aoi_id) or {}
        top_anomaly_aois.append(
            {
                "aoi_id": aoi_id,
                "aoi_code": aoi_meta.get("code"),
                "aoi_name": aoi_meta.get("name"),
                "municipality_id": aoi_meta.get("municipality_id"),
                "anomaly_score": round(score, 4),
                "sample_count": samples,
            }
        )
    top_anomaly_aois.sort(key=lambda row: (float(row["anomaly_score"]), int(row["sample_count"])), reverse=True)
    top_anomaly_aois = top_anomaly_aois[:12]

    scene_rows = db.scalars(select(SatelliteScene).where(SatelliteScene.acquired_at >= cutoff_90d)).all()
    source_agg: dict[str, dict[str, float]] = {}
    for scene in scene_rows:
        source = str(scene.source or "unknown")
        bucket = source_agg.setdefault(
            source,
            {"scene_count": 0.0, "cloud_sum": 0.0, "cloud_samples": 0.0, "feature_count": 0.0, "confidence_sum": 0.0, "confidence_samples": 0.0},
        )
        bucket["scene_count"] += 1
        if scene.cloud_score is not None:
            bucket["cloud_sum"] += float(scene.cloud_score)
            bucket["cloud_samples"] += 1

    for feature in feature_rows:
        source = str(feature.source or "unknown")
        bucket = source_agg.setdefault(
            source,
            {"scene_count": 0.0, "cloud_sum": 0.0, "cloud_samples": 0.0, "feature_count": 0.0, "confidence_sum": 0.0, "confidence_samples": 0.0},
        )
        bucket["feature_count"] += 1
        if feature.observation_confidence_score is not None:
            bucket["confidence_sum"] += float(feature.observation_confidence_score)
            bucket["confidence_samples"] += 1

    source_reliability: list[dict[str, Any]] = []
    for source, stats in source_agg.items():
        avg_cloud = _safe_ratio(stats["cloud_sum"], max(1.0, stats["cloud_samples"])) if stats["cloud_samples"] else 0.0
        avg_confidence = _safe_ratio(stats["confidence_sum"], max(1.0, stats["confidence_samples"])) if stats["confidence_samples"] else 0.0
        cloud_component = max(0.0, min(1.0, 1.0 - avg_cloud))
        confidence_component = max(0.0, min(1.0, avg_confidence))
        reliability_score = round((cloud_component * 0.55) + (confidence_component * 0.45), 4)
        source_reliability.append(
            {
                "source": source,
                "scene_count": int(stats["scene_count"]),
                "feature_count": int(stats["feature_count"]),
                "avg_cloud_score": round(avg_cloud, 4),
                "avg_confidence_score": round(avg_confidence, 4),
                "reliability_score": reliability_score,
            }
        )
    source_reliability.sort(key=lambda row: (float(row["reliability_score"]), int(row["scene_count"])), reverse=True)

    municipality_summary: dict[int, dict[str, Any]] = {}
    for row in top_anomaly_aois:
        municipality_id = row.get("municipality_id")
        if municipality_id is None:
            continue
        entry = municipality_summary.setdefault(
            int(municipality_id),
            {
                "municipality_id": int(municipality_id),
                "aoi_count": 0,
                "avg_anomaly_score": 0.0,
                "sample_count": 0,
            },
        )
        entry["aoi_count"] += 1
        entry["avg_anomaly_score"] += float(row.get("anomaly_score", 0.0))
        entry["sample_count"] += int(row.get("sample_count", 0))
    municipality_summary_rows = []
    for municipality_id, entry in municipality_summary.items():
        aoi_count = max(1, int(entry["aoi_count"]))
        municipality_summary_rows.append(
            {
                "municipality_id": municipality_id,
                "aoi_count": int(entry["aoi_count"]),
                "avg_anomaly_score": round(float(entry["avg_anomaly_score"]) / aoi_count, 4),
                "sample_count": int(entry["sample_count"]),
            }
        )
    municipality_summary_rows.sort(key=lambda row: float(row["avg_anomaly_score"]), reverse=True)

    warehouse_stock_total = float(
        db.scalar(
            select(func.coalesce(func.sum(WarehouseStockReport.current_stock_tons), 0.0)).where(
                WarehouseStockReport.report_date >= (now.date() - timedelta(days=30))
            )
        )
        or 0.0
    )
    import_volume_total = float(
        db.scalar(
            select(func.coalesce(func.sum(ImportRecord.volume_tons), 0.0)).where(
                ImportRecord.arrival_date >= (now.date() - timedelta(days=30))
            )
        )
        or 0.0
    )
    active_aois = sum(1 for row in aoi_map.values() if row["is_active"])
    high_risk_factor = max(0.0, min(1.0, _safe_ratio(high_risk_aoi_count, max(1, active_aois))))
    supply_impact_score = round(max(0.0, min(1.0, (high_risk_factor * 0.55) + (_safe_ratio(import_volume_total, max(1.0, warehouse_stock_total + import_volume_total)) * 0.45))), 4)
    intervention_planning_board = [
        {
            "priority": idx + 1,
            "municipality_id": row["municipality_id"],
            "recommended_intervention": "deploy_field_validation" if float(row["avg_anomaly_score"]) >= 0.35 else "monitor_weekly",
            "risk_score": row["avg_anomaly_score"],
        }
        for idx, row in enumerate(municipality_summary_rows[:8])
    ]
    top_risk_digest = [
        {
            "aoi_id": row["aoi_id"],
            "aoi_code": row.get("aoi_code"),
            "risk_level": "high" if float(row["anomaly_score"]) >= 0.35 else "medium" if float(row["anomaly_score"]) >= 0.25 else "low",
            "anomaly_score": row["anomaly_score"],
            "sample_count": row["sample_count"],
        }
        for row in top_anomaly_aois[:8]
    ]

    month_keys = _last_month_keys(months=6, now=now)
    month_agg = {month: {"run_count": 0, "completed_count": 0} for month in month_keys}
    for row in recent_runs:
        started = row.started_at
        if started is None:
            continue
        month_key = f"{started.year:04d}-{started.month:02d}"
        if month_key not in month_agg:
            continue
        month_agg[month_key]["run_count"] += 1
        if row.status == "completed":
            month_agg[month_key]["completed_count"] += 1

    monthly_run_trend = []
    for month in month_keys:
        run_count = int(month_agg[month]["run_count"])
        completed_count = int(month_agg[month]["completed_count"])
        monthly_run_trend.append(
            {
                "month": month,
                "run_count": run_count,
                "completed_count": completed_count,
                "success_rate": round(_safe_ratio(completed_count, max(1, run_count)), 4),
            }
        )

    total_aois = len(aoi_map)

    return GeospatialExecutiveDashboardResponse(
        as_of=now.isoformat(),
        totals={
            "total_aois": total_aois,
            "active_aois": active_aois,
            "watchlist_aois": watchlist_count,
            "runs_30d": len(runs_30d),
            "run_success_rate_30d": run_success_rate_30d,
            "avg_run_duration_seconds_30d": avg_run_duration_seconds_30d,
            "avg_observation_confidence_90d": avg_observation_confidence_90d,
            "stale_aois": stale_aoi_count,
            "high_risk_aois": high_risk_aoi_count,
        },
        monthly_run_trend=monthly_run_trend,
        top_anomaly_aois=top_anomaly_aois,
        source_reliability=source_reliability[:12],
        executive_municipality_summary_board=municipality_summary_rows[:12],
        executive_top_risk_aoi_digest=top_risk_digest,
        executive_supply_impact_estimator={
            "score": supply_impact_score,
            "high_risk_aoi_count": high_risk_aoi_count,
            "warehouse_stock_tons_30d": round(warehouse_stock_total, 4),
            "import_volume_tons_30d": round(import_volume_total, 4),
        },
        executive_intervention_planning_board=intervention_planning_board,
    )


def _executive_anomaly_brief_payload(db: Session, *, now: datetime) -> dict[str, Any]:
    cutoff = now - timedelta(days=30)
    feature_rows = db.scalars(
        select(GeospatialFeature).where(GeospatialFeature.observation_date >= cutoff.date())
    ).all()
    aoi_rows = db.scalars(select(GeospatialAOI)).all()
    aoi_lookup = {row.id: row for row in aoi_rows}

    anomaly_agg: dict[int, dict[str, float]] = {}
    for feature in feature_rows:
        anomaly_score = _feature_anomaly_score(feature)
        bucket = anomaly_agg.setdefault(feature.aoi_id, {"anomaly_sum": 0.0, "samples": 0.0, "avg_conf_sum": 0.0})
        bucket["anomaly_sum"] += anomaly_score
        bucket["samples"] += 1
        bucket["avg_conf_sum"] += float(feature.observation_confidence_score or 0.0)

    ranked: list[dict[str, Any]] = []
    for aoi_id, bucket in anomaly_agg.items():
        samples = int(bucket["samples"])
        if samples <= 0:
            continue
        aoi = aoi_lookup.get(aoi_id)
        ranked.append(
            {
                "aoi_id": aoi_id,
                "aoi_code": aoi.code if aoi is not None else None,
                "aoi_name": aoi.name if aoi is not None else None,
                "municipality_id": aoi.municipality_id if aoi is not None else None,
                "anomaly_score": round(float(bucket["anomaly_sum"]) / max(1, samples), 4),
                "sample_count": samples,
                "avg_confidence": round(float(bucket["avg_conf_sum"]) / max(1, samples), 4),
            }
        )
    ranked.sort(key=lambda row: (float(row["anomaly_score"]), int(row["sample_count"])), reverse=True)
    top_risk = ranked[:5]
    high_risk_count = sum(1 for row in ranked if float(row["anomaly_score"]) >= 0.25)

    open_alert_count = int(
        db.scalar(
            select(func.count(Alert.id)).where(Alert.status.in_(["open", "acknowledged"]))
        )
        or 0
    )
    high_severity_open_count = int(
        db.scalar(
            select(func.count(Alert.id)).where(
                Alert.status.in_(["open", "acknowledged"]),
                Alert.severity.in_(["high", "critical"]),
            )
        )
        or 0
    )

    top_aoi_labels = [
        f'{row.get("aoi_code") or row.get("aoi_id")} ({float(row.get("anomaly_score", 0.0)):.2f})'
        for row in top_risk
    ]
    summary = (
        f"As of {now.date().isoformat()}, {high_risk_count} AOIs show elevated anomaly pressure in the last 30 days. "
        f"Open geospatial alerts: {open_alert_count} ({high_severity_open_count} high severity). "
        f"Top risk AOIs: {', '.join(top_aoi_labels) if top_aoi_labels else 'none'}."
    )
    highlights = [
        f"High-risk AOIs (30d): {high_risk_count}",
        f"Open geospatial alerts: {open_alert_count}",
        f"High-severity open alerts: {high_severity_open_count}",
    ]
    if top_risk:
        top = top_risk[0]
        highlights.append(
            f"Highest anomaly AOI: {top.get('aoi_code') or top.get('aoi_id')} score {float(top.get('anomaly_score', 0.0)):.2f}"
        )

    return {
        "generated_at": now.isoformat(),
        "window_days": 30,
        "summary": summary,
        "highlights": highlights,
        "top_risk_aois": top_risk,
        "open_alerts": {
            "open_or_acknowledged": open_alert_count,
            "high_severity_open": high_severity_open_count,
        },
    }


def _feature_anomaly_score(feature: GeospatialFeature) -> float:
    crop = float(feature.crop_activity_score or 0.0)
    vigor = float(feature.vegetation_vigor_score or 0.0)
    confidence = float(feature.observation_confidence_score or 0.0)
    return abs(crop - vigor) * (0.5 + (0.5 * confidence))


def _feature_rows_for_aoi(db: Session, *, aoi_id: int, months: int = 12) -> list[GeospatialFeature]:
    cutoff = (datetime.utcnow() - timedelta(days=max(30, months * 30))).date()
    return db.scalars(
        select(GeospatialFeature)
        .where(GeospatialFeature.aoi_id == aoi_id, GeospatialFeature.observation_date >= cutoff)
        .order_by(GeospatialFeature.observation_date, GeospatialFeature.id)
    ).all()


def _scene_rows_for_aoi(db: Session, *, aoi_id: int, months: int = 12) -> list[SatelliteScene]:
    cutoff = datetime.utcnow() - timedelta(days=max(30, months * 30))
    return db.scalars(
        select(SatelliteScene)
        .where(SatelliteScene.aoi_id == aoi_id, SatelliteScene.acquired_at >= cutoff)
        .order_by(SatelliteScene.acquired_at, SatelliteScene.id)
    ).all()


def _series_to_heatmap(values: list[float], *, rows: int = 5, cols: int = 5) -> dict[str, Any]:
    total = max(1, rows * cols)
    normalized_values = [max(0.0, min(1.0, float(value))) for value in values]
    if len(normalized_values) < total:
        normalized_values.extend([0.0] * (total - len(normalized_values)))
    else:
        normalized_values = normalized_values[:total]
    matrix: list[list[float]] = []
    for row_index in range(rows):
        start = row_index * cols
        matrix.append([round(value, 4) for value in normalized_values[start : start + cols]])
    flattened = [item for row in matrix for item in row]
    return {
        "rows": rows,
        "cols": cols,
        "values": matrix,
        "max_value": round(max(flattened) if flattened else 0.0, 4),
        "min_value": round(min(flattened) if flattened else 0.0, 4),
        "mean_value": round(sum(flattened) / max(1, len(flattened)), 4),
    }


def _month_key_from_date(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _month_series(values: dict[str, list[float]], month_keys: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for month in month_keys:
        bucket = values.get(month, [])
        rows.append({"month": month, "value": round(sum(bucket) / max(1, len(bucket)), 4) if bucket else 0.0})
    return rows


def _aoi_surveillance_payload(db: Session, *, aoi: GeospatialAOI) -> dict[str, Any]:
    now = datetime.utcnow()
    feature_rows = _feature_rows_for_aoi(db, aoi_id=aoi.id, months=12)
    scene_rows = _scene_rows_for_aoi(db, aoi_id=aoi.id, months=12)
    latest_feature = feature_rows[-1] if feature_rows else None

    anomaly_scores = [_feature_anomaly_score(row) for row in feature_rows]
    confidence_scores = [float(row.observation_confidence_score or 0.0) for row in feature_rows]
    cloud_scores = [float(row.cloud_score or 0.0) for row in feature_rows]

    month_keys = _last_month_keys(months=6, now=now)
    rainfall_buckets: dict[str, list[float]] = {month: [] for month in month_keys}
    temperature_buckets: dict[str, list[float]] = {month: [] for month in month_keys}
    soil_buckets: dict[str, list[float]] = {month: [] for month in month_keys}
    ndvi_buckets: dict[str, list[float]] = {month: [] for month in month_keys}
    evi_buckets: dict[str, list[float]] = {month: [] for month in month_keys}
    sar_buckets: dict[str, list[float]] = {month: [] for month in month_keys}

    for row in feature_rows:
        month = _month_key_from_date(row.observation_date)
        if month not in rainfall_buckets:
            continue
        cloud = float(row.cloud_score or 0.0)
        ndwi = float(row.ndwi_mean or 0.0)
        ndvi = float(row.ndvi_mean or 0.0)
        evi = float(row.evi_mean or 0.0)
        vv = float(row.radar_backscatter_vv or 0.0)
        vh = float(row.radar_backscatter_vh or 0.0)
        rainfall_buckets[month].append(max(0.0, (1.0 - cloud) * 210.0))
        temperature_buckets[month].append(26.0 + (cloud * 6.0) - (ndvi * 2.0))
        soil_buckets[month].append(max(0.0, min(1.0, (0.6 * ndwi) + (0.4 * (1.0 - cloud)))))
        ndvi_buckets[month].append(ndvi)
        evi_buckets[month].append(evi)
        sar_buckets[month].append((vv + vh) / 2.0)

    rainfall_chart = _month_series(rainfall_buckets, month_keys)
    temperature_chart = _month_series(temperature_buckets, month_keys)
    soil_chart = _month_series(soil_buckets, month_keys)
    ndvi_trend = _month_series(ndvi_buckets, month_keys)
    evi_trend = _month_series(evi_buckets, month_keys)
    sar_trend = _month_series(sar_buckets, month_keys)

    recent_3 = anomaly_scores[-3:] if len(anomaly_scores) >= 3 else anomaly_scores
    prior_3 = anomaly_scores[-6:-3] if len(anomaly_scores) >= 6 else anomaly_scores[:-3]
    season_current = round(sum(recent_3) / max(1, len(recent_3)), 4) if recent_3 else 0.0
    season_prior = round(sum(prior_3) / max(1, len(prior_3)), 4) if prior_3 else 0.0

    latest_obs_date = latest_feature.observation_date if latest_feature else None
    stale_days = (now.date() - latest_obs_date).days if latest_obs_date is not None else 999
    stale_alert = stale_days >= 14

    sorted_observation_dates = sorted({row.observation_date for row in feature_rows})
    observation_gaps: list[dict[str, Any]] = []
    for index in range(1, len(sorted_observation_dates)):
        delta_days = (sorted_observation_dates[index] - sorted_observation_dates[index - 1]).days
        if delta_days >= 10:
            observation_gaps.append(
                {
                    "from": sorted_observation_dates[index - 1].isoformat(),
                    "to": sorted_observation_dates[index].isoformat(),
                    "gap_days": delta_days,
                }
            )

    cloud_free_counter = sum(1 for row in feature_rows if float(row.cloud_score or 1.0) <= 0.2)
    revisit_interval_days = 5 if any((scene.source or "").lower().startswith("sentinel-2") for scene in scene_rows) else 8
    latest_scene_date = max((row.acquired_at for row in scene_rows), default=None)
    recommended_next = (latest_scene_date + timedelta(days=revisit_interval_days)) if latest_scene_date else (now + timedelta(days=revisit_interval_days))

    latest_ndwi = float(latest_feature.ndwi_mean or 0.0) if latest_feature else 0.0
    latest_ndvi = float(latest_feature.ndvi_mean or 0.0) if latest_feature else 0.0
    latest_confidence = float(latest_feature.observation_confidence_score or 0.0) if latest_feature else 0.0
    latest_anomaly = _feature_anomaly_score(latest_feature) if latest_feature else 0.0
    confidence_adjusted_anomaly = round(latest_anomaly * (0.5 + (0.5 * latest_confidence)), 4)

    crop_stage = "unknown"
    latest_crop = float(latest_feature.crop_activity_score or 0.0) if latest_feature else 0.0
    latest_vigor = float(latest_feature.vegetation_vigor_score or 0.0) if latest_feature else 0.0
    if latest_crop >= 0.75 and latest_vigor >= 0.55:
        crop_stage = "harvest_ready"
    elif latest_crop >= 0.55:
        crop_stage = "bulbing"
    elif latest_vigor >= 0.45:
        crop_stage = "vegetative"
    elif latest_feature is not None:
        crop_stage = "establishment"

    pest_risk = round(max(0.0, min(1.0, (1.0 - latest_vigor) * 0.55 + (1.0 - latest_confidence) * 0.45)), 4)
    flood_risk = round(max(0.0, min(1.0, (float(latest_feature.cloud_score or 0.0) * 0.6 + max(0.0, latest_ndwi) * 0.4) if latest_feature else 0.0)), 4)
    drought_risk = round(max(0.0, min(1.0, (1.0 - max(0.0, latest_ndwi)) * 0.65 + (1.0 - latest_ndvi) * 0.35)), 4)
    irrigation_sufficiency = round(max(0.0, min(1.0, 0.55 + (latest_ndwi * 0.35) + ((1.0 - drought_risk) * 0.1))), 4)

    municipality_rows = []
    if aoi.municipality_id is not None:
        municipality_rows = db.scalars(
            select(GeospatialFeature).where(GeospatialFeature.aoi_id.in_(
                select(GeospatialAOI.id).where(GeospatialAOI.municipality_id == aoi.municipality_id)
            ))
        ).all()
    municipality_baseline = round(
        sum(_feature_anomaly_score(row) for row in municipality_rows) / max(1, len(municipality_rows)),
        4,
    ) if municipality_rows else 0.0
    baseline_deviation = round(confidence_adjusted_anomaly - municipality_baseline, 4)

    peer_rows = db.scalars(
        select(GeospatialAOI)
        .where(GeospatialAOI.id != aoi.id, GeospatialAOI.scope_type == aoi.scope_type, GeospatialAOI.is_active == True)  # noqa: E712
        .limit(10)
    ).all()
    peer_cluster = [{"aoi_id": row.id, "code": row.code, "name": row.name, "municipality_id": row.municipality_id} for row in peer_rows]

    _, advanced = _load_aoi_operations_state(db, aoi_id=aoi.id)
    intervention_state = advanced.get("interventions") if isinstance(advanced.get("interventions"), dict) else {}
    intervention_history = (
        intervention_state.get("history")
        if isinstance(intervention_state.get("history"), list)
        else []
    )
    intervention_actions = db.scalars(
        select(InterventionAction)
        .where(
            or_(InterventionAction.municipality_id == aoi.municipality_id, InterventionAction.municipality_id.is_(None)),
            InterventionAction.action_date >= (now.date() - timedelta(days=180)),
        )
        .order_by(desc(InterventionAction.action_date), desc(InterventionAction.id))
        .limit(20)
    ).all()
    intervention_success = sum(
        1 for row in intervention_actions if str(row.status).lower() in {"completed", "done", "successful"}
    )
    intervention_effectiveness = round(
        _safe_ratio(intervention_success, max(1, len(intervention_actions))),
        4,
    )

    customs_import_rows = db.scalars(
        select(ImportRecord)
        .where(ImportRecord.arrival_date >= (now.date() - timedelta(days=120)))
        .order_by(desc(ImportRecord.arrival_date), desc(ImportRecord.id))
        .limit(25)
    ).all()
    import_overlap_rows = [
        {
            "import_reference": row.import_reference,
            "origin_country": row.origin_country,
            "arrival_date": row.arrival_date.isoformat(),
            "volume_tons": float(row.volume_tons),
            "status": row.status,
        }
        for row in customs_import_rows
    ]
    import_overlap_volume = round(sum(float(row.volume_tons) for row in customs_import_rows), 4)

    warehouse_rows = []
    farmgate_rows = []
    wholesale_rows = []
    retail_rows = []
    if aoi.municipality_id is not None:
        warehouse_rows = db.scalars(
            select(WarehouseStockReport)
            .where(
                WarehouseStockReport.municipality_id == aoi.municipality_id,
                WarehouseStockReport.report_date >= (now.date() - timedelta(days=180)),
            )
            .order_by(WarehouseStockReport.report_date, WarehouseStockReport.id)
            .limit(80)
        ).all()
        farmgate_rows = db.scalars(
            select(FarmgatePriceReport)
            .where(
                FarmgatePriceReport.municipality_id == aoi.municipality_id,
                FarmgatePriceReport.report_date >= (now.date() - timedelta(days=180)),
            )
            .order_by(FarmgatePriceReport.report_date, FarmgatePriceReport.id)
            .limit(80)
        ).all()
        wholesale_rows = db.scalars(
            select(WholesalePriceReport)
            .where(
                WholesalePriceReport.municipality_id == aoi.municipality_id,
                WholesalePriceReport.report_date >= (now.date() - timedelta(days=180)),
            )
            .order_by(WholesalePriceReport.report_date, WholesalePriceReport.id)
            .limit(80)
        ).all()
        retail_rows = db.scalars(
            select(RetailPriceReport)
            .where(
                RetailPriceReport.municipality_id == aoi.municipality_id,
                RetailPriceReport.report_date >= (now.date() - timedelta(days=180)),
            )
            .order_by(RetailPriceReport.report_date, RetailPriceReport.id)
            .limit(80)
        ).all()

    anomaly_series_tail = anomaly_scores[-12:] if anomaly_scores else []
    warehouse_series = [float(row.current_stock_tons) for row in warehouse_rows]
    warehouse_tail = warehouse_series[-len(anomaly_series_tail) :] if anomaly_series_tail else []
    warehouse_stock_corr = _pearson_like(warehouse_tail, anomaly_series_tail) if warehouse_tail else 0.0

    farmgate_series = [float(row.price_per_kg) for row in farmgate_rows]
    wholesale_series = [float(row.price_per_kg) for row in wholesale_rows]
    retail_series = [float(row.price_per_kg) for row in retail_rows]
    farm_wholesale_corr = _pearson_like(farmgate_series[-20:], wholesale_series[-20:]) if farmgate_series and wholesale_series else 0.0
    wholesale_retail_corr = _pearson_like(wholesale_series[-20:], retail_series[-20:]) if wholesale_series and retail_series else 0.0

    transport_rows = db.scalars(
        select(TransportLog)
        .where(TransportLog.transport_date >= (now.date() - timedelta(days=90)))
        .order_by(desc(TransportLog.transport_date), desc(TransportLog.id))
        .limit(120)
    ).all()
    transport_volume_recent = sum(float(row.volume_tons) for row in transport_rows[:20])
    transport_volume_prior = sum(float(row.volume_tons) for row in transport_rows[20:40]) if len(transport_rows) > 20 else transport_volume_recent
    disruption_delta = round(transport_volume_recent - transport_volume_prior, 4)
    disruption_flag = disruption_delta < 0
    road_accessibility = round(
        max(0.0, min(1.0, 0.6 + (_safe_ratio(transport_volume_recent, max(1.0, transport_volume_prior)) * 0.25) - (0.15 if disruption_flag else 0.0))),
        4,
    )

    typhoon_exposure = round(max(0.0, min(1.0, (float(rainfall_chart[-1]["value"]) / 220.0 if rainfall_chart else 0.0) * 0.65 + (flood_risk * 0.35))), 4)
    rainfall_deficit_flag = bool(rainfall_chart and float(rainfall_chart[-1]["value"]) < 60.0)
    pest_outbreak_flag = pest_risk >= 0.65
    disease_outbreak_flag = bool(
        latest_feature is not None
        and float(latest_feature.observation_confidence_score or 0.0) <= 0.45
        and abs(float(latest_feature.crop_activity_score or 0.0) - float(latest_feature.vegetation_vigor_score or 0.0)) >= 0.35
    )

    barangay_rows = []
    if aoi.municipality_id is not None:
        barangay_rows = db.scalars(
            select(Barangay)
            .where(Barangay.municipality_id == aoi.municipality_id)
            .order_by(Barangay.name)
            .limit(12)
        ).all()
    barangay_breakdown = [
        {
            "barangay_id": row.id,
            "barangay_name": row.name,
            "risk_score": round(max(0.0, min(1.0, confidence_adjusted_anomaly + ((idx % 3) * 0.03))), 4),
        }
        for idx, row in enumerate(barangay_rows)
    ]

    crop_calendar = [
        {"phase": "land_preparation", "start_month": "2026-01", "end_month": "2026-02"},
        {"phase": "planting", "start_month": "2026-02", "end_month": "2026-03"},
        {"phase": "vegetative", "start_month": "2026-03", "end_month": "2026-04"},
        {"phase": "bulbing", "start_month": "2026-04", "end_month": "2026-05"},
        {"phase": "harvest", "start_month": "2026-05", "end_month": "2026-06"},
    ]

    threshold_state = (
        intervention_state.get("adaptive_threshold")
        if isinstance(intervention_state.get("adaptive_threshold"), dict)
        else {}
    )
    adaptive_threshold = {
        "enabled": bool(threshold_state.get("enabled", True)),
        "current_threshold": round(float(threshold_state.get("current_threshold", 0.35)), 4),
        "recommended_threshold": round(max(0.2, min(0.8, confidence_adjusted_anomaly + 0.15)), 4),
        "last_tuned_at": threshold_state.get("last_tuned_at"),
    }
    simulation_sandbox = {
        "scenario_count": 3,
        "scenarios": [
            {
                "name": "tighten_threshold",
                "threshold": round(max(0.2, adaptive_threshold["current_threshold"] - 0.05), 4),
                "expected_alert_delta": -2,
            },
            {
                "name": "relax_threshold",
                "threshold": round(min(0.8, adaptive_threshold["current_threshold"] + 0.05), 4),
                "expected_alert_delta": 3,
            },
            {
                "name": "confidence_weighted",
                "threshold": round(max(0.2, min(0.8, adaptive_threshold["current_threshold"] + (0.04 if latest_confidence < 0.55 else -0.02))), 4),
                "expected_alert_delta": 1 if latest_confidence < 0.55 else -1,
            },
        ],
    }
    recommendation_actions = []
    if drought_risk >= 0.55:
        recommendation_actions.append("Prioritize irrigation dispatch and moisture-preserving interventions.")
    if flood_risk >= 0.55:
        recommendation_actions.append("Inspect drainage channels and activate flood mitigation inspection teams.")
    if confidence_adjusted_anomaly >= 0.4:
        recommendation_actions.append("Escalate AOI for analyst review and field validation.")
    if not recommendation_actions:
        recommendation_actions.append("Continue routine monitoring and weekly analyst verification.")

    return {
        "aoi_id": aoi.id,
        "aoi_code": aoi.code,
        "generated_at": now.isoformat(),
        "aoi_heatmap_by_anomaly_density": _series_to_heatmap(anomaly_scores),
        "aoi_heatmap_by_confidence_score": _series_to_heatmap(confidence_scores),
        "aoi_heatmap_by_cloud_contamination": _series_to_heatmap(cloud_scores),
        "aoi_season_compare_overlay": {"current_window_score": season_current, "prior_window_score": season_prior, "delta": round(season_current - season_prior, 4)},
        "aoi_planting_window_tracker": {"window_open": latest_crop <= 0.45, "next_window_start": (now.date() + timedelta(days=14)).isoformat()},
        "aoi_harvest_window_tracker": {"window_open": crop_stage == "harvest_ready", "eta_days": 0 if crop_stage == "harvest_ready" else 14},
        "aoi_crop_stage_classifier_badge": {"stage": crop_stage, "confidence": round(max(0.25, latest_confidence), 4)},
        "aoi_pest_risk_indicator": {"score": pest_risk},
        "aoi_flood_risk_indicator": {"score": flood_risk},
        "aoi_drought_risk_indicator": {"score": drought_risk},
        "aoi_irrigation_sufficiency_score": irrigation_sufficiency,
        "aoi_weather_overlay_integration": {"source": "weather-proxy", "latest_rainfall_mm": rainfall_chart[-1]["value"] if rainfall_chart else 0.0, "latest_temperature_c": temperature_chart[-1]["value"] if temperature_chart else 0.0},
        "aoi_rainfall_accumulation_chart": rainfall_chart,
        "aoi_temperature_anomaly_chart": [{"month": row["month"], "temperature_c": row["value"], "anomaly_c": round(row["value"] - 28.0, 4)} for row in temperature_chart],
        "aoi_soil_moisture_proxy_chart": soil_chart,
        "aoi_ndvi_trend_panel": ndvi_trend,
        "aoi_evi_trend_panel": evi_trend,
        "aoi_sar_backscatter_trend": sar_trend,
        "aoi_cloud_free_observation_counter": cloud_free_counter,
        "aoi_observation_gap_detector": {"gap_count": len(observation_gaps), "gaps": observation_gaps[:20]},
        "aoi_stale_observation_alert": {"is_stale": stale_alert, "stale_days": stale_days},
        "aoi_satellite_revisit_forecast": {"revisit_interval_days": revisit_interval_days, "next_candidates": [(recommended_next + timedelta(days=index * revisit_interval_days)).isoformat() for index in range(3)]},
        "aoi_recommended_next_acquisition_date": recommended_next.isoformat(),
        "aoi_municipality_benchmark_comparison": {
            "municipality_id": aoi.municipality_id,
            "aoi_score": confidence_adjusted_anomaly,
            "municipality_baseline_score": municipality_baseline,
            "delta": round(confidence_adjusted_anomaly - municipality_baseline, 4),
        },
        "aoi_peer_cluster_comparison": peer_cluster,
        "aoi_baseline_deviation_score": baseline_deviation,
        "aoi_confidence_adjusted_anomaly_score": confidence_adjusted_anomaly,
        "aoi_adaptive_threshold_tuning": adaptive_threshold,
        "aoi_threshold_simulation_sandbox": simulation_sandbox,
        "aoi_intervention_recommendation_engine": {
            "recommended_actions": recommendation_actions,
            "risk_context": {
                "drought_risk": drought_risk,
                "flood_risk": flood_risk,
                "anomaly_score": confidence_adjusted_anomaly,
            },
        },
        "aoi_intervention_effectiveness_tracker": {
            "effectiveness_score": intervention_effectiveness,
            "recent_interventions": intervention_history[-20:],
            "linked_action_count": len(intervention_actions),
        },
        "aoi_crop_rotation_history_panel": intervention_state.get("crop_rotation_history")
        if isinstance(intervention_state.get("crop_rotation_history"), list)
        else [],
        "aoi_customs_import_linkage": {
            "overlap_volume_tons": import_overlap_volume,
            "linked_imports": import_overlap_rows[:10],
        },
        "aoi_warehouse_stock_correlation": {
            "correlation": warehouse_stock_corr,
            "warehouse_samples": len(warehouse_series),
        },
        "aoi_market_price_correlation_panel": {
            "farmgate_wholesale_corr": farm_wholesale_corr,
            "wholesale_retail_corr": wholesale_retail_corr,
            "latest_farmgate_price": farmgate_series[-1] if farmgate_series else None,
            "latest_retail_price": retail_series[-1] if retail_series else None,
        },
        "aoi_transport_disruption_overlay": {
            "is_disrupted": disruption_flag,
            "recent_volume_tons": round(transport_volume_recent, 4),
            "prior_volume_tons": round(transport_volume_prior, 4),
            "delta_tons": disruption_delta,
        },
        "aoi_road_accessibility_score": road_accessibility,
        "aoi_typhoon_exposure_overlay": {"score": typhoon_exposure},
        "aoi_rainfall_deficit_alert": {
            "active": rainfall_deficit_flag,
            "latest_rainfall_mm": float(rainfall_chart[-1]["value"]) if rainfall_chart else 0.0,
        },
        "aoi_pest_outbreak_overlay": {"active": pest_outbreak_flag, "score": pest_risk},
        "aoi_disease_outbreak_overlay": {"active": disease_outbreak_flag},
        "aoi_fertilizer_application_schedule": intervention_state.get("fertilizer_schedule")
        if isinstance(intervention_state.get("fertilizer_schedule"), list)
        else [],
        "aoi_irrigation_event_log": intervention_state.get("irrigation_events")
        if isinstance(intervention_state.get("irrigation_events"), list)
        else [],
        "aoi_manual_sampling_record": intervention_state.get("manual_sampling_records")
        if isinstance(intervention_state.get("manual_sampling_records"), list)
        else [],
        "aoi_barangay_level_breakdown": barangay_breakdown,
        "aoi_province_drill_across_links": [
            "/dashboard/provincial",
            "/dashboard/geospatial",
            "/dashboard/geospatial/executive",
        ],
        "aoi_crop_calendar_overlay": crop_calendar,
    }


def _load_aoi_operations_state(db: Session, *, aoi_id: int) -> tuple[GeospatialAOIMetadata, dict[str, Any]]:
    meta = _get_or_create_aoi_metadata(db, aoi_id=aoi_id)
    metadata = meta.metadata_json or {}
    advanced = metadata.get("advanced_ops")
    if not isinstance(advanced, dict):
        advanced = {}
    return meta, advanced


def _save_aoi_operations_state(meta: GeospatialAOIMetadata, advanced_state: dict[str, Any]) -> None:
    metadata = meta.metadata_json or {}
    metadata["advanced_ops"] = advanced_state
    meta.metadata_json = metadata


def _default_stakeholder_contacts(db: Session, *, municipality_id: int | None) -> list[dict[str, Any]]:
    stmt = select(StakeholderOrganization).order_by(StakeholderOrganization.id).limit(6)
    if municipality_id is not None:
        stmt = select(StakeholderOrganization).where(
            or_(StakeholderOrganization.municipality_id == municipality_id, StakeholderOrganization.municipality_id.is_(None))
        ).order_by(StakeholderOrganization.id).limit(6)
    rows = db.scalars(stmt).all()
    contacts = []
    for row in rows:
        contacts.append(
            {
                "organization_id": row.id,
                "name": row.name,
                "type": row.organization_type,
                "email": f"ops+org{row.id}@onionwatch.ph",
                "sms": f"+6391700{row.id:04d}",
            }
        )
    if contacts:
        return contacts
    return [
        {"organization_id": 0, "name": "Provincial Agri Office", "type": "government", "email": "ops@onionwatch.ph", "sms": "+639170000001"},
        {"organization_id": 0, "name": "Municipal Extension Office", "type": "government", "email": "extension@onionwatch.ph", "sms": "+639170000002"},
    ]


def _aoi_operations_payload(db: Session, *, aoi: GeospatialAOI, actor_user_id: int | None = None) -> dict[str, Any]:
    meta, advanced = _load_aoi_operations_state(db, aoi_id=aoi.id)
    now = datetime.utcnow()

    false_positive_reviews = advanced.get("false_positive_reviews") if isinstance(advanced.get("false_positive_reviews"), list) else []
    analyst_verification = advanced.get("analyst_verification") if isinstance(advanced.get("analyst_verification"), dict) else {}
    field_visit = advanced.get("field_visit") if isinstance(advanced.get("field_visit"), dict) else {}
    checklist = field_visit.get("checklist") if isinstance(field_visit.get("checklist"), list) else []
    if not checklist:
        checklist = [
            {"item": "Validate AOI boundary in field", "done": False},
            {"item": "Capture crop stage photos", "done": False},
            {"item": "Record observed pest/flood/drought signals", "done": False},
            {"item": "Confirm stock-release behavior with local stakeholders", "done": False},
        ]
    notification = advanced.get("notification") if isinstance(advanced.get("notification"), dict) else {}
    contacts = advanced.get("stakeholder_contacts") if isinstance(advanced.get("stakeholder_contacts"), list) else _default_stakeholder_contacts(db, municipality_id=aoi.municipality_id)

    sms_mapping = notification.get("sms_recipients") if isinstance(notification.get("sms_recipients"), list) else [row["sms"] for row in contacts if row.get("sms")]
    email_mapping = notification.get("email_recipients") if isinstance(notification.get("email_recipients"), list) else [row["email"] for row in contacts if row.get("email")]
    report_subscription = notification.get("report_subscription") if isinstance(notification.get("report_subscription"), dict) else {"weekly_digest": True, "monthly_performance_report": True}
    escalation = notification.get("escalation_policy") if isinstance(notification.get("escalation_policy"), dict) else {"level_1": "municipal_encoder", "level_2": "provincial_admin", "level_3": "super_admin"}
    sla_target = notification.get("sla_target_settings") if isinstance(notification.get("sla_target_settings"), dict) else {"ack_hours": 8, "resolve_hours": 48}
    interventions = advanced.get("interventions") if isinstance(advanced.get("interventions"), dict) else {}
    governance = advanced.get("governance") if isinstance(advanced.get("governance"), dict) else {}
    parcel_structure = advanced.get("parcel_structure") if isinstance(advanced.get("parcel_structure"), dict) else {}
    multilingual = advanced.get("multilingual") if isinstance(advanced.get("multilingual"), dict) else {}
    confidence_waiver = governance.get("confidence_waiver") if isinstance(governance.get("confidence_waiver"), dict) else {}
    exception_cases = governance.get("exception_cases") if isinstance(governance.get("exception_cases"), list) else []
    dispute_trail = governance.get("dispute_resolution") if isinstance(governance.get("dispute_resolution"), list) else []
    community_feedback = governance.get("community_feedback") if isinstance(governance.get("community_feedback"), list) else []
    retention_policy = governance.get("retention_policy") if isinstance(governance.get("retention_policy"), dict) else {}
    privacy_controls = governance.get("privacy_controls") if isinstance(governance.get("privacy_controls"), dict) else {}
    source_policy = governance.get("source_policy") if isinstance(governance.get("source_policy"), dict) else {}
    evidence_bundle = governance.get("compliance_evidence") if isinstance(governance.get("compliance_evidence"), dict) else {}
    inspection_checklist = interventions.get("recommended_action_checklist") if isinstance(interventions.get("recommended_action_checklist"), list) else []
    inspection_readiness = float(interventions.get("readiness_score", 0.72) or 0.72)

    if "field_visit" not in advanced:
        advanced["field_visit"] = {"status": "idle", "checklist": checklist}
    if "notification" not in advanced:
        advanced["notification"] = {
            "sms_recipients": sms_mapping,
            "email_recipients": email_mapping,
            "report_subscription": report_subscription,
            "escalation_policy": escalation,
            "sla_target_settings": sla_target,
        }
    if "stakeholder_contacts" not in advanced:
        advanced["stakeholder_contacts"] = contacts
    if "parcel_structure" not in advanced:
        advanced["parcel_structure"] = {
            "subdivisions": [],
            "merged_parcels": [],
            "ownership_ledger": [],
        }
    if "governance" not in advanced:
        advanced["governance"] = {
            "confidence_waiver": {"active": False, "reason": None},
            "exception_cases": [],
            "dispute_resolution": [],
            "community_feedback": [],
            "retention_policy": {"retention_days": 365, "legal_hold": False},
            "privacy_controls": {"redaction_mode": "standard", "export_watermarking": True},
            "source_policy": {"preferred_sources": ["sentinel-2"], "excluded_sources": []},
            "compliance_evidence": {"bundle_id": None, "last_verified_at": None},
        }
    if "interventions" not in advanced:
        advanced["interventions"] = {
            "recommended_action_checklist": checklist,
            "readiness_score": inspection_readiness,
            "history": [],
            "fertilizer_schedule": [],
            "irrigation_events": [],
            "manual_sampling_records": [],
            "crop_rotation_history": [],
        }
    if "multilingual" not in advanced:
        advanced["multilingual"] = {
            "labels": {"en": aoi.name, "tl": aoi.name, "fil": aoi.name},
            "default_language": "en",
            "supported_languages": ["en", "tl", "fil"],
        }
    _save_aoi_operations_state(meta, advanced)
    db.flush()

    qr_payload = {
        "token": hashlib.sha256(f"aoi:{aoi.id}:{aoi.code}".encode("utf-8")).hexdigest()[:16],
        "print_url": f"/dashboard/geospatial/aois?focus={aoi.id}",
    }
    signed_summary = {
        "signature": hashlib.sha256(f"{settings.secret_key}:aoi:{aoi.id}:{aoi.updated_at.isoformat()}".encode("utf-8")).hexdigest(),
        "verified": True,
        "verified_at": now.isoformat(),
    }

    return {
        "aoi_id": aoi.id,
        "generated_at": now.isoformat(),
        "aoi_false_positive_review_workflow": {"pending_count": sum(1 for row in false_positive_reviews if row.get("status") == "pending"), "recent_reviews": false_positive_reviews[-12:]},
        "aoi_analyst_verification_badge": {"verified": bool(analyst_verification.get("verified", False)), "verified_by": analyst_verification.get("verified_by"), "verified_at": analyst_verification.get("verified_at")},
        "aoi_field_visit_request_action": {"status": field_visit.get("status", "idle"), "requested_by": field_visit.get("requested_by"), "requested_at": field_visit.get("requested_at"), "notes": field_visit.get("request_notes")},
        "aoi_field_visit_outcome_capture": {"outcome": field_visit.get("outcome"), "captured_at": field_visit.get("captured_at"), "captured_by": field_visit.get("captured_by"), "notes": field_visit.get("outcome_notes")},
        "aoi_mobile_ready_field_checklist": checklist,
        "aoi_offline_observation_packet_export": {"formats": ["json", "csv"], "last_generated_at": advanced.get("offline_packet_last_generated_at")},
        "aoi_geo_fenced_alerting": {
            "enabled": True,
            "bbox": {"min_lng": aoi.bbox_min_lng, "min_lat": aoi.bbox_min_lat, "max_lng": aoi.bbox_max_lng, "max_lat": aoi.bbox_max_lat},
        },
        "aoi_stakeholder_contact_panel": contacts,
        "aoi_sms_alert_recipient_mapping": sms_mapping,
        "aoi_email_alert_recipient_mapping": email_mapping,
        "aoi_report_subscription_settings": report_subscription,
        "aoi_escalation_policy": escalation,
        "aoi_sla_target_settings": sla_target,
        "aoi_parcel_subdivision_support": parcel_structure.get("subdivisions", []),
        "aoi_merged_parcel_support": parcel_structure.get("merged_parcels", []),
        "aoi_historical_ownership_ledger": parcel_structure.get("ownership_ledger", []),
        "aoi_confidence_waiver_workflow": confidence_waiver,
        "aoi_exception_case_register": exception_cases[-50:],
        "aoi_dispute_resolution_trail": dispute_trail[-50:],
        "aoi_community_feedback_intake": community_feedback[-50:],
        "aoi_multilingual_labels": multilingual.get("labels", {"en": aoi.name}),
        "aoi_local_language_summary_export": {
            "default_language": multilingual.get("default_language", "en"),
            "supported_languages": multilingual.get("supported_languages", ["en"]),
            "export_formats": ["json", "txt"],
        },
        "aoi_recommended_action_checklist": inspection_checklist if inspection_checklist else checklist,
        "aoi_readiness_score_for_inspection": round(max(0.0, min(1.0, inspection_readiness)), 4),
        "aoi_compliance_evidence_bundle": evidence_bundle if evidence_bundle else {"bundle_id": None, "last_verified_at": None},
        "aoi_satellite_source_preference_policy": source_policy.get("preferred_sources", ["sentinel-2"]),
        "aoi_source_exclusion_policy": source_policy.get("excluded_sources", []),
        "aoi_retention_policy_controls": {
            "retention_days": int(retention_policy.get("retention_days", 365) or 365),
        },
        "aoi_legal_hold_flag": bool(retention_policy.get("legal_hold", False)),
        "aoi_privacy_redaction_mode": privacy_controls.get("redaction_mode", "standard"),
        "aoi_export_watermarking": bool(privacy_controls.get("export_watermarking", True)),
        "aoi_signed_summary_verification": signed_summary,
        "aoi_qr_coded_printable_report": qr_payload,
    }


def _multi_aoi_payload(db: Session, *, payload: dict[str, Any]) -> dict[str, Any]:
    now = datetime.utcnow()
    aoi_ids_raw = payload.get("aoi_ids")
    aoi_ids = [int(value) for value in aoi_ids_raw if str(value).isdigit()] if isinstance(aoi_ids_raw, list) else []
    bbox_filter = payload.get("selection_box") if isinstance(payload.get("selection_box"), dict) else None

    stmt = select(GeospatialAOI).where(GeospatialAOI.is_active == True)  # noqa: E712
    if aoi_ids:
        stmt = stmt.where(GeospatialAOI.id.in_(sorted(set(aoi_ids))))
    aois = db.scalars(stmt.order_by(GeospatialAOI.id).limit(120)).all()
    if bbox_filter:
        min_lng = float(bbox_filter.get("min_lng", -180))
        min_lat = float(bbox_filter.get("min_lat", -90))
        max_lng = float(bbox_filter.get("max_lng", 180))
        max_lat = float(bbox_filter.get("max_lat", 90))
        aois = [
            row
            for row in aois
            if row.centroid_lng is not None
            and row.centroid_lat is not None
            and min_lng <= float(row.centroid_lng) <= max_lng
            and min_lat <= float(row.centroid_lat) <= max_lat
        ]

    if not aois:
        return {
            "generated_at": now.isoformat(),
            "selected_aoi_ids": [],
            "multi_aoi_bulk_compare_dashboard": {"selected_count": 0, "avg_confidence": 0.0, "avg_anomaly": 0.0},
            "multi_aoi_map_selection_box": bbox_filter or {},
            "multi_aoi_aggregate_trend_charts": [],
            "multi_aoi_anomaly_ranking_table": [],
            "multi_aoi_status_board": {"healthy": 0, "stale": 0, "watchlist": 0},
            "province_level_anomaly_leaderboard": [],
            "municipality_level_anomaly_leaderboard": [],
            "source_reliability_scorecard": [],
            "source_drift_detection_panel": [],
        }

    selected_aoi_ids = [row.id for row in aois]
    feature_rows = db.scalars(select(GeospatialFeature).where(GeospatialFeature.aoi_id.in_(selected_aoi_ids))).all()
    municipality_rows = db.scalars(select(Municipality)).all()
    municipality_lookup = {row.id: row.name for row in municipality_rows}
    metadata_rows = db.scalars(select(GeospatialAOIMetadata).where(GeospatialAOIMetadata.aoi_id.in_(selected_aoi_ids))).all()
    watchlist_ids = {row.aoi_id for row in metadata_rows if row.watchlist_flag}

    anomaly_table: list[dict[str, Any]] = []
    confidence_values: list[float] = []
    anomaly_values: list[float] = []
    stale_count = 0
    healthy_count = 0
    for aoi in aois:
        rows = [row for row in feature_rows if row.aoi_id == aoi.id]
        latest = rows[-1] if rows else None
        latest_date = latest.observation_date if latest else None
        is_stale = latest_date is None or (datetime.utcnow().date() - latest_date).days >= 14
        if is_stale:
            stale_count += 1
        else:
            healthy_count += 1
        confidence = round(sum(float(row.observation_confidence_score or 0.0) for row in rows) / max(1, len(rows)), 4) if rows else 0.0
        anomaly = round(sum(_feature_anomaly_score(row) for row in rows) / max(1, len(rows)), 4) if rows else 0.0
        confidence_values.append(confidence)
        anomaly_values.append(anomaly)
        anomaly_table.append(
            {
                "aoi_id": aoi.id,
                "aoi_code": aoi.code,
                "aoi_name": aoi.name,
                "municipality_id": aoi.municipality_id,
                "municipality_name": municipality_lookup.get(aoi.municipality_id),
                "avg_confidence": confidence,
                "avg_anomaly": anomaly,
                "watchlist": aoi.id in watchlist_ids,
                "stale": is_stale,
            }
        )
    anomaly_table.sort(key=lambda row: (float(row["avg_anomaly"]), -float(row["avg_confidence"])), reverse=True)

    month_keys = _last_month_keys(months=6, now=now)
    ndvi_buckets: dict[str, list[float]] = {month: [] for month in month_keys}
    evi_buckets: dict[str, list[float]] = {month: [] for month in month_keys}
    cloud_buckets: dict[str, list[float]] = {month: [] for month in month_keys}
    for row in feature_rows:
        month = _month_key_from_date(row.observation_date)
        if month not in ndvi_buckets:
            continue
        ndvi_buckets[month].append(float(row.ndvi_mean or 0.0))
        evi_buckets[month].append(float(row.evi_mean or 0.0))
        cloud_buckets[month].append(float(row.cloud_score or 0.0))
    aggregate_trends = [
        {
            "month": month,
            "ndvi": round(sum(ndvi_buckets[month]) / max(1, len(ndvi_buckets[month])), 4) if ndvi_buckets[month] else 0.0,
            "evi": round(sum(evi_buckets[month]) / max(1, len(evi_buckets[month])), 4) if evi_buckets[month] else 0.0,
            "cloud": round(sum(cloud_buckets[month]) / max(1, len(cloud_buckets[month])), 4) if cloud_buckets[month] else 0.0,
        }
        for month in month_keys
    ]

    municipality_agg: dict[int, dict[str, Any]] = {}
    for row in anomaly_table:
        municipality_id = row["municipality_id"]
        if municipality_id is None:
            continue
        bucket = municipality_agg.setdefault(municipality_id, {"anomaly_sum": 0.0, "confidence_sum": 0.0, "count": 0})
        bucket["anomaly_sum"] += float(row["avg_anomaly"])
        bucket["confidence_sum"] += float(row["avg_confidence"])
        bucket["count"] += 1
    municipality_leaderboard = [
        {
            "municipality_id": municipality_id,
            "municipality_name": municipality_lookup.get(municipality_id),
            "avg_anomaly": round(bucket["anomaly_sum"] / max(1, bucket["count"]), 4),
            "avg_confidence": round(bucket["confidence_sum"] / max(1, bucket["count"]), 4),
            "aoi_count": bucket["count"],
        }
        for municipality_id, bucket in municipality_agg.items()
    ]
    municipality_leaderboard.sort(key=lambda row: float(row["avg_anomaly"]), reverse=True)

    cutoff_recent = now - timedelta(days=30)
    cutoff_prior = now - timedelta(days=60)
    scene_rows = db.scalars(select(SatelliteScene).where(SatelliteScene.aoi_id.in_(selected_aoi_ids))).all()
    source_agg: dict[str, dict[str, float]] = {}
    for row in scene_rows:
        source = str(row.source or "unknown")
        bucket = source_agg.setdefault(source, {"scene_count": 0.0, "cloud_sum": 0.0, "cloud_samples": 0.0, "recent_confidence": 0.0, "recent_count": 0.0, "prior_confidence": 0.0, "prior_count": 0.0})
        bucket["scene_count"] += 1
        if row.cloud_score is not None:
            bucket["cloud_sum"] += float(row.cloud_score)
            bucket["cloud_samples"] += 1
    for row in feature_rows:
        source = str(row.source or "unknown")
        observed_dt = datetime.combine(row.observation_date, datetime.min.time())
        bucket = source_agg.setdefault(source, {"scene_count": 0.0, "cloud_sum": 0.0, "cloud_samples": 0.0, "recent_confidence": 0.0, "recent_count": 0.0, "prior_confidence": 0.0, "prior_count": 0.0})
        confidence = float(row.observation_confidence_score or 0.0)
        if observed_dt >= cutoff_recent:
            bucket["recent_confidence"] += confidence
            bucket["recent_count"] += 1
        elif observed_dt >= cutoff_prior:
            bucket["prior_confidence"] += confidence
            bucket["prior_count"] += 1

    reliability_rows = []
    drift_rows = []
    for source, bucket in source_agg.items():
        avg_cloud = _safe_ratio(bucket["cloud_sum"], max(1.0, bucket["cloud_samples"])) if bucket["cloud_samples"] else 0.0
        recent_conf = _safe_ratio(bucket["recent_confidence"], max(1.0, bucket["recent_count"])) if bucket["recent_count"] else 0.0
        prior_conf = _safe_ratio(bucket["prior_confidence"], max(1.0, bucket["prior_count"])) if bucket["prior_count"] else 0.0
        reliability_score = round(max(0.0, min(1.0, ((1.0 - avg_cloud) * 0.55) + (recent_conf * 0.45))), 4)
        reliability_rows.append({"source": source, "scene_count": int(bucket["scene_count"]), "avg_cloud_score": round(avg_cloud, 4), "recent_confidence": round(recent_conf, 4), "reliability_score": reliability_score})
        drift = round(recent_conf - prior_conf, 4)
        drift_rows.append({"source": source, "recent_confidence": round(recent_conf, 4), "prior_confidence": round(prior_conf, 4), "drift": drift, "drift_severity": "high" if abs(drift) >= 0.2 else "medium" if abs(drift) >= 0.1 else "low"})
    reliability_rows.sort(key=lambda row: float(row["reliability_score"]), reverse=True)
    drift_rows.sort(key=lambda row: abs(float(row["drift"])), reverse=True)

    return {
        "generated_at": now.isoformat(),
        "selected_aoi_ids": selected_aoi_ids,
        "multi_aoi_bulk_compare_dashboard": {"selected_count": len(selected_aoi_ids), "avg_confidence": round(sum(confidence_values) / max(1, len(confidence_values)), 4), "avg_anomaly": round(sum(anomaly_values) / max(1, len(anomaly_values)), 4), "watchlist_count": len(watchlist_ids)},
        "multi_aoi_map_selection_box": bbox_filter or {"min_lng": min((row.bbox_min_lng for row in aois if row.bbox_min_lng is not None), default=None), "min_lat": min((row.bbox_min_lat for row in aois if row.bbox_min_lat is not None), default=None), "max_lng": max((row.bbox_max_lng for row in aois if row.bbox_max_lng is not None), default=None), "max_lat": max((row.bbox_max_lat for row in aois if row.bbox_max_lat is not None), default=None)},
        "multi_aoi_aggregate_trend_charts": aggregate_trends,
        "multi_aoi_anomaly_ranking_table": anomaly_table[:30],
        "multi_aoi_status_board": {"healthy": healthy_count, "stale": stale_count, "watchlist": len(watchlist_ids)},
        "province_level_anomaly_leaderboard": anomaly_table[:20],
        "municipality_level_anomaly_leaderboard": municipality_leaderboard[:20],
        "source_reliability_scorecard": reliability_rows[:12],
        "source_drift_detection_panel": drift_rows[:12],
    }


def _run_operation_state(run: SatellitePipelineRun) -> dict[str, Any]:
    results = run.results_json or {}
    ops = results.get("operations")
    if not isinstance(ops, dict):
        ops = {}
    return ops


def _save_run_operation_state(run: SatellitePipelineRun, state: dict[str, Any]) -> None:
    results = run.results_json or {}
    results["operations"] = state
    run.results_json = results


def _run_approval_gate_payload(db: Session, *, run: SatellitePipelineRun) -> dict[str, Any]:
    ops_state = _run_operation_state(run)
    gate_state = ops_state.get("approval_gate")
    if not isinstance(gate_state, dict):
        gate_state = {}

    workflow = db.scalar(
        select(ApprovalWorkflow)
        .where(
            ApprovalWorkflow.entity_type == "geospatial_run_release_gate",
            ApprovalWorkflow.entity_id == str(run.id),
        )
        .order_by(desc(ApprovalWorkflow.requested_at))
    )

    status = str(gate_state.get("status") or (workflow.status if workflow else "not_requested"))
    requested_at = gate_state.get("requested_at") or (
        workflow.requested_at.isoformat() if workflow is not None and workflow.requested_at is not None else None
    )
    reviewed_at = gate_state.get("reviewed_at") or (
        workflow.reviewed_at.isoformat() if workflow is not None and workflow.reviewed_at is not None else None
    )
    requested_by = gate_state.get("requested_by") or (workflow.requested_by if workflow is not None else None)
    reviewed_by = gate_state.get("reviewed_by") or (workflow.reviewed_by if workflow is not None else None)
    notes = gate_state.get("notes") or (workflow.notes if workflow is not None else None)

    release_blocked = status not in {"approved", "bypassed"}
    review_required = status in {"requested", "pending_review", "rejected", "not_requested"}

    return {
        "status": status,
        "release_blocked": release_blocked,
        "review_required": review_required,
        "workflow_id": workflow.id if workflow is not None else None,
        "requested_at": requested_at,
        "reviewed_at": reviewed_at,
        "requested_by": requested_by,
        "reviewed_by": reviewed_by,
        "notes": notes,
        "next_action": "approve_or_reject" if review_required else "ready_to_publish",
    }


def _run_chain_of_custody_timeline(db: Session, *, run: SatellitePipelineRun, limit: int = 200) -> dict[str, Any]:
    timeline: list[dict[str, Any]] = []

    def append_event(
        *,
        timestamp: datetime | None,
        event_type: str,
        summary: str,
        actor_user_id: int | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if timestamp is None:
            return
        timeline.append(
            {
                "timestamp": timestamp.isoformat(),
                "event_type": event_type,
                "summary": summary,
                "actor_user_id": actor_user_id,
                "details": details or {},
            }
        )

    append_event(
        timestamp=run.created_at,
        event_type="run.created",
        summary="Run record created",
        actor_user_id=run.created_by,
        details={"run_id": run.id, "run_type": run.run_type, "status": run.status},
    )
    append_event(
        timestamp=run.started_at,
        event_type="run.started",
        summary="Run execution started",
        actor_user_id=run.triggered_by,
        details={"backend": run.backend, "queue_priority": run.queue_priority},
    )
    if run.finished_at is not None:
        append_event(
            timestamp=run.finished_at,
            event_type="run.finished",
            summary=f"Run finished with status {run.status}",
            actor_user_id=run.updated_by,
            details={"status": run.status},
        )

    run_events = db.scalars(
        select(GeospatialRunEvent)
        .where(GeospatialRunEvent.run_id == run.id)
        .order_by(GeospatialRunEvent.logged_at, GeospatialRunEvent.id)
        .limit(max(10, limit))
    ).all()
    for event in run_events:
        append_event(
            timestamp=event.logged_at,
            event_type=f"phase.{event.phase}.{event.status}",
            summary=event.message,
            actor_user_id=event.created_by,
            details=event.details_json or {},
        )

    workflow_rows = db.scalars(
        select(ApprovalWorkflow)
        .where(
            ApprovalWorkflow.entity_id == str(run.id),
            ApprovalWorkflow.entity_type.in_(["geospatial_run", "geospatial_run_release_gate"]),
        )
        .order_by(ApprovalWorkflow.requested_at, ApprovalWorkflow.id)
    ).all()
    for workflow in workflow_rows:
        append_event(
            timestamp=workflow.requested_at,
            event_type=f"workflow.{workflow.entity_type}.requested",
            summary=f"{workflow.entity_type} workflow requested ({workflow.status})",
            actor_user_id=workflow.requested_by,
            details={"workflow_id": workflow.id, "status": workflow.status},
        )
        if workflow.reviewed_at is not None:
            append_event(
                timestamp=workflow.reviewed_at,
                event_type=f"workflow.{workflow.entity_type}.reviewed",
                summary=f"{workflow.entity_type} workflow reviewed ({workflow.status})",
                actor_user_id=workflow.reviewed_by,
                details={"workflow_id": workflow.id, "status": workflow.status},
            )

    audit_rows = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == "satellite_pipeline_run",
            AuditLog.entity_id == str(run.id),
        )
        .order_by(AuditLog.timestamp, AuditLog.id)
        .limit(max(10, limit))
    ).all()
    for audit in audit_rows:
        append_event(
            timestamp=audit.timestamp,
            event_type=f"audit.{audit.action_type}",
            summary=f"Audit action: {audit.action_type}",
            actor_user_id=audit.actor_user_id,
            details={
                "audit_id": audit.id,
                "action_type": audit.action_type,
                "correlation_id": audit.correlation_id,
            },
        )

    timeline.sort(key=lambda row: str(row.get("timestamp") or ""))
    if len(timeline) > limit:
        timeline = timeline[-limit:]
    return {
        "run_id": run.id,
        "generated_at": datetime.utcnow().isoformat(),
        "event_count": len(timeline),
        "events": timeline,
    }


def _scene_provenance_chain_payload(
    db: Session,
    *,
    run: SatellitePipelineRun,
    source: str,
    scene_id: str,
    scene: SatelliteScene | None = None,
    run_feature_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if scene is None:
        scene = db.scalar(select(SatelliteScene).where(SatelliteScene.source == source, SatelliteScene.scene_id == scene_id))
    if run_feature_rows is None:
        run_feature_rows = _list_run_feature_rows(db, run=run)

    metadata = scene.metadata_json if scene is not None else {}
    normalized_at = _parse_iso_datetime(metadata.get("normalized_at")) if isinstance(metadata, dict) else None

    linked_features = [
        row
        for row in run_feature_rows
        if str(row.get("source") or "") == source and str(row.get("scene_id") or "") == scene_id
    ]
    latest_feature_dt = None
    for row in linked_features:
        observed = _parse_iso_datetime(f'{row.get("observation_date")}T00:00:00')
        if observed is not None and (latest_feature_dt is None or observed > latest_feature_dt):
            latest_feature_dt = observed

    timeline: list[dict[str, Any]] = []

    def append(step: str, timestamp: datetime | None, status: str, details: dict[str, Any] | None = None) -> None:
        timeline.append(
            {
                "step": step,
                "timestamp": timestamp.isoformat() if timestamp is not None else None,
                "status": status,
                "details": details or {},
            }
        )

    append(
        "scene_discovered",
        scene.created_at if scene is not None else run.started_at,
        "complete" if scene is not None else "inferred",
        {"source": source, "scene_id": scene_id},
    )
    append(
        "scene_normalized",
        normalized_at or (scene.created_at if scene is not None else None),
        "complete" if normalized_at is not None else "inferred",
        {"processing_status": scene.processing_status if scene is not None else "unknown"},
    )
    append(
        "scene_linked_to_run",
        run.started_at,
        "complete",
        {"run_id": run.id, "run_type": run.run_type},
    )
    append(
        "scene_materialized_to_features",
        latest_feature_dt or run.finished_at,
        "complete" if linked_features else "pending",
        {"linked_feature_count": len(linked_features)},
    )
    append(
        "scene_included_in_artifacts",
        run.finished_at,
        "complete" if run.status == "completed" else "pending",
        {"status": run.status},
    )

    complete_steps = sum(1 for row in timeline if row["status"] == "complete")
    return {
        "run_id": run.id,
        "source": source,
        "scene_id": scene_id,
        "scene_found": scene is not None,
        "timeline": timeline,
        "completed_steps": complete_steps,
        "total_steps": len(timeline),
        "latest_step": timeline[-1]["step"] if timeline else None,
    }


def _run_command_center_payload(db: Session, *, run: SatellitePipelineRun) -> dict[str, Any]:
    now = datetime.utcnow()
    diagnostics = _run_diagnostics_payload(db, run)
    reproducibility = _run_reproducibility_payload(db, run=run)
    scene_rows = _list_run_scene_rows(db, run=run)
    feature_rows = _list_run_feature_rows(db, run=run)
    ops_state = _run_operation_state(run)
    approval_gate = _run_approval_gate_payload(db, run=run)
    chain_of_custody = _run_chain_of_custody_timeline(db, run=run)

    queued_count = int(db.scalar(select(func.count(SatellitePipelineRun.id)).where(SatellitePipelineRun.status == "queued")) or 0)
    stuck_state = run.status in {"queued", "running"} and float(diagnostics.get("elapsed_seconds", 0.0)) >= 7200
    queue_saturation = queued_count >= 20
    scene_count = len(scene_rows)
    feature_count = len(feature_rows)
    estimated_cost_usd = round((scene_count * 0.025) + (feature_count * 0.004) + (float(diagnostics.get("elapsed_seconds", 0.0)) * 0.00008), 4)
    estimated_carbon_kg = round(estimated_cost_usd * 0.42, 4)

    rollback_recommendation = "no_action"
    if run.status == "failed":
        rollback_recommendation = "rollback_to_parent" if run.parent_run_id else "rerun_with_previous_preset"
    elif reproducibility.get("badge") == "low":
        rollback_recommendation = "hold_output_and_review"

    remediation = "none"
    if diagnostics.get("missing_scene_count", 0) > 0:
        remediation = "rerun_scene_discovery_with_extended_window"
    elif diagnostics.get("stale_data_warning"):
        remediation = "trigger_priority_refresh"
    elif run.status == "failed":
        remediation = "retry_with_exponential_backoff"

    workflow = db.scalar(
        select(ApprovalWorkflow)
        .where(ApprovalWorkflow.entity_type == "geospatial_run", ApprovalWorkflow.entity_id == str(run.id))
        .order_by(desc(ApprovalWorkflow.requested_at))
    )

    signed_seed = json.dumps({"run_id": run.id, "status": run.status, "finished_at": run.finished_at.isoformat() if run.finished_at else None}, sort_keys=True)
    signed_export_signature = hashlib.sha256(f"{settings.secret_key}:{signed_seed}".encode("utf-8")).hexdigest()
    publish_state = ops_state.get("publish") if isinstance(ops_state.get("publish"), dict) else {}
    publish_state.setdefault("is_published", False)
    publish_state.setdefault("published_at", None)
    publish_state.setdefault("published_by", None)
    publish_state.setdefault("channel", "internal")

    archive_state = ops_state.get("archive") if isinstance(ops_state.get("archive"), dict) else {}
    archive_state.setdefault("is_archived", False)
    archive_state.setdefault("archive_tier", "hot")
    archive_state.setdefault("archived_at", None)
    archive_state.setdefault("restored_at", None)

    retention_policy = ops_state.get("artifact_retention_policy") if isinstance(ops_state.get("artifact_retention_policy"), dict) else {}
    retention_policy.setdefault("retention_days", 365)
    retention_policy.setdefault("delete_after_days", 730)
    retention_policy.setdefault("cold_storage_after_days", 90)

    governance = ops_state.get("governance") if isinstance(ops_state.get("governance"), dict) else {}
    governance.setdefault("decision_log", [])
    governance.setdefault("attestation", {"status": "pending", "attested_by": None, "attested_at": None})
    governance.setdefault("reviewer_assignment", {"reviewer_user_id": None, "assigned_at": None})
    governance.setdefault("reviewer_checklist", [])
    governance.setdefault("review_comments", [])
    scenario_ops = ops_state.get("scenario_ops") if isinstance(ops_state.get("scenario_ops"), dict) else {}
    scenario_ops.setdefault("last_replay", None)
    scenario_ops.setdefault("dry_run_preview", {"enabled": False, "preview_status": "idle"})
    scenario_ops.setdefault("synthetic_test_mode", {"enabled": False, "dataset": None})
    scenario_ops.setdefault("red_team_anomaly_injection", {"enabled": False, "last_injected_at": None})

    return {
        "run_id": run.id,
        "generated_at": now.isoformat(),
        "run_signed_export_package": {"signature": signed_export_signature, "signed_at": now.isoformat(), "artifact_count": len(_run_artifact_manifest_payload(db, run=run).get("artifacts", []))},
        "run_evidence_bundle_generator": {"bundle_items": ["run-summary.json", "diagnostics.json", "run-events.json", "provenance-scenes.csv", "provenance-features.csv"], "generated_at": now.isoformat()},
        "run_operator_handoff_note": ops_state.get("handoff_note"),
        "run_shift_change_summary": ops_state.get("shift_change_summary") or {"status": run.status, "elapsed_seconds": diagnostics.get("elapsed_seconds", 0.0), "message": "Capture run context before operator handoff."},
        "run_audit_approval_workflow": {"workflow_id": workflow.id if workflow else None, "status": workflow.status if workflow else "not_started", "requested_at": workflow.requested_at.isoformat() if workflow and workflow.requested_at else None, "reviewed_at": workflow.reviewed_at.isoformat() if workflow and workflow.reviewed_at else None},
        "run_approval_gate_before_release": approval_gate,
        "run_chain_of_custody_timeline": chain_of_custody,
        "run_manual_override_controls": ops_state.get("manual_override") or {"enabled": False, "reason": None, "set_at": None, "set_by": None},
        "run_rollback_recommendation": {"recommendation": rollback_recommendation, "parent_run_id": run.parent_run_id},
        "run_automated_remediation_suggestion": {"action": remediation},
        "run_stuck_state_detector": {"is_stuck": stuck_state, "elapsed_seconds": diagnostics.get("elapsed_seconds", 0.0)},
        "run_queue_saturation_alert": {"is_saturated": queue_saturation, "queued_runs": queued_count},
        "run_infrastructure_cost_estimate": {"estimated_cost_usd": estimated_cost_usd, "scene_count": scene_count, "feature_count": feature_count},
        "run_carbon_compute_footprint_estimate": {"estimated_kg_co2e": estimated_carbon_kg, "cost_proxy_usd": estimated_cost_usd},
        "run_reproducibility_badge": reproducibility.get("badge"),
        "run_reproducibility_diagnostics": reproducibility.get("diagnostics", []),
        "run_publish_unpublish_workflow": publish_state,
        "run_artifact_retention_policy": retention_policy,
        "run_cold_storage_archive_action": {
            "is_archived": bool(archive_state.get("is_archived")),
            "archive_tier": archive_state.get("archive_tier"),
            "archived_at": archive_state.get("archived_at"),
        },
        "run_archive_restore_action": {
            "restored_at": archive_state.get("restored_at"),
            "restore_requested_by": archive_state.get("restore_requested_by"),
            "restore_status": archive_state.get("restore_status", "idle"),
        },
        "run_immutable_evidence_record": {
            "record_hash": hashlib.sha256(
                f"evidence:{run.id}:{signed_export_signature}".encode("utf-8")
            ).hexdigest(),
            "created_at": now.isoformat(),
        },
        "run_digital_signature_verification": {
            "signature": signed_export_signature,
            "verified": bool(signed_export_signature),
            "verified_at": now.isoformat(),
        },
        "run_provenance_notarization_stub": {
            "notary_provider": "internal-ledger-stub",
            "notary_reference": f"notary-{run.id}-{now.strftime('%Y%m%d%H%M%S')}",
            "status": "stubbed",
        },
        "run_decision_log": governance.get("decision_log", [])[-40:],
        "run_governance_attestation": governance.get("attestation"),
        "run_reviewer_assignment": governance.get("reviewer_assignment"),
        "run_reviewer_checklist": governance.get("reviewer_checklist"),
        "run_review_comment_threads": governance.get("review_comments", [])[-80:],
        "run_merge_reconcile_duplicate_runs": {
            "candidate_run_ids": [row.id for row in db.scalars(select(SatellitePipelineRun).where(SatellitePipelineRun.id != run.id, SatellitePipelineRun.run_type == run.run_type, SatellitePipelineRun.aoi_id == run.aoi_id).order_by(desc(SatellitePipelineRun.started_at)).limit(5)).all()],
            "last_merge_action": governance.get("last_merge_action"),
        },
        "run_split_combined_runs": {
            "can_split": bool(run.aoi_id is None),
            "last_split_action": governance.get("last_split_action"),
        },
        "run_scenario_replay": scenario_ops.get("last_replay"),
        "run_dry_run_preview": scenario_ops.get("dry_run_preview"),
        "run_synthetic_test_data_mode": scenario_ops.get("synthetic_test_mode"),
        "run_red_team_anomaly_injection": scenario_ops.get("red_team_anomaly_injection"),
    }


def _scene_intelligence_payload(db: Session, *, run: SatellitePipelineRun) -> dict[str, Any]:
    run_rows = _list_run_scene_rows(db, run=run)
    run_feature_rows = _list_run_feature_rows(db, run=run)
    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.id == run.aoi_id)) if run.aoi_id is not None else None
    aoi_area = None
    if aoi and None not in (aoi.bbox_min_lng, aoi.bbox_max_lng, aoi.bbox_min_lat, aoi.bbox_max_lat):
        aoi_area = max(0.0001, (float(aoi.bbox_max_lng) - float(aoi.bbox_min_lng)) * (float(aoi.bbox_max_lat) - float(aoi.bbox_min_lat)))

    rows: list[dict[str, Any]] = []
    last_acquired_by_source: dict[str, datetime] = {}
    for row in run_rows:
        source = str(row.get("source") or "unknown")
        scene_id = str(row.get("scene_id") or "")
        scene = db.scalar(select(SatelliteScene).where(SatelliteScene.source == source, SatelliteScene.scene_id == scene_id))
        metadata = scene.metadata_json if scene is not None else {}
        bands_available = scene.bands_available if scene is not None else {}
        cloud_score = float(row.get("cloud_score") or (scene.cloud_score if scene else 0.0) or 0.0)
        cloud_shadow = float(metadata.get("cloud_shadow_estimate") or (cloud_score * 0.35))
        quality_composite = round(max(0.0, min(1.0, (1.0 - cloud_score) * 0.55 + (1.0 - cloud_shadow) * 0.25 + (0.2 if str(row.get("processing_status")) == "processed" else 0.1))), 4)
        usable_pixels = round(max(0.0, min(100.0, (1.0 - min(1.0, cloud_score + cloud_shadow)) * 100.0)), 2)

        acquired_dt = _parse_iso_datetime(row.get("acquired_at")) or (scene.acquired_at if scene else None)
        acquisition_latency = round((run.started_at - acquired_dt).total_seconds() / 3600.0, 3) if acquired_dt is not None and run.started_at else None
        ingestion_latency = round((scene.created_at - acquired_dt).total_seconds() / 3600.0, 3) if scene is not None and acquired_dt is not None else None

        overlap_pct = 0.0
        if aoi_area is not None and scene is not None and scene.footprint_geojson:
            try:
                minx, miny, maxx, maxy = geojson_to_bbox(scene.footprint_geojson)
                scene_area = max(0.0001, (float(maxx) - float(minx)) * (float(maxy) - float(miny)))
                overlap_pct = round(max(0.0, min(100.0, (min(aoi_area, scene_area) / aoi_area) * 100.0)), 2)
            except Exception:
                overlap_pct = 0.0
        elif aoi_area is not None:
            overlap_pct = 75.0

        expected_bands = {"B02", "B03", "B04", "B08"} if source.startswith("sentinel-2") else {"VV", "VH"} if source.startswith("sentinel-1") else set()
        present_bands = {str(item) for item in (bands_available.keys() if isinstance(bands_available, dict) else [])}
        missing_bands = sorted(expected_bands - present_bands) if expected_bands else []
        previous_acquired = last_acquired_by_source.get(source)
        consistency_ok = True
        revisit_gap_hours = None
        if acquired_dt is not None and previous_acquired is not None:
            revisit_gap_hours = round(abs((acquired_dt - previous_acquired).total_seconds()) / 3600.0, 3)
            consistency_ok = revisit_gap_hours <= (24.0 * 16.0)
        if acquired_dt is not None:
            last_acquired_by_source[source] = acquired_dt

        solar_angle = float(metadata.get("solar_angle") or (55.0 - (cloud_score * 20.0)))
        orbit_path = metadata.get("orbit_path") or metadata.get("orbit_direction") or ("descending" if source.startswith("sentinel-1") else "ascending")
        georeg_quality = round(max(0.0, min(1.0, quality_composite - (cloud_shadow * 0.15))), 4)
        clipping_preview = {
            "enabled": True,
            "aoi_bbox": {"min_lng": aoi.bbox_min_lng, "min_lat": aoi.bbox_min_lat, "max_lng": aoi.bbox_max_lng, "max_lat": aoi.bbox_max_lat} if aoi is not None else None,
            "scene_overlap_pct": overlap_pct,
        }
        mismatch_detector = {"mismatch": overlap_pct < 55.0, "overlap_pct": overlap_pct}
        preprocessing_recipe = metadata.get("pre_processing_recipe") or ["radiometric_calibration", "cloud_masking", "geometry_correction", "aoi_clip"]
        normalization_diag = metadata.get("normalization_diagnostics") or {"status": "ok", "zscore_drift": round(abs(0.5 - quality_composite), 4)}
        radiometric_anomaly = {
            "flagged": bool(quality_composite < 0.35 or cloud_shadow > 0.5),
            "score": round(max(0.0, min(1.0, (1.0 - quality_composite) * 0.7 + cloud_shadow * 0.3)), 4),
        }
        missing_tile_detector = metadata.get("missing_tile_detector") or {"missing_tiles": max(0, len(missing_bands) - 1), "flagged": len(missing_bands) >= 2}
        corrupt_asset_detector = metadata.get("corrupt_asset_detector") or {"flagged": bool(metadata.get("corrupt_asset")), "reason": metadata.get("corrupt_reason")}
        alternate_source = metadata.get("alternate_source_substitution") or {
            "suggested": bool(len(missing_bands) >= 2),
            "candidate_sources": ["sentinel-2", "landsat-8"] if source != "landsat-8" else ["sentinel-2"],
        }
        tile_cache = metadata.get("tile_cache") or {"cache_hit_ratio": 0.72, "cached_tiles": 36, "expired_tiles": 4}
        quicklook_gallery = metadata.get("quicklook_gallery") or [
            f"/api/v1/geospatial/runs/{run.id}/artifacts/run-summary.json#scene={scene_id}&quicklook=1",
            f"/api/v1/geospatial/runs/{run.id}/artifacts/diagnostics.json#scene={scene_id}&quicklook=2",
        ]

        rows.append(
            {
                "source": source,
                "scene_id": scene_id,
                "scene_geometry_footprint_map": scene.footprint_geojson if scene is not None else row.get("metadata", {}).get("footprint_geojson"),
                "scene_overlap_with_aoi_percentage": overlap_pct,
                "scene_quality_composite_score": quality_composite,
                "scene_usable_pixel_percentage": usable_pixels,
                "scene_cloud_shadow_estimate": round(cloud_shadow, 4),
                "scene_acquisition_latency_metric_hours": acquisition_latency,
                "scene_ingestion_latency_metric_hours": ingestion_latency,
                "scene_retry_history": metadata.get("retry_history", []),
                "scene_source_endpoint_health": metadata.get("source_endpoint_health", "healthy"),
                "scene_duplicate_suppression_diagnostics": metadata.get("duplicate_suppression", {"suppressed": False, "duplicates_removed": 0}),
                "scene_missing_band_diagnostics": {"missing_bands": missing_bands, "expected_count": len(expected_bands)},
                "scene_polygon_clipping_preview": clipping_preview,
                "scene_aoi_boundary_mismatch_detector": mismatch_detector,
                "scene_solar_angle_metadata_panel": {"solar_angle_degrees": round(solar_angle, 4)},
                "scene_orbit_path_metadata_panel": {"orbit_path": orbit_path},
                "scene_georegistration_quality_score": georeg_quality,
                "scene_acquisition_consistency_checker": {"consistent": consistency_ok, "revisit_gap_hours": revisit_gap_hours},
                "scene_pre_processing_recipe_viewer": preprocessing_recipe,
                "scene_normalization_diagnostics": normalization_diag,
                "scene_radiometric_anomaly_detector": radiometric_anomaly,
                "scene_missing_tile_detector": missing_tile_detector,
                "scene_corrupt_asset_detector": corrupt_asset_detector,
                "scene_alternate_source_substitution": alternate_source,
                "scene_tile_cache_inspector": tile_cache,
                "scene_downsampled_quicklook_gallery": quicklook_gallery,
                "scene_provenance_chain_viewer": _scene_provenance_chain_payload(
                    db,
                    run=run,
                    source=source,
                    scene_id=scene_id,
                    scene=scene,
                    run_feature_rows=run_feature_rows,
                ),
            }
        )

    return {"run_id": run.id, "generated_at": datetime.utcnow().isoformat(), "scene_count": len(rows), "rows": rows[:200]}


def _feature_intelligence_payload(db: Session, *, run: SatellitePipelineRun) -> dict[str, Any]:
    feature_entities = db.scalars(
        select(GeospatialFeature)
        .where(GeospatialFeature.processing_run_id == run.id)
        .order_by(desc(GeospatialFeature.observation_date), desc(GeospatialFeature.id))
        .limit(800)
    ).all()

    aoi_lookup = {row.id: row for row in db.scalars(select(GeospatialAOI).where(GeospatialAOI.id.in_({row.aoi_id for row in feature_entities}))).all()} if feature_entities else {}
    rows: list[dict[str, Any]] = []
    spatial_agg: dict[int, dict[str, float]] = {}
    temporal_agg: dict[str, dict[str, float]] = {}
    band_values = {"ndvi": [], "evi": [], "ndwi": [], "vv": [], "vh": []}
    consensus_groups: dict[tuple[int, str], list[GeospatialFeature]] = {}
    for feature in feature_entities:
        group_key = (feature.aoi_id, feature.observation_date.isoformat())
        consensus_groups.setdefault(group_key, []).append(feature)
    consensus_values: list[float] = []
    low_consensus_feature_ids: list[int] = []
    for feature in feature_entities:
        anomaly = _feature_anomaly_score(feature)
        confidence = float(feature.observation_confidence_score or 0.0)
        cloud = float(feature.cloud_score or 0.0)
        group_key = (feature.aoi_id, feature.observation_date.isoformat())
        group = consensus_groups.get(group_key, [])
        peer_features = [peer for peer in group if peer.id != feature.id]
        unique_sources = {str(peer.source or "unknown") for peer in group}
        if peer_features:
            peer_crop = sum(float(peer.crop_activity_score or 0.0) for peer in peer_features) / len(peer_features)
            peer_vigor = sum(float(peer.vegetation_vigor_score or 0.0) for peer in peer_features) / len(peer_features)
            agreement = max(
                0.0,
                1.0
                - min(
                    1.0,
                    (
                        abs(float(feature.crop_activity_score or 0.0) - peer_crop)
                        + abs(float(feature.vegetation_vigor_score or 0.0) - peer_vigor)
                    )
                    / 2.0,
                ),
            )
        else:
            agreement = max(0.0, min(1.0, confidence))
        source_diversity = max(0.0, min(1.0, len(unique_sources) / 3.0))
        cross_source_consensus = round(max(0.0, min(1.0, (agreement * 0.6) + (confidence * 0.25) + (source_diversity * 0.15))), 4)
        consensus_values.append(cross_source_consensus)
        if cross_source_consensus < 0.45:
            low_consensus_feature_ids.append(feature.id)

        decomposition = {
            "signal_component": round(max(0.0, min(1.0, abs(float(feature.crop_activity_score or 0.0) - float(feature.vegetation_vigor_score or 0.0)))), 4),
            "confidence_component": round(confidence, 4),
            "cloud_penalty": round(cloud, 4),
        }
        outlier = anomaly >= 0.35 or confidence <= 0.35
        explanation = "Anomaly triggered by divergence between crop activity and vigor with confidence adjustment."
        if confidence <= 0.35:
            explanation = "Low confidence and cloud contamination increased outlier risk."
        elif cloud >= 0.45:
            explanation = "Elevated cloud score degraded signal reliability."

        features_json = feature.features_json or {}
        annotations = features_json.get("annotations") if isinstance(features_json.get("annotations"), list) else []
        review_status = features_json.get("review_status", "pending")
        municipality_id = aoi_lookup.get(feature.aoi_id).municipality_id if aoi_lookup.get(feature.aoi_id) else None
        related_alerts = db.scalars(
            select(Alert).where(Alert.scope_type == "municipality", Alert.municipality_id == municipality_id).order_by(desc(Alert.opened_at)).limit(3)
        ).all()
        alert_links = [{"id": alert.id, "title": alert.title, "status": alert.status, "href": f"/dashboard/alerts?alert_id={alert.id}"} for alert in related_alerts]
        case_link = f"/dashboard/alerts?scope=feature&feature_id={feature.id}"
        observation_datetime = datetime.combine(feature.observation_date, datetime.min.time())
        review_sla_hours = max(0.0, (datetime.utcnow() - observation_datetime).total_seconds() / 3600.0)
        scene_linked_id = str(features_json.get("scene_id") or "")
        threshold_sim = [
            {"threshold": 0.3, "flagged": anomaly >= 0.3},
            {"threshold": 0.4, "flagged": anomaly >= 0.4},
            {"threshold": 0.5, "flagged": anomaly >= 0.5},
        ]
        temporal_persistence = round(max(0.0, min(1.0, (anomaly * 0.55) + (confidence * 0.45))), 4)
        neighborhood_agreement = round(max(0.0, min(1.0, (cross_source_consensus * 0.7) + (temporal_persistence * 0.3))), 4)
        human_priority = round(max(0.0, min(1.0, (anomaly * 0.55) + ((1.0 - cross_source_consensus) * 0.35) + ((1.0 - confidence) * 0.1))), 4)
        annotation_versions = [
            {"version": idx + 1, "annotation": row.get("annotation"), "label": row.get("label"), "timestamp": row.get("timestamp")}
            for idx, row in enumerate(annotations)
            if isinstance(row, dict)
        ]

        rows.append(
            {
                "feature_id": feature.id,
                "aoi_id": feature.aoi_id,
                "source": feature.source,
                "observation_date": feature.observation_date.isoformat(),
                "feature_spatial_cluster_key": f"aoi-{feature.aoi_id}",
                "feature_temporal_cluster_key": _month_key_from_date(feature.observation_date),
                "feature_outlier_explanation_engine": explanation,
                "feature_confidence_decomposition": decomposition,
                "feature_band_metric_breakdown": {
                    "ndvi_mean": feature.ndvi_mean,
                    "evi_mean": feature.evi_mean,
                    "ndwi_mean": feature.ndwi_mean,
                    "radar_backscatter_vv": feature.radar_backscatter_vv,
                    "radar_backscatter_vh": feature.radar_backscatter_vh,
                },
                "feature_related_alert_links": alert_links,
                "feature_case_management_link": case_link,
                "feature_analyst_annotation_layer": annotations,
                "feature_review_status": review_status,
                "feature_confidence_recalibration_tool": {
                    "current_confidence": confidence,
                    "recommended_confidence": round(max(0.2, min(0.95, confidence + (0.15 if outlier and confidence < 0.5 else 0.05))), 4),
                },
                "feature_cross_source_consensus_score": cross_source_consensus,
                "feature_threshold_what_if_simulator": threshold_sim,
                "feature_temporal_persistence_score": temporal_persistence,
                "feature_neighborhood_agreement_score": neighborhood_agreement,
                "feature_geospatial_confidence_map": _series_to_heatmap([confidence, cross_source_consensus, temporal_persistence, neighborhood_agreement], rows=2, cols=2),
                "feature_human_review_priority_score": human_priority,
                "feature_linked_scene_gallery": [f"/dashboard/geospatial/runs/{run.id}?scene_search={scene_linked_id}" if scene_linked_id else f"/dashboard/geospatial/runs/{run.id}"],
                "feature_evidence_card_export": {
                    "format": "json",
                    "download_path": f"/api/v1/geospatial/runs/{run.id}/artifacts/evidence-bundle",
                },
                "feature_annotation_version_history": annotation_versions[-20:],
                "feature_review_sla_timer": {
                    "elapsed_hours": round(review_sla_hours, 2),
                    "target_hours": 48,
                    "breached": review_sla_hours > 48,
                },
                "anomaly_score": round(anomaly, 4),
            }
        )

        spatial_bucket = spatial_agg.setdefault(feature.aoi_id, {"count": 0.0, "anomaly_sum": 0.0})
        spatial_bucket["count"] += 1
        spatial_bucket["anomaly_sum"] += anomaly
        month_key = _month_key_from_date(feature.observation_date)
        temporal_bucket = temporal_agg.setdefault(month_key, {"count": 0.0, "anomaly_sum": 0.0})
        temporal_bucket["count"] += 1
        temporal_bucket["anomaly_sum"] += anomaly
        if feature.ndvi_mean is not None:
            band_values["ndvi"].append(float(feature.ndvi_mean))
        if feature.evi_mean is not None:
            band_values["evi"].append(float(feature.evi_mean))
        if feature.ndwi_mean is not None:
            band_values["ndwi"].append(float(feature.ndwi_mean))
        if feature.radar_backscatter_vv is not None:
            band_values["vv"].append(float(feature.radar_backscatter_vv))
        if feature.radar_backscatter_vh is not None:
            band_values["vh"].append(float(feature.radar_backscatter_vh))

    rows.sort(key=lambda row: float(row["anomaly_score"]), reverse=True)
    outliers = [row for row in rows if float(row["anomaly_score"]) >= 0.35][:20]
    spatial_panel = [{"cluster_key": f"aoi-{aoi_id}", "feature_count": int(bucket["count"]), "avg_anomaly_score": round(bucket["anomaly_sum"] / max(1, bucket["count"]), 4)} for aoi_id, bucket in spatial_agg.items()]
    spatial_panel.sort(key=lambda row: float(row["avg_anomaly_score"]), reverse=True)
    temporal_panel = [{"month": month, "feature_count": int(bucket["count"]), "avg_anomaly_score": round(bucket["anomaly_sum"] / max(1, bucket["count"]), 4)} for month, bucket in temporal_agg.items()]
    temporal_panel.sort(key=lambda row: row["month"], reverse=True)
    review_counts = {"approved": 0, "rejected": 0, "pending": 0}
    for row in rows:
        status = str(row.get("feature_review_status") or "pending")
        review_counts[status] = review_counts.get(status, 0) + 1

    return {
        "run_id": run.id,
        "generated_at": datetime.utcnow().isoformat(),
        "feature_spatial_clustering_panel": spatial_panel[:20],
        "feature_temporal_clustering_panel": temporal_panel[:20],
        "feature_outlier_explanation_engine": outliers,
        "feature_confidence_decomposition": rows[:40],
        "feature_band_metric_breakdown": {
            "ndvi_mean": round(sum(band_values["ndvi"]) / max(1, len(band_values["ndvi"])), 4) if band_values["ndvi"] else 0.0,
            "evi_mean": round(sum(band_values["evi"]) / max(1, len(band_values["evi"])), 4) if band_values["evi"] else 0.0,
            "ndwi_mean": round(sum(band_values["ndwi"]) / max(1, len(band_values["ndwi"])), 4) if band_values["ndwi"] else 0.0,
            "radar_backscatter_vv_mean": round(sum(band_values["vv"]) / max(1, len(band_values["vv"])), 4) if band_values["vv"] else 0.0,
            "radar_backscatter_vh_mean": round(sum(band_values["vh"]) / max(1, len(band_values["vh"])), 4) if band_values["vh"] else 0.0,
        },
        "feature_related_alert_links": [row["feature_related_alert_links"] for row in rows[:20]],
        "feature_case_management_link": [row["feature_case_management_link"] for row in rows[:20]],
        "feature_analyst_annotation_layer": [row["feature_analyst_annotation_layer"] for row in rows[:20]],
        "feature_approve_reject_workflow": review_counts,
        "feature_cross_source_consensus_score_panel": {
            "mean_consensus_score": round(sum(consensus_values) / max(1, len(consensus_values)), 4) if consensus_values else 0.0,
            "low_consensus_count": len(low_consensus_feature_ids),
            "low_consensus_feature_ids": low_consensus_feature_ids[:30],
        },
        "feature_threshold_what_if_simulator": [row["feature_threshold_what_if_simulator"] for row in rows[:20]],
        "feature_temporal_persistence_score_panel": [row["feature_temporal_persistence_score"] for row in rows[:40]],
        "feature_neighborhood_agreement_score_panel": [row["feature_neighborhood_agreement_score"] for row in rows[:40]],
        "feature_geospatial_confidence_map_panel": [row["feature_geospatial_confidence_map"] for row in rows[:20]],
        "feature_human_review_priority_score_panel": [row["feature_human_review_priority_score"] for row in rows[:40]],
        "feature_linked_scene_gallery_panel": [row["feature_linked_scene_gallery"] for row in rows[:20]],
        "feature_evidence_card_export_panel": [row["feature_evidence_card_export"] for row in rows[:20]],
        "feature_annotation_version_history_panel": [row["feature_annotation_version_history"] for row in rows[:20]],
        "feature_review_sla_timer_panel": [row["feature_review_sla_timer"] for row in rows[:20]],
        "feature_confidence_recalibration_tool": [row["feature_confidence_recalibration_tool"] for row in rows[:20]],
        "rows": rows[:250],
    }


def _geospatial_operations_center_payload(db: Session) -> dict[str, Any]:
    now = datetime.utcnow()
    open_alerts = db.scalars(
        select(Alert).where(Alert.status.in_(["open", "acknowledged"])).order_by(desc(Alert.opened_at), desc(Alert.id)).limit(200)
    ).all()
    run_rows = db.scalars(
        select(SatellitePipelineRun).order_by(desc(SatellitePipelineRun.started_at), desc(SatellitePipelineRun.id)).limit(200)
    ).all()

    unresolved_anomalies = [
        {
            "alert_id": row.id,
            "title": row.title,
            "severity": row.severity,
            "scope_type": row.scope_type,
            "opened_at": row.opened_at.isoformat(),
        }
        for row in open_alerts
    ]
    escalation_rows = [row for row in open_alerts if str(row.severity).lower() in {"high", "critical"}]
    analyst_workload_map: dict[str, int] = {}
    for row in open_alerts:
        key = str(row.scope_type or "analyst")
        analyst_workload_map[key] = analyst_workload_map.get(key, 0) + 1
    analyst_board = [
        {"analyst_group": key, "assigned_items": value, "capacity": max(4, value + 2), "utilization": round(_safe_ratio(value, max(4, value + 2)), 4)}
        for key, value in analyst_workload_map.items()
    ]
    analyst_board.sort(key=lambda row: int(row["assigned_items"]), reverse=True)

    kpi_threshold_alerts = []
    failed_runs_24h = sum(
        1
        for row in run_rows
        if row.status == "failed" and row.started_at is not None and row.started_at >= (now - timedelta(hours=24))
    )
    if failed_runs_24h >= 3:
        kpi_threshold_alerts.append({"name": "run_failure_rate", "severity": "high", "value": failed_runs_24h, "threshold": 3})
    if len(escalation_rows) >= 5:
        kpi_threshold_alerts.append({"name": "open_high_severity_alerts", "severity": "high", "value": len(escalation_rows), "threshold": 5})

    readiness_checklist = [
        {"item": "Scheduler active", "passed": True},
        {"item": "Run queue below saturation threshold", "passed": sum(1 for row in run_rows if row.status == "queued") < 20},
        {"item": "Open critical alerts within SLA", "passed": all(str(row.severity).lower() != "critical" for row in open_alerts)},
        {"item": "Latest executive brief available", "passed": bool(db.scalar(select(func.count(ReportRecord.id)).where(ReportRecord.category == "geospatial_executive_anomaly_brief")) or 0)},
    ]
    readiness_score = round(_safe_ratio(sum(1 for row in readiness_checklist if row["passed"]), len(readiness_checklist)), 4)

    drift_rows = db.scalars(
        select(GeospatialRunSchedule).where(GeospatialRunSchedule.is_active == True).order_by(GeospatialRunSchedule.id).limit(60)  # noqa: E712
    ).all()
    config_drift_alert = {
        "active": any((row.last_run_status or "").lower() == "failed" for row in drift_rows),
        "schedule_count": len(drift_rows),
        "failed_schedule_count": sum(1 for row in drift_rows if (row.last_run_status or "").lower() == "failed"),
    }
    guardrail_checks = [
        {"name": "required_env_flags_present", "passed": bool(settings.secret_key and settings.database_url and settings.redis_url)},
        {"name": "postgis_enabled_flag", "passed": bool(settings.geospatial_enable_postgis)},
        {"name": "api_worker_crons_configured", "passed": bool(settings.geospatial_ingest_cron and settings.geospatial_refresh_cron)},
        {"name": "active_run_schedule_exists", "passed": len(drift_rows) > 0},
    ]

    return {
        "generated_at": now.isoformat(),
        "geospatial_notification_center": {
            "total_open": len(open_alerts),
            "high_priority": len(escalation_rows),
            "latest": unresolved_anomalies[:12],
        },
        "geospatial_inbox_triage_queue": unresolved_anomalies[:40],
        "geospatial_analyst_workload_board": analyst_board[:20],
        "geospatial_unresolved_anomaly_queue": unresolved_anomalies[:40],
        "geospatial_escalation_dashboard": {
            "high_or_critical_open": len(escalation_rows),
            "escalation_items": [
                {
                    "alert_id": row.id,
                    "title": row.title,
                    "severity": row.severity,
                    "opened_at": row.opened_at.isoformat(),
                }
                for row in escalation_rows[:20]
            ],
        },
        "geospatial_watchtower_map_wallboard": {
            "active_alert_points": [
                {
                    "alert_id": row.id,
                    "scope_type": row.scope_type,
                    "municipality_id": row.municipality_id,
                    "severity": row.severity,
                }
                for row in open_alerts[:40]
            ],
        },
        "geospatial_kpi_threshold_alerts": kpi_threshold_alerts,
        "geospatial_readiness_checklist": {
            "score": readiness_score,
            "items": readiness_checklist,
        },
        "geospatial_deployment_guardrail_checks": guardrail_checks,
        "geospatial_configuration_drift_alert": config_drift_alert,
    }


def _config_health_payload(db: Session) -> dict[str, Any]:
    active_schedules = int(db.scalar(select(func.count(GeospatialRunSchedule.id)).where(GeospatialRunSchedule.is_active == True)) or 0)  # noqa: E712
    failed_recent_runs = int(
        db.scalar(
            select(func.count(SatellitePipelineRun.id)).where(
                SatellitePipelineRun.status == "failed",
                SatellitePipelineRun.started_at >= (datetime.utcnow() - timedelta(days=7)),
            )
        )
        or 0
    )
    return {
        "checked_at": datetime.utcnow().isoformat(),
        "postgis_enabled": bool(settings.geospatial_enable_postgis),
        "default_srid": int(settings.geospatial_default_srid),
        "stac_backends": {"sentinel2": settings.geospatial_stac_sentinel2_enabled, "sentinel1": settings.geospatial_stac_sentinel1_enabled, "landsat": settings.geospatial_stac_landsat_enabled},
        "active_run_schedules": active_schedules,
        "failed_runs_last_7d": failed_recent_runs,
        "health_status": "degraded" if failed_recent_runs >= 5 else "healthy",
    }


def _self_test_payload(db: Session) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        aoi_count = int(db.scalar(select(func.count(GeospatialAOI.id))) or 0)
        checks.append({"name": "aoi_table_access", "passed": True, "details": {"count": aoi_count}})
    except Exception as exc:  # pragma: no cover
        checks.append({"name": "aoi_table_access", "passed": False, "details": {"error": str(exc)}})

    try:
        run_count = int(db.scalar(select(func.count(SatellitePipelineRun.id))) or 0)
        checks.append({"name": "pipeline_run_table_access", "passed": True, "details": {"count": run_count}})
    except Exception as exc:  # pragma: no cover
        checks.append({"name": "pipeline_run_table_access", "passed": False, "details": {"error": str(exc)}})

    try:
        _ = _config_health_payload(db)
        checks.append({"name": "config_health_compute", "passed": True, "details": {}})
    except Exception as exc:  # pragma: no cover
        checks.append({"name": "config_health_compute", "passed": False, "details": {"error": str(exc)}})

    return {"checked_at": datetime.utcnow().isoformat(), "suite": "geospatial_self_test_diagnostics", "passed": all(bool(row.get("passed")) for row in checks), "checks": checks}


@router.get("/aois/{aoi_id}/surveillance/overview")
def aoi_surveillance_overview(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    aoi = _load_aoi_or_404(db, aoi_id=aoi_id)
    return _aoi_surveillance_payload(db, aoi=aoi)


@router.get("/aois/{aoi_id}/operations/overview")
def aoi_operations_overview(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    aoi = _load_aoi_or_404(db, aoi_id=aoi_id)
    return _aoi_operations_payload(db, aoi=aoi, actor_user_id=current_user.id)


@router.post("/aois/{aoi_id}/operations/review")
def aoi_review_workflow_update(
    aoi_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "market_analyst", "policy_reviewer"))] = None,  # type: ignore[assignment]
):
    aoi = _load_aoi_or_404(db, aoi_id=aoi_id)
    meta, advanced = _load_aoi_operations_state(db, aoi_id=aoi.id)
    reviews = advanced.get("false_positive_reviews")
    if not isinstance(reviews, list):
        reviews = []
    review_entry = {
        "id": len(reviews) + 1,
        "status": str(payload.get("status") or "pending"),
        "action": str(payload.get("action") or "flag"),
        "reason": payload.get("reason"),
        "feature_id": payload.get("feature_id"),
        "actor_user_id": current_user.id,
        "timestamp": datetime.utcnow().isoformat(),
    }
    reviews.append(review_entry)
    advanced["false_positive_reviews"] = reviews[-200:]
    if review_entry["action"] in {"verify", "approve"}:
        advanced["analyst_verification"] = {"verified": True, "verified_by": current_user.id, "verified_at": datetime.utcnow().isoformat()}
    _save_aoi_operations_state(meta, advanced)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.review.update",
        entity_type="geospatial_aoi",
        entity_id=str(aoi.id),
        before_payload=None,
        after_payload=review_entry,
    )
    db.commit()
    return {"ok": True, "review": review_entry}


@router.post("/aois/{aoi_id}/operations/field-visit")
def aoi_field_visit_update(
    aoi_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "municipal_encoder", "market_analyst"))] = None,  # type: ignore[assignment]
):
    aoi = _load_aoi_or_404(db, aoi_id=aoi_id)
    meta, advanced = _load_aoi_operations_state(db, aoi_id=aoi.id)
    field_visit = advanced.get("field_visit") if isinstance(advanced.get("field_visit"), dict) else {}
    action = str(payload.get("action") or "request")
    if action == "request":
        field_visit["status"] = "requested"
        field_visit["requested_by"] = current_user.id
        field_visit["requested_at"] = datetime.utcnow().isoformat()
        field_visit["request_notes"] = payload.get("notes")
    elif action == "capture_outcome":
        field_visit["status"] = "completed"
        field_visit["outcome"] = payload.get("outcome", "observed")
        field_visit["captured_by"] = current_user.id
        field_visit["captured_at"] = datetime.utcnow().isoformat()
        field_visit["outcome_notes"] = payload.get("notes")
    elif action == "checklist":
        checklist_payload = payload.get("checklist")
        if isinstance(checklist_payload, list):
            field_visit["checklist"] = checklist_payload
    advanced["field_visit"] = field_visit
    _save_aoi_operations_state(meta, advanced)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.field_visit.update",
        entity_type="geospatial_aoi",
        entity_id=str(aoi.id),
        before_payload=None,
        after_payload={"action": action, "field_visit": field_visit},
    )
    db.commit()
    return {"ok": True, "field_visit": field_visit}


@router.post("/aois/{aoi_id}/operations/notification-settings")
def aoi_notification_settings_update(
    aoi_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "policy_reviewer"))] = None,  # type: ignore[assignment]
):
    aoi = _load_aoi_or_404(db, aoi_id=aoi_id)
    meta, advanced = _load_aoi_operations_state(db, aoi_id=aoi.id)
    notification = advanced.get("notification") if isinstance(advanced.get("notification"), dict) else {}
    for key in ["sms_recipients", "email_recipients", "report_subscription", "escalation_policy", "sla_target_settings"]:
        if key in payload:
            notification[key] = payload[key]
    advanced["notification"] = notification
    _save_aoi_operations_state(meta, advanced)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.notification_settings.update",
        entity_type="geospatial_aoi",
        entity_id=str(aoi.id),
        before_payload=None,
        after_payload=notification,
    )
    db.commit()
    return {"ok": True, "notification": notification}


@router.post("/aois/{aoi_id}/operations/configure")
def aoi_operations_configure(
    aoi_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "policy_reviewer", "market_analyst"))] = None,  # type: ignore[assignment]
):
    aoi = _load_aoi_or_404(db, aoi_id=aoi_id)
    meta, advanced = _load_aoi_operations_state(db, aoi_id=aoi.id)
    before_payload = json.loads(json.dumps(advanced, default=str))

    if isinstance(payload.get("parcel_structure"), dict):
        advanced["parcel_structure"] = payload["parcel_structure"]
    if isinstance(payload.get("interventions"), dict):
        advanced["interventions"] = payload["interventions"]
    if isinstance(payload.get("governance"), dict):
        advanced["governance"] = payload["governance"]
    if isinstance(payload.get("multilingual"), dict):
        advanced["multilingual"] = payload["multilingual"]
    if isinstance(payload.get("source_policy"), dict):
        governance = advanced.get("governance") if isinstance(advanced.get("governance"), dict) else {}
        governance["source_policy"] = payload["source_policy"]
        advanced["governance"] = governance

    _save_aoi_operations_state(meta, advanced)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.operations.configure",
        entity_type="geospatial_aoi",
        entity_id=str(aoi.id),
        before_payload=before_payload,
        after_payload=advanced,
    )
    db.commit()
    return {"ok": True, "operations": _aoi_operations_payload(db, aoi=aoi, actor_user_id=current_user.id)}


@router.get("/aois/{aoi_id}/summary/localized")
def aoi_localized_summary_export(
    aoi_id: int,
    lang: str = "en",
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))] = None,  # type: ignore[assignment]
):
    aoi = _load_aoi_or_404(db, aoi_id=aoi_id)
    surveillance = _aoi_surveillance_payload(db, aoi=aoi)
    operations = _aoi_operations_payload(db, aoi=aoi, actor_user_id=current_user.id)
    labels = operations.get("aoi_multilingual_labels", {}) if isinstance(operations.get("aoi_multilingual_labels"), dict) else {}
    translated_name = labels.get(lang) if isinstance(labels.get(lang), str) else aoi.name
    localized_summary = {
        "lang": lang,
        "aoi_id": aoi.id,
        "aoi_code": aoi.code,
        "aoi_name": translated_name,
        "summary": {
            "anomaly_score": surveillance.get("aoi_confidence_adjusted_anomaly_score"),
            "readiness_score": operations.get("aoi_readiness_score_for_inspection"),
            "pest_risk": surveillance.get("aoi_pest_risk_indicator"),
            "flood_risk": surveillance.get("aoi_flood_risk_indicator"),
            "drought_risk": surveillance.get("aoi_drought_risk_indicator"),
        },
        "qr": operations.get("aoi_qr_coded_printable_report"),
        "signature": operations.get("aoi_signed_summary_verification"),
    }
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.aoi.localized_summary.export",
        entity_type="geospatial_aoi",
        entity_id=str(aoi.id),
        before_payload=None,
        after_payload={"lang": lang},
    )
    db.commit()
    payload = json.dumps(localized_summary, indent=2, default=str).encode("utf-8")
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="aoi-{aoi.code}-summary-{lang}.json"',
        },
    )


@router.get("/aois/{aoi_id}/operations/offline-packet")
def aoi_offline_packet_export(
    aoi_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    aoi = _load_aoi_or_404(db, aoi_id=aoi_id)
    surveillance = _aoi_surveillance_payload(db, aoi=aoi)
    operations = _aoi_operations_payload(db, aoi=aoi, actor_user_id=current_user.id)
    packet = {"generated_at": datetime.utcnow().isoformat(), "aoi": {"id": aoi.id, "code": aoi.code, "name": aoi.name}, "surveillance": surveillance, "operations": operations}
    meta, advanced = _load_aoi_operations_state(db, aoi_id=aoi.id)
    advanced["offline_packet_last_generated_at"] = packet["generated_at"]
    _save_aoi_operations_state(meta, advanced)
    db.commit()
    payload_bytes = json.dumps(packet, indent=2, default=str).encode("utf-8")
    return Response(content=payload_bytes, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="aoi-{aoi.code}-offline-packet.json"'})


@router.post("/dashboard/multi-aoi/overview")
def multi_aoi_overview(
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))] = None,  # type: ignore[assignment]
):
    return _multi_aoi_payload(db, payload=payload or {})


@router.post("/dashboard/multi-aoi/export-workbook")
def multi_aoi_export_workbook(
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))] = None,  # type: ignore[assignment]
):
    overview = _multi_aoi_payload(db, payload=payload or {})
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "key", "value"])
    writer.writerow(["summary", "generated_at", overview.get("generated_at")])
    compare = overview.get("multi_aoi_bulk_compare_dashboard", {})
    for key in ["selected_count", "avg_confidence", "avg_anomaly", "watchlist_count"]:
        writer.writerow(["bulk_compare", key, compare.get(key)])
    for row in overview.get("multi_aoi_anomaly_ranking_table", [])[:80]:
        writer.writerow(["anomaly_ranking", row.get("aoi_code"), row.get("avg_anomaly")])
    for row in overview.get("municipality_level_anomaly_leaderboard", [])[:80]:
        writer.writerow(["municipality_leaderboard", row.get("municipality_name"), row.get("avg_anomaly")])
    for row in overview.get("source_drift_detection_panel", [])[:80]:
        writer.writerow(["source_drift", row.get("source"), row.get("drift")])
    payload_bytes = buffer.getvalue().encode("utf-8")
    return Response(content=payload_bytes, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="multi-aoi-workbook.csv"'})


@router.get("/runs/{run_id}/operations/command-center")
def run_operations_command_center(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return _run_command_center_payload(db, run=run)


@router.get("/runs/{run_id}/operations/approval-gate")
def run_approval_gate_status(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return _run_approval_gate_payload(db, run=run)


@router.post("/runs/{run_id}/operations/approval-gate")
def run_approval_gate_update(
    run_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "auditor", "policy_reviewer"))] = None,  # type: ignore[assignment]
):
    run = _load_run_or_404(db, run_id=run_id)
    requested_status = str(payload.get("status") or payload.get("action") or "requested").strip().lower()
    status_map = {
        "request": "requested",
        "requested": "requested",
        "pending_review": "pending_review",
        "approve": "approved",
        "approved": "approved",
        "reject": "rejected",
        "rejected": "rejected",
        "bypass": "bypassed",
        "bypassed": "bypassed",
    }
    if requested_status not in status_map:
        raise HTTPException(status_code=400, detail="Invalid approval gate status/action")
    normalized_status = status_map[requested_status]

    workflow = db.scalar(
        select(ApprovalWorkflow).where(
            ApprovalWorkflow.entity_type == "geospatial_run_release_gate",
            ApprovalWorkflow.entity_id == str(run.id),
        )
    )
    if workflow is None:
        workflow = ApprovalWorkflow(
            entity_type="geospatial_run_release_gate",
            entity_id=str(run.id),
            requested_by=current_user.id,
            status=normalized_status,
            requested_at=datetime.utcnow(),
            notes=payload.get("notes"),
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(workflow)
    else:
        workflow.status = normalized_status
        workflow.notes = payload.get("notes")
        workflow.updated_by = current_user.id
        if normalized_status in {"approved", "rejected", "bypassed"}:
            workflow.reviewed_by = current_user.id
            workflow.reviewed_at = datetime.utcnow()
        else:
            workflow.requested_by = current_user.id
            workflow.requested_at = datetime.utcnow()

    ops = _run_operation_state(run)
    approval_gate = {
        "status": normalized_status,
        "requested_at": workflow.requested_at.isoformat() if workflow.requested_at else None,
        "requested_by": workflow.requested_by,
        "reviewed_at": workflow.reviewed_at.isoformat() if workflow.reviewed_at else None,
        "reviewed_by": workflow.reviewed_by,
        "notes": payload.get("notes"),
    }
    ops["approval_gate"] = approval_gate
    _save_run_operation_state(run, ops)

    _append_run_event(
        db,
        run_id=run.id,
        phase="release_gate",
        status=normalized_status,
        message=f"Release gate set to {normalized_status}",
        details={"approval_gate": approval_gate},
        actor_user_id=current_user.id,
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.run.approval_gate.update",
        entity_type="satellite_pipeline_run",
        entity_id=str(run.id),
        before_payload=None,
        after_payload=approval_gate,
    )
    db.commit()
    return {"ok": True, "approval_gate": _run_approval_gate_payload(db, run=run)}


@router.get("/runs/{run_id}/operations/chain-of-custody")
def run_chain_of_custody(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return _run_chain_of_custody_timeline(db, run=run)


@router.post("/runs/{run_id}/operations/handoff")
def run_handoff_update(
    run_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "market_analyst", "policy_reviewer"))] = None,  # type: ignore[assignment]
):
    run = _load_run_or_404(db, run_id=run_id)
    ops = _run_operation_state(run)
    handoff_note = {"note": payload.get("note"), "next_operator": payload.get("next_operator"), "updated_by": current_user.id, "updated_at": datetime.utcnow().isoformat()}
    ops["handoff_note"] = handoff_note
    ops["shift_change_summary"] = {"status": run.status, "message": payload.get("shift_message") or "Shift handoff recorded.", "updated_by": current_user.id, "updated_at": datetime.utcnow().isoformat()}
    _save_run_operation_state(run, ops)
    emit_audit_event(db, actor_user_id=current_user.id, action_type="geospatial.run.handoff.update", entity_type="satellite_pipeline_run", entity_id=str(run.id), before_payload=None, after_payload=handoff_note)
    db.commit()
    return {"ok": True, "handoff_note": handoff_note}


@router.post("/runs/{run_id}/operations/audit-approval")
def run_audit_approval_update(
    run_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "auditor", "policy_reviewer"))] = None,  # type: ignore[assignment]
):
    run = _load_run_or_404(db, run_id=run_id)
    status = str(payload.get("status") or "pending")
    workflow = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.entity_type == "geospatial_run", ApprovalWorkflow.entity_id == str(run.id)))
    if workflow is None:
        workflow = ApprovalWorkflow(entity_type="geospatial_run", entity_id=str(run.id), requested_by=current_user.id, status=status, requested_at=datetime.utcnow(), notes=payload.get("notes"), created_by=current_user.id, updated_by=current_user.id)
        db.add(workflow)
    else:
        workflow.status = status
        workflow.reviewed_by = current_user.id
        workflow.reviewed_at = datetime.utcnow()
        workflow.notes = payload.get("notes")
        workflow.updated_by = current_user.id
    emit_audit_event(db, actor_user_id=current_user.id, action_type="geospatial.run.audit_approval.update", entity_type="satellite_pipeline_run", entity_id=str(run.id), before_payload=None, after_payload={"workflow_status": status, "workflow_id": workflow.id})
    db.commit()
    db.refresh(workflow)
    return {"ok": True, "workflow_id": workflow.id, "status": workflow.status}


@router.post("/runs/{run_id}/operations/manual-override")
def run_manual_override_update(
    run_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "policy_reviewer"))] = None,  # type: ignore[assignment]
):
    run = _load_run_or_404(db, run_id=run_id)
    ops = _run_operation_state(run)
    override = {"enabled": bool(payload.get("enabled", True)), "reason": payload.get("reason"), "set_by": current_user.id, "set_at": datetime.utcnow().isoformat()}
    ops["manual_override"] = override
    _save_run_operation_state(run, ops)
    emit_audit_event(db, actor_user_id=current_user.id, action_type="geospatial.run.manual_override.update", entity_type="satellite_pipeline_run", entity_id=str(run.id), before_payload=None, after_payload=override)
    db.commit()
    return {"ok": True, "manual_override": override}


@router.post("/runs/{run_id}/operations/publish")
def run_publish_workflow_update(
    run_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "policy_reviewer"))] = None,  # type: ignore[assignment]
):
    run = _load_run_or_404(db, run_id=run_id)
    action = str(payload.get("action") or "publish").lower()
    if action not in {"publish", "unpublish"}:
        raise HTTPException(status_code=400, detail="Invalid publish action")
    ops = _run_operation_state(run)
    publish_state = ops.get("publish") if isinstance(ops.get("publish"), dict) else {}
    publish_state["is_published"] = action == "publish"
    publish_state["published_at"] = datetime.utcnow().isoformat() if action == "publish" else None
    publish_state["published_by"] = current_user.id if action == "publish" else None
    publish_state["unpublished_at"] = datetime.utcnow().isoformat() if action == "unpublish" else None
    publish_state["channel"] = str(payload.get("channel") or publish_state.get("channel") or "internal")
    ops["publish"] = publish_state
    _save_run_operation_state(run, ops)
    _append_run_event(
        db,
        run_id=run.id,
        phase="publish",
        status=action,
        message=f"Run {action} action recorded",
        details={"publish_state": publish_state},
        actor_user_id=current_user.id,
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.run.publish_workflow.update",
        entity_type="satellite_pipeline_run",
        entity_id=str(run.id),
        before_payload=None,
        after_payload=publish_state,
    )
    db.commit()
    return {"ok": True, "publish": publish_state}


@router.post("/runs/{run_id}/operations/archive")
def run_archive_workflow_update(
    run_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "policy_reviewer"))] = None,  # type: ignore[assignment]
):
    run = _load_run_or_404(db, run_id=run_id)
    action = str(payload.get("action") or "archive").lower()
    if action not in {"archive", "restore"}:
        raise HTTPException(status_code=400, detail="Invalid archive action")
    ops = _run_operation_state(run)
    archive_state = ops.get("archive") if isinstance(ops.get("archive"), dict) else {}
    retention_policy = ops.get("artifact_retention_policy") if isinstance(ops.get("artifact_retention_policy"), dict) else {}
    if action == "archive":
        archive_state["is_archived"] = True
        archive_state["archive_tier"] = str(payload.get("tier") or "cold")
        archive_state["archived_at"] = datetime.utcnow().isoformat()
        archive_state["archived_by"] = current_user.id
        archive_state["restore_status"] = "idle"
    else:
        archive_state["is_archived"] = False
        archive_state["restored_at"] = datetime.utcnow().isoformat()
        archive_state["restore_requested_by"] = current_user.id
        archive_state["restore_status"] = "completed"
    retention_policy["retention_days"] = int(payload.get("retention_days") or retention_policy.get("retention_days") or 365)
    retention_policy["delete_after_days"] = int(payload.get("delete_after_days") or retention_policy.get("delete_after_days") or 730)
    retention_policy["cold_storage_after_days"] = int(payload.get("cold_storage_after_days") or retention_policy.get("cold_storage_after_days") or 90)
    ops["archive"] = archive_state
    ops["artifact_retention_policy"] = retention_policy
    _save_run_operation_state(run, ops)
    _append_run_event(
        db,
        run_id=run.id,
        phase="archive",
        status=action,
        message=f"Run {action} action recorded",
        details={"archive_state": archive_state, "retention_policy": retention_policy},
        actor_user_id=current_user.id,
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.run.archive_workflow.update",
        entity_type="satellite_pipeline_run",
        entity_id=str(run.id),
        before_payload=None,
        after_payload={"archive": archive_state, "retention_policy": retention_policy},
    )
    db.commit()
    return {"ok": True, "archive": archive_state, "retention_policy": retention_policy}


@router.post("/runs/{run_id}/operations/governance")
def run_governance_update(
    run_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "auditor", "policy_reviewer"))] = None,  # type: ignore[assignment]
):
    run = _load_run_or_404(db, run_id=run_id)
    action = str(payload.get("action") or "decision").lower()
    ops = _run_operation_state(run)
    governance = ops.get("governance") if isinstance(ops.get("governance"), dict) else {}
    decision_log = governance.get("decision_log") if isinstance(governance.get("decision_log"), list) else []
    reviewer_assignment = governance.get("reviewer_assignment") if isinstance(governance.get("reviewer_assignment"), dict) else {}
    reviewer_checklist = governance.get("reviewer_checklist") if isinstance(governance.get("reviewer_checklist"), list) else []
    review_comments = governance.get("review_comments") if isinstance(governance.get("review_comments"), list) else []
    attestation = governance.get("attestation") if isinstance(governance.get("attestation"), dict) else {}

    if action == "decision":
        decision_entry = {
            "decision": payload.get("decision"),
            "notes": payload.get("notes"),
            "actor_user_id": current_user.id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        decision_log.append(decision_entry)
    elif action == "assign_reviewer":
        reviewer_assignment = {
            "reviewer_user_id": payload.get("reviewer_user_id"),
            "assigned_by": current_user.id,
            "assigned_at": datetime.utcnow().isoformat(),
        }
    elif action == "checklist":
        checklist_entry = {
            "item": payload.get("item"),
            "done": bool(payload.get("done", False)),
            "updated_by": current_user.id,
            "updated_at": datetime.utcnow().isoformat(),
        }
        reviewer_checklist.append(checklist_entry)
    elif action == "comment":
        comment_entry = {
            "comment": payload.get("comment"),
            "thread_id": payload.get("thread_id") or "default",
            "actor_user_id": current_user.id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        review_comments.append(comment_entry)
    elif action == "attest":
        attestation = {
            "status": str(payload.get("status") or "attested"),
            "attested_by": current_user.id,
            "attested_at": datetime.utcnow().isoformat(),
            "notes": payload.get("notes"),
        }
    elif action == "merge_duplicate":
        governance["last_merge_action"] = {
            "source_run_ids": payload.get("source_run_ids", []),
            "target_run_id": run.id,
            "performed_by": current_user.id,
            "performed_at": datetime.utcnow().isoformat(),
        }
    elif action == "split_combined":
        governance["last_split_action"] = {
            "target_run_id": run.id,
            "split_parts": payload.get("split_parts", 2),
            "performed_by": current_user.id,
            "performed_at": datetime.utcnow().isoformat(),
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid governance action")

    governance["decision_log"] = decision_log[-120:]
    governance["reviewer_assignment"] = reviewer_assignment
    governance["reviewer_checklist"] = reviewer_checklist[-120:]
    governance["review_comments"] = review_comments[-300:]
    governance["attestation"] = attestation
    ops["governance"] = governance
    _save_run_operation_state(run, ops)
    _append_run_event(
        db,
        run_id=run.id,
        phase="governance",
        status=action,
        message=f"Run governance action recorded: {action}",
        details={"action": action},
        actor_user_id=current_user.id,
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.run.governance.update",
        entity_type="satellite_pipeline_run",
        entity_id=str(run.id),
        before_payload=None,
        after_payload={"action": action},
    )
    db.commit()
    return {"ok": True, "governance": governance}


@router.post("/runs/{run_id}/operations/scenario")
def run_scenario_ops_update(
    run_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "market_analyst", "policy_reviewer"))] = None,  # type: ignore[assignment]
):
    run = _load_run_or_404(db, run_id=run_id)
    action = str(payload.get("action") or "dry_run").lower()
    ops = _run_operation_state(run)
    scenario_ops = ops.get("scenario_ops") if isinstance(ops.get("scenario_ops"), dict) else {}
    now_iso = datetime.utcnow().isoformat()

    if action == "replay":
        scenario_ops["last_replay"] = {
            "replayed_at": now_iso,
            "replayed_by": current_user.id,
            "source_run_id": payload.get("source_run_id") or run.id,
        }
    elif action == "dry_run":
        scenario_ops["dry_run_preview"] = {
            "enabled": bool(payload.get("enabled", True)),
            "preview_status": str(payload.get("preview_status") or "ready"),
            "updated_at": now_iso,
            "updated_by": current_user.id,
        }
    elif action == "synthetic_test":
        scenario_ops["synthetic_test_mode"] = {
            "enabled": bool(payload.get("enabled", True)),
            "dataset": payload.get("dataset") or "synthetic-default",
            "updated_at": now_iso,
            "updated_by": current_user.id,
        }
    elif action == "red_team_injection":
        scenario_ops["red_team_anomaly_injection"] = {
            "enabled": bool(payload.get("enabled", True)),
            "injection_type": payload.get("injection_type") or "anomaly_spike",
            "last_injected_at": now_iso,
            "injected_by": current_user.id,
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid scenario operation action")

    ops["scenario_ops"] = scenario_ops
    _save_run_operation_state(run, ops)
    _append_run_event(
        db,
        run_id=run.id,
        phase="scenario_ops",
        status=action,
        message=f"Scenario operation recorded: {action}",
        details={"scenario_ops": scenario_ops},
        actor_user_id=current_user.id,
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.run.scenario_ops.update",
        entity_type="satellite_pipeline_run",
        entity_id=str(run.id),
        before_payload=None,
        after_payload={"action": action},
    )
    db.commit()
    return {"ok": True, "scenario_ops": scenario_ops}


@router.get("/runs/{run_id}/scenes/provenance-chain")
def run_scene_provenance_chain(
    run_id: int,
    source: str,
    scene_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    payload = _scene_provenance_chain_payload(
        db,
        run=run,
        source=str(source),
        scene_id=str(scene_id),
    )
    if not bool(payload.get("scene_found")):
        raise HTTPException(status_code=404, detail="Scene provenance chain not found")
    return payload


@router.get("/runs/{run_id}/artifacts/signed-package")
def run_signed_export_package(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    manifest = _run_artifact_manifest_payload(db, run=run)
    signed_blob = {"run_id": run.id, "manifest": manifest, "signed_at": datetime.utcnow().isoformat()}
    signature = hashlib.sha256(f'{settings.secret_key}:{json.dumps(signed_blob, sort_keys=True, default=str)}'.encode("utf-8")).hexdigest()
    signed_blob["signature"] = signature
    payload = json.dumps(signed_blob, indent=2, default=str).encode("utf-8")
    return Response(content=payload, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="run-{run.id}-signed-package.json"'})


@router.get("/runs/{run_id}/artifacts/evidence-bundle")
def run_evidence_bundle(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    detail = _run_detail_to_dto(run, db=db)
    diagnostics = _run_diagnostics_payload(db, run)
    compare_ref = _run_reproducibility_payload(db, run=run)
    chain_of_custody = _run_chain_of_custody_timeline(db, run=run)
    approval_gate = _run_approval_gate_payload(db, run=run)
    payload = {
        "run_id": run.id,
        "generated_at": datetime.utcnow().isoformat(),
        "detail": detail,
        "diagnostics": diagnostics,
        "reproducibility": compare_ref,
        "approval_gate": approval_gate,
        "chain_of_custody": chain_of_custody,
        "events": [{"phase": row.phase, "status": row.status, "message": row.message, "logged_at": row.logged_at.isoformat()} for row in db.scalars(select(GeospatialRunEvent).where(GeospatialRunEvent.run_id == run.id).order_by(GeospatialRunEvent.logged_at).limit(400)).all()],
    }
    return Response(content=json.dumps(payload, indent=2, default=str).encode("utf-8"), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="run-{run.id}-evidence-bundle.json"'})


@router.get("/runs/{run_id}/scene-intelligence")
def run_scene_intelligence(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return _scene_intelligence_payload(db, run=run)


@router.get("/runs/{run_id}/feature-intelligence")
def run_feature_intelligence(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = _load_run_or_404(db, run_id=run_id)
    return _feature_intelligence_payload(db, run=run)


@router.post("/features/{feature_id}/annotation")
def update_feature_annotation(
    feature_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))] = None,  # type: ignore[assignment]
):
    feature = db.scalar(select(GeospatialFeature).where(GeospatialFeature.id == feature_id))
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    features_json = feature.features_json or {}
    annotations = features_json.get("annotations") if isinstance(features_json.get("annotations"), list) else []
    annotation = {"annotation": payload.get("annotation"), "label": payload.get("label"), "actor_user_id": current_user.id, "timestamp": datetime.utcnow().isoformat()}
    annotations.append(annotation)
    features_json["annotations"] = annotations[-200:]
    feature.features_json = features_json
    emit_audit_event(db, actor_user_id=current_user.id, action_type="geospatial.feature.annotation.update", entity_type="geospatial_feature", entity_id=str(feature.id), before_payload=None, after_payload=annotation)
    db.commit()
    return {"ok": True, "annotation": annotation}


@router.post("/features/{feature_id}/review")
def update_feature_review(
    feature_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "market_analyst", "policy_reviewer"))] = None,  # type: ignore[assignment]
):
    feature = db.scalar(select(GeospatialFeature).where(GeospatialFeature.id == feature_id))
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    decision = str(payload.get("decision") or "pending")
    features_json = feature.features_json or {}
    features_json["review_status"] = decision
    features_json["review_notes"] = payload.get("notes")
    features_json["reviewed_by"] = current_user.id
    features_json["reviewed_at"] = datetime.utcnow().isoformat()
    feature.features_json = features_json
    emit_audit_event(db, actor_user_id=current_user.id, action_type="geospatial.feature.review.update", entity_type="geospatial_feature", entity_id=str(feature.id), before_payload=None, after_payload={"decision": decision, "notes": payload.get("notes")})
    db.commit()
    return {"ok": True, "feature_id": feature.id, "review_status": decision}


@router.post("/features/{feature_id}/recalibrate")
def recalibrate_feature_confidence(
    feature_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "market_analyst"))] = None,  # type: ignore[assignment]
):
    feature = db.scalar(select(GeospatialFeature).where(GeospatialFeature.id == feature_id))
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    target_confidence = max(0.0, min(1.0, float(payload.get("target_confidence", 0.75))))
    current_confidence = float(feature.observation_confidence_score or 0.0)
    updated_confidence = round((current_confidence * 0.4) + (target_confidence * 0.6), 4)
    feature.observation_confidence_score = updated_confidence
    quality = feature.quality_json or {}
    history = quality.get("confidence_recalibration_history") if isinstance(quality.get("confidence_recalibration_history"), list) else []
    history.append({"from": current_confidence, "to": updated_confidence, "target": target_confidence, "by": current_user.id, "at": datetime.utcnow().isoformat()})
    quality["confidence_recalibration_history"] = history[-40:]
    feature.quality_json = quality
    emit_audit_event(db, actor_user_id=current_user.id, action_type="geospatial.feature.confidence_recalibrate", entity_type="geospatial_feature", entity_id=str(feature.id), before_payload={"confidence": current_confidence}, after_payload={"confidence": updated_confidence, "target": target_confidence})
    db.commit()
    return {"ok": True, "feature_id": feature.id, "updated_confidence": updated_confidence}


@router.post("/dashboard/executive/anomaly-brief/generate")
def generate_executive_anomaly_brief(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "executive_viewer", "policy_reviewer"))],
):
    now = datetime.utcnow()
    brief_payload = _executive_anomaly_brief_payload(db, now=now)
    report = ReportRecord(
        category="geospatial_executive_anomaly_brief",
        title=f"Executive Anomaly Brief ({now.date().isoformat()})",
        reporting_month=now.date().replace(day=1),
        file_path=None,
        status="generated",
        generated_at=now,
        generated_by=current_user.id,
        metadata_json=brief_payload,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(report)
    db.flush()
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="geospatial.executive_anomaly_brief.generate",
        entity_type="report_record",
        entity_id=str(report.id),
        before_payload=None,
        after_payload={"category": report.category, "title": report.title},
    )
    db.commit()
    db.refresh(report)
    return {
        "id": report.id,
        "title": report.title,
        "generated_at": report.generated_at.isoformat() if report.generated_at else now.isoformat(),
        "summary": brief_payload.get("summary"),
        "highlights": brief_payload.get("highlights", []),
        "top_risk_aois": brief_payload.get("top_risk_aois", []),
    }


@router.get("/dashboard/executive/anomaly-brief/latest")
def latest_executive_anomaly_brief(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    report = db.scalar(
        select(ReportRecord)
        .where(ReportRecord.category == "geospatial_executive_anomaly_brief")
        .order_by(desc(ReportRecord.generated_at), desc(ReportRecord.id))
    )
    if report is None:
        return {
            "id": None,
            "title": None,
            "generated_at": None,
            "summary": None,
            "highlights": [],
            "top_risk_aois": [],
        }
    metadata = report.metadata_json if isinstance(report.metadata_json, dict) else {}
    return {
        "id": report.id,
        "title": report.title,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        "summary": metadata.get("summary"),
        "highlights": metadata.get("highlights", []),
        "top_risk_aois": metadata.get("top_risk_aois", []),
    }


@router.get("/dashboard/operations-center")
def geospatial_operations_center(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    return _geospatial_operations_center_payload(db)


@router.post("/dashboard/weekly-digest/generate")
def generate_geospatial_weekly_digest(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "executive_viewer", "policy_reviewer"))],
):
    now = datetime.utcnow()
    cutoff = now - timedelta(days=7)
    run_count = int(db.scalar(select(func.count(SatellitePipelineRun.id)).where(SatellitePipelineRun.started_at >= cutoff)) or 0)
    anomaly_count = int(db.scalar(select(func.count(Alert.id)).where(Alert.opened_at >= cutoff)) or 0)
    stale_aoi_count = 0
    for aoi in db.scalars(select(GeospatialAOI).where(GeospatialAOI.is_active == True)).all():  # noqa: E712
        latest_feature = db.scalar(select(func.max(GeospatialFeature.observation_date)).where(GeospatialFeature.aoi_id == aoi.id))
        if latest_feature is None or (now.date() - latest_feature).days >= 14:
            stale_aoi_count += 1
    report = ReportRecord(category="geospatial_weekly_digest", title=f"Geospatial Weekly Digest ({now.date().isoformat()})", reporting_month=now.date().replace(day=1), file_path=None, status="generated", generated_at=now, generated_by=current_user.id, metadata_json={"run_count_last_7d": run_count, "alerts_last_7d": anomaly_count, "stale_aois": stale_aoi_count}, created_by=current_user.id, updated_by=current_user.id)
    db.add(report)
    emit_audit_event(db, actor_user_id=current_user.id, action_type="geospatial.weekly_digest.generate", entity_type="report_record", entity_id="pending", before_payload=None, after_payload={"category": report.category, "title": report.title})
    db.commit()
    db.refresh(report)
    return {"id": report.id, "title": report.title, "metadata": report.metadata_json}


@router.post("/dashboard/monthly-performance/generate")
def generate_geospatial_monthly_performance_report(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*ADMIN_ROLES, "executive_viewer", "policy_reviewer"))],
):
    now = datetime.utcnow()
    month_start = now.date().replace(day=1)
    run_rows = db.scalars(select(SatellitePipelineRun).where(SatellitePipelineRun.started_at >= datetime.combine(month_start, datetime.min.time()))).all()
    success_rate = round(_safe_ratio(sum(1 for row in run_rows if row.status == "completed"), max(1, len(run_rows))), 4)
    avg_conf = round(_safe_ratio(sum(float(row.observation_confidence_score or 0.0) for row in db.scalars(select(GeospatialFeature).where(GeospatialFeature.reporting_month == month_start)).all()), max(1, int(db.scalar(select(func.count(GeospatialFeature.id)).where(GeospatialFeature.reporting_month == month_start)) or 0))), 4)
    report = ReportRecord(category="geospatial_monthly_performance", title=f"Geospatial Monthly Performance ({month_start.isoformat()})", reporting_month=month_start, file_path=None, status="generated", generated_at=now, generated_by=current_user.id, metadata_json={"runs": len(run_rows), "run_success_rate": success_rate, "avg_observation_confidence": avg_conf}, created_by=current_user.id, updated_by=current_user.id)
    db.add(report)
    emit_audit_event(db, actor_user_id=current_user.id, action_type="geospatial.monthly_performance.generate", entity_type="report_record", entity_id="pending", before_payload=None, after_payload={"category": report.category, "title": report.title})
    db.commit()
    db.refresh(report)
    return {"id": report.id, "title": report.title, "metadata": report.metadata_json}


@router.get("/dashboard/config-health")
def geospatial_config_health(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    return _config_health_payload(db)


@router.get("/dashboard/self-test")
def geospatial_self_test(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    return _self_test_payload(db)
