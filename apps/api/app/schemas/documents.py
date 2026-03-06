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
