from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.schemas.auth import CurrentUser
from app.schemas.documents import (
    DocumentDetail,
    DocumentIngestionJobDTO,
    DocumentQueueProcessResponse,
    DocumentSearchRequest,
    DocumentSummary,
    DocumentUploadResponse,
)
from app.services.audit_service import emit_audit_event
from app.services.document_ingestion_service import (
    get_document,
    get_document_ingestion_job,
    list_document_ingestion_jobs,
    list_documents,
    process_pending_document_ingestion_jobs,
    queue_document_upload,
    rebuild_document_index,
    search_documents,
)

router = APIRouter(prefix="/documents", tags=["documents"], responses=router_default_responses("documents"))

UPLOAD_DIR = Path(__file__).resolve().parents[5] / "data" / "fixtures" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

READ_ROLES = ("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor")
WRITE_ROLES = ("super_admin", "provincial_admin", "policy_reviewer", "market_analyst")


def _job_to_dto(job) -> DocumentIngestionJobDTO:
    return DocumentIngestionJobDTO(
        id=job.id,
        document_id=job.document_id,
        status=job.status,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        total_chunks=job.total_chunks,
        processed_chunks=job.processed_chunks,
        failed_chunks=job.failed_chunks,
        last_error=job.last_error,
        details=job.details_json,
    )


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    source_type: str = Form("policy"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
):
    safe_name = Path(file.filename).name
    destination = UPLOAD_DIR / safe_name

    with destination.open("wb") as stream:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            stream.write(chunk)

    document, job = queue_document_upload(
        db,
        title=title,
        file_name=safe_name,
        file_path=str(destination),
        source_type=source_type,
        uploaded_by=current_user.id,
    )

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="document.upload.queued",
        entity_type="document",
        entity_id=str(document.id),
        after_payload={
            "title": document.title,
            "file_name": document.file_name,
            "ingestion_job_id": job.id,
            "status": document.status,
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return DocumentUploadResponse(
        id=document.id,
        title=document.title,
        status=document.status,
        progress_pct=document.progress_pct,
        ingestion_job_id=job.id,
        index_status=document.index_status,
    )


@router.post("/jobs/process", response_model=DocumentQueueProcessResponse)
def process_document_queue(
    request: Request,
    limit: int = 4,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(require_role(*WRITE_ROLES))] = None,
):
    jobs = process_pending_document_ingestion_jobs(db, limit=max(1, min(limit, 20)))

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="document.queue.process",
        entity_type="document_ingestion_job_batch",
        entity_id="queue",
        after_payload={"processed_count": len(jobs), "job_ids": [job.id for job in jobs]},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    payload = [_job_to_dto(job) for job in jobs]
    return DocumentQueueProcessResponse(processed_jobs=payload, processed_count=len(payload))


@router.get("/jobs", response_model=list[DocumentIngestionJobDTO])
def document_jobs(
    document_id: int | None = None,
    limit: int = 100,
    db: Annotated[Session, Depends(get_db)] = None,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))] = None,
):
    rows = list_document_ingestion_jobs(db, document_id=document_id, limit=max(1, min(limit, 200)))
    return [_job_to_dto(row) for row in rows]


@router.get("/jobs/{job_id}", response_model=DocumentIngestionJobDTO)
def document_job_detail(
    job_id: int,
    db: Annotated[Session, Depends(get_db)] = None,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))] = None,
):
    row = get_document_ingestion_job(db, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Document ingestion job not found")
    return _job_to_dto(row)


@router.post("/reindex")
def reindex_documents(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer"))],
):
    run = rebuild_document_index(db)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="document.reindex",
        entity_type="document_index_run",
        entity_id=str(run.id),
        after_payload={"status": run.status, "num_chunks": run.num_chunks},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return {"run_id": run.id, "status": run.status, "num_chunks": run.num_chunks}


@router.get("/", response_model=list[DocumentSummary])
def documents(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    rows = list_documents(db)
    return [
        DocumentSummary(
            id=row.id,
            title=row.title,
            file_name=row.file_name,
            status=row.status,
            source_type=row.source_type,
            uploaded_at=row.uploaded_at,
            summary=row.summary,
            progress_pct=row.progress_pct,
            total_chunks=row.total_chunks,
            processed_chunks=row.processed_chunks,
            failed_chunks=row.failed_chunks,
            failure_reason=row.failure_reason,
            index_status=row.index_status,
        )
        for row in rows
    ]


@router.post("/search")
def search(
    payload: DocumentSearchRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    return {"query": payload.query, "results": search_documents(db, payload.query, payload.top_k)}


@router.get("/{document_id}", response_model=DocumentDetail)
def document_detail(
    document_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    document = get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentDetail(
        id=document.id,
        title=document.title,
        file_name=document.file_name,
        file_path=document.file_path,
        status=document.status,
        source_type=document.source_type,
        uploaded_at=document.uploaded_at,
        summary=document.summary,
        progress_pct=document.progress_pct,
        total_chunks=document.total_chunks,
        processed_chunks=document.processed_chunks,
        failed_chunks=document.failed_chunks,
        failure_reason=document.failure_reason,
        index_status=document.index_status,
        last_processed_at=document.last_processed_at,
        last_indexed_at=document.last_indexed_at,
    )
