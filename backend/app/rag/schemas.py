from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.rag.config import MAX_QUESTION_LENGTH


class RAGQueryRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    question: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_LENGTH,
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must not be empty.")

        return value.strip()


class RAGSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    document_name: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    page: int | None = None
    section: str | None = None
    score: float = Field(ge=-1.0, le=1.0)


class RAGRetrievedChunk(RAGSource):
    content: str = Field(min_length=1)


class RAGResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    sources: list[RAGSource]
    retrieved_chunks: list[RAGRetrievedChunk]
    insufficient_evidence: bool
    latency_ms: int = Field(ge=0)
    trace_id: str = Field(min_length=1)
