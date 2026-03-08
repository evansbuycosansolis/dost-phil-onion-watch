from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import GeospatialAOI, SatellitePipelineRun, SatelliteScene
from app.services.hls_service import HLSAdapter
from app.services.landsat_service import LandsatAdapter
from app.services.sentinel1_service import Sentinel1Adapter
from app.services.sentinel2_service import Sentinel2Adapter
from app.services.satellite_types import NormalizedSceneRecord, SatelliteAdapter

logger = get_logger(__name__)


def _adapter_registry() -> list[SatelliteAdapter]:
    # Source adapters are active by default; configurable source selection is handled by caller `sources`.
    return [
        Sentinel2Adapter(),
        Sentinel1Adapter(),
        HLSAdapter(),
        LandsatAdapter(),
    ]


def _upsert_scene(db: Session, record: NormalizedSceneRecord) -> tuple[SatelliteScene, bool]:
    existing = db.scalar(
        select(SatelliteScene).where(
            SatelliteScene.source == record.source,
            SatelliteScene.scene_id == record.scene_id,
        )
    )
    if existing is not None:
        return existing, False

    scene = SatelliteScene(
        source=record.source,
        scene_id=record.scene_id,
        acquired_at=record.acquired_at,
        aoi_id=record.aoi_id,
        cloud_score=record.cloud_score,
        spatial_resolution_m=record.spatial_resolution_m,
        bands_available={"bands": record.bands_available},
        footprint_geojson=record.footprint_geojson,
        processing_status=record.processing_status,
        metadata_json=record.metadata or {},
    )
    db.add(scene)
    db.flush()
    return scene, True


def discover_scenes(
    db: Session,
    *,
    aoi_id: int | None = None,
    sources: list[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit_per_source: int = 200,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    """Discover scenes for AOIs and persist normalized scene metadata.

    Adapters query STAC collections and return normalized scene records.
    """

    registry = _adapter_registry()
    if sources:
        allow = set(sources)
        registry = [adapter for adapter in registry if adapter.source in allow]

    aois_query = select(GeospatialAOI).where(GeospatialAOI.is_active == True)  # noqa: E712
    if aoi_id is not None:
        aois_query = aois_query.where(GeospatialAOI.id == aoi_id)

    aois = db.scalars(aois_query.order_by(GeospatialAOI.id)).all()

    totals = {
        "aois_scanned": len(aois),
        "sources": [adapter.source for adapter in registry],
        "discovered": 0,
        "inserted": 0,
        "existing": 0,
        "scene_refs": [],
    }

    for aoi in aois:
        if should_cancel and should_cancel():
            totals["cancelled"] = True
            return totals
        boundary = aoi.boundary_geojson
        for adapter in registry:
            if should_cancel and should_cancel():
                totals["cancelled"] = True
                return totals
            scenes = adapter.discover_scenes(
                aoi_boundary_geojson=boundary,
                aoi_id=aoi.id,
                start=start,
                end=end,
                limit=limit_per_source,
            )
            totals["discovered"] += len(scenes)
            for record in scenes:
                if should_cancel and should_cancel():
                    totals["cancelled"] = True
                    return totals
                _, created = _upsert_scene(db, record)
                if created:
                    totals["inserted"] += 1
                else:
                    totals["existing"] += 1
                totals["scene_refs"].append(
                    {
                        "source": record.source,
                        "scene_id": record.scene_id,
                        "aoi_id": record.aoi_id,
                        "acquired_at": record.acquired_at.isoformat() if record.acquired_at else None,
                        "cloud_score": record.cloud_score,
                        "spatial_resolution_m": record.spatial_resolution_m,
                        "processing_status": record.processing_status,
                        "provenance_status": "created" if created else "existing",
                    }
                )

    return totals


def queue_ingestion_run(
    db: Session,
    *,
    triggered_by: int | None,
    correlation_id: str | None,
    aoi_id: int | None = None,
    sources: list[str] | None = None,
    backend: str = "gee",
    notes: str | None = None,
    status: str = "queued",
) -> SatellitePipelineRun:
    run = SatellitePipelineRun(
        run_type="ingest",
        backend=backend,
        status=status,
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        triggered_by=triggered_by,
        correlation_id=correlation_id,
        aoi_id=aoi_id,
        sources_json={"sources": sources or []},
        parameters_json={},
        results_json={},
        notes=notes,
    )
    db.add(run)
    db.flush()
    return run


def execute_ingestion_run(
    db: Session,
    *,
    run_id: int,
    aoi_id: int | None = None,
    sources: list[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit_per_source: int = 200,
) -> SatellitePipelineRun:
    run = db.scalar(select(SatellitePipelineRun).where(SatellitePipelineRun.id == run_id))
    if run is None:
        raise ValueError(f"ingestion run not found: {run_id}")

    if run.status == "cancelled":
        if run.finished_at is None:
            run.finished_at = datetime.now(timezone.utc)
            db.flush()
        return run

    if run.status == "cancel_requested":
        run.status = "cancelled"
        run.finished_at = datetime.now(timezone.utc)
        run.results_json = {
            **(run.results_json or {}),
            "cancelled": {"phase": "before_start"},
        }
        db.flush()
        return run

    run.status = "running"
    run.finished_at = None
    run.parameters_json = {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "limit_per_source": limit_per_source,
    }
    db.flush()

    try:
        def _should_cancel() -> bool:
            db.refresh(run)
            return run.status in {"cancel_requested", "cancelled"}

        totals = discover_scenes(
            db,
            aoi_id=aoi_id if aoi_id is not None else run.aoi_id,
            sources=sources,
            start=start,
            end=end,
            limit_per_source=limit_per_source,
            should_cancel=_should_cancel,
        )
        if totals.get("cancelled"):
            run.status = "cancelled"
            run.finished_at = datetime.now(timezone.utc)
            run.results_json = {
                "scene_discovery": totals,
                "cancelled": {"phase": "discovery"},
            }
            logger.info("Geospatial scene discovery cancelled", extra={"run_id": run.id, **totals})
        else:
            run.status = "completed"
            run.finished_at = datetime.now(timezone.utc)
            run.results_json = {"scene_discovery": totals}
            logger.info("Geospatial scene discovery completed", extra={"run_id": run.id, **totals})
    except Exception as exc:  # pragma: no cover
        run.status = "failed"
        run.finished_at = datetime.now(timezone.utc)
        run.results_json = {"error": str(exc)}
        raise
    finally:
        db.flush()

    return run


def run_ingestion(
    db: Session,
    *,
    triggered_by: int | None,
    correlation_id: str | None,
    aoi_id: int | None = None,
    sources: list[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit_per_source: int = 200,
    backend: str = "gee",
    notes: str | None = None,
) -> SatellitePipelineRun:
    run = queue_ingestion_run(
        db,
        triggered_by=triggered_by,
        correlation_id=correlation_id,
        aoi_id=aoi_id,
        sources=sources,
        backend=backend,
        notes=notes,
        status="running",
    )
    return execute_ingestion_run(
        db,
        run_id=run.id,
        aoi_id=aoi_id,
        sources=sources,
        start=start,
        end=end,
        limit_per_source=limit_per_source,
    )
