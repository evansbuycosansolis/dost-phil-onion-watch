from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _parse_datetime(value: str) -> datetime:
    # STAC commonly uses RFC3339 with a trailing 'Z'.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _flatten_coords(coords: Any) -> Iterable[tuple[float, float]]:
    if coords is None:
        return []

    if isinstance(coords, (list, tuple)) and len(coords) == 2 and all(isinstance(x, (int, float)) for x in coords):
        return [(float(coords[0]), float(coords[1]))]

    if isinstance(coords, (list, tuple)):
        out: list[tuple[float, float]] = []
        for item in coords:
            out.extend(list(_flatten_coords(item)))
        return out

    return []


def geojson_to_bbox(geojson: dict[str, Any]) -> tuple[float, float, float, float]:
    if not geojson:
        raise ValueError("AOI boundary geojson is empty")

    if isinstance(geojson.get("bbox"), (list, tuple)) and len(geojson["bbox"]) >= 4:
        bbox = geojson["bbox"]
        return float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])

    geometry = geojson
    if geojson.get("type") == "Feature":
        geometry = geojson.get("geometry") or {}
    elif geojson.get("type") == "FeatureCollection":
        # Union bbox across all features (simple and sufficient for discovery).
        boxes = [geojson_to_bbox(feature) for feature in (geojson.get("features") or [])]
        if not boxes:
            raise ValueError("FeatureCollection has no features")
        minx = min(b[0] for b in boxes)
        miny = min(b[1] for b in boxes)
        maxx = max(b[2] for b in boxes)
        maxy = max(b[3] for b in boxes)
        return minx, miny, maxx, maxy

    coords = geometry.get("coordinates")
    points = list(_flatten_coords(coords))
    if not points:
        raise ValueError(f"Unable to compute bbox from geojson type={geometry.get('type')}")

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def normalize_cloud_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        cloud_pct = float(value)
    except Exception:
        return None

    # STAC eo:cloud_cover is usually 0..100
    if cloud_pct > 1.0:
        cloud = cloud_pct / 100.0
    else:
        cloud = cloud_pct
    return max(0.0, min(1.0, float(cloud)))


def stac_search_items(
    *,
    collection: str,
    bbox: tuple[float, float, float, float],
    start: datetime | None,
    end: datetime | None,
    limit: int,
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    effective_end = end or now
    effective_start = start or (effective_end - timedelta(days=settings.geospatial_default_lookback_days))

    url = settings.stac_api_url.rstrip("/") + "/search"
    payload = {
        "collections": [collection],
        "bbox": [bbox[0], bbox[1], bbox[2], bbox[3]],
        "datetime": f"{effective_start.isoformat()}Z/{effective_end.isoformat()}Z",
        "limit": max(1, min(int(limit), 500)),
        "sortby": [{"field": "datetime", "direction": "desc"}],
    }

    try:
        response = httpx.post(url, json=payload, timeout=settings.stac_timeout_seconds)
        response.raise_for_status()
        data = response.json()
        features = data.get("features") or []
        if not isinstance(features, list):
            return []
        return [item for item in features if isinstance(item, dict)]
    except Exception as exc:
        logger.warning(
            "STAC search failed",
            extra={"collection": collection, "error": str(exc), "url": url},
        )
        return []


def stac_item_datetime(item: dict[str, Any]) -> datetime | None:
    props = item.get("properties") or {}
    value = props.get("datetime") or props.get("start_datetime")
    if not value:
        return None
    try:
        return _parse_datetime(str(value))
    except Exception:
        return None
