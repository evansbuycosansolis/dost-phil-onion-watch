from datetime import date, datetime, timedelta
from pathlib import Path

from jose import jwt


def _configure_oidc_test_provider(monkeypatch, *, role_mapping: str, auto_provision: bool = False):
    import base64

    from app.core.config import settings
    from app.services import oidc_service

    issuer = "https://idp.test.local"
    audience = "phil-onion-watch-api"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    jwks_url = f"{issuer}/.well-known/jwks.json"
    secret = "oidc-test-secret-123"
    kid = "oidc-test-kid"
    encoded_secret = base64.urlsafe_b64encode(secret.encode("utf-8")).decode("utf-8").rstrip("=")

    class _FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload
            self.status_code = 200
            self.text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_get(url: str, timeout: float = 10.0):
        if url == discovery_url:
            return _FakeResponse({"issuer": issuer, "jwks_uri": jwks_url})
        if url == jwks_url:
            return _FakeResponse(
                {
                    "keys": [
                        {
                            "kty": "oct",
                            "k": encoded_secret,
                            "alg": "HS256",
                            "use": "sig",
                            "kid": kid,
                        }
                    ]
                }
            )
        raise RuntimeError(f"Unexpected OIDC URL: {url}")

    monkeypatch.setattr(settings, "oidc_enabled", True, raising=False)
    monkeypatch.setattr(settings, "oidc_issuer_url", issuer, raising=False)
    monkeypatch.setattr(settings, "oidc_discovery_url", discovery_url, raising=False)
    monkeypatch.setattr(settings, "oidc_jwks_url", "", raising=False)
    monkeypatch.setattr(settings, "oidc_audience", audience, raising=False)
    monkeypatch.setattr(settings, "oidc_signing_algorithms", "HS256", raising=False)
    monkeypatch.setattr(settings, "oidc_role_claim", "roles", raising=False)
    monkeypatch.setattr(settings, "oidc_role_mapping", role_mapping, raising=False)
    monkeypatch.setattr(settings, "oidc_email_claim", "email", raising=False)
    monkeypatch.setattr(settings, "oidc_name_claim", "name", raising=False)
    monkeypatch.setattr(settings, "oidc_subject_claim", "sub", raising=False)
    monkeypatch.setattr(settings, "oidc_mfa_claim", "amr", raising=False)
    monkeypatch.setattr(settings, "oidc_mfa_boolean_claim", "mfa", raising=False)
    monkeypatch.setattr(settings, "oidc_mfa_methods", "mfa,otp,webauthn", raising=False)
    monkeypatch.setattr(settings, "oidc_privileged_roles", "super_admin,provincial_admin", raising=False)
    monkeypatch.setattr(settings, "oidc_sync_roles_on_login", True, raising=False)
    monkeypatch.setattr(settings, "oidc_auto_provision_users", auto_provision, raising=False)
    monkeypatch.setattr(settings, "enforce_oidc_for_privileged_roles", False, raising=False)
    monkeypatch.setattr(oidc_service.httpx, "get", fake_get)
    oidc_service._discovery_cache.clear()
    oidc_service._jwks_cache.clear()

    return {"issuer": issuer, "audience": audience, "secret": secret, "kid": kid}


def _build_oidc_id_token(
    *,
    secret: str,
    kid: str,
    issuer: str,
    audience: str,
    subject: str,
    email: str,
    name: str,
    roles: list[str],
    amr: list[str] | None = None,
    mfa: bool | None = None,
) -> str:
    payload = {
        "iss": issuer,
        "aud": audience,
        "exp": int((datetime.utcnow() + timedelta(minutes=10)).timestamp()),
        "iat": int(datetime.utcnow().timestamp()),
        "sub": subject,
        "email": email,
        "name": name,
        "roles": roles,
    }
    if amr is not None:
        payload["amr"] = amr
    if mfa is not None:
        payload["mfa"] = mfa
    return jwt.encode(payload, secret, algorithm="HS256", headers={"kid": kid})


def test_auth_login_success(client):
    response = client.post("/api/v1/auth/login", json={"email": "super_admin@onionwatch.ph", "password": "ChangeMe123!"})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_auth_login_failure(client):
    response = client.post("/api/v1/auth/login", json={"email": "super_admin@onionwatch.ph", "password": "wrong-password"})
    assert response.status_code == 401


def test_auth_oidc_login_success_role_mapping_and_mfa(client, monkeypatch):
    provider = _configure_oidc_test_provider(monkeypatch, role_mapping="dost_super_admin:super_admin", auto_provision=False)
    token = _build_oidc_id_token(
        secret=provider["secret"],
        kid=provider["kid"],
        issuer=provider["issuer"],
        audience=provider["audience"],
        subject="oidc-super-admin-001",
        email="super_admin@onionwatch.ph",
        name="Super Admin",
        roles=["dost_super_admin"],
        amr=["pwd", "mfa"],
    )

    response = client.post("/api/v1/auth/oidc/login", json={"id_token": token})
    assert response.status_code == 200
    payload = response.json()
    assert payload["auth_source"] == "oidc"
    assert payload["mfa_verified"] is True
    assert "access_token" in payload

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert me.status_code == 200
    me_payload = me.json()["user"]
    assert "super_admin" in me_payload["roles"]
    assert me_payload["auth_source"] == "oidc"
    assert me_payload["mfa_verified"] is True


def test_auth_oidc_login_requires_mfa_for_privileged_roles(client, monkeypatch):
    provider = _configure_oidc_test_provider(monkeypatch, role_mapping="dost_super_admin:super_admin", auto_provision=False)
    token = _build_oidc_id_token(
        secret=provider["secret"],
        kid=provider["kid"],
        issuer=provider["issuer"],
        audience=provider["audience"],
        subject="oidc-super-admin-002",
        email="super_admin@onionwatch.ph",
        name="Super Admin",
        roles=["dost_super_admin"],
        amr=["pwd"],
    )

    response = client.post("/api/v1/auth/oidc/login", json={"id_token": token})
    assert response.status_code == 403
    assert "MFA" in response.json()["detail"]


def test_auth_oidc_role_mapping_auto_provision(client, monkeypatch):
    provider = _configure_oidc_test_provider(monkeypatch, role_mapping="dost_analyst:market_analyst", auto_provision=True)
    token = _build_oidc_id_token(
        secret=provider["secret"],
        kid=provider["kid"],
        issuer=provider["issuer"],
        audience=provider["audience"],
        subject="oidc-analyst-001",
        email="oidc.analyst@onionwatch.ph",
        name="OIDC Analyst",
        roles=["dost_analyst"],
        amr=["pwd"],
    )

    response = client.post("/api/v1/auth/oidc/login", json={"id_token": token})
    assert response.status_code == 200
    access_token = response.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    assert "market_analyst" in me.json()["user"]["roles"]


def test_auth_local_login_blocked_when_oidc_enforced_for_privileged(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "enforce_oidc_for_privileged_roles", True, raising=False)
    response = client.post("/api/v1/auth/login", json={"email": "super_admin@onionwatch.ph", "password": "ChangeMe123!"})
    assert response.status_code == 403
    assert "OIDC login is required" in response.json()["detail"]

    allowed = client.post("/api/v1/auth/login", json={"email": "municipal_encoder@onionwatch.ph", "password": "ChangeMe123!"})
    assert allowed.status_code == 200


def test_role_enforcement(client, municipal_headers):
    response = client.post(
        "/api/v1/users/",
        json={"email": "blocked@example.com", "full_name": "Blocked", "roles": ["auditor"]},
        headers=municipal_headers,
    )
    assert response.status_code == 403


def test_dashboard_overview_endpoints(client, auth_headers):
    endpoints = [
        "/api/v1/dashboard/provincial/overview",
        "/api/v1/dashboard/warehouses/overview",
        "/api/v1/dashboard/prices/overview",
        "/api/v1/dashboard/imports/overview",
        "/api/v1/dashboard/alerts/overview",
        "/api/v1/dashboard/reports/overview",
        "/api/v1/dashboard/admin/overview",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint, headers=auth_headers)
        assert response.status_code == 200, endpoint


