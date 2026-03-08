from app.services.geospatial_playbooks_service import compute_kpi_statuses


def test_compute_kpi_statuses_assigns_expected_traffic_lights():
    overall, statuses, thresholds = compute_kpi_statuses(
        {
            "GEO-KPI-001": 0.81,
            "GEO-KPI-002": 30.0,
            "GEO-KPI-003": 101.0,
        },
        {
            "GEO-KPI-001": {"direction": "higher", "green": 0.75, "amber": 0.65},
            "GEO-KPI-002": {"direction": "lower", "green": 24.0, "amber": 36.0},
            "GEO-KPI-003": {"direction": "lower", "green": 72.0, "amber": 96.0},
        },
    )

    assert overall == "red"
    assert statuses["GEO-KPI-001"] == "green"
    assert statuses["GEO-KPI-002"] == "yellow"
    assert statuses["GEO-KPI-003"] == "red"
    assert "GEO-KPI-001" in thresholds


def test_compute_kpi_statuses_handles_missing_or_invalid_metrics():
    overall, statuses, _ = compute_kpi_statuses(
        {"GEO-KPI-001": "not-a-number"},
        {"GEO-KPI-001": {"direction": "higher", "green": 0.75, "amber": 0.65}, "GEO-KPI-002": {"direction": "higher", "green": 0.8, "amber": 0.6}},
    )

    assert overall == "red"
    assert statuses["GEO-KPI-001"] == "red"
    assert statuses["GEO-KPI-002"] == "yellow"
