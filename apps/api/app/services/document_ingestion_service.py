from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, DocumentIndexRun
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


def ingest_document(
    db: Session,
    *,
    title: str,
    file_name: str,
    file_path: str,
    source_type: str,
    uploaded_by: int | None,
) -> Document:
    document = Document(
        title=title,
        file_name=file_name,
        file_path=file_path,
        source_type=source_type,
        uploaded_by=uploaded_by,
        status="uploaded",
    )
    db.add(document)
    db.flush()

    text = _extract_text(Path(file_path))
    chunks = chunk_text(text)

    for idx, content in enumerate(chunks):
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=idx,
                content=content,
                token_count=len(content.split()),
                metadata_json={"source_file": file_name},
            )
        )

    document.status = "processed"
    document.summary = text[:480] if text else "No extractable text content"
    db.flush()

    return document


def rebuild_document_index(db: Session) -> DocumentIndexRun:
    run = DocumentIndexRun(status="running")
    db.add(run)
    db.flush()

    rows = db.execute(
        select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.chunk_index, DocumentChunk.content, Document.title)
        .join(Document, Document.id == DocumentChunk.document_id)
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

    run.status = "completed"
    run.num_chunks = len(payloads)
    run.num_documents = len({row[1] for row in rows})
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
