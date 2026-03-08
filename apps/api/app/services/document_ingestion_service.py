from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Document, DocumentChunk, DocumentIndexRun, DocumentIngestionJob
from app.services.faiss_service import chunk_text, get_store


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_chunks(path: Path) -> tuple[str, list[str]]:
    text = _extract_text(path)
    chunks = chunk_text(text)
    return text, chunks


def _chunk_retry_limit() -> int:
    return max(1, settings.document_chunk_max_retries)


def _job_max_attempts() -> int:
    return max(1, settings.document_ingestion_job_max_attempts)


def _queue_batch_size() -> int:
    return max(1, settings.document_ingestion_batch_size)


def _refresh_document_progress(db: Session, document: Document) -> None:
    totals = db.execute(
        select(
            func.count(DocumentChunk.id),
            func.sum(case((DocumentChunk.status == "processed", 1), else_=0)),
            func.sum(case((DocumentChunk.status.in_(["failed", "failed_permanent"]), 1), else_=0)),
        ).where(DocumentChunk.document_id == document.id)
    ).first()

    total_chunks = int((totals[0] or 0) if totals else 0)
    processed_chunks = int((totals[1] or 0) if totals else 0)
    failed_chunks = int((totals[2] or 0) if totals else 0)

    document.total_chunks = total_chunks
    document.processed_chunks = processed_chunks
    document.failed_chunks = failed_chunks
    document.progress_pct = round((processed_chunks / total_chunks * 100.0), 2) if total_chunks > 0 else 0.0


def _sync_document_chunks(db: Session, document: Document, chunks: list[str]) -> None:
    retry_limit = _chunk_retry_limit()
    existing_rows = list(
        db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == document.id).order_by(DocumentChunk.chunk_index))
    )
    existing_by_index = {row.chunk_index: row for row in existing_rows}

    for chunk_index, content in enumerate(chunks):
        token_count = len(content.split())
        row = existing_by_index.get(chunk_index)

        if row is None:
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_index,
                    content=content,
                    token_count=token_count,
                    status="pending",
                    retry_count=0,
                    max_retries=retry_limit,
                    metadata_json={"source_file": document.file_name},
                )
            )
            continue

        content_changed = row.content != content
        row.content = content
        row.token_count = token_count
        row.max_retries = retry_limit
        row.metadata_json = {**(row.metadata_json or {}), "source_file": document.file_name}

        if content_changed:
            row.embedding_vector = None
            row.status = "pending"
            row.retry_count = 0
            row.failure_reason = None
            row.processed_at = None

        if row.status == "failed" and row.retry_count < row.max_retries:
            row.status = "pending"

    for stale in existing_rows:
        if stale.chunk_index >= len(chunks):
            db.delete(stale)

    db.flush()


def ingest_document(
    db: Session,
    *,
    title: str,
    file_name: str,
    file_path: str,
    source_type: str,
    uploaded_by: int | None,
) -> Document:
    """Synchronous ingestion path used for seed/bootstrap data."""
    document = Document(
        title=title,
        file_name=file_name,
        file_path=file_path,
        source_type=source_type,
        uploaded_by=uploaded_by,
        status="processing",
        index_status="pending",
        progress_pct=0.0,
    )
    db.add(document)
    db.flush()

    text, chunks = _extract_chunks(Path(file_path))
    _sync_document_chunks(db, document, chunks)

    for row in db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == document.id)):
        row.status = "processed"
        row.retry_count = 0
        row.failure_reason = None
        row.processed_at = datetime.now(timezone.utc)

    document.summary = text[:480] if text else "No extractable text content"
    document.status = "processed"
    document.index_status = "pending"
    document.failure_reason = None
    document.last_processed_at = datetime.now(timezone.utc)
    _refresh_document_progress(db, document)
    db.flush()
    return document


def queue_document_upload(
    db: Session,
    *,
    title: str,
    file_name: str,
    file_path: str,
    source_type: str,
    uploaded_by: int | None,
) -> tuple[Document, DocumentIngestionJob]:
    document = Document(
        title=title,
        file_name=file_name,
        file_path=file_path,
        source_type=source_type,
        uploaded_by=uploaded_by,
        status="queued",
        index_status="pending",
        progress_pct=0.0,
        total_chunks=0,
        processed_chunks=0,
        failed_chunks=0,
    )
    db.add(document)
    db.flush()

    job = DocumentIngestionJob(
        document_id=document.id,
        status="queued",
        queued_at=datetime.now(timezone.utc),
        attempt_count=0,
        max_attempts=_job_max_attempts(),
        requested_by=uploaded_by,
        details_json={"phase": "queued", "source_type": source_type},
    )
    db.add(job)
    db.flush()

    return document, job


