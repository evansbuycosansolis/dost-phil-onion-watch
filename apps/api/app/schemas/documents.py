from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DocumentSearchRequest(BaseModel):
    query: str
    top_k: int = 5


class DocumentResult(BaseModel):
    document_id: int
    document_title: str
    chunk_id: int
    chunk_index: int
    score: float
    snippet: str


class DocumentSummary(BaseModel):
    id: int
    title: str
    file_name: str
    status: str
    source_type: str
    uploaded_at: datetime
    summary: str | None = None
    progress_pct: float
    total_chunks: int
    processed_chunks: int
    failed_chunks: int
    failure_reason: str | None = None
    index_status: str


class DocumentDetail(DocumentSummary):
    file_path: str
    last_processed_at: datetime | None = None
    last_indexed_at: datetime | None = None


class DocumentUploadResponse(BaseModel):
    id: int
    title: str
    status: str
    progress_pct: float
    ingestion_job_id: int
    index_status: str


class DocumentIngestionJobDTO(BaseModel):
    id: int
    document_id: int
    status: str
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    attempt_count: int
    max_attempts: int
    total_chunks: int
    processed_chunks: int
    failed_chunks: int
    last_error: str | None = None
    details: dict[str, Any] | None = None


class DocumentQueueProcessResponse(BaseModel):
    processed_jobs: list[DocumentIngestionJobDTO]
    processed_count: int
