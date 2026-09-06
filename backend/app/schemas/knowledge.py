from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


KnowledgeDocumentStatus = Literal[
    "uploaded",
    "processing",
    "ready",
    "failed",
]


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    filename: str
    original_filename: str
    file_type: str
    file_size: int = Field(ge=1)
    status: KnowledgeDocumentStatus
    chunk_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class KnowledgeChunkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    chunk_index: int = Field(ge=0)
    page_number: int | None = Field(default=None, ge=1)
    section: str | None = None
    token_count: int = Field(ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=1)


class KnowledgeDocumentDetailResponse(KnowledgeDocumentResponse):
    chunks: list[KnowledgeChunkResponse]
