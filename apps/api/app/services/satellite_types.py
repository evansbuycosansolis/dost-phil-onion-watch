from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NormalizedSceneRecord:
    source: str
    scene_id: str
    acquired_at: datetime
    aoi_id: int | None
    cloud_score: float | None
    spatial_resolution_m: int | None
    bands_available: list[str]
    processing_status: str = "ready"
    footprint_geojson: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class SatelliteAdapter:
    """Source adapter contract.

    Adapters are responsible for scene discovery and returning normalized scene metadata.
    Feature extraction is handled by later phases.
    """

    source: str

    def discover_scenes(
        self,
        *,
        aoi_boundary_geojson: dict[str, Any],
        aoi_id: int | None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[NormalizedSceneRecord]:
        raise NotImplementedError
