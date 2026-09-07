from collections.abc import Callable
from datetime import datetime, timezone
import logging
import time
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.embeddings.base import EmbeddingError, EmbeddingService
from app.ai.llm.errors import LLMError
from app.ai.llm.types import ChatMessage
from app.knowledge.errors import KnowledgeProcessingError
from app.knowledge.vector_store import (
    LocalVectorStore,
    VectorSearchResult,
    VectorStore,
)
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.rag.config import (
    DEFAULT_RAG_CONFIG,
    INSUFFICIENT_EVIDENCE_ANSWER,
    MAX_QUESTION_LENGTH,
    RAGConfig,
)
from app.rag.context import assemble_context
from app.rag.errors import (
    RAGEmbeddingError,
    RAGError,
    RAGGenerationError,
    RAGRetrievalError,
    RAGTraceError,
    RAGValidationError,
)
from app.rag.prompts import RAG_SYSTEM_PROMPT, build_user_prompt
from app.rag.schemas import (
    RAGResponse,
    RAGRetrievedChunk,
    RAGSource,
)
from app.services.ai_service import AIConfigurationError, AIService
from app.services.embedding_configuration_service import (
    EmbeddingConfigurationService,
)


logger = logging.getLogger(__name__)

VectorStoreFactory = Callable[[Session], VectorStore]
AIServiceFactory = Callable[[Session], AIService]


