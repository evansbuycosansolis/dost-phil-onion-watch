from datetime import date
from pathlib import Path


def test_auth_login_success(client):
    response = client.post("/api/v1/auth/login", json={"email": "super_admin@onionwatch.ph", "password": "ChangeMe123!"})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_auth_login_failure(client):
    response = client.post("/api/v1/auth/login", json={"email": "super_admin@onionwatch.ph", "password": "wrong-password"})
    assert response.status_code == 401


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


def test_forecast_run_endpoint(client, auth_headers):
    response = client.post(
        "/api/v1/forecasting/run",
        json={"run_month": date.today().replace(day=1).isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_anomaly_run_endpoint(client, auth_headers):
    response = client.post(
        "/api/v1/anomalies/run",
        json={"reporting_month": date.today().replace(day=1).isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert "created" in response.json()


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
    run_response = client.post("/api/v1/documents/reindex", headers=auth_headers)
    assert run_response.status_code == 200

    search_response = client.post(
        "/api/v1/documents/search",
        headers=auth_headers,
        json={"query": "release pacing", "top_k": 3},
    )
    assert search_response.status_code == 200
    assert "results" in search_response.json()


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


def test_reports_export_endpoints(client, auth_headers):
    generate_response = client.post(
        "/api/v1/reports/generate",
        headers=auth_headers,
        json={"category": "price_trend", "reporting_month": date.today().replace(day=1).isoformat()},
    )
    assert generate_response.status_code == 200
    report_id = generate_response.json()["id"]

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
