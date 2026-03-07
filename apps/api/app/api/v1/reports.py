from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.schemas.auth import CurrentUser
from app.schemas.reports import (
    ReportDTO,
    ReportDeliveryLogDTO,
    ReportDeliveryProcessResponse,
    ReportDistributionQueueResponse,
    ReportExportMetadata,
    ReportGenerateRequest,
    ReportGenerateResponse,
    ReportRecipientGroupCreate,
    ReportRecipientGroupDTO,
    ReportRecipientGroupUpdate,
)
from app.services.audit_service import emit_audit_event
from app.services.report_distribution_service import (
    create_recipient_group,
    get_recipient_group,
    list_recipient_groups,
    list_report_delivery_logs,
    process_pending_report_deliveries,
    queue_report_distribution,
    queue_undistributed_reports,
    update_recipient_group,
)
from app.services.report_service import export_report, generate_report, get_report, list_reports

router = APIRouter(prefix="/reports", tags=["reports"], responses=router_default_responses("reports"))


def _to_group_dto(group) -> ReportRecipientGroupDTO:
    return ReportRecipientGroupDTO(
        id=group.id,
        name=group.name,
        description=group.description,
        report_category=group.report_category,
        role_name=group.role_name,
        organization_id=group.organization_id,
        delivery_channel=group.delivery_channel,
        export_format=group.export_format,
        max_attempts=group.max_attempts,
        retry_backoff_seconds=group.retry_backoff_seconds,
        notify_on_failure=group.notify_on_failure,
        is_active=group.is_active,
        last_used_at=group.last_used_at,
        metadata=group.metadata_json,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def _to_delivery_dto(row) -> ReportDeliveryLogDTO:
    return ReportDeliveryLogDTO(
        id=row.id,
        report_id=row.report_id,
        recipient_group_id=row.recipient_group_id,
        recipient_user_id=row.recipient_user_id,
        recipient_email=row.recipient_email,
        recipient_role=row.recipient_role,
        recipient_organization_id=row.recipient_organization_id,
        delivery_channel=row.delivery_channel,
        export_format=row.export_format,
        status=row.status,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        next_attempt_at=row.next_attempt_at,
        dispatched_at=row.dispatched_at,
        delivered_at=row.delivered_at,
        last_error=row.last_error,
        notification_sent_at=row.notification_sent_at,
        payload=row.payload_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/", response_model=list[ReportDTO])
def reports(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    rows = list_reports(db)
    return [
        {
            "id": row.id,
            "category": row.category,
            "title": row.title,
            "reporting_month": row.reporting_month,
            "status": row.status,
            "generated_at": row.generated_at,
            "file_path": row.file_path,
            "metadata": row.metadata_json,
        }
        for row in rows
    ]


@router.post("/generate", response_model=ReportGenerateResponse)
def generate(
    payload: ReportGenerateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer", "market_analyst"))],
):
    report = generate_report(db, payload.category, payload.reporting_month, generated_by=current_user.id)
    queue_result = queue_report_distribution(
        db,
        report=report,
        actor_user_id=current_user.id,
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="report.generate",
        entity_type="report_record",
        entity_id=str(report.id),
        after_payload={"category": report.category, "file_path": report.file_path},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {
        "id": report.id,
        "category": report.category,
        "status": report.status,
        "reporting_month": report.reporting_month,
        "file_path": report.file_path,
        "metadata": {
            **(report.metadata_json or {}),
            "distribution_queue": queue_result,
        },
    }


@router.get("/distribution/groups", response_model=list[ReportRecipientGroupDTO])
def distribution_groups(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor"))],
    active_only: bool = False,
):
    rows = list_recipient_groups(db, active_only=active_only)
    return [_to_group_dto(row) for row in rows]


@router.post("/distribution/groups", response_model=ReportRecipientGroupDTO)
def create_distribution_group(
    payload: ReportRecipientGroupCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
):
    try:
        group = create_recipient_group(
            db,
            name=payload.name,
            description=payload.description,
            report_category=payload.report_category,
            role_name=payload.role_name,
            organization_id=payload.organization_id,
            delivery_channel=payload.delivery_channel,
            export_format=payload.export_format,
            max_attempts=payload.max_attempts,
            retry_backoff_seconds=payload.retry_backoff_seconds,
            notify_on_failure=payload.notify_on_failure,
            is_active=payload.is_active,
            metadata=payload.metadata,
            actor_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="report.distribution.group.create",
        entity_type="report_recipient_group",
        entity_id=str(group.id),
        after_payload={"name": group.name, "report_category": group.report_category},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return _to_group_dto(group)


@router.patch("/distribution/groups/{group_id}", response_model=ReportRecipientGroupDTO)
def update_distribution_group(
    group_id: int,
    payload: ReportRecipientGroupUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
):
    group = get_recipient_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Recipient group not found")

    before = {
        "name": group.name,
        "report_category": group.report_category,
        "role_name": group.role_name,
        "organization_id": group.organization_id,
        "delivery_channel": group.delivery_channel,
        "export_format": group.export_format,
        "max_attempts": group.max_attempts,
        "retry_backoff_seconds": group.retry_backoff_seconds,
        "notify_on_failure": group.notify_on_failure,
        "is_active": group.is_active,
        "metadata": group.metadata_json,
    }

    try:
        updated = update_recipient_group(
            db,
            group=group,
            changes=payload.model_dump(exclude_unset=True),
            actor_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="report.distribution.group.update",
        entity_type="report_recipient_group",
        entity_id=str(updated.id),
        before_payload=before,
        after_payload={
            "name": updated.name,
            "report_category": updated.report_category,
            "role_name": updated.role_name,
            "organization_id": updated.organization_id,
            "delivery_channel": updated.delivery_channel,
            "export_format": updated.export_format,
            "max_attempts": updated.max_attempts,
            "retry_backoff_seconds": updated.retry_backoff_seconds,
            "notify_on_failure": updated.notify_on_failure,
            "is_active": updated.is_active,
            "metadata": updated.metadata_json,
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return _to_group_dto(updated)


@router.post("/distribution/process", response_model=ReportDeliveryProcessResponse)
def process_distribution_queue(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
    limit: int = Query(default=50, ge=1, le=500),
):
    queued = queue_undistributed_reports(db, limit=25, actor_user_id=current_user.id)
    processed = process_pending_report_deliveries(db, limit=limit, actor_user_id=current_user.id)

    sent_count = sum(1 for row in processed if row.status == "sent")
    failed_count = sum(1 for row in processed if row.status == "failed")
    retrying_count = sum(1 for row in processed if row.status == "retrying")

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="report.distribution.process",
        entity_type="report_distribution_queue",
        entity_id="scheduled",
        after_payload={
            "processed_count": len(processed),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "retrying_count": retrying_count,
            "queue_scan": queued,
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return ReportDeliveryProcessResponse(
        processed_count=len(processed),
        sent_count=sent_count,
        failed_count=failed_count,
        retrying_count=retrying_count,
        deliveries=[_to_delivery_dto(row) for row in processed],
    )


@router.get("/distribution/deliveries", response_model=list[ReportDeliveryLogDTO])
def distribution_deliveries(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor"))],
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    rows = list_report_delivery_logs(db, status=status, limit=limit)
    return [_to_delivery_dto(row) for row in rows]


@router.get("/{report_id}", response_model=ReportDTO)
def report_detail(
    report_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        CurrentUser,
        Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor")),
    ],
):
    report = get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportDTO(
        id=report.id,
        category=report.category,
        title=report.title,
        reporting_month=report.reporting_month,
        status=report.status,
        generated_at=report.generated_at,
        file_path=report.file_path,
        metadata=report.metadata_json,
    )


@router.post("/{report_id}/distribution/queue", response_model=ReportDistributionQueueResponse)
def queue_report_distribution_endpoint(
    report_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer", "market_analyst"))],
):
    report = get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    result = queue_report_distribution(
        db,
        report=report,
        actor_user_id=current_user.id,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return ReportDistributionQueueResponse(**result)


@router.get("/{report_id}/deliveries", response_model=list[ReportDeliveryLogDTO])
def report_deliveries(
    report_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        CurrentUser,
        Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor")),
    ],
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    report = get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    rows = list_report_delivery_logs(db, report_id=report_id, status=status, limit=limit)
    return [_to_delivery_dto(row) for row in rows]


@router.get("/{report_id}/export/{export_format}", response_model=ReportExportMetadata)
def export_report_metadata(
    report_id: int,
    export_format: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[
        CurrentUser,
        Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor")),
    ],
):
    report = get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        export_path, media_type = export_report(report, export_format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return ReportExportMetadata(
        report_id=report.id,
        format=export_format.lower(),
        media_type=media_type,
        file_path=str(export_path),
        file_name=export_path.name,
    )


@router.get("/{report_id}/download/{export_format}", response_class=FileResponse)
def download_report_export(
    report_id: int,
    export_format: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        CurrentUser,
        Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor")),
    ],
):
    report = get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        export_path, media_type = export_report(report, export_format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="report.export.download",
        entity_type="report_record",
        entity_id=str(report.id),
        after_payload={"format": export_format.lower(), "path": str(export_path)},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return FileResponse(
        path=export_path,
        media_type=media_type,
        filename=export_path.name,
    )
