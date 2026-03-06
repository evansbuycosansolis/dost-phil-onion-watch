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
