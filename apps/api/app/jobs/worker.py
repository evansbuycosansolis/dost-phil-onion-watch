from __future__ import annotations

import time
from datetime import date, datetime
from typing import Callable

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.jobs.monthly_pipeline import REPORT_CATEGORIES, run_monthly_pipeline
from app.models import JobRun
from app.services.alert_service import generate_alerts_from_signals
from app.services.document_ingestion_service import rebuild_document_index
from app.services.notification_service import notify_job_failure
from app.services.report_service import generate_report

logger = get_logger(__name__)


def _record_job_start(db, job_name: str) -> JobRun:
    job = JobRun(
        job_name=job_name,
        status="running",
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


def _run_with_retry(job_name: str, fn: Callable[[], None]) -> None:
    max_retries = max(1, settings.job_max_retries)
    base_backoff = max(1, settings.job_retry_backoff_seconds)

    for attempt in range(1, max_retries + 1):
        try:
            fn()
            logger.info("Scheduled job completed", extra={"job_name": job_name, "attempt": attempt})
            return
        except Exception as exc:  # pragma: no cover
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
                )
                return
            sleep_seconds = base_backoff * (2 ** (attempt - 1))
            time.sleep(sleep_seconds)


def _run_monthly_pipeline_job() -> None:
    def execute() -> None:
        db = SessionLocal()
        try:
            run_monthly_pipeline(db, reporting_month=date.today().replace(day=1))
            db.commit()
        finally:
            db.close()

    _run_with_retry("monthly_pipeline", execute)


def _run_alert_refresh_job() -> None:
    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "alert_refresh")
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

    _run_with_retry("alert_refresh", execute)


def _run_report_generation_job() -> None:
    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "report_generation")
        try:
            month = date.today().replace(day=1)
            reports = [generate_report(db, category, month) for category in REPORT_CATEGORIES]
            _record_job_success(db, job, {"reports_created": len(reports), "reporting_month": month.isoformat()})
            db.commit()
        except Exception as exc:
            _record_job_failure(db, job, str(exc))
            db.commit()
            raise
        finally:
            db.close()

    _run_with_retry("report_generation", execute)


def _run_document_reindex_job() -> None:
    def execute() -> None:
        db = SessionLocal()
        job = _record_job_start(db, "reindex_documents")
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

    _run_with_retry("reindex_documents", execute)


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
        _run_document_reindex_job,
        trigger=_cron(settings.reindex_documents_cron),
        id="reindex_documents",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
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
            "reindex_documents_cron": settings.reindex_documents_cron,
            "max_retries": settings.job_max_retries,
        },
    )
    scheduler.start()


if __name__ == "__main__":
    main()
