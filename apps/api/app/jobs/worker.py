from __future__ import annotations

import time
from datetime import date, datetime
from typing import Callable
from uuid import uuid4

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.jobs.monthly_pipeline import REPORT_CATEGORIES, run_monthly_pipeline
from app.models import JobRun
from app.services.alert_service import generate_alerts_from_signals
from app.services.document_ingestion_service import process_pending_document_ingestion_jobs, rebuild_document_index
from app.services.feed_connector_service import run_all_connector_ingestions
from app.services.geospatial_feature_service import run_feature_refresh
from app.services.geospatial_playbooks_service import (
    run_incident_slo_checks,
    run_monthly_kpi_scorecard_generation,
    run_risk_review_reminders,
)
from app.services.notification_service import notify_job_failure
from app.services.observability_service import get_observability_store
from app.services.report_distribution_service import process_pending_report_deliveries, queue_undistributed_reports
from app.services.report_service import generate_report
from app.services.satellite_ingestion_service import run_ingestion

logger = get_logger(__name__)


def _record_job_start(db, job_name: str, correlation_id: str | None = None) -> JobRun:
    job = JobRun(
        job_name=job_name,
        status="running",
        correlation_id=correlation_id,
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    return job


def _record_job_success(db, job: JobRun, details: dict | None = None) -> None:
    job.status = "completed"
    job.finished_at = datetime.utcnow()
    job.details_json = details or {}
    job.message = "Scheduled task completed"
    db.flush()


def _record_job_failure(db, job: JobRun, message: str) -> None:
    job.status = "failed"
    job.finished_at = datetime.utcnow()
    job.message = message
    db.flush()


def _run_with_retry(
    job_name: str,
    fn: Callable[[], None],
    correlation_id: str | None = None,
    *,
    record_observability: bool = True,
) -> None:
    max_retries = max(1, settings.job_max_retries)
    base_backoff = max(1, settings.job_retry_backoff_seconds)
    store = get_observability_store()

    for attempt in range(1, max_retries + 1):
        started = time.perf_counter()
        try:
            fn()
            if record_observability:
                store.record_job_event(
                    job_name=job_name,
                    status="completed",
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    correlation_id=correlation_id,
                    attempt=attempt,
                )
            logger.info("Scheduled job completed", extra={"job_name": job_name, "attempt": attempt})
            return
        except Exception as exc:  # pragma: no cover
            if record_observability:
                store.record_job_event(
                    job_name=job_name,
                    status="failed",
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    correlation_id=correlation_id,
                    attempt=attempt,
                    details={"error": str(exc)},
                )
            logger.exception(
                "Scheduled job failed",
                extra={"job_name": job_name, "attempt": attempt, "max_retries": max_retries},
            )
            if attempt >= max_retries:
                notify_job_failure(
                    job_name=job_name,
                    attempt=attempt,
                    max_retries=max_retries,
                    error_message=str(exc),
                    context={"correlation_id": correlation_id},
                )
                return
            sleep_seconds = base_backoff * (2 ** (attempt - 1))
            time.sleep(sleep_seconds)


def _run_monthly_pipeline_job() -> None:
    correlation_id = f"job-monthly-pipeline-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        try:
            run_monthly_pipeline(
                db,
                reporting_month=date.today().replace(day=1),
                correlation_id=correlation_id,
            )
            db.commit()
        finally:
            db.close()

    _run_with_retry("monthly_pipeline", execute, correlation_id=correlation_id, record_observability=False)


def _run_alert_refresh_job() -> None:
    correlation_id = f"job-alert-refresh-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "alert_refresh", correlation_id=correlation_id)
        try:
            month = date.today().replace(day=1)
            alerts = generate_alerts_from_signals(db, month)
            _record_job_success(db, job, {"alerts_created": len(alerts), "reporting_month": month.isoformat()})
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("alert_refresh", execute, correlation_id=correlation_id)


def _run_report_generation_job() -> None:
    correlation_id = f"job-report-generation-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "report_generation", correlation_id=correlation_id)
        try:
            month = date.today().replace(day=1)
            reports = [generate_report(db, category, month) for category in REPORT_CATEGORIES]
            queue_summary = queue_undistributed_reports(db, limit=50)
            _record_job_success(
                db,
                job,
                {
                    "reports_created": len(reports),
                    "reporting_month": month.isoformat(),
                    "distribution_queue": queue_summary,
                },
            )
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("report_generation", execute, correlation_id=correlation_id)


def _run_report_distribution_job() -> None:
    correlation_id = f"job-report-distribution-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "report_distribution", correlation_id=correlation_id)
        try:
            queue_summary = queue_undistributed_reports(db, limit=100)
            deliveries = process_pending_report_deliveries(db, limit=settings.report_distribution_batch_size)
            _record_job_success(
                db,
                job,
                {
                    "queue_summary": queue_summary,
                    "processed_deliveries": len(deliveries),
                    "sent_count": len([d for d in deliveries if d.status == "sent"]),
                    "failed_count": len([d for d in deliveries if d.status == "failed"]),
                    "retrying_count": len([d for d in deliveries if d.status == "retrying"]),
                },
            )
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("report_distribution", execute, correlation_id=correlation_id)


def _run_document_reindex_job() -> None:
    correlation_id = f"job-reindex-documents-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "reindex_documents", correlation_id=correlation_id)
        try:
            run = rebuild_document_index(db)
            _record_job_success(db, job, {"index_run_id": run.id, "num_chunks": run.num_chunks})
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("reindex_documents", execute, correlation_id=correlation_id)


def _run_document_ingestion_queue_job() -> None:
    correlation_id = f"job-document-ingestion-queue-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "document_ingestion_queue", correlation_id=correlation_id)
        try:
            processed = process_pending_document_ingestion_jobs(db)
            _record_job_success(
                db,
                job,
                {
                    "jobs_processed": len(processed),
                    "job_ids": [row.id for row in processed],
                    "statuses": [row.status for row in processed],
                },
            )
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("document_ingestion_queue", execute, correlation_id=correlation_id)


def _run_agency_feed_ingestion_job() -> None:
    correlation_id = f"job-agency-feed-ingestion-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "agency_feed_ingestion", correlation_id=correlation_id)
        try:
            result = run_all_connector_ingestions(
                db,
                actor_user_id=None,
                correlation_id=correlation_id,
                limit_per_connector=250,
                dry_run=False,
            )
            _record_job_success(
                db,
                job,
                {
                    "connectors_run": result["connectors_run"],
                    "totals": result["totals"],
                },
            )
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("agency_feed_ingestion", execute, correlation_id=correlation_id)


def _run_observability_monitor_job() -> None:
    correlation_id = f"job-observability-monitor-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "observability_monitor", correlation_id=correlation_id)
        try:
            result = get_observability_store().evaluate_alerts()
            _record_job_success(
                db,
                job,
                {
                    "active_alerts": len(result["active_alerts"]),
                    "sent_alerts": len(result["sent_alerts"]),
                },
            )
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("observability_monitor", execute, correlation_id=correlation_id)


def _run_geospatial_ingest_job() -> None:
    correlation_id = f"job-geospatial-ingest-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "geospatial_ingest", correlation_id=correlation_id)
        try:
            run = run_ingestion(db, triggered_by=None, correlation_id=correlation_id)
            _record_job_success(
                db,
                job,
                {
                    "pipeline_run_id": run.id,
                    "pipeline_status": run.status,
                    "results": run.results_json,
                },
            )
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("geospatial_ingest", execute, correlation_id=correlation_id)


def _run_geospatial_refresh_job() -> None:
    correlation_id = f"job-geospatial-refresh-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "geospatial_refresh", correlation_id=correlation_id)
        try:
            run = run_feature_refresh(db, triggered_by=None, correlation_id=correlation_id)
            _record_job_success(
                db,
                job,
                {
                    "pipeline_run_id": run.id,
                    "pipeline_status": run.status,
                    "results": run.results_json,
                },
            )
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("geospatial_refresh", execute, correlation_id=correlation_id)


def _run_geospatial_kpi_generation_job() -> None:
    correlation_id = f"job-geospatial-kpi-generation-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "geospatial_kpi_generation", correlation_id=correlation_id)
        try:
            scorecard = run_monthly_kpi_scorecard_generation(
                db,
                reporting_month=date.today().replace(day=1),
                actor_user_id=None,
            )
            _record_job_success(
                db,
                job,
                {
                    "scorecard_id": scorecard.id,
                    "period_month": scorecard.period_month.isoformat(),
                    "computed_status": scorecard.computed_status,
                },
            )
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("geospatial_kpi_generation", execute, correlation_id=correlation_id)


def _run_geospatial_risk_review_reminder_job() -> None:
    correlation_id = f"job-geospatial-risk-review-reminder-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "geospatial_risk_review_reminder", correlation_id=correlation_id)
        try:
            tasks = run_risk_review_reminders(db, actor_user_id=None)
            _record_job_success(
                db,
                job,
                {
                    "tasks_created": len(tasks),
                    "task_ids": [row.id for row in tasks],
                },
            )
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("geospatial_risk_review_reminder", execute, correlation_id=correlation_id)


def _run_geospatial_incident_slo_check_job() -> None:
    correlation_id = f"job-geospatial-incident-slo-check-{uuid4().hex[:12]}"

    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "geospatial_incident_slo_check", correlation_id=correlation_id)
        try:
            tasks = run_incident_slo_checks(db, actor_user_id=None)
            _record_job_success(
                db,
                job,
                {
                    "tasks_created": len(tasks),
                    "task_ids": [row.id for row in tasks],
                },
            )
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("geospatial_incident_slo_check", execute, correlation_id=correlation_id)


