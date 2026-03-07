from __future__ import annotations

from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.api.v1 import (
    admin,
    alerts,
    anomalies,
    audit,
    auth,
    cold_storage,
    dashboard,
    distribution,
    documents,
    farmers,
    forecasting,
    geospatial,
    imports,
    municipalities,
    prices,
    production,
    reports,
    users,
    warehouses,
)
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.logging import configure_logging, get_logger
from app.core.middleware import CorrelationIdMiddleware
from app.core.openapi import OPENAPI_TAGS
from app.models import User
from app.services.alert_service import generate_alerts_from_signals
from app.services.anomaly_service import run_anomaly_detection
from app.services.document_ingestion_service import rebuild_document_index
from app.services.forecasting_service import run_forecasting
from app.services.observability_service import get_observability_store
from app.services.seed_service import seed_documents, seed_operational_data, seed_reference_data

logger = get_logger(__name__)

app = FastAPI(title=settings.app_name, version="0.1.0", openapi_tags=OPENAPI_TAGS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)


@app.get("/health")
def health() -> dict:
    store = get_observability_store()
    api_summary = store.api_summary(window_minutes=15)
    job_summary = store.job_summary(window_minutes=60)
    degraded = len(api_summary["degraded_endpoints"])
    failing_jobs = len(job_summary["failing_jobs"])
    status = "degraded" if degraded > 0 or failing_jobs > 0 else "ok"
    return {
        "status": status,
        "service": settings.app_name,
        "degraded_endpoints": degraded,
        "failing_jobs": failing_jobs,
        "api_server_error_rate": api_summary["server_error_rate"],
        "job_failure_rate": job_summary["failure_rate"],
    }


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> PlainTextResponse:
    store = get_observability_store()
    return PlainTextResponse(store.metrics_text(), media_type="text/plain; version=0.0.4")


@app.on_event("startup")
def on_startup() -> None:
    configure_logging()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        has_users = db.scalar(select(User.id).limit(1))
        if not has_users:
            ref_result = seed_reference_data(db)
            op_result = seed_operational_data(db)
            doc_result = seed_documents(db)

            reporting_month = date.today().replace(day=1)
            run_forecasting(db, reporting_month)
            run_anomaly_detection(db, reporting_month)
            generate_alerts_from_signals(db, reporting_month)
            rebuild_document_index(db)

            db.commit()
            logger.info(
                "Initial seed complete",
                extra={"reference": ref_result, "operational": op_result, "documents": doc_result},
            )
        else:
            logger.info("Seed skipped: existing users found")
    except Exception as exc:
        db.rollback()
        logger.exception("Startup initialization failed: %s", exc)
        raise
    finally:
        db.close()


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "version": "0.1.0"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(municipalities.router, prefix="/api/v1")
app.include_router(farmers.router, prefix="/api/v1")
app.include_router(production.router, prefix="/api/v1")
app.include_router(warehouses.router, prefix="/api/v1")
app.include_router(cold_storage.router, prefix="/api/v1")
app.include_router(distribution.router, prefix="/api/v1")
app.include_router(prices.router, prefix="/api/v1")
app.include_router(imports.router, prefix="/api/v1")
app.include_router(forecasting.router, prefix="/api/v1")
app.include_router(anomalies.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(geospatial.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
