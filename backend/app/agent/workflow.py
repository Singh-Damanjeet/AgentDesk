from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from dataclasses import dataclass
from json import JSONDecodeError
import logging
import re
import time
from typing import Protocol
import uuid

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.constants import (
    ACCOUNT_DATA_ANSWER,
    CLASSIFIER_MAX_OUTPUT_TOKENS,
    CLASSIFICATION_FALLBACK_ANSWER,
    CLASSIFIER_SYSTEM_PROMPT,
    INVALID_INPUT_ANSWER,
    MAX_AGENT_ANSWER_LENGTH,
    MAX_CONTEXT_MESSAGE_LENGTH,
    MAX_CONTEXT_MESSAGES,
    OUTPUT_GUARD_ANSWER,
    PROMPT_MANIPULATION_ANSWER,
)
from app.agent.routing import (
    route_after_classification,
    route_after_input_guard,
    route_after_retrieval,
)
from app.agent.state import AgentState, ConversationContextItem
from app.ai.llm.errors import LLMError
from app.ai.llm.types import ChatMessage, LLMResponse
from app.core.tickets import MAX_MESSAGE_LENGTH, TicketPriority
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.company import Company
from app.models.message import Message
from app.rag.config import INSUFFICIENT_EVIDENCE_ANSWER
from app.rag.errors import RAGError
from app.rag.schemas import RAGResponse, RAGRetrievedChunk
from app.rag.service import RAGRetrievalResult, RAGService
from app.schemas.agent import ClassificationResult
from app.services.ai_provider_service import AIProviderService
from app.services.ai_service import AIConfigurationError, AIService
from app.services.company_service import CompanyService
from app.services.ticket_service import TicketService


logger = logging.getLogger(__name__)

AIServiceFactory = Callable[[Session], AIService]


class WorkflowPersistence(Protocol):
    """The conversation-owned persistence boundary for graph responses."""

    def persist_workflow_response(
        self,
        db: Session,
        *,
        ticket_id: str,
        answer: str,
        insufficient_evidence: bool,
        requires_human_review: bool,
    ) -> None:
        ...


class AgentWorkflowError(RuntimeError):
    """Raised when a graph execution cannot safely complete."""

    def __init__(self, message: str):
        self.user_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AgentWorkflowResult:
    """Safe result returned after the graph has persisted its response."""

    trace_id: str
    answer: str
    insufficient_evidence: bool
    requires_human_review: bool
    classification: ClassificationResult | None
    retrieved_chunks: list[RAGRetrievedChunk]


class _NodeOperation(Protocol):
    def __call__(
        self,
        state: AgentState,
    ) -> Awaitable[tuple[dict[str, object], dict[str, object]]]:
        ...