def _cron(expr: str) -> CronTrigger:
    return CronTrigger.from_crontab(expr, timezone=settings.scheduler_timezone)


def create_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=settings.scheduler_timezone)
    scheduler.add_job(
        _run_monthly_pipeline_job,
        trigger=_cron(settings.monthly_pipeline_cron),
        id="monthly_pipeline",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_alert_refresh_job,
        trigger=_cron(settings.alert_refresh_cron),
        id="alert_refresh",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=1800,
    )
    scheduler.add_job(
        _run_report_generation_job,
        trigger=_cron(settings.report_generation_cron),
        id="report_generation",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_report_distribution_job,
        trigger=_cron(settings.report_distribution_cron),
        id="report_distribution",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=1200,
    )
    scheduler.add_job(
        _run_document_reindex_job,
        trigger=_cron(settings.reindex_documents_cron),
        id="reindex_documents",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_document_ingestion_queue_job,
        trigger=_cron(settings.document_ingestion_cron),
        id="document_ingestion_queue",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        _run_agency_feed_ingestion_job,
        trigger=_cron(settings.agency_feed_ingestion_cron),
        id="agency_feed_ingestion",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=900,
    )
    scheduler.add_job(
        _run_observability_monitor_job,
        trigger=_cron(settings.observability_monitor_cron),
        id="observability_monitor",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        _run_geospatial_ingest_job,
        trigger=_cron(settings.geospatial_ingest_cron),
        id="geospatial_ingest",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=1800,
    )
    scheduler.add_job(
        _run_geospatial_refresh_job,
        trigger=_cron(settings.geospatial_refresh_cron),
        id="geospatial_refresh",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_geospatial_kpi_generation_job,
        trigger=_cron(settings.geospatial_kpi_generation_cron),
        id="geospatial_kpi_generation",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_geospatial_risk_review_reminder_job,
        trigger=_cron(settings.geospatial_risk_review_reminder_cron),
        id="geospatial_risk_review_reminder",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=1200,
    )
    scheduler.add_job(
        _run_geospatial_incident_slo_check_job,
        trigger=_cron(settings.geospatial_incident_slo_check_cron),
        id="geospatial_incident_slo_check",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=600,
    )
    return scheduler


def main() -> None:
    configure_logging()
    scheduler = create_scheduler()
    logger.info(
        "Background worker scheduler started",
        extra={
            "timezone": settings.scheduler_timezone,
            "monthly_pipeline_cron": settings.monthly_pipeline_cron,
            "alert_refresh_cron": settings.alert_refresh_cron,
            "report_generation_cron": settings.report_generation_cron,
            "report_distribution_cron": settings.report_distribution_cron,
            "reindex_documents_cron": settings.reindex_documents_cron,
            "document_ingestion_cron": settings.document_ingestion_cron,
            "agency_feed_ingestion_cron": settings.agency_feed_ingestion_cron,
            "observability_monitor_cron": settings.observability_monitor_cron,
            "geospatial_ingest_cron": settings.geospatial_ingest_cron,
            "geospatial_refresh_cron": settings.geospatial_refresh_cron,
            "geospatial_kpi_generation_cron": settings.geospatial_kpi_generation_cron,
            "geospatial_risk_review_reminder_cron": settings.geospatial_risk_review_reminder_cron,
            "geospatial_incident_slo_check_cron": settings.geospatial_incident_slo_check_cron,
            "max_retries": settings.job_max_retries,
        },
    )
    scheduler.start()


if __name__ == "__main__":
    main()
