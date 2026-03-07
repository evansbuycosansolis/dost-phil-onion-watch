from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.jobs.monthly_pipeline import run_monthly_pipeline
from app.models import DocumentIndexRun, JobRun, ReportRecipientGroup, User
from app.schemas.admin import (
    AdminJobRecordDTO,
    AdminOverviewDTO,
    AdminPipelineTriggerResponse,
    AdminSettingResponse,
    AdminSettingUpdate,
)
from app.schemas.auth import CurrentUser
from app.schemas.connectors import (
    ConnectorApprovalDecisionRequest,
    ConnectorApprovalDecisionResponse,
    ConnectorApprovalWorkflowDTO,
    ConnectorDefinitionDTO,
    ConnectorIngestionRequest,
    ConnectorIngestionResponseDTO,
    ConnectorSubmissionDTO,
)
from app.services.audit_service import emit_audit_event
from app.services.feed_connector_service import (
    ConnectorNotFoundError,
    ConnectorValidationError,
    list_connector_approval_workflows,
    list_connector_definitions,
    list_connector_submissions,
    review_connector_workflow,
    run_all_connector_ingestions,
    run_connector_ingestion,
)
from app.services.forecasting_service import latest_model_diagnostics
from app.services.observability_service import get_observability_store
from app.services.report_distribution_service import distribution_status_summary

router = APIRouter(prefix="/admin", tags=["admin"], responses=router_default_responses("admin"))

CONNECTOR_INGEST_REQUEST_EXAMPLE = {
    "limit": 100,
    "dry_run": False,
}


@router.get("/overview", response_model=AdminOverviewDTO)
def overview(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor"))],
):
    users_count = int(db.scalar(select(func.count(User.id))) or 0)
    latest_index = db.scalar(select(DocumentIndexRun).order_by(DocumentIndexRun.id.desc()).limit(1))
    jobs = db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(12)).all()
    diagnostics = latest_model_diagnostics(db)
    distribution_status = distribution_status_summary(db)
    distribution_status["active_groups"] = int(
        db.scalar(select(func.count(ReportRecipientGroup.id)).where(ReportRecipientGroup.is_active.is_(True))) or 0
    )

    return AdminOverviewDTO(
        users_count=users_count,
        document_ingestion_status={
            "latest_run_id": latest_index.id if latest_index else None,
            "latest_status": latest_index.status if latest_index else "not_started",
            "num_chunks": latest_index.num_chunks if latest_index else 0,
        },
        job_status=[
            {
                "id": job.id,
                "job_name": job.job_name,
                "status": job.status,
                "correlation_id": job.correlation_id,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
            }
            for job in jobs
        ],
        pipeline_runs=[
            {"id": job.id, "status": job.status, "details": job.details_json}
            for job in jobs
            if job.job_name == "monthly_pipeline"
        ],
        report_distribution_status=distribution_status,
        forecast_model_diagnostics={
            "run_id": diagnostics.get("run_id"),
            "selected_model_counts": diagnostics.get("selected_model_counts", {}),
            "model_avg_score": diagnostics.get("model_avg_score", {}),
            "model_avg_holdout_mae": diagnostics.get("model_avg_holdout_mae", {}),
            "municipalities_covered": len(diagnostics.get("municipality_diagnostics", [])),
        },
        system_settings={"environment": settings.environment, "ai_summaries": True},
    )


@router.post("/pipeline/run", response_model=AdminPipelineTriggerResponse)
def trigger_pipeline(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
    reporting_month: date | None = None,
):
    correlation_id = getattr(request.state, "correlation_id", None)
    job = run_monthly_pipeline(
        db,
        reporting_month=reporting_month,
        triggered_by=current_user.id,
        correlation_id=correlation_id,
    )

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="admin.pipeline.run",
        entity_type="job_run",
        entity_id=str(job.id),
        after_payload={"status": job.status, "job_name": job.job_name, "correlation_id": correlation_id},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return AdminPipelineTriggerResponse(job_id=job.id, status=job.status)


@router.get("/jobs", response_model=list[AdminJobRecordDTO])
def jobs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor"))],
):
    rows = db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(100)).all()
    return [
        AdminJobRecordDTO(
            id=row.id,
            job_name=row.job_name,
            status=row.status,
            correlation_id=row.correlation_id,
            started_at=row.started_at,
            finished_at=row.finished_at,
            message=row.message,
            details=row.details_json,
        )
        for row in rows
    ]


@router.get("/connectors", response_model=list[ConnectorDefinitionDTO])
def connectors(
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer", "auditor"))],
):
    return [
        ConnectorDefinitionDTO(
            key=row.key,
            source_name=row.source_name,
            display_name=row.display_name,
            description=row.description,
            submission_types=list(row.submission_types),
            adapter_version=row.adapter_version,
        )
        for row in list_connector_definitions()
    ]