def test_geospatial_endpoints_smoke(client, auth_headers):
    from app.core.database import SessionLocal
    from app.services.geospatial_feature_service import queue_feature_refresh_run
    from app.services.satellite_ingestion_service import queue_ingestion_run

    response = client.get("/api/v1/geospatial/aois", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    layers = client.get("/api/v1/geospatial/map/layers", headers=auth_headers)
    assert layers.status_code == 200
    payload = layers.json()
    assert "layers" in payload

    ingest = client.post(
        "/api/v1/geospatial/ingest/run",
        headers=auth_headers,
        params={"sources": ["sentinel2"]},
    )
    assert ingest.status_code == 200
    assert "run_id" in ingest.json()

    refresh = client.post(
        "/api/v1/geospatial/features/recompute",
        headers=auth_headers,
        params={"sources": ["sentinel2"], "backend": "gee"},
    )
    assert refresh.status_code == 200
    assert "run_id" in refresh.json()

    runs = client.get("/api/v1/geospatial/runs?limit=10", headers=auth_headers)
    assert runs.status_code == 200
    run_rows = runs.json()
    assert isinstance(run_rows, list)
    assert any(row["id"] == ingest.json()["run_id"] for row in run_rows)
    assert any(row["id"] == refresh.json()["run_id"] for row in run_rows)
    assert all("run_type" in row and "status" in row for row in run_rows)

    run_detail = client.get(f"/api/v1/geospatial/runs/{refresh.json()['run_id']}", headers=auth_headers)
    assert run_detail.status_code == 200
    detail_payload = run_detail.json()
    assert detail_payload["id"] == refresh.json()["run_id"]
    assert "provenance_summary" in detail_payload
    assert "related_scenes" in detail_payload
    assert "related_features" in detail_payload

    scene_page = client.get(f"/api/v1/geospatial/runs/{refresh.json()['run_id']}/provenance/scenes?page=1&page_size=5", headers=auth_headers)
    assert scene_page.status_code == 200
    scene_payload = scene_page.json()
    assert scene_payload["run_id"] == refresh.json()["run_id"]
    assert scene_payload["page"] == 1
    assert scene_payload["page_size"] == 5
    assert "rows" in scene_payload

    filtered_scene_page = client.get(
        f"/api/v1/geospatial/runs/{refresh.json()['run_id']}/provenance/scenes?page=1&page_size=5&search=sentinel&sort_by=source&sort_dir=asc",
        headers=auth_headers,
    )
    assert filtered_scene_page.status_code == 200
    filtered_scene_payload = filtered_scene_page.json()
    assert filtered_scene_payload["page"] == 1
    assert filtered_scene_payload["page_size"] == 5

    feature_page = client.get(f"/api/v1/geospatial/runs/{refresh.json()['run_id']}/provenance/features?page=1&page_size=5", headers=auth_headers)
    assert feature_page.status_code == 200
    feature_payload = feature_page.json()
    assert feature_payload["run_id"] == refresh.json()["run_id"]
    assert feature_payload["page"] == 1
    assert feature_payload["page_size"] == 5
    assert "rows" in feature_payload

    filtered_feature_page = client.get(
        f"/api/v1/geospatial/runs/{refresh.json()['run_id']}/provenance/features?page=1&page_size=5&sort_by=source&sort_dir=asc",
        headers=auth_headers,
    )
    assert filtered_feature_page.status_code == 200

    with SessionLocal() as db:
        queued_run = queue_feature_refresh_run(
            db,
            triggered_by=1,
            correlation_id=None,
            aoi_id=1,
            sources=["sentinel1"],
            backend="gee",
            notes="Queued for cancel test",
            status="queued",
        )
        db.commit()
        queued_run_id = queued_run.id

    cancel = client.post(f"/api/v1/geospatial/runs/{queued_run_id}/cancel", headers=auth_headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    retry = client.post(f"/api/v1/geospatial/runs/{queued_run_id}/retry", headers=auth_headers)
    assert retry.status_code == 200
    retry_payload = retry.json()
    assert retry_payload["run_id"] != queued_run_id
    assert retry_payload["status"] in {"queued", "running", "completed", "cancelled"}

    with SessionLocal() as db:
        failed_run = queue_ingestion_run(
            db,
            triggered_by=1,
            correlation_id=None,
            aoi_id=1,
            sources=["sentinel2"],
            backend="gee",
            notes="Failed for retry test",
            status="failed",
        )
        failed_run.parameters_json = {
            "start": None,
            "end": None,
            "limit_per_source": 25,
        }
        db.commit()
        failed_run_id = failed_run.id

    retry_failed = client.post(f"/api/v1/geospatial/runs/{failed_run_id}/retry", headers=auth_headers)
    assert retry_failed.status_code == 200
    retry_failed_payload = retry_failed.json()
    assert retry_failed_payload["run_id"] != failed_run_id

    non_retryable = client.post(f"/api/v1/geospatial/runs/{ingest.json()['run_id']}/retry", headers=auth_headers)
    assert non_retryable.status_code == 409


def test_geospatial_aoi_crud_and_versioning(client, auth_headers):
    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [120.0, 12.0],
                [120.1, 12.0],
                [120.1, 12.1],
                [120.0, 12.1],
                [120.0, 12.0],
            ]
        ],
    }

    create = client.post(
        "/api/v1/geospatial/aois",
        headers=auth_headers,
        json={
            "code": "TEST-AOI-CRUD-01",
            "name": "Test AOI",
            "scope_type": "custom",
            "boundary_geojson": boundary,
            "source": "test",
            "change_reason": "create",
        },
    )
    assert create.status_code == 200
    created = create.json()
    assert created["id"]
    assert created["code"] == "TEST-AOI-CRUD-01"
    assert created["is_active"] is True

    aoi_id = created["id"]

    versions = client.get(f"/api/v1/geospatial/aois/{aoi_id}/versions", headers=auth_headers)
    assert versions.status_code == 200
    rows = versions.json()
    assert len(rows) == 1
    assert rows[0]["version"] == 1
    assert rows[0]["change_type"] == "create"

    update = client.put(
        f"/api/v1/geospatial/aois/{aoi_id}",
        headers=auth_headers,
        json={
            "name": "Test AOI (Updated)",
            "change_reason": "update",
            "boundary_geojson": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [120.0, 12.0],
                        [120.12, 12.0],
                        [120.12, 12.12],
                        [120.0, 12.12],
                        [120.0, 12.0],
                    ]
                ],
            },
        },
    )
    assert update.status_code == 200
    updated = update.json()
    assert updated["name"] == "Test AOI (Updated)"

    versions = client.get(f"/api/v1/geospatial/aois/{aoi_id}/versions", headers=auth_headers)
    assert versions.status_code == 200
    rows = versions.json()
    assert len(rows) >= 2
    assert rows[0]["version"] == 2
    assert rows[0]["change_type"] == "update"

    deactivate = client.delete(
        f"/api/v1/geospatial/aois/{aoi_id}",
        headers=auth_headers,
        params={"change_reason": "cleanup"},
    )
    assert deactivate.status_code == 200
    deactivated = deactivate.json()
    assert deactivated["is_active"] is False


