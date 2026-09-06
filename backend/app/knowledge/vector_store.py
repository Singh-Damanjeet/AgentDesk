import math
import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.knowledge.errors import KnowledgeProcessingError
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument


@dataclass(frozen=True, slots=True)
class VectorRecord:
    id: str
    document_id: str
    chunk_index: int
    content: str
    page_number: int | None
    section: str | None
    token_count: int
    char_start: int
    char_end: int
    embedding: list[float]
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    chunk_id: str
    document_id: str
    document_name: str
    score: float
    content: str
    page_number: int | None
    section: str | None
    metadata: dict[str, object]


class VectorStore(Protocol):
    def add(self, records: list[VectorRecord]) -> None:
        ...

    def delete_document(self, document_id: str) -> None:
        ...

    def replace_document(
        self,
        document_id: str,
        records: list[VectorRecord],
    ) -> None:
        ...

    def search(
        self,
        query: list[float],
        *,
        limit: int = 5,
    ) -> list[VectorSearchResult]:
        ...


class LocalVectorStore:
    """SQLite-backed vector storage with Python cosine similarity search."""

    def __init__(self, db: Session):
        self.db = db

    def add(self, records: list[VectorRecord]) -> None:
        chunks = []
        expected_dimension: int | None = None

        for record in records:
            self._validate_vector(record.embedding)
            if expected_dimension is None:
                expected_dimension = len(record.embedding)
            elif len(record.embedding) != expected_dimension:
                raise KnowledgeProcessingError(
                    "The embedding service returned inconsistent dimensions."
                )

            chunks.append(
                KnowledgeChunk(
                    id=record.id,
                    document_id=record.document_id,
                    chunk_index=record.chunk_index,
                    content=record.content,
                    page_number=record.page_number,
                    section=record.section,
                    token_count=record.token_count,
                    char_start=record.char_start,
                    char_end=record.char_end,
                    embedding=record.embedding,
                    chunk_metadata=record.metadata,
                )
            )

        self.db.add_all(chunks)

    def delete_document(self, document_id: str) -> None:
        self.db.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.document_id == document_id
            )
        )

    def replace_document(
        self,
        document_id: str,
        records: list[VectorRecord],
    ) -> None:
        self.delete_document(document_id)
        self.add(records)

    def search(
        self,
        query: list[float],
        *,
        limit: int = 5,
    ) -> list[VectorSearchResult]:
        self._validate_vector(query)

        if limit <= 0:
            return []

        results: list[VectorSearchResult] = []
        query_norm = self._norm(query)

        chunks = self.db.execute(
            select(KnowledgeChunk, KnowledgeDocument.filename)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeChunk.document_id,
            )
            .where(KnowledgeDocument.status == "ready")
        )

        for chunk, document_name in chunks:
            embedding = [float(value) for value in chunk.embedding]
            if len(embedding) != len(query):
                raise KnowledgeProcessingError(
                    "Stored and query embedding dimensions do not match."
                )

            score = self._dot(query, embedding) / (
                query_norm * self._norm(embedding)
            )
            score = max(-1.0, min(1.0, score))
            results.append(
                VectorSearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_name=document_name,
                    score=score,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    metadata=dict(chunk.chunk_metadata),
                )
            )

        results.sort(key=lambda result: (-result.score, result.chunk_id))
        return results[:limit]

    def has_ready_chunks(self) -> bool:
        chunk_id = self.db.scalar(
            select(KnowledgeChunk.id)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeChunk.document_id,
            )
            .where(KnowledgeDocument.status == "ready")
            .limit(1)
        )
        return chunk_id is not None

    @staticmethod
    def _validate_vector(vector: list[float]) -> None:
        try:
            is_invalid = not vector or any(
                isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in vector
            )
        except (TypeError, ValueError):
            is_invalid = True

        if is_invalid:
            raise KnowledgeProcessingError(
                "The embedding service returned an invalid vector."
            )

    @staticmethod
    def _dot(left: list[float], right: list[float]) -> float:
        return sum(left_value * right_value for left_value, right_value in zip(
            left,
            right,
            strict=True,
        ))

    @staticmethod
    def _norm(vector: list[float]) -> float:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            raise KnowledgeProcessingError(
                "The embedding service returned a zero vector."
            )

        return norm


def new_vector_id() -> str:
    return str(uuid.uuid4())