def _process_chunk_embeddings(db: Session, document: Document) -> tuple[int, int, int]:
    store = get_store()
    pending_chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.status.in_(["pending", "failed"]),
                DocumentChunk.retry_count < DocumentChunk.max_retries,
            )
            .order_by(DocumentChunk.chunk_index)
        )
    )

    for chunk in pending_chunks:
        chunk.last_attempt_at = datetime.now(timezone.utc)
        try:
            chunk.embedding_vector = store.embedder.embed(chunk.content).astype(float).tolist()
            chunk.status = "processed"
            chunk.failure_reason = None
            chunk.processed_at = datetime.now(timezone.utc)
        except Exception as exc:
            chunk.retry_count += 1
            chunk.failure_reason = str(exc)[:1000]
            if chunk.retry_count >= chunk.max_retries:
                chunk.status = "failed_permanent"
            else:
                chunk.status = "failed"

    db.flush()
    _refresh_document_progress(db, document)

    retryable_failed = int(
        db.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.status == "failed",
            )
        )
        or 0
    )
    permanent_failed = int(
        db.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.status == "failed_permanent",
            )
        )
        or 0
    )
    pending = int(
        db.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.status == "pending",
            )
        )
        or 0
    )
    return pending, retryable_failed, permanent_failed


def process_document_ingestion_job(db: Session, job: DocumentIngestionJob) -> DocumentIngestionJob:
    document = db.scalar(select(Document).where(Document.id == job.document_id))
    if not document:
        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        job.last_error = f"Document {job.document_id} not found"
        db.flush()
        return job

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    job.attempt_count += 1
    job.last_error = None

    document.status = "processing"
    document.failure_reason = None
    document.index_status = "pending"

    try:
        text, chunks = _extract_chunks(Path(document.file_path))
        if not chunks:
            raise ValueError("No extractable text chunks from document")

        _sync_document_chunks(db, document, chunks)
        document.summary = text[:480] if text else "No extractable text content"

        pending, retryable_failed, permanent_failed = _process_chunk_embeddings(db, document)

        job.total_chunks = document.total_chunks
        job.processed_chunks = document.processed_chunks
        job.failed_chunks = document.failed_chunks

        if permanent_failed > 0:
            document.status = "failed"
            document.failure_reason = f"{permanent_failed} chunks reached max retries"
            document.last_processed_at = datetime.now(timezone.utc)
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.last_error = document.failure_reason
            job.details_json = {
                "phase": "failed",
                "permanent_failed_chunks": permanent_failed,
            }
            db.flush()
            return job

        if retryable_failed > 0 or pending > 0:
            document.status = "retrying"
            document.failure_reason = f"{retryable_failed + pending} chunks pending retry"
            document.last_processed_at = datetime.now(timezone.utc)

            if job.attempt_count >= job.max_attempts:
                retry_rows = list(
                    db.scalars(
                        select(DocumentChunk).where(
                            DocumentChunk.document_id == document.id,
                            DocumentChunk.status.in_(["pending", "failed"]),
                        )
                    )
                )
                for row in retry_rows:
                    row.status = "failed_permanent"
                    if not row.failure_reason:
                        row.failure_reason = "Max job attempts reached before successful embedding"
                db.flush()
                _refresh_document_progress(db, document)
                document.status = "failed"
                document.failure_reason = "Document ingestion job max attempts reached"
                document.last_processed_at = datetime.now(timezone.utc)
                job.status = "failed"
                job.finished_at = datetime.now(timezone.utc)
                job.last_error = document.failure_reason
                job.details_json = {
                    "phase": "failed",
                    "reason": "max_job_attempts_reached",
                }
            else:
                job.status = "retrying"
                job.finished_at = datetime.now(timezone.utc)
                job.last_error = document.failure_reason
                job.details_json = {
                    "phase": "retrying",
                    "retryable_failed_chunks": retryable_failed,
                    "pending_chunks": pending,
                    "next_attempt": job.attempt_count + 1,
                }
            db.flush()
            return job

        document.status = "indexing"
        document.index_status = "running"
        db.flush()

        index_run = rebuild_document_index(db)
        document.status = "processed"
        document.index_status = "indexed"
        document.failure_reason = None
        document.progress_pct = 100.0
        document.last_processed_at = datetime.now(timezone.utc)
        document.last_indexed_at = datetime.now(timezone.utc)

        job.status = "completed"
        job.finished_at = datetime.now(timezone.utc)
        job.last_error = None
        job.details_json = {
            "phase": "completed",
            "index_run_id": index_run.id,
            "index_status": index_run.status,
        }
        db.flush()
        return job

    except Exception as exc:
        document.status = "failed"
        document.index_status = "failed"
        document.failure_reason = str(exc)
        document.last_processed_at = datetime.now(timezone.utc)

        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        job.last_error = str(exc)
        job.details_json = {
            "phase": "failed",
            "error": str(exc),
        }
        db.flush()
        return job


