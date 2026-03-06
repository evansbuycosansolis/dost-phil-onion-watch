from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.schemas.auth import CurrentUser
from app.schemas.reports import ReportDTO, ReportExportMetadata, ReportGenerateRequest, ReportGenerateResponse
from app.services.audit_service import emit_audit_event
from app.services.report_service import export_report, generate_report, get_report, list_reports

router = APIRouter(prefix="/reports", tags=["reports"], responses=router_default_responses("reports"))


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
    }


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
    )


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
