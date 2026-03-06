from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import JobRun
from app.services.alert_service import generate_alerts_from_signals
from app.services.anomaly_service import run_anomaly_detection
from app.services.document_ingestion_service import rebuild_document_index
from app.services.forecasting_service import run_forecasting
from app.services.report_service import generate_report


REPORT_CATEGORIES = [
    "provincial_exec_summary",
    "municipality_summary",
    "warehouse_utilization",
    "price_trend",
    "alert_digest",
]


def run_monthly_pipeline(db: Session, reporting_month: date | None = None, triggered_by: int | None = None) -> JobRun:
    month = reporting_month or date.today().replace(day=1)

    job = JobRun(
        job_name="monthly_pipeline",
        status="running",
        started_at=datetime.utcnow(),
        triggered_by=triggered_by,
    )
    db.add(job)
    db.flush()

    try:
        # 1. validate pending submissions - MVP placeholder via metadata marker.
        details = {"validated_submissions": True}

        # 2-5. recompute analytics and intelligence.
        forecast_run = run_forecasting(db, month)
        anomalies = run_anomaly_detection(db, month)

        # 6. generate alerts from outputs.
        alerts = generate_alerts_from_signals(db, month)

        # 7. refresh document index for knowledge center.
        index_run = rebuild_document_index(db)

        # 8. generate baseline report artifacts.
        reports = [generate_report(db, category, month, triggered_by) for category in REPORT_CATEGORIES]

        job.status = "completed"
        job.finished_at = datetime.utcnow()
        job.details_json = {
            **details,
            "forecast_run_id": forecast_run.id,
            "anomalies_created": len(anomalies),
            "alerts_created": len(alerts),
            "reports_created": len(reports),
            "index_run_id": index_run.id,
        }
        job.message = "Monthly pipeline completed successfully"
    except Exception as exc:  # pragma: no cover
        job.status = "failed"
        job.finished_at = datetime.utcnow()
        job.message = str(exc)
        raise
    finally:
        db.flush()

    return job


def main() -> None:
    db = SessionLocal()
    try:
        run_monthly_pipeline(db)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
