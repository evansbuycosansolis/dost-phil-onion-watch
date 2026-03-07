from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.satellite_types import NormalizedSceneRecord, SatelliteAdapter


class HLSAdapter(SatelliteAdapter):
    source = "hls"

    def discover_scenes(
        self,
        *,
        aoi_boundary_geojson: dict[str, Any],
        aoi_id: int | None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[NormalizedSceneRecord]:
        # Phase B stub: integrate NASA LP DAAC HLS (often via GEE) in Phase C.
        return []
