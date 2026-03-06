from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.schemas.auth import CurrentUser
from app.schemas.documents import DocumentSearchRequest
from app.services.audit_service import emit_audit_event
from app.services.document_ingestion_service import (
    get_document,
    ingest_document,
    list_documents,
    rebuild_document_index,
    search_documents,
)

router = APIRouter(prefix="/documents", tags=["documents"], responses=router_default_responses("documents"))

UPLOAD_DIR = Path(__file__).resolve().parents[5] / "data" / "fixtures" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    source_type: str = Form("policy"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("super_admin", "provincial_admin", "policy_reviewer", "market_analyst")),
):
    destination = UPLOAD_DIR / file.filename
    content = await file.read()
    destination.write_bytes(content)

    document = ingest_document(
        db,
        title=title,
        file_name=file.filename,
        file_path=str(destination),
        source_type=source_type,
        uploaded_by=current_user.id,
    )

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="document.upload",
        entity_type="document",
        entity_id=str(document.id),
        after_payload={"title": document.title, "file_name": document.file_name},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"id": document.id, "title": document.title, "status": document.status}


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


@router.get("/")
def documents(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    rows = list_documents(db)
    return [
        {
            "id": row.id,
            "title": row.title,
            "file_name": row.file_name,
            "status": row.status,
            "source_type": row.source_type,
            "uploaded_at": row.uploaded_at,
            "summary": row.summary,
        }
        for row in rows
    ]


@router.post("/search")
def search(
    payload: DocumentSearchRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    return {"query": payload.query, "results": search_documents(db, payload.query, payload.top_k)}


@router.get("/{document_id}")
def document_detail(
    document_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    document = get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": document.id,
        "title": document.title,
        "file_name": document.file_name,
        "file_path": document.file_path,
        "status": document.status,
        "summary": document.summary,
        "source_type": document.source_type,
        "uploaded_at": document.uploaded_at,
    }