@router.post("/connectors/{connector_key}/ingest", response_model=ConnectorIngestionResponseDTO)
def ingest_connector(
    connector_key: str,
    payload: Annotated[
        ConnectorIngestionRequest,
        Body(
            openapi_examples={
                "ingestConnector": {
                    "summary": "Run connector ingestion with validation and workflow creation",
                    "value": CONNECTOR_INGEST_REQUEST_EXAMPLE,
                }
            }
        ),
    ],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer"))],
):
    correlation_id = getattr(request.state, "correlation_id", None)
    try:
        result = run_connector_ingestion(
            db,
            connector_key=connector_key,
            actor_user_id=current_user.id,
            correlation_id=correlation_id,
            limit=payload.limit,
            dry_run=payload.dry_run,
        )
    except ConnectorNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ConnectorValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="connector.ingestion.run",
        entity_type="connector",
        entity_id=connector_key,
        after_payload={
            "sync_batch_id": result["sync_batch_id"],
            "dry_run": payload.dry_run,
            "fetched_count": result["fetched_count"],
            "accepted_count": result["accepted_count"],
            "rejected_count": result["rejected_count"],
            "duplicate_count": result["duplicate_count"],
            "conflict_count": result["conflict_count"],
            "workflow_created_count": result["workflow_created_count"],
        },
        correlation_id=correlation_id,
    )
    return ConnectorIngestionResponseDTO(**result)


@router.post("/connectors/ingest-all")
def ingest_all_connectors(
    payload: Annotated[
        ConnectorIngestionRequest,
        Body(
            openapi_examples={
                "ingestAllConnectors": {
                    "summary": "Run all connector adapters",
                    "value": CONNECTOR_INGEST_REQUEST_EXAMPLE,
                }
            }
        ),
    ],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer"))],
):
    correlation_id = getattr(request.state, "correlation_id", None)
    result = run_all_connector_ingestions(
        db,
        actor_user_id=current_user.id,
        correlation_id=correlation_id,
        limit_per_connector=payload.limit,
        dry_run=payload.dry_run,
    )
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="connector.ingestion.run_all",
        entity_type="connector_batch",
        entity_id="all",
        after_payload=result,
        correlation_id=correlation_id,
    )
    return result


@router.get("/connectors/submissions", response_model=list[ConnectorSubmissionDTO])
def connector_submissions(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer", "auditor"))],
    connector_key: str | None = None,
    status: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
):
    rows = list_connector_submissions(db, connector_key=connector_key, status=status, limit=limit)
    return [ConnectorSubmissionDTO(**row) for row in rows]


@router.get("/connectors/approvals", response_model=list[ConnectorApprovalWorkflowDTO])
def connector_approvals(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer", "auditor"))],
    connector_key: str | None = None,
    status: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
):
    rows = list_connector_approval_workflows(db, connector_key=connector_key, status=status, limit=limit)
    return [ConnectorApprovalWorkflowDTO(**row) for row in rows]


def _connector_decision(
    *,
    action: str,
    workflow_id: int,
    payload: ConnectorApprovalDecisionRequest,
    request: Request,
    db: Session,
    current_user: CurrentUser,
) -> ConnectorApprovalDecisionResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    try:
        result = review_connector_workflow(
            db,
            workflow_id=workflow_id,
            action=action,
            reviewer_user_id=current_user.id,
            notes=payload.notes,
        )
    except ConnectorValidationError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail)

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type=f"connector.approval.{action}",
        entity_type="approval_workflow",
        entity_id=str(workflow_id),
        after_payload=jsonable_encoder(result),
        correlation_id=correlation_id,
    )
    return ConnectorApprovalDecisionResponse(**result)


@router.post("/connectors/approvals/{workflow_id}/approve", response_model=ConnectorApprovalDecisionResponse)
def approve_connector_submission(
    workflow_id: int,
    payload: ConnectorApprovalDecisionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer"))],
):
    return _connector_decision(
        action="approve",
        workflow_id=workflow_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )


@router.post("/connectors/approvals/{workflow_id}/reject", response_model=ConnectorApprovalDecisionResponse)
def reject_connector_submission(
    workflow_id: int,
    payload: ConnectorApprovalDecisionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer"))],
):
    return _connector_decision(
        action="reject",
        workflow_id=workflow_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )


@router.get("/observability/overview")
def observability_overview(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor"))],
    window_minutes: int = 60,
):
    store = get_observability_store()
    api_summary = store.api_summary(window_minutes=window_minutes)
    job_summary = store.job_summary(window_minutes=window_minutes)
    alerts = store.evaluate_alerts()
    return {
        "window_minutes": window_minutes,
        "api": api_summary,
        "jobs": job_summary,
        "active_alerts": alerts["active_alerts"],
    }


@router.post("/observability/evaluate")
def evaluate_observability_alerts(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor"))],
):
    store = get_observability_store()
    result = store.evaluate_alerts()
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="admin.observability.evaluate",
        entity_type="observability_alerts",
        entity_id="runtime",
        after_payload={"sent_alerts": len(result["sent_alerts"]), "active_alerts": len(result["active_alerts"])},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return result


@router.get("/observability/traces/{correlation_id}")
def observability_trace(
    correlation_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor"))],
    limit: int = 100,
):
    store = get_observability_store()
    runtime_trace = store.trace_by_correlation_id(correlation_id, limit=limit)
    jobs = db.scalars(
        select(JobRun).where(JobRun.correlation_id == correlation_id).order_by(JobRun.started_at.desc()).limit(max(1, min(limit, 500)))
    ).all()
    return {
        "correlation_id": correlation_id,
        "runtime": runtime_trace,
        "job_runs": [
            {
                "id": row.id,
                "job_name": row.job_name,
                "status": row.status,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "message": row.message,
                "details": row.details_json,
            }
            for row in jobs
        ],
    }


@router.post("/settings", response_model=AdminSettingResponse)
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
    return AdminSettingResponse(message="Setting recorded", key=payload.key, value=payload.value)
