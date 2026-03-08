from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.satellite_types import NormalizedSceneRecord, SatelliteAdapter
from app.services.stac_service import geojson_to_bbox, normalize_cloud_score, stac_item_datetime, stac_search_items


class HLSAdapter(SatelliteAdapter):
    source = "hls"
    _collections = ("hls", "hls-l30", "hls-s30")

    def discover_scenes(
        self,
        *,
        aoi_boundary_geojson: dict[str, Any],
        aoi_id: int | None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[NormalizedSceneRecord]:
        bbox = geojson_to_bbox(aoi_boundary_geojson)

        items: list[dict[str, Any]] = []
        for collection in self._collections:
            items = stac_search_items(collection=collection, bbox=bbox, start=start, end=end, limit=limit)
            if items:
                break

        scenes: list[NormalizedSceneRecord] = []
        for item in items:
            acquired_at = stac_item_datetime(item)
            if acquired_at is None:
                continue

            props = item.get("properties") or {}
            cloud = normalize_cloud_score(props.get("eo:cloud_cover"))
            geometry = item.get("geometry") if isinstance(item.get("geometry"), dict) else None
            assets = item.get("assets") or {}
            bands = sorted(list(assets.keys())) if isinstance(assets, dict) else []

            scenes.append(
                NormalizedSceneRecord(
                    source=self.source,
                    scene_id=str(item.get("id") or ""),
                    acquired_at=acquired_at,
                    aoi_id=aoi_id,
                    cloud_score=cloud,
                    spatial_resolution_m=30,
                    bands_available=bands,
                    processing_status="discovered",
                    footprint_geojson=geometry,
                    metadata={
                        "collection": item.get("collection"),
                        "stac_version": item.get("stac_version"),
                        "properties": props,
                    },
                )
            )

        return [scene for scene in scenes if scene.scene_id]