class _GraphExecution:
    """Per-request graph dependencies kept outside serializable graph state."""

    _STEP_INPUT_SUMMARIES = {
        "load_context": "Validate the ticket and load bounded support context.",
        "input_guard": "Validate the customer message deterministically.",
        "classify": "Classify the support request for deterministic routing.",
        "account_data_guard": "Guard account-specific requests without account access.",
        "retrieve_knowledge": "Retrieve bounded evidence from the knowledge base.",
        "generate": "Generate a grounded response from selected evidence.",
        "output_guard": "Validate the generated response before persistence.",
        "persist": "Persist the workflow response through ConversationService.",
    }

    def __init__(
        self,
        *,
        service: "AgentWorkflowService",
        db: Session,
        run: AgentRun,
    ):
        self.service = service
        self.db = db
        self.run = run
        self.provider: str | None = None
        self.model: str | None = None

    def build(self):
        graph = StateGraph(AgentState)
        graph.add_node(
            "load_context",
            self._wrap("load_context", 1, self._load_context),
        )
        graph.add_node(
            "input_guard",
            self._wrap("input_guard", 2, self._input_guard),
        )
        graph.add_node(
            "classify",
            self._wrap("classify", 3, self._classify),
        )
        graph.add_node(
            "account_data_guard",
            self._wrap(
                "account_data_guard",
                4,
                self._account_data_guard,
            ),
        )
        graph.add_node(
            "retrieve_knowledge",
            self._wrap(
                "retrieve_knowledge",
                4,
                self._retrieve_knowledge,
            ),
        )
        graph.add_node(
            "generate",
            self._wrap("generate", 5, self._generate),
        )
        graph.add_node(
            "output_guard",
            self._wrap("output_guard", 6, self._output_guard),
        )
        graph.add_node(
            "persist",
            self._wrap("persist", 7, self._persist),
        )

        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "input_guard")
        graph.add_conditional_edges(
            "input_guard",
            route_after_input_guard,
            {
                "classify": "classify",
                "persist": "persist",
            },
        )
        graph.add_conditional_edges(
            "classify",
            route_after_classification,
            {
                "account_data_guard": "account_data_guard",
                "retrieve_knowledge": "retrieve_knowledge",
                "persist": "persist",
            },
        )
        graph.add_edge("account_data_guard", "persist")
        graph.add_conditional_edges(
            "retrieve_knowledge",
            route_after_retrieval,
            {
                "generate": "generate",
                "output_guard": "output_guard",
            },
        )
        graph.add_edge("generate", "output_guard")
        graph.add_edge("output_guard", "persist")
        graph.add_edge("persist", END)
        return graph.compile(name="agentdesk_support_workflow")

    def _wrap(
        self,
        step_type: str,
        sequence_number: int,
        operation: _NodeOperation,
    ) -> Callable[[AgentState], Awaitable[dict[str, object]]]:
        async def run_node(state: AgentState) -> dict[str, object]:
            started = time.perf_counter()
            try:
                updates, metadata = await operation(state)
            except Exception as exc:
                self._record_step(
                    step_type=step_type,
                    sequence_number=sequence_number,
                    duration_ms=self._elapsed_ms(started),
                    passed=False,
                    metadata={
                        "reason": "node_failed",
                        "exception_type": type(exc).__name__,
                    },
                )
                raise

            safe_metadata = dict(metadata)
            passed = bool(safe_metadata.pop("passed", True))
            input_summary = safe_metadata.pop(
                "input_summary",
                self._STEP_INPUT_SUMMARIES[step_type],
            )
            output_summary = safe_metadata.pop(
                "output_summary",
                f"{step_type.replace('_', ' ').capitalize()} completed.",
            )
            safe_metadata["passed"] = passed
            duration_ms = self._elapsed_ms(started)
            self._record_step(
                step_type=step_type,
                sequence_number=sequence_number,
                duration_ms=duration_ms,
                passed=passed,
                metadata=safe_metadata,
                input_summary=input_summary,
                output_summary=output_summary,
            )
            return updates

        return run_node

    async def _load_context(
        self,
        state: AgentState,
    ) -> tuple[dict[str, object], dict[str, object]]:
        ticket = TicketService.get(self.db, state["ticket_id"])
        requested_session_id = state.get("session_id")
        if (
            requested_session_id is not None
            and ticket.session_id != requested_session_id
        ):
            raise AgentWorkflowError("Conversation session validation failed.")

        messages = self.db.scalars(
            select(Message)
            .where(Message.ticket_id == ticket.id)
            .order_by(
                Message.sequence_number.desc(),
                Message.created_at.desc(),
                Message.id.desc(),
            )
            .limit(MAX_CONTEXT_MESSAGES)
        ).all()
        context: list[ConversationContextItem] = [
            {
                "sender_type": message.sender_type,
                "content": message.content[:MAX_CONTEXT_MESSAGE_LENGTH],
            }
            for message in reversed(messages)
        ]

        company = CompanyService.get(self.db)
        company_context = self._company_context(company)
        return (
            {
                "session_id": ticket.session_id,
                "conversation_context": context,
                "company_context": company_context,
            },
            {
                "history_count": len(context),
                "company_context_fields": sorted(company_context),
                "session_validated": True,
                "ticket_status": ticket.status,
            },
        )

    async def _input_guard(
        self,
        state: AgentState,
    ) -> tuple[dict[str, object], dict[str, object]]:
        message = state.get("user_message")
        reason = self._input_rejection_reason(message)
        if reason is None:
            return (
                {"input_rejected": False},
                {"reason": "passed"},
            )

        answer = (
            PROMPT_MANIPULATION_ANSWER
            if reason == "prompt_manipulation"
            else INVALID_INPUT_ANSWER
        )
        return (
            {
                "input_rejected": True,
                "answer": answer,
                "insufficient_evidence": False,
                "requires_human_review": True,
                "guard_reason": reason,
            },
            {
                "passed": False,
                "reason": reason,
                "output_summary": "The message was rejected by the input guard.",
            },
        )

    async def _classify(
        self,
        state: AgentState,
    ) -> tuple[dict[str, object], dict[str, object]]:
        try:
            ai_service = self.service.ai_service_factory(self.db)
            self.provider = ai_service.provider
            self.model = ai_service.model
            result = await ai_service.structured_output(
                self._classifier_messages(state),
                ClassificationResult,
                temperature=0.0,
                max_output_tokens=CLASSIFIER_MAX_OUTPUT_TOKENS,
            )
            classification = ClassificationResult.model_validate(result)
            TicketService.update_classification(
                self.db,
                state["ticket_id"],
                category=classification.category,
                urgency=classification.urgency,
            )
        except (AIConfigurationError, LLMError, ValidationError) as exc:
            failure_metadata = self._classification_failure_metadata(exc)
            logger.warning(
                "Agent classification unavailable provider=%s model=%s "
                "exception_type=%s diagnostic=%s cause_type=%s",
                self.provider,
                self.model,
                type(exc).__name__,
                failure_metadata.get("failure_diagnostic"),
                failure_metadata.get("failure_cause_type"),
            )
            return (
                {
                    "classification": None,
                    "classifier_failed": True,
                    "answer": CLASSIFICATION_FALLBACK_ANSWER,
                    "insufficient_evidence": False,
                    "requires_human_review": True,
                },
                {
                    **failure_metadata,
                    "passed": False,
                    "reason": "classification_unavailable",
                    "output_summary": (
                        "The request was routed to human review safely."
                    ),
                },
            )

        return (
            {"classification": classification},
            {
                "category": classification.category,
                "urgency": classification.urgency,
                "needs_account_data": classification.needs_account_data,
                "confidence": classification.confidence,
                "priority": self.service.priority_for_urgency(
                    classification.urgency
                ),
            },
        )

    @staticmethod
    def _classification_failure_metadata(
        error: Exception,
    ) -> dict[str, object]:
        diagnostics = getattr(error, "diagnostics", {})
        safe_metadata: dict[str, object] = {
            "failure_type": type(error).__name__,
        }
        if isinstance(diagnostics, Mapping):
            safe_metadata.update(
                {
                    str(key): value
                    for key, value in diagnostics.items()
                    if isinstance(key, str)
                }
            )

        cause = error.__cause__
        if cause is not None:
            safe_metadata.setdefault(
                "failure_cause_type",
                type(cause).__name__,
            )

        if isinstance(error, AIConfigurationError):
            safe_metadata.setdefault("failure_diagnostic", "configuration")
        elif isinstance(error, ValidationError):
            safe_metadata.setdefault(
                "failure_diagnostic",
                "schema_validation",
            )
            _GraphExecution._add_validation_metadata(
                safe_metadata,
                error,
            )
        elif isinstance(cause, ValidationError):
            safe_metadata.setdefault(
                "failure_diagnostic",
                "schema_validation",
            )
            _GraphExecution._add_validation_metadata(
                safe_metadata,
                cause,
            )
        elif isinstance(cause, JSONDecodeError):
            safe_metadata.setdefault(
                "failure_diagnostic",
                "invalid_json",
            )
        elif isinstance(error, LLMError):
            diagnostic_by_type = {
                "LLMAuthenticationError": "authentication",
                "LLMConfigurationError": "provider_configuration",
                "LLMInputError": "invalid_request",
                "LLMProviderError": "provider_failure",
                "LLMRateLimitError": "rate_limited",
                "LLMResponseError": "provider_response",
                "LLMStructuredOutputError": "structured_output",
                "LLMTimeoutError": "timeout",
            }
            safe_metadata.setdefault(
                "failure_diagnostic",
                diagnostic_by_type.get(
                    type(error).__name__,
                    "llm_failure",
                ),
            )
        else:
            safe_metadata.setdefault("failure_diagnostic", "classifier_failure")

        return safe_metadata

    @staticmethod
    def _add_validation_metadata(
        metadata: dict[str, object],
        error: ValidationError,
    ) -> None:
        validation_errors = error.errors()
        metadata.setdefault(
            "validation_fields",
            sorted(
                {
                    str(location)
                    for validation_error in validation_errors
                    for location in validation_error.get("loc", ())
                }
            ),
        )
        metadata.setdefault(
            "validation_error_types",
            sorted(
                {
                    str(validation_error.get("type"))
                    for validation_error in validation_errors
                    if validation_error.get("type") is not None
                }
            ),
        )

    async def _account_data_guard(
        self,
        state: AgentState,
    ) -> tuple[dict[str, object], dict[str, object]]:
        return (
            {
                "answer": ACCOUNT_DATA_ANSWER,
                "insufficient_evidence": False,
                "requires_human_review": True,
            },
            {
                "reason": "account_data_integration_not_configured",
                "output_summary": (
                    "Account-specific facts were not generated or invented."
                ),
            },
        )

    async def _retrieve_knowledge(
        self,
        state: AgentState,
    ) -> tuple[dict[str, object], dict[str, object]]:
        retrieval = await self.service.rag_service.retrieve(
            self.db,
            state["user_message"],
        )
        if not isinstance(retrieval, RAGRetrievalResult):
            raise AgentWorkflowError(
                "The knowledge retrieval result was invalid."
            )

        selected_chunks = list(retrieval.context.chunks)
        return (
            {
                "retrieved_chunks": selected_chunks,
                "insufficient_evidence": retrieval.insufficient_evidence,
                "retrieval_reason": retrieval.reason,
                "answer": (
                    INSUFFICIENT_EVIDENCE_ANSWER
                    if retrieval.insufficient_evidence
                    else None
                ),
                "requires_human_review": retrieval.insufficient_evidence,
            },
            {
                "reason": retrieval.reason,
                "candidate_count": len(retrieval.candidates),
                "selected_count": len(selected_chunks),
                "selected_chunk_ids": [
                    chunk.chunk_id for chunk in selected_chunks
                ],
                "selected_chunks": [
                    self._chunk_trace_metadata(chunk)
                    for chunk in selected_chunks
                ],
                "embedding_latency_ms": retrieval.embedding_latency_ms,
                "retrieval_latency_ms": retrieval.retrieval_latency_ms,
                "output_summary": (
                    f"Selected {len(selected_chunks)} of "
                    f"{len(retrieval.candidates)} retrieved chunks."
                ),
            },
        )

    async def _generate(
        self,
        state: AgentState,
    ) -> tuple[dict[str, object], dict[str, object]]:
        generation = await self.service.rag_service.generate_from_context(
            self.db,
            state["user_message"],
            state.get("retrieved_chunks", []),
        )
        if isinstance(generation, LLMResponse):
            self.provider = generation.provider
            self.model = generation.model
            answer = generation.content.strip()
            latency_ms = generation.latency_ms
        elif isinstance(generation, RAGResponse):
            answer = generation.answer.strip()
            latency_ms = generation.latency_ms
        else:
            raise AgentWorkflowError(
                "The grounded generation result was invalid."
            )

        if not answer:
            raise AgentWorkflowError(
                "The AI provider returned an empty grounded answer."
            )

        return (
            {"answer": answer},
            {
                "provider": self.provider,
                "model": self.model,
                "latency_ms": latency_ms,
                "generation_succeeded": True,
            },
        )

    async def _output_guard(
        self,
        state: AgentState,
    ) -> tuple[dict[str, object], dict[str, object]]:
        answer = state.get("answer")
        reason = self._output_rejection_reason(
            answer,
            source_count=len(state.get("retrieved_chunks", [])),
        )
        if reason is None:
            return (
                {},
                {
                    "reason": "passed",
                    "source_count": len(state.get("retrieved_chunks", [])),
                },
            )

        return (
            {
                "answer": OUTPUT_GUARD_ANSWER,
                "requires_human_review": True,
                "guard_reason": reason,
            },
            {
                "passed": False,
                "reason": reason,
                "output_summary": (
                    "The generated output was replaced with a safe response."
                ),
            },
        )

    async def _persist(
        self,
        state: AgentState,
    ) -> tuple[dict[str, object], dict[str, object]]:
        if self.service.persistence is None:
            raise AgentWorkflowError(
                "Conversation persistence is not configured."
            )

        answer = state.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise AgentWorkflowError(
                "The workflow did not produce a safe response."
            )

        self.service.persistence.persist_workflow_response(
            self.db,
            ticket_id=state["ticket_id"],
            answer=answer.strip(),
            insufficient_evidence=state.get(
                "insufficient_evidence",
                False,
            ),
            requires_human_review=state.get(
                "requires_human_review",
                False,
            ),
        )
        return (
            {"persisted": True},
            {"response_persisted": True},
        )

    def _record_step(
        self,
        *,
        step_type: str,
        sequence_number: int,
        duration_ms: int,
        passed: bool,
        metadata: Mapping[str, object],
        input_summary: str | None = None,
        output_summary: str | None = None,
    ) -> None:
        step = AgentStep(
            agent_run_id=self.run.id,
            sequence_number=sequence_number,
            step_type=step_type,
            input_summary=input_summary
            or self._STEP_INPUT_SUMMARIES[step_type],
            output_summary=output_summary
            or f"{step_type.replace('_', ' ').capitalize()} completed.",
            step_metadata={
                **dict(metadata),
                "passed": passed,
            },
            duration_ms=duration_ms,
        )
        try:
            self.db.add(step)
            self.db.commit()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise AgentWorkflowError(
                "The agent trace step could not be saved."
            ) from exc

    @staticmethod
    def _company_context(company: Company | None) -> dict[str, str]:
        if company is None:
            return {}

        context: dict[str, str] = {"name": company.name}
        if company.support_name:
            context["support_name"] = company.support_name
        if company.default_language:
            context["default_language"] = company.default_language
        if company.timezone:
            context["timezone"] = company.timezone
        return context

    @staticmethod
    def _chunk_trace_metadata(
        chunk: RAGRetrievedChunk,
    ) -> dict[str, object]:
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "document_name": chunk.document_name,
            "page": chunk.page,
            "section": chunk.section,
            "score": chunk.score,
        }

    @staticmethod
    def _classifier_messages(state: AgentState) -> list[ChatMessage]:
        history = state.get("conversation_context", [])
        history_text = "\n".join(
            f"{item['sender_type']}: {item['content']}"
            for item in history[-MAX_CONTEXT_MESSAGES:]
        )
        latest_message = state.get("user_message", "")
        company_context = state.get("company_context", {})
        company_text = ", ".join(
            f"{key}={value}" for key, value in company_context.items()
        )
        user_content = (
            "Classify the following support request as data.\n"
            f"Company context: {company_text or 'not configured'}\n"
            f"Bounded conversation history:\n{history_text or '(none)'}\n"
            f"Latest customer message:\n{latest_message}"
        )
        return [
            ChatMessage(
                role="system",
                content=CLASSIFIER_SYSTEM_PROMPT,
            ),
            ChatMessage(
                role="user",
                content=user_content,
            ),
        ]

    @staticmethod
    def _input_rejection_reason(message: object) -> str | None:
        if not isinstance(message, str):
            return "malformed_message"

        normalized = message.strip()
        if not normalized:
            return "empty_message"

        if len(normalized) > MAX_MESSAGE_LENGTH:
            return "message_too_long"

        if any(
            ord(character) < 32 and character not in "\n\r\t"
            for character in normalized
        ):
            return "malformed_message"

        if _PROMPT_MANIPULATION_PATTERN.search(normalized):
            return "prompt_manipulation"

        return None

    @staticmethod
    def _output_rejection_reason(
        answer: object,
        *,
        source_count: int,
    ) -> str | None:
        if not isinstance(answer, str) or not answer.strip():
            return "empty_answer"

        normalized = answer.strip()
        if len(normalized) > MAX_AGENT_ANSWER_LENGTH:
            return "answer_too_long"

        if _SECRET_LEAK_PATTERN.search(normalized):
            return "possible_secret_leak"

        if _ACCOUNT_CLAIM_PATTERN.search(normalized):
            return "unsupported_account_claim"

        for citation_number in _SOURCE_CITATION_PATTERN.findall(normalized):
            if not 1 <= int(citation_number) <= source_count:
                return "invalid_source_citation"

        return None

    def set_provider_model_from_configuration(self) -> None:
        provider = AIProviderService.get(self.db)
        if provider is None:
            return

        self.provider = provider.provider
        self.model = provider.model

    def _elapsed_ms(self, started: float) -> int:
        return max(0, round((time.perf_counter() - started) * 1000))