class RAGService:
    """Run one-shot grounded retrieval and answer generation."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRIEVAL_STEP = "retrieval"

    def __init__(
        self,
        *,
        config: RAGConfig | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_store_factory: VectorStoreFactory | None = None,
        ai_service_factory: AIServiceFactory | None = None,
    ):
        self.config = config or DEFAULT_RAG_CONFIG
        self.embedding_service = embedding_service
        self.vector_store_factory = vector_store_factory or LocalVectorStore
        self.ai_service_factory = (
            ai_service_factory or AIService.from_configuration
        )

    async def answer(
        self,
        db: Session,
        question: str,
        *,
        ticket_id: str | None = None,
    ) -> RAGResponse:
        normalized_question = self._normalize_question(question)
        started_at = datetime.now(timezone.utc)
        started_perf = time.perf_counter()
        trace_id = str(uuid.uuid4())
        run = self._start_trace(
            db,
            trace_id=trace_id,
            started_at=started_at,
            ticket_id=ticket_id,
        )

        try:
            vector_store = self.vector_store_factory(db)
            if not vector_store.has_ready_chunks():
                self._record_retrieval_step(
                    db,
                    run,
                    candidates=[],
                    selected=[],
                    embedding_latency_ms=0,
                    retrieval_latency_ms=0,
                    reason="no_ready_knowledge",
                )
                response = self._build_response(
                    answer=INSUFFICIENT_EVIDENCE_ANSWER,
                    selected_chunks=(),
                    insufficient_evidence=True,
                    trace_id=trace_id,
                    started_perf=started_perf,
                )
                self._finish_trace(db, run, response)
                return response

            embedding_started = time.perf_counter()
            embedding_service = await self._get_embedding_service(db)
            query_vector = await embedding_service.embed_text(
                normalized_question
            )
            embedding_latency_ms = self._elapsed_ms(embedding_started)

            retrieval_started = time.perf_counter()
            try:
                search_results = vector_store.search(
                    query_vector,
                    limit=self.config.top_k,
                )
            except KnowledgeProcessingError as exc:
                raise RAGRetrievalError(exc.user_message) from exc
            retrieval_latency_ms = self._elapsed_ms(retrieval_started)

            candidates = [
                self._to_retrieved_chunk(result)
                for result in search_results
            ]
            relevant_candidates = [
                chunk
                for chunk in candidates
                if chunk.score >= self.config.min_relevance_score
            ]
            context = assemble_context(
                relevant_candidates,
                max_characters=self.config.max_context_characters,
            )
            reason = (
                "no_relevant_evidence"
                if not context.chunks
                else "relevance_threshold"
            )
            retrieval_step = self._record_retrieval_step(
                db,
                run,
                candidates=candidates,
                selected=context.chunks,
                embedding_latency_ms=embedding_latency_ms,
                retrieval_latency_ms=retrieval_latency_ms,
                reason=reason,
            )

            if not context.chunks:
                response = self._build_response(
                    answer=INSUFFICIENT_EVIDENCE_ANSWER,
                    selected_chunks=(),
                    insufficient_evidence=True,
                    trace_id=trace_id,
                    started_perf=started_perf,
                )
                self._finish_trace(db, run, response)
                return response

            generation_started = time.perf_counter()
            try:
                ai_service = self.ai_service_factory(db)
                run.provider = ai_service.provider
                run.model = ai_service.model
                llm_response = await ai_service.chat(
                    [
                        ChatMessage(
                            role="system",
                            content=RAG_SYSTEM_PROMPT,
                        ),
                        ChatMessage(
                            role="user",
                            content=build_user_prompt(
                                normalized_question,
                                context.text,
                            ),
                        ),
                    ],
                    temperature=0.0,
                    max_output_tokens=800,
                )
            except AIConfigurationError as exc:
                raise RAGGenerationError(str(exc)) from exc
            except LLMError as exc:
                raise RAGGenerationError(exc.user_message) from exc

            generation_latency_ms = self._elapsed_ms(generation_started)
            answer = llm_response.content.strip()
            if not answer:
                raise RAGGenerationError(
                    "The AI provider returned an empty grounded answer."
                )

            response = self._build_response(
                answer=answer,
                selected_chunks=context.chunks,
                insufficient_evidence=False,
                trace_id=trace_id,
                started_perf=started_perf,
            )
            self._record_generation_latency(
                db,
                retrieval_step,
                generation_latency_ms,
                response.latency_ms,
            )
            self._finish_trace(db, run, response)
            return response
        except RAGError as exc:
            self._fail_trace(db, run, exc.user_message, started_perf)
            raise
        except EmbeddingError as exc:
            error = RAGEmbeddingError(exc.user_message)
            self._fail_trace(db, run, error.user_message, started_perf)
            raise error from exc
        except SQLAlchemyError as exc:
            error = RAGRetrievalError(
                "The knowledge base is currently unavailable."
            )
            self._fail_trace(db, run, error.user_message, started_perf)
            raise error from exc
        except Exception as exc:
            logger.exception("RAG query failed trace_id=%s", trace_id)
            error = RAGError("The grounded answer could not be completed.")
            self._fail_trace(db, run, error.user_message, started_perf)
            raise error from exc

    async def _get_embedding_service(self, db: Session) -> EmbeddingService:
        if self.embedding_service is not None:
            return self.embedding_service

        try:
            return EmbeddingConfigurationService.create(db)
        except EmbeddingError as exc:
            raise RAGEmbeddingError(exc.user_message) from exc

    def _start_trace(
        self,
        db: Session,
        *,
        trace_id: str,
        started_at: datetime,
        ticket_id: str | None,
    ) -> AgentRun:
        run = AgentRun(
            ticket_id=ticket_id,
            trace_id=trace_id,
            status=self.RUNNING,
            started_at=started_at,
        )

        try:
            db.add(run)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise RAGTraceError(
                "The RAG trace could not be started."
            ) from exc

        return run

    def _record_retrieval_step(
        self,
        db: Session,
        run: AgentRun,
        *,
        candidates: list[RAGRetrievedChunk],
        selected: tuple[RAGRetrievedChunk, ...] | list[RAGRetrievedChunk],
        embedding_latency_ms: int,
        retrieval_latency_ms: int,
        reason: str,
    ) -> AgentStep:
        step = AgentStep(
            agent_run_id=run.id,
            step_type=self.RETRIEVAL_STEP,
            input_summary="Knowledge retrieval for a single question.",
            output_summary=(
                f"Selected {len(selected)} of {len(candidates)} "
                "retrieved chunks."
            ),
            duration_ms=embedding_latency_ms + retrieval_latency_ms,
            step_metadata={
                "reason": reason,
                "top_k": self.config.top_k,
                "min_relevance_score": self.config.min_relevance_score,
                "embedding_latency_ms": embedding_latency_ms,
                "retrieval_latency_ms": retrieval_latency_ms,
                "candidates": [
                    self._chunk_trace_metadata(chunk)
                    for chunk in candidates
                ],
                "selected_chunk_ids": [
                    chunk.chunk_id
                    for chunk in selected
                ],
            },
        )

        try:
            db.add(step)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise RAGTraceError(
                "The RAG retrieval trace could not be saved."
            ) from exc

        return step

    def _record_generation_latency(
        self,
        db: Session,
        step: AgentStep,
        generation_latency_ms: int,
        total_latency_ms: int,
    ) -> None:
        step_metadata = dict(step.step_metadata or {})
        step_metadata["generation_latency_ms"] = generation_latency_ms
        step_metadata["total_latency_ms"] = total_latency_ms
        step.step_metadata = step_metadata
        step.duration_ms = (
            float(step.duration_ms or 0) + generation_latency_ms
        )

        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise RAGTraceError(
                "The RAG generation trace could not be saved."
            ) from exc

    def _finish_trace(
        self,
        db: Session,
        run: AgentRun,
        response: RAGResponse,
    ) -> None:
        run.status = self.COMPLETED
        run.finished_at = datetime.now(timezone.utc)
        run.latency_ms = response.latency_ms
        run.error = None

        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise RAGTraceError(
                "The RAG trace could not be completed."
            ) from exc

    def _fail_trace(
        self,
        db: Session,
        run: AgentRun,
        message: str,
        started_perf: float,
    ) -> None:
        try:
            db.rollback()
            persisted_run = db.get(AgentRun, run.id)
            if persisted_run is None:
                return

            persisted_run.status = self.FAILED
            persisted_run.finished_at = datetime.now(timezone.utc)
            persisted_run.latency_ms = self._elapsed_ms(started_perf)
            persisted_run.error = message
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "Unable to record failed RAG trace trace_id=%s",
                run.trace_id,
            )

    def _build_response(
        self,
        *,
        answer: str,
        selected_chunks: tuple[RAGRetrievedChunk, ...]
        | list[RAGRetrievedChunk],
        insufficient_evidence: bool,
        trace_id: str,
        started_perf: float,
    ) -> RAGResponse:
        return RAGResponse(
            answer=answer,
            sources=[
                self._to_source(chunk)
                for chunk in selected_chunks
            ],
            retrieved_chunks=list(selected_chunks),
            insufficient_evidence=insufficient_evidence,
            latency_ms=self._elapsed_ms(started_perf),
            trace_id=trace_id,
        )

    @staticmethod
    def _to_retrieved_chunk(result: VectorSearchResult) -> RAGRetrievedChunk:
        return RAGRetrievedChunk(
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            document_name=result.document_name,
            content=result.content,
            score=result.score,
            page=result.page_number,
            section=result.section,
        )

    @staticmethod
    def _to_source(chunk: RAGRetrievedChunk) -> RAGSource:
        return RAGSource(
            document_id=chunk.document_id,
            document_name=chunk.document_name,
            chunk_id=chunk.chunk_id,
            page=chunk.page,
            section=chunk.section,
            score=chunk.score,
        )

    @staticmethod
    def _chunk_trace_metadata(chunk: RAGRetrievedChunk) -> dict[str, object]:
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "document_name": chunk.document_name,
            "page": chunk.page,
            "section": chunk.section,
            "score": chunk.score,
        }

    @staticmethod
    def _normalize_question(question: str) -> str:
        if not isinstance(question, str):
            raise RAGValidationError("Question must be a string.")

        normalized = question.strip()
        if not normalized:
            raise RAGValidationError("Question must not be empty.")

        if len(normalized) > MAX_QUESTION_LENGTH:
            raise RAGValidationError(
                "Question exceeds the maximum supported length."
            )

        return normalized

    @staticmethod
    def _elapsed_ms(started_perf: float) -> int:
        return max(0, round((time.perf_counter() - started_perf) * 1000))
