from __future__ import annotations

from datetime import datetime

from app.services.hls_service import HLSAdapter
from app.services.landsat_service import LandsatAdapter
from app.services.sentinel1_service import Sentinel1Adapter
from app.services.sentinel2_service import Sentinel2Adapter
from app.services.stac_service import geojson_to_bbox


def test_geojson_to_bbox_polygon():
    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [120.0, 12.0],
                [121.0, 12.0],
                [121.0, 13.0],
                [120.0, 13.0],
                [120.0, 12.0],
            ]
        ],
    }

    assert geojson_to_bbox(boundary) == (120.0, 12.0, 121.0, 13.0)


def test_sentinel2_adapter_normalizes_stac_items(monkeypatch):
    calls = {"count": 0, "last_payload": None}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "S2_TEST_SCENE_001",
                        "collection": "sentinel-2-l2a",
                        "stac_version": "1.0.0",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [120.0, 12.0],
                                    [121.0, 12.0],
                                    [121.0, 13.0],
                                    [120.0, 13.0],
                                    [120.0, 12.0],
                                ]
                            ],
                        },
                        "properties": {
                            "datetime": "2026-03-01T10:11:12Z",
                            "eo:cloud_cover": 25.0,
                        },
                        "assets": {"B02": {}, "B03": {}, "B04": {}, "B08": {}},
                    }
                ],
            }

    def fake_post(url, *, json, timeout):
        assert str(url).endswith("/search")
        assert json["collections"][0] in {"sentinel-2-l2a", "sentinel-2-l2a-cogs"}
        assert json["bbox"] == [120.0, 12.0, 121.0, 13.0]
        calls["count"] += 1
        calls["last_payload"] = json
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [120.0, 12.0],
                [121.0, 12.0],
                [121.0, 13.0],
                [120.0, 13.0],
                [120.0, 12.0],
            ]
        ],
    }

    adapter = Sentinel2Adapter()
    scenes = adapter.discover_scenes(
        aoi_boundary_geojson=boundary,
        aoi_id=123,
        start=datetime(2026, 3, 1, 0, 0, 0),
        end=datetime(2026, 3, 2, 0, 0, 0),
        limit=5,
    )

    assert calls["count"] == 1
    assert len(scenes) == 1
    scene = scenes[0]
    assert scene.source == "sentinel2"
    assert scene.scene_id == "S2_TEST_SCENE_001"
    assert scene.aoi_id == 123
    assert scene.cloud_score == 0.25
    assert scene.spatial_resolution_m == 10
    assert "B08" in scene.bands_available


def test_sentinel1_adapter_normalizes_stac_items(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "S1_TEST_SCENE_001",
                        "collection": "sentinel-1-grd",
                        "stac_version": "1.0.0",
                        "geometry": None,
                        "properties": {
                            "datetime": "2026-03-01T10:11:12Z",
                        },
                        "assets": {"vv": {}, "vh": {}},
                    }
                ],
            }

    def fake_post(url, *, json, timeout):
        assert json["collections"][0] in {"sentinel-1-grd", "sentinel-1-grd-cogs"}
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [120.0, 12.0],
                [121.0, 12.0],
                [121.0, 13.0],
                [120.0, 13.0],
                [120.0, 12.0],
            ]
        ],
    }

    adapter = Sentinel1Adapter()
    scenes = adapter.discover_scenes(
        aoi_boundary_geojson=boundary,
        aoi_id=321,
        start=datetime(2026, 3, 1, 0, 0, 0),
        end=datetime(2026, 3, 2, 0, 0, 0),
        limit=5,
    )

    assert len(scenes) == 1
    scene = scenes[0]
    assert scene.source == "sentinel1"
    assert scene.scene_id == "S1_TEST_SCENE_001"
    assert scene.cloud_score is None
    assert scene.spatial_resolution_m == 10


def test_hls_adapter_normalizes_stac_items(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "HLS_TEST_SCENE_001",
                        "collection": "hls-l30",
                        "stac_version": "1.0.0",
                        "geometry": None,
                        "properties": {
                            "datetime": "2026-03-01T10:11:12Z",
                            "eo:cloud_cover": 45.0,
                        },
                        "assets": {"B04": {}, "B05": {}, "Fmask": {}},
                    }
                ],
            }

    def fake_post(url, *, json, timeout):
        assert json["collections"][0] in {"hls", "hls-l30", "hls-s30"}
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [120.0, 12.0],
                [121.0, 12.0],
                [121.0, 13.0],
                [120.0, 13.0],
                [120.0, 12.0],
            ]
        ],
    }

    adapter = HLSAdapter()
    scenes = adapter.discover_scenes(
        aoi_boundary_geojson=boundary,
        aoi_id=1001,
        start=datetime(2026, 3, 1, 0, 0, 0),
        end=datetime(2026, 3, 2, 0, 0, 0),
        limit=5,
    )

    assert len(scenes) == 1
    scene = scenes[0]
    assert scene.source == "hls"
    assert scene.scene_id == "HLS_TEST_SCENE_001"
    assert scene.cloud_score == 0.45
    assert scene.spatial_resolution_m == 30
    assert "B04" in scene.bands_available


def test_landsat_adapter_normalizes_stac_items(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "LANDSAT_TEST_SCENE_001",
                        "collection": "landsat-c2-l2",
                        "stac_version": "1.0.0",
                        "geometry": None,
                        "properties": {
                            "datetime": "2026-03-01T10:11:12Z",
                            "landsat:cloud_cover_land": 18.0,
                        },
                        "assets": {"SR_B2": {}, "SR_B3": {}, "SR_B4": {}, "SR_B5": {}},
                    }
                ],
            }

    def fake_post(url, *, json, timeout):
        assert json["collections"][0] in {"landsat-c2-l2", "landsat-8-c2-l2", "landsat-9-c2-l2"}
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [120.0, 12.0],
                [121.0, 12.0],
                [121.0, 13.0],
                [120.0, 13.0],
                [120.0, 12.0],
            ]
        ],
    }

    adapter = LandsatAdapter()
    scenes = adapter.discover_scenes(
        aoi_boundary_geojson=boundary,
        aoi_id=1002,
        start=datetime(2026, 3, 1, 0, 0, 0),
        end=datetime(2026, 3, 2, 0, 0, 0),
        limit=5,
    )

    assert len(scenes) == 1
    scene = scenes[0]
    assert scene.source == "landsat"
    assert scene.scene_id == "LANDSAT_TEST_SCENE_001"
    assert scene.cloud_score == 0.18
    assert scene.spatial_resolution_m == 30
    assert "SR_B5" in scene.bands_available
