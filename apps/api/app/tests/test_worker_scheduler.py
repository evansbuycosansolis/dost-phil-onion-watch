import pytest

from app.jobs import worker


def test_worker_retry_notifies_after_final_failure(monkeypatch):
    attempts = {"count": 0}
    notifications = {"count": 0}

    def failing_job():
        attempts["count"] += 1
        raise RuntimeError("forced failure")

    def fake_notify(**kwargs):
        notifications["count"] += 1
        assert kwargs["job_name"] == "test_job"
        assert kwargs["attempt"] == 2

    monkeypatch.setattr(worker.settings, "job_max_retries", 2, raising=False)
    monkeypatch.setattr(worker.settings, "job_retry_backoff_seconds", 1, raising=False)
    monkeypatch.setattr(worker, "notify_job_failure", fake_notify)
    monkeypatch.setattr(worker.time, "sleep", lambda _: None)

    worker._run_with_retry("test_job", failing_job)

    assert attempts["count"] == 2
    assert notifications["count"] == 1


def test_worker_retry_stops_after_success(monkeypatch):
    attempts = {"count": 0}
    notifications = {"count": 0}

    def flaky_job():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient issue")

    monkeypatch.setattr(worker.settings, "job_max_retries", 3, raising=False)
    monkeypatch.setattr(worker.settings, "job_retry_backoff_seconds", 1, raising=False)
    monkeypatch.setattr(worker, "notify_job_failure", lambda **kwargs: notifications.__setitem__("count", notifications["count"] + 1))
    monkeypatch.setattr(worker.time, "sleep", lambda _: None)

    worker._run_with_retry("test_job", flaky_job)

    assert attempts["count"] == 2
    assert notifications["count"] == 0


def test_observability_alerting_for_degraded_endpoints_and_job_failures(monkeypatch):
    from app.core.config import settings
    from app.services import observability_service

    sent_alerts = {"count": 0}

    def fake_notify(**kwargs):
        sent_alerts["count"] += 1
        assert "alert_type" in kwargs
        assert "summary" in kwargs

    monkeypatch.setattr(observability_service, "notify_observability_alert", fake_notify)
    monkeypatch.setattr(settings, "degraded_endpoint_min_requests", 2, raising=False)
    monkeypatch.setattr(settings, "degraded_endpoint_error_rate_threshold", 0.4, raising=False)
    monkeypatch.setattr(settings, "degraded_endpoint_p95_latency_ms_threshold", 99_999.0, raising=False)
    monkeypatch.setattr(settings, "job_failure_min_runs", 2, raising=False)
    monkeypatch.setattr(settings, "job_failure_rate_threshold", 0.4, raising=False)
    monkeypatch.setattr(settings, "observability_alert_cooldown_seconds", 0, raising=False)

    store = observability_service.get_observability_store()
    observability_service.reset_observability_store()
    store.record_api_request(method="GET", path="/api/v1/test", status_code=500, duration_ms=120.0, correlation_id="c1")
    store.record_api_request(method="GET", path="/api/v1/test", status_code=500, duration_ms=150.0, correlation_id="c1")
    store.record_job_event(job_name="sample_job", status="failed", duration_ms=100.0, correlation_id="c1")
    store.record_job_event(job_name="sample_job", status="failed", duration_ms=130.0, correlation_id="c1")

    result = store.evaluate_alerts()
    assert result["active_alerts"]
    assert any(row["alert_type"] == "degraded_endpoint" for row in result["active_alerts"])
    assert any(row["alert_type"] == "job_failure_rate" for row in result["active_alerts"])
    assert sent_alerts["count"] >= 2


def test_scheduler_registers_geospatial_playbook_jobs():
    scheduler = worker.create_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}

    assert "geospatial_kpi_generation" in job_ids
    assert "geospatial_risk_review_reminder" in job_ids
    assert "geospatial_incident_slo_check" in job_ids


def test_worker_requires_job_runs_table_before_startup(monkeypatch):
    class DummySession:
        def get_bind(self):
            return object()

        def close(self):
            return None

    class DummyInspector:
        def __init__(self, table_names):
            self._table_names = table_names

        def get_table_names(self):
            return self._table_names

    monkeypatch.setattr(worker, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(worker, "inspect", lambda _bind: DummyInspector(["users", "alerts"]))

    with pytest.raises(RuntimeError, match="job_runs"):
        worker.ensure_job_runs_table_present()