def test_geospatial_advanced_backlog_endpoints(client, auth_headers):
    aois = client.get("/api/v1/geospatial/aois", headers=auth_headers)
    assert aois.status_code == 200
    aoi_rows = aois.json()
    assert aoi_rows
    aoi_id = int(aoi_rows[0]["id"])

    metadata = client.get(f"/api/v1/geospatial/aois/{aoi_id}/metadata", headers=auth_headers)
    assert metadata.status_code == 200
    updated_metadata = client.post(
        f"/api/v1/geospatial/aois/{aoi_id}/metadata",
        headers=auth_headers,
        json={"tags": ["test-tag"], "labels": ["test-label"], "watchlist_flag": True},
    )
    assert updated_metadata.status_code == 200
    assert "test-tag" in (updated_metadata.json().get("tags") or [])

    favorite = client.post(f"/api/v1/geospatial/aois/{aoi_id}/favorite", headers=auth_headers, json={"is_pinned": True})
    assert favorite.status_code == 200
    favorites = client.get("/api/v1/geospatial/favorites/aois", headers=auth_headers)
    assert favorites.status_code == 200
    assert any(row["aoi_id"] == aoi_id for row in favorites.json())

    note = client.post(
        f"/api/v1/geospatial/aois/{aoi_id}/notes",
        headers=auth_headers,
        json={"note_type": "note", "body": "Test advanced note", "mentions": ["@policy_reviewer"]},
    )
    assert note.status_code == 200
    notes = client.get(f"/api/v1/geospatial/aois/{aoi_id}/notes", headers=auth_headers)
    assert notes.status_code == 200
    assert any(row["body"] == "Test advanced note" for row in notes.json())

    attachment = client.post(
        f"/api/v1/geospatial/aois/{aoi_id}/attachments",
        headers=auth_headers,
        json={"asset_type": "photo", "title": "Seed attachment", "url": "https://example.com/photo.jpg", "notes": "seed"},
    )
    assert attachment.status_code == 200

    link = client.post(
        f"/api/v1/geospatial/aois/{aoi_id}/document-links",
        headers=auth_headers,
        json={"title": "Seed doc link", "url": "https://example.com/doc"},
    )
    assert link.status_code == 200

    activity = client.get(f"/api/v1/geospatial/aois/{aoi_id}/activity?limit=20", headers=auth_headers)
    assert activity.status_code == 200
    assert "events" in activity.json()

    analytics = client.get(f"/api/v1/geospatial/aois/{aoi_id}/analytics?months=6", headers=auth_headers)
    assert analytics.status_code == 200
    assert "risk_score" in analytics.json()

    export_geojson = client.get("/api/v1/geospatial/aois/export/geojson", headers=auth_headers)
    assert export_geojson.status_code == 200
    assert export_geojson.json()["type"] == "FeatureCollection"

    export_csv = client.get("/api/v1/geospatial/aois/export/csv", headers=auth_headers)
    assert export_csv.status_code == 200
    assert "text/csv" in export_csv.headers.get("content-type", "")

    runs = client.get("/api/v1/geospatial/runs?limit=5", headers=auth_headers)
    assert runs.status_code == 200
    run_rows = runs.json()
    assert run_rows
    run_id = int(run_rows[0]["id"])

    diagnostics = client.get(f"/api/v1/geospatial/runs/{run_id}/diagnostics", headers=auth_headers)
    assert diagnostics.status_code == 200
    assert "phase_progress" in diagnostics.json()

    update_priority = client.post(f"/api/v1/geospatial/runs/{run_id}/priority", headers=auth_headers, json={"queue_priority": 88})
    assert update_priority.status_code == 200
    assert update_priority.json()["queue_priority"] == 88

    update_notes = client.post(
        f"/api/v1/geospatial/runs/{run_id}/notes",
        headers=auth_headers,
        json={"operator_notes": "Advanced backlog endpoint test"},
    )
    assert update_notes.status_code == 200

    clone = client.post(
        f"/api/v1/geospatial/runs/{run_id}/clone",
        headers=auth_headers,
        json={"notes": "clone from test", "queue_priority": 70, "retry_strategy": "standard"},
    )
    assert clone.status_code == 200
    cloned_run_id = clone.json()["run_id"]

    compare = client.post(
        "/api/v1/geospatial/run-compare",
        headers=auth_headers,
        json={"left_run_id": run_id, "right_run_id": cloned_run_id},
    )
    assert compare.status_code == 200
    compare_payload = compare.json()
    assert "diff" in compare_payload
    assert "metrics_summary" in compare_payload
    assert "provenance_diff" in compare_payload
    assert "scene_overlap_matrix" in compare_payload
    assert "feature_overlap_matrix" in compare_payload
    assert "parameter_delta" in compare_payload
    assert compare_payload["scene_overlap_matrix"]["values"]
    assert compare_payload["feature_overlap_matrix"]["values"]

    lineage = client.get(f"/api/v1/geospatial/runs/{cloned_run_id}/lineage", headers=auth_headers)
    assert lineage.status_code == 200
    assert lineage.json()["root_run_id"] == cloned_run_id
    assert len(lineage.json().get("nodes", [])) >= 1

    upstream = client.get(f"/api/v1/geospatial/runs/{cloned_run_id}/dependencies/upstream", headers=auth_headers)
    assert upstream.status_code == 200
    upstream_payload = upstream.json()
    assert upstream_payload["direction"] == "upstream"
    assert upstream_payload["root_run_id"] == cloned_run_id
    assert upstream_payload["node_count"] >= 1

    downstream = client.get(f"/api/v1/geospatial/runs/{run_id}/dependencies/downstream", headers=auth_headers)
    assert downstream.status_code == 200
    downstream_payload = downstream.json()
    assert downstream_payload["direction"] == "downstream"
    assert downstream_payload["root_run_id"] == run_id
    assert downstream_payload["node_count"] >= 1

    reproducibility = client.get(f"/api/v1/geospatial/runs/{cloned_run_id}/reproducibility", headers=auth_headers)
    assert reproducibility.status_code == 200
    reproducibility_payload = reproducibility.json()
    assert reproducibility_payload["run_id"] == cloned_run_id
    assert reproducibility_payload["badge"] in {"high", "medium", "low"}
    assert isinstance(reproducibility_payload["diagnostics"], list)
    assert "summary" in reproducibility_payload

    manifest = client.get(f"/api/v1/geospatial/runs/{run_id}/artifacts/manifest", headers=auth_headers)
    assert manifest.status_code == 200
    manifest_payload = manifest.json()
    assert manifest_payload["run_id"] == run_id
    assert manifest_payload["artifacts"]
    first_artifact_key = manifest_payload["artifacts"][0]["artifact_key"]

    artifact_download = client.get(
        f"/api/v1/geospatial/runs/{run_id}/artifacts/{first_artifact_key}",
        headers=auth_headers,
    )
    assert artifact_download.status_code == 200
    assert artifact_download.content

    download_center = client.get(f"/api/v1/geospatial/runs/{run_id}/artifacts/download-center", headers=auth_headers)
    assert download_center.status_code == 200
    center_payload = download_center.json()
    assert center_payload["run_id"] == run_id
    assert center_payload["artifact_count"] >= 1
    assert center_payload["total_size_bytes"] >= 1
    assert center_payload["artifacts"]

    preset = client.post(
        "/api/v1/geospatial/run-presets",
        headers=auth_headers,
        json={
            "name": f"test-preset-{run_id}",
            "run_type": "feature_refresh",
            "description": "test",
            "sources": ["sentinel-2"],
            "parameters": {"limit_per_source": 123},
            "retry_strategy": "standard",
            "queue_priority": 75,
        },
    )
    assert preset.status_code == 200

    schedule = client.post(
        "/api/v1/geospatial/run-schedules",
        headers=auth_headers,
        json={
            "name": f"test-schedule-{run_id}",
            "run_type": "feature_refresh",
            "cron_expression": "0 4 1 * *",
            "timezone": "Asia/Manila",
            "recurrence_template": "monthly_start",
            "retry_strategy": "standard",
            "queue_priority": 75,
            "is_active": True,
            "sources": ["sentinel-2"],
            "parameters": {"reference_run_id": run_id},
            "notify_channels": ["email:test@example.com"],
        },
    )
    assert schedule.status_code == 200

    filter_preset = client.post(
        "/api/v1/geospatial/run-filter-presets",
        headers=auth_headers,
        json={"preset_type": "scene", "name": f"scene-filter-{run_id}", "filters": {"scene_source": "sentinel-2"}},
    )
    assert filter_preset.status_code == 200

    filter_list = client.get("/api/v1/geospatial/run-filter-presets?preset_type=scene", headers=auth_headers)
    assert filter_list.status_code == 200
    assert any(row["preset_type"] == "scene" for row in filter_list.json())

    operator_dashboard = client.get("/api/v1/geospatial/dashboard/operator", headers=auth_headers)
    assert operator_dashboard.status_code == 200
    assert "totals" in operator_dashboard.json()

    executive_dashboard = client.get("/api/v1/geospatial/dashboard/executive", headers=auth_headers)
    assert executive_dashboard.status_code == 200
    assert "totals" in executive_dashboard.json()
    assert "monthly_run_trend" in executive_dashboard.json()
    assert executive_dashboard.json()["executive_catalog_coverage"]["fully_covered"] is True

    surveillance = client.get(f"/api/v1/geospatial/aois/{aoi_id}/surveillance/overview", headers=auth_headers)
    assert surveillance.status_code == 200
    surveillance_payload = surveillance.json()
    assert "aoi_heatmap_by_anomaly_density" in surveillance_payload
    assert "aoi_weather_overlay_integration" in surveillance_payload
    assert "aoi_confidence_adjusted_anomaly_score" in surveillance_payload
    assert "aoi_adaptive_threshold_tuning" in surveillance_payload
    assert "aoi_intervention_recommendation_engine" in surveillance_payload
    assert "aoi_market_price_correlation_panel" in surveillance_payload
    assert "aoi_crop_calendar_overlay" in surveillance_payload
    assert surveillance_payload["aoi_catalog_coverage"]["fully_covered"] is True

    aoi_ops = client.get(f"/api/v1/geospatial/aois/{aoi_id}/operations/overview", headers=auth_headers)
    assert aoi_ops.status_code == 200
    assert "aoi_false_positive_review_workflow" in aoi_ops.json()
    assert "aoi_mobile_ready_field_checklist" in aoi_ops.json()
    assert "aoi_escalation_policy" in aoi_ops.json()
    assert "aoi_parcel_subdivision_support" in aoi_ops.json()
    assert "aoi_confidence_waiver_workflow" in aoi_ops.json()
    assert "aoi_local_language_summary_export" in aoi_ops.json()
    assert aoi_ops.json()["aoi_catalog_coverage"]["fully_covered"] is True

    review_update = client.post(
        f"/api/v1/geospatial/aois/{aoi_id}/operations/review",
        headers=auth_headers,
        json={"action": "verify", "status": "approved", "reason": "test-verify", "feature_id": 0},
    )
    assert review_update.status_code == 200

    field_visit_update = client.post(
        f"/api/v1/geospatial/aois/{aoi_id}/operations/field-visit",
        headers=auth_headers,
        json={"action": "request", "notes": "test field visit"},
    )
    assert field_visit_update.status_code == 200

    notification_update = client.post(
        f"/api/v1/geospatial/aois/{aoi_id}/operations/notification-settings",
        headers=auth_headers,
        json={
            "sms_recipients": ["+639170001111"],
            "email_recipients": ["ops@example.com"],
            "report_subscription": {"weekly_digest": True, "monthly_performance_report": True},
            "escalation_policy": {"level_1": "municipal_encoder", "level_2": "provincial_admin"},
            "sla_target_settings": {"ack_hours": 6, "resolve_hours": 36},
        },
    )
    assert notification_update.status_code == 200

    config_update = client.post(
        f"/api/v1/geospatial/aois/{aoi_id}/operations/configure",
        headers=auth_headers,
        json={
            "parcel_structure": {
                "subdivisions": [{"id": "S1", "name": "North Parcel"}],
                "merged_parcels": [{"id": "M1", "children": ["S1", "S2"]}],
                "ownership_ledger": [{"owner": "LGU", "effective_date": "2026-01-01"}],
            },
            "governance": {
                "confidence_waiver": {"active": True, "reason": "Cloud contamination"},
                "exception_cases": [{"id": "EX-1", "status": "open"}],
                "dispute_resolution": [{"id": "DP-1", "status": "pending"}],
                "community_feedback": [{"id": "FB-1", "message": "Needs field validation"}],
                "retention_policy": {"retention_days": 400, "legal_hold": False},
                "privacy_controls": {"redaction_mode": "strict", "export_watermarking": True},
                "source_policy": {"preferred_sources": ["sentinel-2"], "excluded_sources": ["landsat-8"]},
                "compliance_evidence": {"bundle_id": "EV-1", "last_verified_at": "2026-03-01T00:00:00"},
            },
            "multilingual": {"labels": {"en": "AOI Test", "tl": "Pook Test"}, "default_language": "tl", "supported_languages": ["en", "tl"]},
            "interventions": {
                "recommended_action_checklist": [{"item": "Validate boundaries", "done": False}],
                "readiness_score": 0.83,
                "history": [{"action": "monitoring", "result": "improving"}],
                "fertilizer_schedule": [{"date": "2026-03-15", "type": "NPK"}],
                "irrigation_events": [{"date": "2026-03-10", "volume": 10}],
                "manual_sampling_records": [{"date": "2026-03-08", "observer": "analyst"}],
                "crop_rotation_history": [{"season": "2025-Q4", "crop": "onion"}],
            },
        },
    )
    assert config_update.status_code == 200

    localized_summary = client.get(
        f"/api/v1/geospatial/aois/{aoi_id}/summary/localized?lang=tl",
        headers=auth_headers,
    )
    assert localized_summary.status_code == 200
    assert localized_summary.headers["content-type"].startswith("application/json")

    offline_packet = client.get(f"/api/v1/geospatial/aois/{aoi_id}/operations/offline-packet", headers=auth_headers)
    assert offline_packet.status_code == 200
    assert offline_packet.headers["content-type"].startswith("application/json")

    multi_aoi_overview = client.post(
        "/api/v1/geospatial/dashboard/multi-aoi/overview",
        headers=auth_headers,
        json={"aoi_ids": [aoi_id]},
    )
    assert multi_aoi_overview.status_code == 200
    multi_payload = multi_aoi_overview.json()
    assert "multi_aoi_bulk_compare_dashboard" in multi_payload
    assert "province_level_anomaly_leaderboard" in multi_payload
    assert "source_drift_detection_panel" in multi_payload

    multi_aoi_export = client.post(
        "/api/v1/geospatial/dashboard/multi-aoi/export-workbook",
        headers=auth_headers,
        json={"aoi_ids": [aoi_id]},
    )
    assert multi_aoi_export.status_code == 200
    assert multi_aoi_export.headers["content-type"].startswith("text/csv")

    run_ops = client.get(f"/api/v1/geospatial/runs/{run_id}/operations/command-center", headers=auth_headers)
    assert run_ops.status_code == 200
    run_ops_payload = run_ops.json()
    assert "run_signed_export_package" in run_ops_payload
    assert "run_automated_remediation_suggestion" in run_ops_payload
    assert "run_queue_saturation_alert" in run_ops_payload
    assert "run_approval_gate_before_release" in run_ops_payload
    assert "run_chain_of_custody_timeline" in run_ops_payload
    assert "run_publish_unpublish_workflow" in run_ops_payload
    assert "run_artifact_retention_policy" in run_ops_payload
    assert "run_decision_log" in run_ops_payload
    assert "run_scenario_replay" in run_ops_payload
    assert run_ops_payload["run_catalog_coverage"]["fully_covered"] is True
    assert "run_a_supervised_field_pilot_with_real_operators_and_reviewers" in run_ops_payload

    approval_gate_status = client.get(f"/api/v1/geospatial/runs/{run_id}/operations/approval-gate", headers=auth_headers)
    assert approval_gate_status.status_code == 200
    assert "status" in approval_gate_status.json()

    approval_gate_request = client.post(
        f"/api/v1/geospatial/runs/{run_id}/operations/approval-gate",
        headers=auth_headers,
        json={"status": "requested", "notes": "request release review"},
    )
    assert approval_gate_request.status_code == 200
    assert approval_gate_request.json()["approval_gate"]["status"] in {"requested", "pending_review"}

    approval_gate_approve = client.post(
        f"/api/v1/geospatial/runs/{run_id}/operations/approval-gate",
        headers=auth_headers,
        json={"status": "approved", "notes": "release approved"},
    )
    assert approval_gate_approve.status_code == 200
    assert approval_gate_approve.json()["approval_gate"]["status"] == "approved"

    chain_of_custody = client.get(f"/api/v1/geospatial/runs/{run_id}/operations/chain-of-custody", headers=auth_headers)
    assert chain_of_custody.status_code == 200
    chain_payload = chain_of_custody.json()
    assert chain_payload["run_id"] == run_id
    assert isinstance(chain_payload.get("events"), list)
    assert chain_payload["event_count"] >= 1

    publish_update = client.post(
        f"/api/v1/geospatial/runs/{run_id}/operations/publish",
        headers=auth_headers,
        json={"action": "publish", "channel": "executive"},
    )
    assert publish_update.status_code == 200

    archive_update = client.post(
        f"/api/v1/geospatial/runs/{run_id}/operations/archive",
        headers=auth_headers,
        json={"action": "archive", "tier": "cold", "retention_days": 365},
    )
    assert archive_update.status_code == 200

    governance_update = client.post(
        f"/api/v1/geospatial/runs/{run_id}/operations/governance",
        headers=auth_headers,
        json={"action": "decision", "decision": "approve_release", "notes": "test"},
    )
    assert governance_update.status_code == 200

    scenario_update = client.post(
        f"/api/v1/geospatial/runs/{run_id}/operations/scenario",
        headers=auth_headers,
        json={"action": "synthetic_test", "enabled": True, "dataset": "synthetic-default"},
    )
    assert scenario_update.status_code == 200

    handoff_update = client.post(
        f"/api/v1/geospatial/runs/{run_id}/operations/handoff",
        headers=auth_headers,
        json={"note": "handoff test", "next_operator": "ops-night"},
    )
    assert handoff_update.status_code == 200

    audit_approval_update = client.post(
        f"/api/v1/geospatial/runs/{run_id}/operations/audit-approval",
        headers=auth_headers,
        json={"status": "approved", "notes": "approval test"},
    )
    assert audit_approval_update.status_code == 200

    manual_override_update = client.post(
        f"/api/v1/geospatial/runs/{run_id}/operations/manual-override",
        headers=auth_headers,
        json={"enabled": True, "reason": "test override"},
    )
    assert manual_override_update.status_code == 200

    signed_package = client.get(f"/api/v1/geospatial/runs/{run_id}/artifacts/signed-package", headers=auth_headers)
    assert signed_package.status_code == 200
    assert signed_package.headers["content-type"].startswith("application/json")

    evidence_bundle = client.get(f"/api/v1/geospatial/runs/{run_id}/artifacts/evidence-bundle", headers=auth_headers)
    assert evidence_bundle.status_code == 200
    assert evidence_bundle.headers["content-type"].startswith("application/json")

    scene_intel = client.get(f"/api/v1/geospatial/runs/{run_id}/scene-intelligence", headers=auth_headers)
    assert scene_intel.status_code == 200
    scene_payload = scene_intel.json()
    assert "rows" in scene_payload
    assert scene_payload["scene_catalog_coverage"]["fully_covered"] is True
    if scene_payload["rows"]:
        first_scene = scene_payload["rows"][0]
        assert "scene_provenance_chain_viewer" in first_scene
        assert "scene_polygon_clipping_preview" in first_scene
        assert "scene_georegistration_quality_score" in first_scene
        assert "scene_tile_cache_inspector" in first_scene
        scene_chain = client.get(
            f"/api/v1/geospatial/runs/{run_id}/scenes/provenance-chain?source={first_scene['source']}&scene_id={first_scene['scene_id']}",
            headers=auth_headers,
        )
        assert scene_chain.status_code == 200
        assert "timeline" in scene_chain.json()

    feature_intel = client.get(f"/api/v1/geospatial/runs/{run_id}/feature-intelligence", headers=auth_headers)
    assert feature_intel.status_code == 200
    feature_payload = feature_intel.json()
    assert "rows" in feature_payload
    assert "feature_spatial_clustering_panel" in feature_payload
    assert "feature_cross_source_consensus_score_panel" in feature_payload
    assert "feature_threshold_what_if_simulator" in feature_payload
    assert "feature_review_sla_timer_panel" in feature_payload
    assert feature_payload["feature_catalog_coverage"]["fully_covered"] is True
    if feature_payload["rows"]:
        assert "feature_cross_source_consensus_score" in feature_payload["rows"][0]
        assert "feature_human_review_priority_score" in feature_payload["rows"][0]

    if feature_payload["rows"]:
        feature_id = feature_payload["rows"][0]["feature_id"]
        annotation = client.post(
            f"/api/v1/geospatial/features/{feature_id}/annotation",
            headers=auth_headers,
            json={"annotation": "test annotation", "label": "note"},
        )
        assert annotation.status_code == 200

        review = client.post(
            f"/api/v1/geospatial/features/{feature_id}/review",
            headers=auth_headers,
            json={"decision": "approved", "notes": "test review"},
        )
        assert review.status_code == 200

        recalibrate = client.post(
            f"/api/v1/geospatial/features/{feature_id}/recalibrate",
            headers=auth_headers,
            json={"target_confidence": 0.81},
        )
        assert recalibrate.status_code == 200

    weekly_digest = client.post("/api/v1/geospatial/dashboard/weekly-digest/generate", headers=auth_headers)
    assert weekly_digest.status_code == 200
    assert weekly_digest.json()["id"]

    monthly_perf = client.post("/api/v1/geospatial/dashboard/monthly-performance/generate", headers=auth_headers)
    assert monthly_perf.status_code == 200
    assert monthly_perf.json()["id"]

    executive_brief = client.post("/api/v1/geospatial/dashboard/executive/anomaly-brief/generate", headers=auth_headers)
    assert executive_brief.status_code == 200
    brief_payload = executive_brief.json()
    assert brief_payload["id"] is not None
    assert brief_payload["summary"]
    assert isinstance(brief_payload["top_risk_aois"], list)

    latest_brief = client.get("/api/v1/geospatial/dashboard/executive/anomaly-brief/latest", headers=auth_headers)
    assert latest_brief.status_code == 200
    assert latest_brief.json()["id"] == brief_payload["id"]

    ops_center = client.get("/api/v1/geospatial/dashboard/operations-center", headers=auth_headers)
    assert ops_center.status_code == 200
    assert "geospatial_notification_center" in ops_center.json()
    assert "geospatial_configuration_drift_alert" in ops_center.json()
    assert ops_center.json()["geospatial_catalog_coverage"]["fully_covered"] is True
    assert "geospatial_case_management_for_anomaly_investigations" in ops_center.json()
    assert "geospatial_decision_playbooks_per_anomaly_type" in ops_center.json()
    assert "geospatial_gis_interoperability_expansion_for_geotiff_shapefile_wms_wfs_style_exchange" in ops_center.json()
    assert "geospatial_create_a_phased_rollout_plan_by_province_municipality_and_user_cohort" in ops_center.json()
    assert "geospatial_maintain_a_data_dictionary_for_geospatial_review_reporting_and_audit_entities" in ops_center.json()

    config_health = client.get("/api/v1/geospatial/dashboard/config-health", headers=auth_headers)
    assert config_health.status_code == 200
    assert "health_status" in config_health.json()

    self_test = client.get("/api/v1/geospatial/dashboard/self-test", headers=auth_headers)
    assert self_test.status_code == 200
    assert "checks" in self_test.json()


