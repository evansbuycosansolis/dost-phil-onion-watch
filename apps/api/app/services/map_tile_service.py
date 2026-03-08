from __future__ import annotations

import hashlib

SUPPORTED_LAYER_KEYS = {
    "crop_activity_score",
    "vegetation_vigor_score",
    "radar_change_score",
    "cloud_confidence_score",
    "observation_confidence_score",
}


def _layer_hex_color(layer_key: str) -> str:
    digest = hashlib.sha256(layer_key.encode("utf-8")).hexdigest()
    return f"#{digest[:6]}"


def generate_map_tiles(*, layer_key: str, cache_max_age_seconds: int = 300) -> dict:
    normalized_key = layer_key.strip().lower()
    if normalized_key not in SUPPORTED_LAYER_KEYS:
        return {
            "layer_key": layer_key,
            "status": "failed",
            "error": "unsupported_layer",
        }

    return {
        "layer_key": normalized_key,
        "status": "ready",
        "tile_url_template": f"/api/v1/geospatial/map/tiles/{normalized_key}" + "/{z}/{x}/{y}.png",
        "cache_control": f"public, max-age={max(0, int(cache_max_age_seconds))}",
        "min_zoom": 6,
        "max_zoom": 14,
        "palette_hint": _layer_hex_color(normalized_key),
    }
