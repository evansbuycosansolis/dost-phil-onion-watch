from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models import GeospatialAOI, GeospatialFeature, SatellitePipelineRun, SatelliteScene

logger = get_logger(__name__)


def _reporting_month(d: date) -> date:
    return d.replace(day=1)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def queue_feature_refresh_run(
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
        run_type="feature_refresh",
        backend=backend,
        status=status,
        started_at=datetime.utcnow(),
        finished_at=None,
        triggered_by=triggered_by,
        correlation_id=correlation_id,
        aoi_id=aoi_id,
        sources_json={"sources": sources or []},
        parameters_json={"lookback_days": settings.geospatial_default_lookback_days},
        results_json={},
        notes=notes,
    )
    db.add(run)
    db.flush()
    return run


def execute_feature_refresh_run(
    db: Session,
    *,
    run_id: int,
    aoi_id: int | None = None,
    sources: list[str] | None = None,
) -> SatellitePipelineRun:
    run = db.scalar(select(SatellitePipelineRun).where(SatellitePipelineRun.id == run_id))
    if run is None:
        raise ValueError(f"feature refresh run not found: {run_id}")

    if run.status == "cancelled":
        if run.finished_at is None:
            run.finished_at = datetime.utcnow()
            db.flush()
        return run

    if run.status == "cancel_requested":
        run.status = "cancelled"
        run.finished_at = datetime.utcnow()
        run.results_json = {
            **(run.results_json or {}),
            "cancelled": {"phase": "before_start"},
        }
        db.flush()
        return run

    started_at = datetime.utcnow()
    run.status = "running"
    run.finished_at = None
    run.parameters_json = {"lookback_days": settings.geospatial_default_lookback_days}
    db.flush()

    try:
        allow_sources = set(sources or [])
        lookback_start = started_at - timedelta(days=settings.geospatial_default_lookback_days)

        effective_aoi_id = aoi_id if aoi_id is not None else run.aoi_id
        aoi_query = select(GeospatialAOI).where(GeospatialAOI.is_active == True)  # noqa: E712
        if effective_aoi_id is not None:
            aoi_query = aoi_query.where(GeospatialAOI.id == effective_aoi_id)
        aois = db.scalars(aoi_query.order_by(GeospatialAOI.id)).all()

        totals = {"aois_scanned": len(aois), "scenes_scanned": 0, "features_inserted": 0, "features_updated": 0}
        cancelled = False

        def _should_cancel() -> bool:
            db.refresh(run)
            return run.status in {"cancel_requested", "cancelled"}

        for aoi in aois:
            if _should_cancel():
                cancelled = True
                break
            scene_query = select(SatelliteScene).where(
                and_(
                    SatelliteScene.aoi_id == aoi.id,
                    SatelliteScene.acquired_at >= lookback_start,
                )
            )
            if allow_sources:
                scene_query = scene_query.where(SatelliteScene.source.in_(sorted(list(allow_sources))))

            scenes = db.scalars(scene_query.order_by(SatelliteScene.acquired_at.desc())).all()
            totals["scenes_scanned"] += len(scenes)

            for scene in scenes:
                if _should_cancel():
                    cancelled = True
                    break
                obs_date = scene.acquired_at.date()

                existing = db.scalar(
                    select(GeospatialFeature).where(
                        and_(
                            GeospatialFeature.aoi_id == aoi.id,
                            GeospatialFeature.source == scene.source,
                            GeospatialFeature.observation_date == obs_date,
                        )
                    )
                )

                cloud = scene.cloud_score
                if cloud is None:
                    confidence = 0.65
                else:
                    confidence = 1.0 - _clamp01(cloud)

                if existing is None:
                    db.add(
                        GeospatialFeature(
                            aoi_id=aoi.id,
                            source=scene.source,
                            observation_date=obs_date,
                            reporting_month=_reporting_month(obs_date),
                            cloud_score=cloud,
                            vegetation_vigor_score=None,
                            crop_activity_score=None,
                            observation_confidence_score=_clamp01(confidence),
                            processing_run_id=run.id,
                            features_json={
                                "scene_id": scene.scene_id,
                                "acquired_at": scene.acquired_at.isoformat(),
                            },
                            quality_json={
                                "confidence_method": "scene_metadata_cloud",
                            },
                        )
                    )
                    totals["features_inserted"] += 1
                else:
                    existing.cloud_score = cloud
                    existing.observation_confidence_score = _clamp01(confidence)
                    existing.processing_run_id = run.id
                    existing.features_json = {**(existing.features_json or {}), "scene_id": scene.scene_id}
                    totals["features_updated"] += 1

            if cancelled:
                break

        if cancelled:
            run.status = "cancelled"
            run.finished_at = datetime.utcnow()
            run.results_json = {"materialized": totals, "cancelled": {"phase": "materialization"}}
            logger.info("Geospatial feature refresh cancelled", extra={"run_id": run.id, **totals})
        else:
            run.status = "completed"
            run.finished_at = datetime.utcnow()
            run.results_json = {"materialized": totals}
            logger.info("Geospatial feature refresh completed", extra={"run_id": run.id, **totals})
    except Exception as exc:  # pragma: no cover
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.results_json = {"error": str(exc)}
        raise
    finally:
        db.flush()

    return run


def run_feature_refresh(
    db: Session,
    *,
    triggered_by: int | None,
    correlation_id: str | None,
    aoi_id: int | None = None,
    sources: list[str] | None = None,
    backend: str = "gee",
    notes: str | None = None,
) -> SatellitePipelineRun:
    """Materialize AOI-level feature rows from discovered scenes.

    This intentionally stays "features-not-imagery": it uses scene metadata (e.g., cloud)
    to populate `geospatial_features` and establishes provenance for later extraction.
    """

    run = queue_feature_refresh_run(
        db,
        triggered_by=triggered_by,
        correlation_id=correlation_id,
        aoi_id=aoi_id,
        sources=sources,
        backend=backend,
        notes=notes,
        status="running",
    )
    return execute_feature_refresh_run(db, run_id=run.id, aoi_id=aoi_id, sources=sources)