def process_pending_document_ingestion_jobs(db: Session, limit: int | None = None) -> list[DocumentIngestionJob]:
    batch_limit = limit or _queue_batch_size()
    jobs = list(
        db.scalars(
            select(DocumentIngestionJob)
            .where(
                DocumentIngestionJob.status.in_(["queued", "retrying"]),
                DocumentIngestionJob.attempt_count < DocumentIngestionJob.max_attempts,
            )
            .order_by(DocumentIngestionJob.queued_at, DocumentIngestionJob.id)
            .limit(batch_limit)
        )
    )

    processed: list[DocumentIngestionJob] = []
    for job in jobs:
        processed.append(process_document_ingestion_job(db, job))
    return processed


def list_document_ingestion_jobs(db: Session, document_id: int | None = None, limit: int = 100) -> list[DocumentIngestionJob]:
    stmt = select(DocumentIngestionJob).order_by(DocumentIngestionJob.queued_at.desc(), DocumentIngestionJob.id.desc()).limit(limit)
    if document_id is not None:
        stmt = stmt.where(DocumentIngestionJob.document_id == document_id)
    return list(db.scalars(stmt))


def get_document_ingestion_job(db: Session, job_id: int) -> DocumentIngestionJob | None:
    return db.scalar(select(DocumentIngestionJob).where(DocumentIngestionJob.id == job_id))


def rebuild_document_index(db: Session) -> DocumentIndexRun:
    run = DocumentIndexRun(status="running")
    db.add(run)
    db.flush()

    rows = db.execute(
        select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.chunk_index, DocumentChunk.content, Document.title)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.status == "processed")
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
    ).all()

    payloads: list[dict[str, Any]] = []
    for chunk_id, document_id, chunk_index, content, title in rows:
        payloads.append(
            {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "chunk_index": chunk_index,
                "document_title": title,
                "content": content,
            }
        )

    store = get_store()
    store.rebuild(payloads)

    processed_document_ids = {row[1] for row in rows}
    if processed_document_ids:
        documents = list(db.scalars(select(Document).where(Document.id.in_(processed_document_ids))))
        for document in documents:
            document.index_status = "indexed"
            document.last_indexed_at = datetime.now(timezone.utc)

    run.status = "completed"
    run.num_chunks = len(payloads)
    run.num_documents = len(processed_document_ids)
    run.details_json = {"index_backend": "faiss" if store.index is not None else "numpy"}
    db.flush()
    return run


def search_documents(db: Session, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    store = get_store()
    results = store.search(query, top_k)

    normalized = []
    for result in results:
        normalized.append(
            {
                "document_id": result["document_id"],
                "document_title": result["document_title"],
                "chunk_id": result["chunk_id"],
                "chunk_index": result["chunk_index"],
                "score": round(float(result["score"]), 4),
                "snippet": result["content"][:260],
            }
        )
    return normalized


def list_documents(db: Session) -> list[Document]:
    return list(db.scalars(select(Document).order_by(Document.uploaded_at.desc())))


def get_document(db: Session, document_id: int) -> Document | None:
    return db.scalar(select(Document).where(Document.id == document_id))
