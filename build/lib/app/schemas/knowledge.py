from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class KnowledgeConfigRead(BaseModel):
    vector_backend: str
    index_type: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    chunk_chars: int
    chunk_overlap_chars: int
    supported_types: list[str]
    rag_top_k: int
    rag_min_similarity: float

class KnowledgeDocumentRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    filename: str
    content_type: str
    sha256: str
    version: int
    status: str
    embedding_model: str
    chunk_count: int
    char_count: int
    created_at: datetime

class KnowledgeIngestResponse(BaseModel):
    document: KnowledgeDocumentRead
    deduplicated: bool
    embedding_tokens: int
    estimated_embedding_cost_usd: str | None

class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=5000)
    top_k: int | None = Field(default=None, ge=1, le=20)

class KnowledgeSourceRead(BaseModel):
    rank: int
    document_id: uuid.UUID
    filename: str
    version: int
    chunk_id: uuid.UUID
    chunk_index: int
    page_number: int | None
    similarity: float
    content: str

class KnowledgeSearchResponse(BaseModel):
    query: str
    embedding_model: str
    embedding_tokens: int
    sources: list[KnowledgeSourceRead]

class KnowledgeQueryResponse(BaseModel):
    run_id: uuid.UUID | None
    answer: str
    sources: list[KnowledgeSourceRead]
