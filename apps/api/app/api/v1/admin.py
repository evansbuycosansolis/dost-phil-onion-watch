from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.jobs.monthly_pipeline import run_monthly_pipeline
from app.models import DocumentIndexRun, JobRun, User
from app.schemas.admin import AdminSettingUpdate
from app.schemas.auth import CurrentUser
from app.services.audit_service import emit_audit_event

router = APIRouter(prefix="/admin", tags=["admin"], responses=router_default_responses("admin"))


@router.get("/overview")
def overview(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor"))],
):
    users_count = int(db.scalar(select(func.count(User.id))) or 0)
    latest_index = db.scalar(select(DocumentIndexRun).order_by(DocumentIndexRun.id.desc()).limit(1))
    jobs = db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(12)).all()

    return {
        "users_count": users_count,
        "document_ingestion_status": {
            "latest_run_id": latest_index.id if latest_index else None,
            "latest_status": latest_index.status if latest_index else "not_started",
            "num_chunks": latest_index.num_chunks if latest_index else 0,
        },
        "job_status": [
            {
                "id": job.id,
                "job_name": job.job_name,
                "status": job.status,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
            }
            for job in jobs
        ],
        "pipeline_runs": [
            {"id": job.id, "status": job.status, "details": job.details_json}
            for job in jobs
            if job.job_name == "monthly_pipeline"
        ],
        "system_settings": {"environment": "development", "ai_summaries": True},
    }


@router.post("/pipeline/run")
def trigger_pipeline(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
    reporting_month: date | None = None,
):
    job = run_monthly_pipeline(db, reporting_month=reporting_month, triggered_by=current_user.id)

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="admin.pipeline.run",
        entity_type="job_run",
        entity_id=str(job.id),
        after_payload={"status": job.status, "job_name": job.job_name},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"job_id": job.id, "status": job.status}


@router.get("/jobs")
def jobs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor"))],
):
    rows = db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(100)).all()
    return [
        {
            "id": row.id,
            "job_name": row.job_name,
            "status": row.status,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "message": row.message,
            "details": row.details_json,
        }
        for row in rows
    ]


@router.post("/settings")
def update_setting(
    payload: AdminSettingUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin"))],
):
    # MVP stores setting update as auditable event.
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="admin.settings.update",
        entity_type="system_setting",
        entity_id=payload.key,
        after_payload={"value": payload.value},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return {"message": "Setting recorded", "key": payload.key, "value": payload.value}
