from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.services.satellite_ingestion_service import run_ingestion

logger = get_logger(__name__)


def run_geospatial_ingest(
    db: Session,
    *,
    correlation_id: str | None = None,
    aoi_id: int | None = None,
    sources: list[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit_per_source: int = 200,
    backend: str = "gee",
) -> dict:
    run = run_ingestion(
        db,
        triggered_by=None,
        correlation_id=correlation_id,
        aoi_id=aoi_id,
        sources=sources,
        start=start,
        end=end,
        limit_per_source=limit_per_source,
        backend=backend,
    )
    return {"run_id": run.id, "status": run.status, "results": run.results_json}
