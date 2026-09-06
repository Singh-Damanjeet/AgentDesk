from datetime import datetime, timezone
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.embeddings.base import EmbeddingError, EmbeddingService
from app.knowledge.chunking import TextChunk, TextChunker
from app.knowledge.errors import (
    KnowledgeError,
    KnowledgeNotFoundError,
    KnowledgeProcessingError,
    KnowledgeStorageError,
)
from app.knowledge.normalization import TextNormalizer
from app.knowledge.parsers.factory import DocumentParserFactory
from app.knowledge.storage import DocumentStorage
from app.knowledge.validation import validate_upload
from app.knowledge.vector_store import (
    LocalVectorStore,
    VectorRecord,
    new_vector_id,
)
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.schemas.knowledge import (
    KnowledgeChunkResponse,
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentResponse,
)
from app.services.embedding_configuration_service import (
    EmbeddingConfigurationService,
)


logger = logging.getLogger(__name__)


class KnowledgeService:
    """Orchestrate safe document ingestion without owning retrieval or RAG."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

    def __init__(
        self,
        *,
        storage: DocumentStorage | None = None,
        chunker: TextChunker | None = None,
        embedding_service: EmbeddingService | None = None,
    ):
        self.storage = storage or DocumentStorage()
        self.chunker = chunker or TextChunker()
        self.embedding_service = embedding_service

    async def ingest(
        self,
        db: Session,
        *,
        filename: str | None,
        content_type: str | None,
        content: bytes,
    ) -> KnowledgeDocument:
        validated = validate_upload(
            filename=filename,
            content_type=content_type,
            content=content,
        )
        document_id = str(uuid.uuid4())
        document = KnowledgeDocument(
            id=document_id,
            filename=validated.filename,
            original_filename=validated.filename,
            file_type=validated.file_type,
            file_size=len(validated.content),
            status=self.UPLOADED,
        )
        source_saved = False

        try:
            self.storage.save(
                document_id=document_id,
                file_type=validated.file_type,
                content=validated.content,
            )
            source_saved = True
            db.add(document)
            db.commit()
            db.refresh(document)
        except KnowledgeError:
            db.rollback()
            if source_saved:
                self._remove_source_safely(document_id)
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            if source_saved:
                self._remove_source_safely(document_id)
            raise KnowledgeStorageError(
                "The document metadata could not be saved."
            ) from exc
        except Exception as exc:
            db.rollback()
            if source_saved:
                self._remove_source_safely(document_id)
            raise KnowledgeStorageError(
                "The document could not be stored."
            ) from exc

        await self._process(db, document_id)
        return self._get_document(db, document_id)

    async def reindex(
        self,
        db: Session,
        document_id: str,
    ) -> KnowledgeDocument:
        self._get_document(db, document_id)
        await self._process(db, document_id)
        return self._get_document(db, document_id)

    def list_documents(self, db: Session) -> list[KnowledgeDocumentResponse]:
        rows = db.execute(
            select(
                KnowledgeDocument,
                func.count(KnowledgeChunk.id).label("chunk_count"),
            )
            .outerjoin(
                KnowledgeChunk,
                KnowledgeChunk.document_id == KnowledgeDocument.id,
            )
            .group_by(KnowledgeDocument.id)
            .order_by(KnowledgeDocument.created_at.desc())
        ).all()

        return [
            self.to_response(document, chunk_count)
            for document, chunk_count in rows
        ]

    def get_document(
        self,
        db: Session,
        document_id: str,
    ) -> KnowledgeDocumentDetailResponse:
        document = self._get_document(db, document_id)
        chunks = db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
        ).all()
        return self._to_detail_response(document, chunks)

    def delete(self, db: Session, document_id: str) -> None:
        document = self._get_document(db, document_id)

        # Remove the generated source directory before committing metadata
        # deletion so an ordinary storage failure does not leave a database
        # record that falsely appears fully deleted.
        self.storage.delete(document.id)

        try:
            LocalVectorStore(db).delete_document(document.id)
            db.delete(document)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise KnowledgeStorageError(
                "The document metadata could not be deleted."
            ) from exc

    async def _process(self, db: Session, document_id: str) -> None:
        document = self._get_document(db, document_id)
        document.status = self.PROCESSING
        document.error = None
        document.updated_at = datetime.now(timezone.utc)
        db.commit()

        try:
            source_path = self.storage.source_path(
                document.id,
                document.file_type,
            )
            if not source_path.is_file():
                raise KnowledgeProcessingError(
                    "The stored document source is unavailable."
                )

            parser = DocumentParserFactory.create(document.file_type)
            parsed_sections = parser.parse(source_path)
            normalized_sections = TextNormalizer.normalize(parsed_sections)
            text_chunks = self.chunker.chunk(normalized_sections)

            if not text_chunks:
                raise KnowledgeProcessingError(
                    "The document does not contain readable content."
                )

            embedding_service = await self._get_embedding_service(db)
            embeddings = await embedding_service.embed_batch(
                [chunk.text for chunk in text_chunks]
            )

            if len(embeddings) != len(text_chunks):
                raise KnowledgeProcessingError(
                    "The embedding service returned an unexpected result."
                )

            records = self._to_vector_records(
                document,
                text_chunks,
                embeddings,
            )
            LocalVectorStore(db).replace_document(document.id, records)

            document = self._get_document(db, document.id)
            document.status = self.READY
            document.error = None
            document.updated_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            self._mark_failed(db, document_id, self._safe_error(exc))

    async def _get_embedding_service(self, db: Session) -> EmbeddingService:
        if self.embedding_service is not None:
            return self.embedding_service

        try:
            return EmbeddingConfigurationService.create(db)
        except EmbeddingError as exc:
            raise KnowledgeProcessingError(exc.user_message) from exc

    @staticmethod
    def _to_vector_records(
        document: KnowledgeDocument,
        chunks: list[TextChunk],
        embeddings: list[list[float]],
    ) -> list[VectorRecord]:
        records: list[VectorRecord] = []

        for chunk_index, (chunk, embedding) in enumerate(
            zip(chunks, embeddings, strict=True)
        ):
            records.append(
                VectorRecord(
                    id=new_vector_id(),
                    document_id=document.id,
                    chunk_index=chunk_index,
                    content=chunk.text,
                    page_number=chunk.page,
                    section=chunk.section,
                    token_count=chunk.token_count,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    embedding=embedding,
                    metadata={
                        "document_id": document.id,
                        "source_filename": document.original_filename,
                        "file_type": document.file_type,
                        "page": chunk.page,
                        "section": chunk.section,
                        **chunk.metadata,
                    },
                )
            )

        return records

    def _mark_failed(
        self,
        db: Session,
        document_id: str,
        message: str,
    ) -> None:
        try:
            document = db.get(KnowledgeDocument, document_id)
            if document is None:
                return

            document.status = self.FAILED
            document.error = message
            document.updated_at = datetime.now(timezone.utc)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "Unable to record knowledge document failure document_id=%s",
                document_id,
            )

    def _get_document(self, db: Session, document_id: str) -> KnowledgeDocument:
        document = db.get(KnowledgeDocument, document_id)
        if document is None:
            raise KnowledgeNotFoundError("Knowledge document not found.")

        return document

    @staticmethod
    def to_response(
        document: KnowledgeDocument,
        chunk_count: int,
    ) -> KnowledgeDocumentResponse:
        return KnowledgeDocumentResponse(
            id=document.id,
            filename=document.filename,
            original_filename=document.original_filename,
            file_type=document.file_type,
            file_size=document.file_size,
            status=document.status,
            chunk_count=max(chunk_count, 0),
            created_at=document.created_at,
            updated_at=document.updated_at,
            error=document.error,
        )

    @classmethod
    def _to_detail_response(
        cls,
        document: KnowledgeDocument,
        chunks: list[KnowledgeChunk],
    ) -> KnowledgeDocumentDetailResponse:
        response = cls.to_response(document, len(chunks))
        return KnowledgeDocumentDetailResponse(
            **response.model_dump(),
            chunks=[
                KnowledgeChunkResponse(
                    id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    token_count=chunk.token_count,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                )
                for chunk in chunks
            ],
        )

    def _remove_source_safely(self, document_id: str) -> None:
        try:
            self.storage.delete(document_id)
        except KnowledgeStorageError:
            logger.exception(
                "Unable to clean up knowledge source document_id=%s",
                document_id,
            )

    @staticmethod
    def _safe_error(error: Exception) -> str:
        if isinstance(error, KnowledgeError):
            return error.user_message

        if isinstance(error, EmbeddingError):
            return error.user_message

        return "Document processing failed."