def test_metrics_endpoint_and_observability_overview(client, auth_headers):
    ok = client.get("/health")
    assert ok.status_code == 200

    missing = client.get("/api/v1/not-found-endpoint")
    assert missing.status_code == 404

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "pow_api_requests_total" in metrics.text
    assert "pow_job_runs_total" in metrics.text

    obs = client.get("/api/v1/admin/observability/overview?window_minutes=60", headers=auth_headers)
    assert obs.status_code == 200
    payload = obs.json()
    assert "api" in payload
    assert "jobs" in payload
    assert "active_alerts" in payload
    assert "requests_total" in payload["api"]
    assert "runs_total" in payload["jobs"]


def test_trace_correlation_between_api_and_job_runs(client, auth_headers):
    correlation_id = "trace-test-pipeline-001"
    response = client.post(
        "/api/v1/admin/pipeline/run",
        headers={**auth_headers, "x-correlation-id": correlation_id},
    )
    assert response.status_code == 200

    trace = client.get(f"/api/v1/admin/observability/traces/{correlation_id}", headers=auth_headers)
    assert trace.status_code == 200
    payload = trace.json()
    assert payload["correlation_id"] == correlation_id
    assert any(row["job_name"] == "monthly_pipeline" for row in payload["job_runs"])
    assert any(row["path"] == "/api/v1/admin/pipeline/run" for row in payload["runtime"]["api_requests"])