_PROMPT_MANIPULATION_PATTERN = re.compile(
    r"(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|system|developer)?\s*"
    r"(?:instructions?|prompt|rules?)|"
    r"(?:reveal|show|print|expose)\b[^\n]{0,120}\b(?:api\s*key|secret|system\s+prompt)",
    re.IGNORECASE,
)
_SECRET_LEAK_PATTERN = re.compile(
    r"(?:(?:gemini|openrouter)[_ -]?api[_ -]?key|"
    r"authorization\s*:\s*bearer|"
    r"-----BEGIN [A-Z ]+ PRIVATE KEY-----|\bsk-[A-Za-z0-9]{12,}|"
    r"\bAIza[0-9A-Za-z_-]{20,}\b)",
    re.IGNORECASE,
)
_ACCOUNT_CLAIM_PATTERN = re.compile(
    r"\b(?:your\s+(?:account|order|payment|subscription)\s+"
    r"(?:is|was|has|shows)|order\s*#\s*[A-Za-z0-9-]+|"
    r"account\s+(?:balance|status|details)\s+(?:is|was|shows))\b",
    re.IGNORECASE,
)
_SOURCE_CITATION_PATTERN = re.compile(
    r"\[(?:source|SOURCE)\s+(\d+)\]",
)


class AgentWorkflowService:
    """Execute the single support workflow used by widget and conversations."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    def __init__(
        self,
        *,
        rag_service: RAGService | None = None,
        ai_service_factory: AIServiceFactory | None = None,
        persistence: WorkflowPersistence | None = None,
    ):
        resolved_rag_service = rag_service or RAGService()
        self.rag_service = resolved_rag_service
        self.ai_service_factory = (
            ai_service_factory
            or getattr(
                resolved_rag_service,
                "ai_service_factory",
                AIService.from_configuration,
            )
        )
        self.persistence = persistence

    def bind_persistence(self, persistence: WorkflowPersistence) -> None:
        """Bind the ConversationService-owned response persistence boundary."""
        self.persistence = persistence

    @staticmethod
    def priority_for_urgency(urgency: str) -> TicketPriority:
        priority_by_urgency = {
            "low": TicketPriority.LOW,
            "normal": TicketPriority.NORMAL,
            "high": TicketPriority.HIGH,
            "urgent": TicketPriority.URGENT,
        }
        try:
            return priority_by_urgency[urgency]
        except KeyError as exc:
            raise AgentWorkflowError(
                "The classification urgency was invalid."
            ) from exc

    async def run(
        self,
        db: Session,
        *,
        ticket_id: str,
        user_message: str,
        session_id: str | None = None,
    ) -> AgentWorkflowResult:
        ticket = TicketService.get(db, ticket_id)
        if session_id is not None and ticket.session_id != session_id:
            raise AgentWorkflowError("Conversation session validation failed.")

        started_at = datetime.now(timezone.utc)
        started_perf = time.perf_counter()
        run = AgentRun(
            ticket_id=ticket.id,
            trace_id=str(uuid.uuid4()),
            status=self.RUNNING,
            started_at=started_at,
        )
        db.add(run)
        try:
            db.commit()
            db.refresh(run)
        except SQLAlchemyError as exc:
            db.rollback()
            raise AgentWorkflowError(
                "The agent workflow could not be started."
            ) from exc

        execution = _GraphExecution(
            service=self,
            db=db,
            run=run,
        )
        try:
            execution.set_provider_model_from_configuration()
            run.provider = execution.provider
            run.model = execution.model
            db.commit()
            graph = execution.build()
            final_state = await graph.ainvoke(
                {
                    "trace_id": run.trace_id,
                    "ticket_id": ticket.id,
                    "session_id": session_id or ticket.session_id,
                    "user_message": user_message,
                    "conversation_context": [],
                    "company_context": {},
                    "classification": None,
                    "retrieved_chunks": [],
                    "answer": None,
                    "insufficient_evidence": False,
                    "requires_human_review": False,
                    "input_rejected": False,
                    "classifier_failed": False,
                    "persisted": False,
                    "error": None,
                }
            )
        except Exception as exc:
            message = self._safe_failure_message(exc)
            self._fail_run(
                db,
                run_id=run.id,
                message=message,
                started_perf=started_perf,
                ticket_id=ticket.id,
            )
            raise AgentWorkflowError(message) from exc

        answer = final_state.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            message = "The workflow did not produce a safe response."
            self._fail_run(
                db,
                run_id=run.id,
                message=message,
                started_perf=started_perf,
                ticket_id=ticket.id,
            )
            raise AgentWorkflowError(message)

        try:
            self._finish_run(
                db,
                run_id=run.id,
                provider=execution.provider,
                model=execution.model,
                started_perf=started_perf,
            )
        except AgentWorkflowError as exc:
            self._fail_run(
                db,
                run_id=run.id,
                message=exc.user_message,
                started_perf=started_perf,
                ticket_id=ticket.id,
            )
            raise

        return AgentWorkflowResult(
            trace_id=run.trace_id,
            answer=answer,
            insufficient_evidence=bool(
                final_state.get("insufficient_evidence", False)
            ),
            requires_human_review=bool(
                final_state.get("requires_human_review", False)
            ),
            classification=final_state.get("classification"),
            retrieved_chunks=list(final_state.get("retrieved_chunks", [])),
        )

    def _finish_run(
        self,
        db: Session,
        *,
        run_id: str,
        provider: str | None,
        model: str | None,
        started_perf: float,
    ) -> None:
        run = db.get(AgentRun, run_id)
        if run is None:
            raise AgentWorkflowError("The agent workflow trace disappeared.")

        run.status = self.COMPLETED
        run.provider = provider or run.provider
        run.model = model or run.model
        run.finished_at = datetime.now(timezone.utc)
        run.latency_ms = max(
            0,
            round((time.perf_counter() - started_perf) * 1000),
        )
        run.error = None
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise AgentWorkflowError(
                "The agent workflow trace could not be completed."
            ) from exc

    def _fail_run(
        self,
        db: Session,
        *,
        run_id: str,
        message: str,
        started_perf: float,
        ticket_id: str,
    ) -> None:
        try:
            db.rollback()
            run = db.get(AgentRun, run_id)
            if run is not None:
                run.status = self.FAILED
                run.finished_at = datetime.now(timezone.utc)
                run.latency_ms = max(
                    0,
                    round((time.perf_counter() - started_perf) * 1000),
                )
                run.error = message
                db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "Unable to record failed agent workflow run_id=%s",
                run_id,
            )

        try:
            ticket = TicketService.get(db, ticket_id)
            if ticket.status == "ai_processing":
                TicketService.update_status(
                    db,
                    ticket.id,
                    "human_review",
                )
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "Unable to move failed agent workflow to human review "
                "ticket_id=%s",
                ticket_id,
            )

    @staticmethod
    def _safe_failure_message(exc: Exception) -> str:
        if isinstance(exc, AgentWorkflowError):
            return exc.user_message

        if isinstance(exc, RAGError):
            return exc.user_message

        if isinstance(exc, LLMError):
            return exc.user_message

        logger.exception(
            "Agent workflow failed exception_type=%s",
            type(exc).__name__,
        )
        return "The support response could not be generated safely."
