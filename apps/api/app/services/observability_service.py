from __future__ import annotations

import math
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.services.notification_service import notify_observability_alert


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    rank = max(1, math.ceil((percentile / 100.0) * len(values)))
    index = min(len(values) - 1, rank - 1)
    sorted_values = sorted(values)
    return float(sorted_values[index])


def _to_key(path: str) -> str:
    cleaned = path.replace("\\", "_").replace("/", "_").replace("-", "_")
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in cleaned)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "root"


class ObservabilityStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._api_events: deque[dict[str, Any]] = deque(maxlen=100_000)
        self._job_events: deque[dict[str, Any]] = deque(maxlen=50_000)
        self._active_alerts: dict[str, dict[str, Any]] = {}
        self._last_alert_sent_at: dict[str, datetime] = {}

    def reset(self) -> None:
        with self._lock:
            self._api_events.clear()
            self._job_events.clear()
            self._active_alerts.clear()
            self._last_alert_sent_at.clear()

    def _trim_locked(self, now: datetime) -> None:
        retention_minutes = max(60, int(settings.observability_event_retention_minutes))
        min_ts = now - timedelta(minutes=retention_minutes)
        while self._api_events and self._api_events[0]["timestamp"] < min_ts:
            self._api_events.popleft()
        while self._job_events and self._job_events[0]["timestamp"] < min_ts:
            self._job_events.popleft()

    def record_api_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        correlation_id: str | None = None,
    ) -> None:
        now = _now_utc()
        with self._lock:
            self._trim_locked(now)
            self._api_events.append(
                {
                    "timestamp": now,
                    "method": method,
                    "path": path,
                    "status_code": int(status_code),
                    "duration_ms": float(max(0.0, duration_ms)),
                    "correlation_id": correlation_id,
                }
            )

    def record_job_event(
        self,
        *,
        job_name: str,
        status: str,
        duration_ms: float,
        correlation_id: str | None = None,
        attempt: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        now = _now_utc()
        with self._lock:
            self._trim_locked(now)
            self._job_events.append(
                {
                    "timestamp": now,
                    "job_name": job_name,
                    "status": status,
                    "duration_ms": float(max(0.0, duration_ms)),
                    "correlation_id": correlation_id,
                    "attempt": attempt,
                    "details": details or {},
                }
            )

    def api_summary(self, *, window_minutes: int | None = None) -> dict[str, Any]:
        now = _now_utc()
        window = max(1, int(window_minutes or settings.observability_window_minutes))
        start = now - timedelta(minutes=window)
        endpoint_rows: list[dict[str, Any]] = []

        with self._lock:
            events = [row for row in self._api_events if row["timestamp"] >= start]

        by_endpoint: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in events:
            by_endpoint[(row["method"], row["path"])].append(row)

        total_requests = len(events)
        total_errors = sum(1 for row in events if row["status_code"] >= 500)
        total_client_errors = sum(1 for row in events if 400 <= row["status_code"] < 500)

        degraded = []
        for (method, path), rows in by_endpoint.items():
            durations = [float(row["duration_ms"]) for row in rows]
            total = len(rows)
            server_errors = sum(1 for row in rows if row["status_code"] >= 500)
            client_errors = sum(1 for row in rows if 400 <= row["status_code"] < 500)
            error_rate = (server_errors / total) if total else 0.0
            p95_ms = _percentile(durations, 95.0)
            avg_ms = sum(durations) / total if total else 0.0

            endpoint_row = {
                "method": method,
                "path": path,
                "request_count": total,
                "server_error_count": server_errors,
                "client_error_count": client_errors,
                "server_error_rate": round(error_rate, 4),
                "p95_latency_ms": round(p95_ms, 2),
                "avg_latency_ms": round(avg_ms, 2),
            }
            endpoint_rows.append(endpoint_row)

            if total >= settings.degraded_endpoint_min_requests and (
                error_rate >= settings.degraded_endpoint_error_rate_threshold
                or p95_ms >= settings.degraded_endpoint_p95_latency_ms_threshold
            ):
                degraded.append(endpoint_row)

        endpoint_rows.sort(key=lambda row: (-row["server_error_rate"], -row["p95_latency_ms"], -row["request_count"]))
        degraded.sort(key=lambda row: (-row["server_error_rate"], -row["p95_latency_ms"]))
        return {
            "window_minutes": window,
            "requests_total": total_requests,
            "server_errors_total": total_errors,
            "client_errors_total": total_client_errors,
            "server_error_rate": round((total_errors / total_requests) if total_requests else 0.0, 4),
            "degraded_endpoints": degraded,
            "endpoints": endpoint_rows,
        }

    def job_summary(self, *, window_minutes: int | None = None) -> dict[str, Any]:
        now = _now_utc()
        window = max(1, int(window_minutes or settings.observability_window_minutes))
        start = now - timedelta(minutes=window)

        with self._lock:
            events = [row for row in self._job_events if row["timestamp"] >= start]

        by_job: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in events:
            by_job[row["job_name"]].append(row)

        rows: list[dict[str, Any]] = []
        failing_jobs: list[dict[str, Any]] = []
        total_runs = len(events)
        failed_runs = sum(1 for row in events if row["status"] == "failed")

        for job_name, job_rows in by_job.items():
            total = len(job_rows)
            failed = sum(1 for row in job_rows if row["status"] == "failed")
            completed = sum(1 for row in job_rows if row["status"] == "completed")
            durations = [float(row["duration_ms"]) for row in job_rows]
            failure_rate = (failed / total) if total else 0.0
            row = {
                "job_name": job_name,
                "run_count": total,
                "completed_count": completed,
                "failed_count": failed,
                "failure_rate": round(failure_rate, 4),
                "avg_duration_ms": round((sum(durations) / total) if total else 0.0, 2),
                "p95_duration_ms": round(_percentile(durations, 95.0), 2),
            }
            rows.append(row)
            if total >= settings.job_failure_min_runs and failure_rate >= settings.job_failure_rate_threshold:
                failing_jobs.append(row)

        rows.sort(key=lambda row: (-row["failure_rate"], -row["run_count"]))
        failing_jobs.sort(key=lambda row: (-row["failure_rate"], -row["run_count"]))
        return {
            "window_minutes": window,
            "runs_total": total_runs,
            "failed_total": failed_runs,
            "failure_rate": round((failed_runs / total_runs) if total_runs else 0.0, 4),
            "failing_jobs": failing_jobs,
            "jobs": rows,
        }

    def trace_by_correlation_id(self, correlation_id: str, *, limit: int = 200) -> dict[str, Any]:
        with self._lock:
            api_rows = [row for row in self._api_events if row.get("correlation_id") == correlation_id][-limit:]
            job_rows = [row for row in self._job_events if row.get("correlation_id") == correlation_id][-limit:]
        return {
            "correlation_id": correlation_id,
            "api_requests": api_rows,
            "job_events": job_rows,
        }

    def _can_send_alert_locked(self, key: str, now: datetime) -> bool:
        last = self._last_alert_sent_at.get(key)
        if not last:
            return True
        cooldown = timedelta(seconds=max(1, int(settings.observability_alert_cooldown_seconds)))
        return (now - last) >= cooldown

    def evaluate_alerts(self) -> dict[str, Any]:
        now = _now_utc()
        api = self.api_summary()
        jobs = self.job_summary()
        candidate_alerts: list[dict[str, Any]] = []

        for endpoint in api["degraded_endpoints"]:
            candidate_alerts.append(
                {
                    "key": f"endpoint:{endpoint['method']}:{endpoint['path']}",
                    "alert_type": "degraded_endpoint",
                    "severity": "high" if endpoint["server_error_rate"] >= 0.5 else "medium",
                    "summary": (
                        f"Endpoint {endpoint['method']} {endpoint['path']} is degraded. "
                        f"server_error_rate={endpoint['server_error_rate']}, p95_latency_ms={endpoint['p95_latency_ms']}"
                    ),
                    "metrics": endpoint,
                }
            )

        for job in jobs["failing_jobs"]:
            candidate_alerts.append(
                {
                    "key": f"job:{job['job_name']}",
                    "alert_type": "job_failure_rate",
                    "severity": "high" if job["failure_rate"] >= 0.5 else "medium",
                    "summary": (
                        f"Job {job['job_name']} failure rate is elevated. "
                        f"failure_rate={job['failure_rate']} over {job['run_count']} runs"
                    ),
                    "metrics": job,
                }
            )

        sent_alerts = []
        with self._lock:
            active_keys = {row["key"] for row in candidate_alerts}
            for key in list(self._active_alerts.keys()):
                if key not in active_keys:
                    del self._active_alerts[key]

            for alert in candidate_alerts:
                key = alert["key"]
                self._active_alerts[key] = {
                    **alert,
                    "updated_at": now.isoformat(),
                }
                if self._can_send_alert_locked(key, now):
                    notify_observability_alert(
                        alert_type=alert["alert_type"],
                        severity=alert["severity"],
                        summary=alert["summary"],
                        metrics=alert["metrics"],
                    )
                    self._last_alert_sent_at[key] = now
                    sent_alerts.append(alert)

            active_alerts = list(self._active_alerts.values())

        return {
            "evaluated_at": now.isoformat(),
            "active_alerts": active_alerts,
            "sent_alerts": sent_alerts,
        }

    def metrics_text(self) -> str:
        api = self.api_summary()
        jobs = self.job_summary()

        lines = [
            "# HELP pow_api_requests_total Total API requests observed",
            "# TYPE pow_api_requests_total counter",
            f"pow_api_requests_total {api['requests_total']}",
            "# HELP pow_api_server_errors_total Total API server errors observed",
            "# TYPE pow_api_server_errors_total counter",
            f"pow_api_server_errors_total {api['server_errors_total']}",
            "# HELP pow_api_server_error_rate API server error rate over configured window",
            "# TYPE pow_api_server_error_rate gauge",
            f"pow_api_server_error_rate {api['server_error_rate']}",
            "# HELP pow_job_runs_total Total background job runs observed",
            "# TYPE pow_job_runs_total counter",
            f"pow_job_runs_total {jobs['runs_total']}",
            "# HELP pow_job_failed_total Total failed background job runs observed",
            "# TYPE pow_job_failed_total counter",
            f"pow_job_failed_total {jobs['failed_total']}",
            "# HELP pow_job_failure_rate Background job failure rate over configured window",
            "# TYPE pow_job_failure_rate gauge",
            f"pow_job_failure_rate {jobs['failure_rate']}",
        ]

        for endpoint in api["endpoints"]:
            key = _to_key(f"{endpoint['method']}_{endpoint['path']}")
            lines.append(
                f'pow_api_endpoint_requests_total{{method="{endpoint["method"]}",path="{endpoint["path"]}",key="{key}"}} {endpoint["request_count"]}'
            )
            lines.append(
                f'pow_api_endpoint_server_error_rate{{method="{endpoint["method"]}",path="{endpoint["path"]}",key="{key}"}} {endpoint["server_error_rate"]}'
            )
            lines.append(
                f'pow_api_endpoint_p95_latency_ms{{method="{endpoint["method"]}",path="{endpoint["path"]}",key="{key}"}} {endpoint["p95_latency_ms"]}'
            )

        for row in jobs["jobs"]:
            key = _to_key(row["job_name"])
            lines.append(f'pow_job_run_count{{job="{row["job_name"]}",key="{key}"}} {row["run_count"]}')
            lines.append(f'pow_job_failure_rate_by_job{{job="{row["job_name"]}",key="{key}"}} {row["failure_rate"]}')
            lines.append(f'pow_job_p95_duration_ms{{job="{row["job_name"]}",key="{key}"}} {row["p95_duration_ms"]}')

        active_alert_count = len(api["degraded_endpoints"]) + len(jobs["failing_jobs"])
        lines.append("# HELP pow_observability_active_alerts Active observability alerts")
        lines.append("# TYPE pow_observability_active_alerts gauge")
        lines.append(f"pow_observability_active_alerts {active_alert_count}")
        return "\n".join(lines) + "\n"


_store = ObservabilityStore()


def get_observability_store() -> ObservabilityStore:
    return _store


def reset_observability_store() -> None:
    _store.reset()