def test_forecast_run_endpoint(client, auth_headers):
    response = client.post(
        "/api/v1/forecasting/run",
        json={"run_month": date.today().replace(day=1).isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    latest_response = client.get("/api/v1/forecasting/latest", headers=auth_headers)
    assert latest_response.status_code == 200
    latest_payload = latest_response.json()
    assert latest_payload["run"] is not None
    assert latest_payload["outputs"]
    assert all(output.get("selected_model") for output in latest_payload["outputs"])
    assert all(isinstance(output.get("fallback_order"), list) for output in latest_payload["outputs"])
    assert latest_payload["diagnostics"]["selected_model_counts"]

    diagnostics_response = client.get("/api/v1/forecasting/diagnostics/latest", headers=auth_headers)
    assert diagnostics_response.status_code == 200
    diagnostics_payload = diagnostics_response.json()
    assert diagnostics_payload["run_id"] is not None
    assert diagnostics_payload["municipality_diagnostics"]
    assert diagnostics_payload["municipality_diagnostics"][0]["candidates"]


def test_anomaly_run_endpoint(client, auth_headers):
    response = client.post(
        "/api/v1/anomalies/run",
        json={"reporting_month": date.today().replace(day=1).isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert "created" in response.json()

    anomalies_response = client.get("/api/v1/anomalies", headers=auth_headers)
    assert anomalies_response.status_code == 200
    anomalies = anomalies_response.json()
    assert anomalies
    assert any(
        "rule_contributions" in (row.get("metrics") or {}) and "score_contributions" in (row.get("metrics") or {}) for row in anomalies
    )


def test_anomaly_threshold_update_versioning_and_audit(client, auth_headers, municipal_headers):
    thresholds_response = client.get("/api/v1/anomalies/thresholds", headers=auth_headers)
    assert thresholds_response.status_code == 200
    thresholds = thresholds_response.json()
    assert thresholds

    target = next((row for row in thresholds if row["anomaly_type"] == "price_spread_outlier"), thresholds[0])
    anomaly_type = target["anomaly_type"]
    previous_version = target["version"]
    previous_thresholds = target["thresholds"]

    forbidden_update = client.post(
        f"/api/v1/anomalies/thresholds/{anomaly_type}",
        headers=municipal_headers,
        json={"thresholds": {"spread_threshold": 30}, "reason": "unauthorized test"},
    )
    assert forbidden_update.status_code == 403

    update_response = client.post(
        f"/api/v1/anomalies/thresholds/{anomaly_type}",
        headers=auth_headers,
        json={"thresholds": {"spread_threshold": 30}, "reason": "analyst calibration"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["version"] == previous_version + 1
    assert updated["thresholds"]["spread_threshold"] == 30
    assert updated["thresholds"] != previous_thresholds

    versions_response = client.get(f"/api/v1/anomalies/thresholds/{anomaly_type}/versions", headers=auth_headers)
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert versions
    assert versions[0]["version"] >= updated["version"]
    assert any(row.get("change_reason") == "analyst calibration" for row in versions)

    audit_response = client.get("/api/v1/audit/events", headers=auth_headers)
    assert audit_response.status_code == 200
    assert any(event["action_type"] == "anomaly.threshold.update" for event in audit_response.json())


def test_alert_acknowledge_resolve_flow(client, auth_headers):
    list_response = client.get("/api/v1/alerts", headers=auth_headers)
    assert list_response.status_code == 200
    alerts = list_response.json()
    assert alerts
    alert_id = alerts[0]["id"]

    ack_response = client.post(f"/api/v1/alerts/{alert_id}/acknowledge", json={"notes": "Noted"}, headers=auth_headers)
    assert ack_response.status_code == 200
    assert ack_response.json()["status"] == "acknowledged"

    resolve_response = client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"notes": "Action complete"}, headers=auth_headers)
    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "resolved"


def test_document_upload_search_flow(client, auth_headers, tmp_path):
    doc_path = tmp_path / "sample_doc.txt"
    doc_path.write_text("Onion storage policy for release pacing and market stabilization.", encoding="utf-8")

    with doc_path.open("rb") as handle:
        upload_response = client.post(
            "/api/v1/documents/upload",
            headers=auth_headers,
            files={"file": ("sample_doc.txt", handle, "text/plain")},
            data={"title": "Sample Policy", "source_type": "policy"},
        )

    assert upload_response.status_code == 200
    upload_payload = upload_response.json()
    document_id = upload_payload["id"]
    assert upload_payload["status"] == "queued"
    assert upload_payload["ingestion_job_id"] > 0

    processed = False
    for _ in range(6):
        process_response = client.post("/api/v1/documents/jobs/process?limit=10", headers=auth_headers)
        assert process_response.status_code == 200

        detail_response = client.get(f"/api/v1/documents/{document_id}", headers=auth_headers)
        assert detail_response.status_code == 200
        detail = detail_response.json()
        if detail["status"] == "processed":
            processed = True
            break
    assert processed, "document should be processed from queue"
    assert detail["progress_pct"] == 100.0
    assert detail["failure_reason"] is None

    search_response = client.post(
        "/api/v1/documents/search",
        headers=auth_headers,
        json={"query": "release pacing", "top_k": 3},
    )
    assert search_response.status_code == 200
    assert "results" in search_response.json()


def test_document_ingestion_chunk_retry_safety(client, auth_headers, monkeypatch, tmp_path):
    from app.services.document_ingestion_service import get_store

    doc_path = tmp_path / "retry_doc.txt"
    doc_path.write_text("retry-marker onion policy chunk for retry safety", encoding="utf-8")

    with doc_path.open("rb") as handle:
        upload_response = client.post(
            "/api/v1/documents/upload",
            headers=auth_headers,
            files={"file": ("retry_doc.txt", handle, "text/plain")},
            data={"title": "Retry Policy", "source_type": "policy"},
        )

    assert upload_response.status_code == 200
    document_id = upload_response.json()["id"]

    store = get_store()
    original_embed = store.embedder.embed
    state = {"failed_once": False}

    def flaky_embed(text: str):
        if "retry-marker" in text and not state["failed_once"]:
            state["failed_once"] = True
            raise RuntimeError("transient embedding failure")
        return original_embed(text)

    monkeypatch.setattr(store.embedder, "embed", flaky_embed)

    first_process = client.post("/api/v1/documents/jobs/process?limit=10", headers=auth_headers)
    assert first_process.status_code == 200

    detail_after_first = client.get(f"/api/v1/documents/{document_id}", headers=auth_headers)
    assert detail_after_first.status_code == 200
    first_payload = detail_after_first.json()
    assert first_payload["status"] in {"retrying", "failed", "processing"}
    assert first_payload["failed_chunks"] >= 1

    second_process = client.post("/api/v1/documents/jobs/process?limit=10", headers=auth_headers)
    assert second_process.status_code == 200

    final_detail = client.get(f"/api/v1/documents/{document_id}", headers=auth_headers)
    assert final_detail.status_code == 200
    final_payload = final_detail.json()
    assert final_payload["status"] == "processed"
    assert final_payload["failed_chunks"] == 0
    assert final_payload["processed_chunks"] == final_payload["total_chunks"]
    assert final_payload["progress_pct"] == 100.0

    jobs_response = client.get(f"/api/v1/documents/jobs?document_id={document_id}", headers=auth_headers)
    assert jobs_response.status_code == 200
    jobs = jobs_response.json()
    assert jobs
    assert jobs[0]["attempt_count"] >= 2


def test_mobile_sync_contract_idempotency_conflicts_and_audit(client, municipal_headers, auth_headers):
    reporting_month = date.today().replace(day=1)
    harvest_date = reporting_month + timedelta(days=5)
    batch_id = f"mobile-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-sj-001"

    payload = {
        "contract_version": "1.0",
        "sync_batch_id": batch_id,
        "provenance": {
            "source_channel": "mobile_app",
            "client_id": "municipal-field-app",
            "device_id": "android-sj-001",
            "app_version": "1.2.0",
            "submitted_at": datetime.utcnow().isoformat() + "Z",
        },
        "submissions": [
            {
                "idempotency_key": f"harvest-{batch_id}-item001",
                "submission_type": "harvest_report",
                "observed_server_updated_at": "2026-03-01T00:00:00Z",
                "payload": {
                    "municipality_id": 1,
                    "reporting_month": reporting_month.isoformat(),
                    "harvest_date": harvest_date.isoformat(),
                    "volume_tons": 17.5,
                    "quality_grade": "A",
                },
            }
        ],
    }

    first = client.post("/api/v1/production/mobile-sync", headers=municipal_headers, json=payload)
    assert first.status_code == 200
    first_result = first.json()["results"][0]
    assert first_result["status"] in {"accepted", "updated"}
    assert first_result["source_submission_id"] is not None

    duplicate = client.post("/api/v1/production/mobile-sync", headers=municipal_headers, json=payload)
    assert duplicate.status_code == 200
    duplicate_result = duplicate.json()["results"][0]
    assert duplicate_result["status"] == "duplicate"

    idempotency_conflict_payload = {
        **payload,
        "submissions": [
            {
                **payload["submissions"][0],
                "payload": {
                    **payload["submissions"][0]["payload"],
                    "volume_tons": 22.1,
                },
            }
        ],
    }
    idempotency_conflict = client.post(
        "/api/v1/production/mobile-sync",
        headers=municipal_headers,
        json=idempotency_conflict_payload,
    )
    assert idempotency_conflict.status_code == 200
    conflict_result = idempotency_conflict.json()["results"][0]
    assert conflict_result["status"] == "conflict"
    assert conflict_result["conflict_reason"] == "idempotency_key_reuse_with_different_payload"

    stale_conflict_payload = {
        **payload,
        "submissions": [
            {
                **payload["submissions"][0],
                "idempotency_key": f"harvest-{batch_id}-item002",
                "observed_server_updated_at": "2000-01-01T00:00:00Z",
                "payload": {
                    **payload["submissions"][0]["payload"],
                    "volume_tons": 23.3,
                },
            }
        ],
    }
    stale_conflict = client.post("/api/v1/production/mobile-sync", headers=municipal_headers, json=stale_conflict_payload)
    assert stale_conflict.status_code == 200
    stale_result = stale_conflict.json()["results"][0]
    assert stale_result["status"] == "conflict"
    assert stale_result["conflict_reason"] == "stale_observed_server_updated_at"

    submissions = client.get(
        f"/api/v1/production/mobile-sync/submissions?sync_batch_id={batch_id}&limit=50",
        headers=municipal_headers,
    )
    assert submissions.status_code == 200
    rows = submissions.json()
    assert rows
    assert all(row["source_channel"] == "mobile_app" for row in rows)
    assert any(row["status"] == "accepted" for row in rows)
    assert any(row["status"] == "conflict" for row in rows)

    audit_response = client.get("/api/v1/audit/events?limit=500", headers=auth_headers)
    assert audit_response.status_code == 200
    audit_rows = audit_response.json()
    assert any(row["action_type"] == "submission.mobile.batch.process" and row["entity_id"] == batch_id for row in audit_rows)
    assert any(row["action_type"] in {"submission.mobile.accepted", "submission.mobile.updated"} for row in audit_rows)
    assert any(row["action_type"] == "submission.mobile.conflict" for row in audit_rows)
    batch_events = [
        row
        for row in audit_rows
        if row["action_type"] == "submission.mobile.batch.process" and row["entity_id"] == batch_id
    ]
    assert batch_events
    metadata = batch_events[0].get("metadata") or {}
    assert metadata.get("source_channel") == "mobile_app"
    assert (metadata.get("provenance") or {}).get("client_id") == "municipal-field-app"


def test_mobile_sync_scope_guard_and_submission_visibility(client, municipal_headers, auth_headers):
    reporting_month = date.today().replace(day=1)
    scoped_violation_payload = {
        "contract_version": "1.0",
        "sync_batch_id": f"mobile-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-scope-deny",
        "provenance": {
            "source_channel": "mobile_app",
            "client_id": "municipal-field-app",
            "device_id": "android-sj-001",
            "app_version": "1.2.0",
        },
        "submissions": [
            {
                "idempotency_key": f"scope-deny-{datetime.utcnow().strftime('%H%M%S%f')}",
                "submission_type": "farmgate_price_report",
                "payload": {
                    "municipality_id": 2,
                    "report_date": reporting_month.isoformat(),
                    "reporting_month": reporting_month.isoformat(),
                    "price_per_kg": 54.2,
                },
            }
        ],
    }
    denied = client.post("/api/v1/production/mobile-sync", headers=municipal_headers, json=scoped_violation_payload)
    assert denied.status_code == 200
    denied_result = denied.json()["results"][0]
    assert denied_result["status"] == "rejected"
    assert "scope violation" in (denied_result["conflict_reason"] or "")

    admin_batch_id = f"mobile-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-admin-001"
    admin_payload = {
        "contract_version": "1.0",
        "sync_batch_id": admin_batch_id,
        "provenance": {
            "source_channel": "mobile_app",
            "client_id": "provincial-admin-app",
            "device_id": "admin-tablet-001",
            "app_version": "1.2.0",
        },
        "submissions": [
            {
                "idempotency_key": f"admin-sync-{datetime.utcnow().strftime('%H%M%S%f')}",
                "submission_type": "farmgate_price_report",
                "payload": {
                    "municipality_id": 2,
                    "report_date": reporting_month.isoformat(),
                    "reporting_month": reporting_month.isoformat(),
                    "price_per_kg": 56.8,
                },
            }
        ],
    }
    admin_submit = client.post("/api/v1/production/mobile-sync", headers=auth_headers, json=admin_payload)
    assert admin_submit.status_code == 200

    scoped_history = client.get(
        f"/api/v1/production/mobile-sync/submissions?sync_batch_id={admin_batch_id}&limit=20",
        headers=municipal_headers,
    )
    assert scoped_history.status_code == 200
    assert scoped_history.json() == []

    admin_history = client.get(
        f"/api/v1/production/mobile-sync/submissions?sync_batch_id={admin_batch_id}&limit=20",
        headers=auth_headers,
    )
    assert admin_history.status_code == 200
    assert admin_history.json()


def test_connector_ingestion_and_approval_flow(client, auth_headers):
    connectors = client.get("/api/v1/admin/connectors", headers=auth_headers)
    assert connectors.status_code == 200
    keys = {row["key"] for row in connectors.json()}
    assert {"da_price_feed", "boc_import_feed", "nfa_warehouse_stock_feed"}.issubset(keys)

    ingest = client.post(
        "/api/v1/admin/connectors/da_price_feed/ingest",
        headers=auth_headers,
        json={"limit": 50, "dry_run": False},
    )
    assert ingest.status_code == 200
    ingest_payload = ingest.json()
    assert ingest_payload["fetched_count"] >= 1
    assert ingest_payload["accepted_count"] + ingest_payload["duplicate_count"] + ingest_payload["conflict_count"] + ingest_payload["rejected_count"] == ingest_payload["fetched_count"]

    submissions_response = client.get(
        "/api/v1/admin/connectors/submissions?connector_key=da_price_feed&limit=100",
        headers=auth_headers,
    )
    assert submissions_response.status_code == 200
    submissions = submissions_response.json()
    assert submissions
    assert any(row["status"] == "pending_approval" for row in submissions)

    approvals_response = client.get(
        "/api/v1/admin/connectors/approvals?connector_key=da_price_feed&status=pending&limit=100",
        headers=auth_headers,
    )
    assert approvals_response.status_code == 200
    approvals = approvals_response.json()
    assert approvals
    workflow_id = approvals[0]["workflow_id"]

    approve = client.post(
        f"/api/v1/admin/connectors/approvals/{workflow_id}/approve",
        headers=auth_headers,
        json={"notes": "validated feed quality"},
    )
    assert approve.status_code == 200
    approve_payload = approve.json()
    assert approve_payload["status"] == "approved"
    assert approve_payload["source_submission_status"] == "approved"
    assert approve_payload["target_entity_type"] == "farmgate_price_report"
    assert approve_payload["target_entity_id"] is not None

    audit_response = client.get("/api/v1/audit/events?limit=500", headers=auth_headers)
    assert audit_response.status_code == 200
    actions = {row["action_type"] for row in audit_response.json()}
    assert "connector.ingestion.run" in actions
    assert "connector.approval.approve" in actions


def test_connector_reject_and_role_enforcement(client, auth_headers, municipal_headers):
    forbidden = client.post(
        "/api/v1/admin/connectors/nfa_warehouse_stock_feed/ingest",
        headers=municipal_headers,
        json={"limit": 50, "dry_run": False},
    )
    assert forbidden.status_code == 403

    ingest = client.post(
        "/api/v1/admin/connectors/nfa_warehouse_stock_feed/ingest",
        headers=auth_headers,
        json={"limit": 50, "dry_run": False},
    )
    assert ingest.status_code == 200
    ingest_payload = ingest.json()
    assert ingest_payload["accepted_count"] + ingest_payload["duplicate_count"] + ingest_payload["conflict_count"] + ingest_payload["rejected_count"] == ingest_payload["fetched_count"]

    approvals_response = client.get(
        "/api/v1/admin/connectors/approvals?connector_key=nfa_warehouse_stock_feed&status=pending&limit=100",
        headers=auth_headers,
    )
    assert approvals_response.status_code == 200
    approvals = approvals_response.json()
    assert approvals
    workflow_id = approvals[0]["workflow_id"]
    source_submission_id = approvals[0]["source_submission_id"]

    reject = client.post(
        f"/api/v1/admin/connectors/approvals/{workflow_id}/reject",
        headers=auth_headers,
        json={"notes": "failed manual verification"},
    )
    assert reject.status_code == 200
    reject_payload = reject.json()
    assert reject_payload["status"] == "rejected"
    assert reject_payload["source_submission_status"] == "rejected"

    submissions_response = client.get(
        "/api/v1/admin/connectors/submissions?connector_key=nfa_warehouse_stock_feed&limit=100",
        headers=auth_headers,
    )
    assert submissions_response.status_code == 200
    submissions = submissions_response.json()
    match = next((row for row in submissions if row["id"] == source_submission_id), None)
    assert match is not None
    assert match["status"] == "rejected"
    assert match["conflict_reason"] == "approval_rejected"


def test_audit_log_created_on_mutation(client, auth_headers):
    code = f"OM-T{date.today().strftime('%m%d')}"
    response = client.post(
        "/api/v1/municipalities/",
        headers=auth_headers,
        json={"code": code, "name": "Test Municipality", "province": "Occidental Mindoro", "region": "MIMAROPA"},
    )
    assert response.status_code in (200, 409)

    audit_response = client.get("/api/v1/audit/events", headers=auth_headers)
    assert audit_response.status_code == 200
    assert any(event["action_type"] == "municipality.create" for event in audit_response.json())


def test_audit_diff_filters_and_export(client, auth_headers, municipal_headers):
    code = f"OM-A{datetime.utcnow().strftime('%H%M%S')}"
    create_response = client.post(
        "/api/v1/municipalities/",
        headers=auth_headers,
        json={"code": code, "name": f"Audit Municipality {code}", "province": "Occidental Mindoro", "region": "MIMAROPA"},
    )
    assert create_response.status_code == 200

    filtered = client.get("/api/v1/audit/events?entity_type=municipality&limit=200", headers=auth_headers)
    assert filtered.status_code == 200
    rows = filtered.json()
    assert rows
    assert all(row["entity_type"] == "municipality" for row in rows)

    target = next((row for row in rows if row["action_type"] == "municipality.create"), rows[0])
    diff_response = client.get(f"/api/v1/audit/events/{target['id']}/diff", headers=auth_headers)
    assert diff_response.status_code == 200
    diff_payload = diff_response.json()
    assert diff_payload["event"]["id"] == target["id"]
    assert diff_payload["summary"]["total_changes"] == len(diff_payload["changes"])
    if diff_payload["changes"]:
        assert diff_payload["changes"][0]["path"]
        assert diff_payload["changes"][0]["change_type"] in {"added", "removed", "modified"}

    csv_export = client.get("/api/v1/audit/events/export?format=csv&entity_type=municipality&limit=200", headers=auth_headers)
    assert csv_export.status_code == 200
    assert csv_export.headers["content-type"].startswith("text/csv")
    assert "action_type" in csv_export.text

    json_export = client.get("/api/v1/audit/events/export?format=json&entity_type=municipality&limit=200", headers=auth_headers)
    assert json_export.status_code == 200
    assert json_export.headers["content-type"].startswith("application/json")
    json_rows = json_export.json()
    assert isinstance(json_rows, list)
    assert json_rows
    assert "diff_summary" in json_rows[0]
    assert "changed_paths" in json_rows[0]

    forbidden = client.get("/api/v1/audit/events/export?format=csv", headers=municipal_headers)
    assert forbidden.status_code == 403


def test_reports_export_endpoints(client, auth_headers):
    generate_response = client.post(
        "/api/v1/reports/generate",
        headers=auth_headers,
        json={"category": "price_trend", "reporting_month": date.today().replace(day=1).isoformat()},
    )
    assert generate_response.status_code == 200
    assert "forecast_model_diagnostics" in (generate_response.json().get("metadata") or {})
    assert "distribution_queue" in (generate_response.json().get("metadata") or {})
    report_id = generate_response.json()["id"]

    report_detail = client.get(f"/api/v1/reports/{report_id}", headers=auth_headers)
    assert report_detail.status_code == 200
    assert "forecast_model_diagnostics" in (report_detail.json().get("metadata") or {})

    csv_meta = client.get(f"/api/v1/reports/{report_id}/export/csv", headers=auth_headers)
    assert csv_meta.status_code == 200
    assert csv_meta.json()["format"] == "csv"

    pdf_meta = client.get(f"/api/v1/reports/{report_id}/export/pdf", headers=auth_headers)
    assert pdf_meta.status_code == 200
    assert pdf_meta.json()["format"] == "pdf"

    csv_download = client.get(f"/api/v1/reports/{report_id}/download/csv", headers=auth_headers)
    assert csv_download.status_code == 200
    assert csv_download.headers["content-type"].startswith("text/csv")

    pdf_download = client.get(f"/api/v1/reports/{report_id}/download/pdf", headers=auth_headers)
    assert pdf_download.status_code == 200
    assert pdf_download.headers["content-type"].startswith("application/pdf")

    report_file = Path(report_detail.json()["file_path"])
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "Forecast Model Diagnostics" in content


def test_report_distribution_queue_process_and_audit(client, auth_headers):
    generate_response = client.post(
        "/api/v1/reports/generate",
        headers=auth_headers,
        json={"category": "municipality_summary", "reporting_month": date.today().replace(day=1).isoformat()},
    )
    assert generate_response.status_code == 200
    report_id = generate_response.json()["id"]

    deliveries_before = client.get(f"/api/v1/reports/{report_id}/deliveries", headers=auth_headers)
    assert deliveries_before.status_code == 200
    assert deliveries_before.json()
    assert any(row["status"] in {"queued", "retrying", "sent"} for row in deliveries_before.json())

    process_response = client.post("/api/v1/reports/distribution/process?limit=200", headers=auth_headers)
    assert process_response.status_code == 200
    payload = process_response.json()
    assert payload["processed_count"] >= 1
    assert payload["sent_count"] >= 1

    deliveries_after = client.get(f"/api/v1/reports/{report_id}/deliveries", headers=auth_headers)
    assert deliveries_after.status_code == 200
    statuses = {row["status"] for row in deliveries_after.json()}
    assert "sent" in statuses

    audit_response = client.get("/api/v1/audit/events", headers=auth_headers)
    assert audit_response.status_code == 200
    actions = {event["action_type"] for event in audit_response.json()}
    assert "report.distribution.queued" in actions
    assert "report.distribution.sent" in actions


def test_report_distribution_retry_and_failure_notification(client, auth_headers):
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import ReportDeliveryLog

    create_group = client.post(
        "/api/v1/reports/distribution/groups",
        headers=auth_headers,
        json={
            "name": "Webhook Failure Test Group",
            "description": "force webhook failures",
            "report_category": "price_trend",
            "role_name": "executive_viewer",
            "delivery_channel": "webhook",
            "export_format": "pdf",
            "max_attempts": 2,
            "retry_backoff_seconds": 5,
            "notify_on_failure": True,
            "is_active": True,
        },
    )
    assert create_group.status_code == 200
    group_id = create_group.json()["id"]

    generate_response = client.post(
        "/api/v1/reports/generate",
        headers=auth_headers,
        json={"category": "price_trend", "reporting_month": date.today().replace(day=1).isoformat()},
    )
    assert generate_response.status_code == 200
    report_id = generate_response.json()["id"]

    first_process = client.post("/api/v1/reports/distribution/process?limit=200", headers=auth_headers)
    assert first_process.status_code == 200

    deliveries_after_first = client.get(f"/api/v1/reports/{report_id}/deliveries", headers=auth_headers)
    assert deliveries_after_first.status_code == 200
    webhook_rows = [row for row in deliveries_after_first.json() if row["recipient_group_id"] == group_id]
    assert webhook_rows
    webhook_row = webhook_rows[0]
    assert webhook_row["status"] in {"retrying", "failed"}
    assert webhook_row["attempt_count"] >= 1

    # Force retry window elapsed for deterministic test.
    with SessionLocal() as db:
        row = db.scalar(select(ReportDeliveryLog).where(ReportDeliveryLog.id == webhook_row["id"]))
        assert row is not None
        row.next_attempt_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()

    second_process = client.post("/api/v1/reports/distribution/process?limit=200", headers=auth_headers)
    assert second_process.status_code == 200

    deliveries_after_second = client.get(f"/api/v1/reports/{report_id}/deliveries", headers=auth_headers)
    assert deliveries_after_second.status_code == 200
    webhook_rows_second = [row for row in deliveries_after_second.json() if row["recipient_group_id"] == group_id]
    assert webhook_rows_second
    final_row = webhook_rows_second[0]
    assert final_row["status"] == "failed"
    assert final_row["attempt_count"] >= 2
    assert final_row["notification_sent_at"] is not None


def test_admin_overview_contains_forecast_diagnostics(client, auth_headers):
    response = client.get("/api/v1/admin/overview", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    diagnostics = payload["forecast_model_diagnostics"]
    assert "selected_model_counts" in diagnostics
    assert "model_avg_score" in diagnostics
    assert "municipalities_covered" in diagnostics
    assert "report_distribution_status" in payload
    assert "queued" in payload["report_distribution_status"]


def test_openapi_contains_tag_examples_and_router_responses(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    tags = {tag["name"] for tag in payload.get("tags", [])}

    expected_tags = {
        "auth",
        "users",
        "municipalities",
        "farmers",
        "production",
        "warehouses",
        "cold-storage",
        "distribution",
        "prices",
        "imports",
        "forecasting",
        "anomalies",
        "alerts",
        "dashboard",
        "documents",
        "reports",
        "admin",
        "audit",
    }
    assert expected_tags.issubset(tags)

    required_prefixes = [
        "/api/v1/auth/",
        "/api/v1/users/",
        "/api/v1/municipalities/",
        "/api/v1/farmers/",
        "/api/v1/production/",
        "/api/v1/warehouses/",
        "/api/v1/cold-storage/",
        "/api/v1/distribution/",
        "/api/v1/prices/",
        "/api/v1/imports/",
        "/api/v1/forecasting/",
        "/api/v1/anomalies/",
        "/api/v1/alerts/",
        "/api/v1/dashboard/",
        "/api/v1/documents/",
        "/api/v1/reports/",
        "/api/v1/admin/",
        "/api/v1/audit/",
    ]
    for prefix in required_prefixes:
        operations = [
            operation
            for path, methods in payload["paths"].items()
            if path.startswith(prefix)
            for operation in methods.values()
        ]
        assert operations, prefix
        has_schema_responses = any("401" in op.get("responses", {}) and "200" in op.get("responses", {}) for op in operations)
        assert has_schema_responses, prefix
