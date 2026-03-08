from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import GeospatialFeature


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_fusion_refresh(
    db: Session,
    *,
    correlation_id: str | None = None,
    since_date: date | None = None,
) -> dict:
    """Fuse optical/radar/change signals into AOI-level crop surveillance features."""

    cutoff_date = since_date or (datetime.now(timezone.utc).date() - timedelta(days=45))
    rows = list(
        db.scalars(
            select(GeospatialFeature)
            .where(GeospatialFeature.observation_date >= cutoff_date)
            .order_by(desc(GeospatialFeature.observation_date), GeospatialFeature.id.desc())
        )
    )

    updated = 0
    skipped = 0
    by_source: dict[str, int] = {}
    for row in rows:
        cloud = _to_float(row.cloud_score)
        cloud_penalty = _clamp01(cloud or 0.0)

        ndvi = _to_float(row.ndvi_mean)
        evi = _to_float(row.evi_mean)
        change = _to_float(row.change_score)
        radar_vv = _to_float(row.radar_backscatter_vv)
        radar_vh = _to_float(row.radar_backscatter_vh)

        optical_parts = [value for value in (ndvi, evi) if value is not None]
        optical_score = sum(optical_parts) / len(optical_parts) if optical_parts else None

        radar_parts = [value for value in (radar_vv, radar_vh) if value is not None]
        radar_score = sum(radar_parts) / len(radar_parts) if radar_parts else None

        if optical_score is None and radar_score is None and change is None:
            skipped += 1
            continue

        fused_components = [value for value in (optical_score, radar_score, change) if value is not None]
        fused_base = sum(fused_components) / len(fused_components)

        vegetation_vigor = _clamp01((optical_score if optical_score is not None else fused_base))
        crop_activity = _clamp01((0.7 * fused_base) + (0.3 * (1.0 - cloud_penalty)))
        confidence = _clamp01((0.65 * (1.0 - cloud_penalty)) + (0.35 * crop_activity))

        row.vegetation_vigor_score = round(vegetation_vigor, 4)
        row.crop_activity_score = round(crop_activity, 4)
        row.observation_confidence_score = round(confidence, 4)
        row.features_json = {
            **(row.features_json or {}),
            "fusion": {
                "correlation_id": correlation_id,
                "fused_at": datetime.now(timezone.utc).isoformat(),
                "optical_score": optical_score,
                "radar_score": radar_score,
                "change_score": change,
            },
        }
        row.quality_json = {
            **(row.quality_json or {}),
            "fusion_quality": {
                "cloud_penalty": round(cloud_penalty, 4),
                "input_count": len(fused_components),
                "status": "computed",
            },
        }
        updated += 1
        by_source[row.source] = by_source.get(row.source, 0) + 1

    db.flush()
    return {
        "status": "completed",
        "cutoff_date": cutoff_date.isoformat(),
        "rows_scanned": len(rows),
        "rows_updated": updated,
        "rows_skipped": skipped,
        "by_source": by_source,
    }
