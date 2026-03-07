from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.geospatial_feature_service import run_feature_refresh


def run_geospatial_refresh(
    db: Session,
    *,
    correlation_id: str | None = None,
    aoi_id: int | None = None,
    sources: list[str] | None = None,
    backend: str = "gee",
) -> dict:
    run = run_feature_refresh(
        db,
        triggered_by=None,
        correlation_id=correlation_id,
        aoi_id=aoi_id,
        sources=sources,
        backend=backend,
    )
    return {"run_id": run.id, "status": run.status, "results": run.results_json}
