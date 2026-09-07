from collections import defaultdict
from datetime import datetime, timezone
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.llm.errors import LLMError
from app.core.tickets import (
    MAX_MESSAGE_LENGTH,
    MessageSenderType,
    TicketStatus,
)
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.customer import Customer
from app.models.message import Message
from app.models.ticket import Ticket
from app.rag.errors import RAGError
from app.rag.service import RAGService
from app.schemas.tickets import (
    AgentTraceRetrievalSummary,
    AgentTraceSummary,
    ConversationCustomerInput,
    TicketCustomerResponse,
    TicketDetailResponse,
    TicketMessageResponse,
)
from app.services.ticket_service import (
    TicketConflictError,
    TicketService,
    TicketServiceError,
    TicketValidationError,
)


logger = logging.getLogger(__name__)


class ConversationServiceError(RuntimeError):
    """Base class for safe conversation service errors."""

    def __init__(self, message: str):
        self.user_message = message
        super().__init__(message)


class ConversationBusyError(ConversationServiceError):
    """Raised when a ticket is already processing another customer message."""


class ConversationGenerationError(ConversationServiceError):
    """Raised when a customer message cannot receive an AI response."""


class ConversationService:
    """Persist channel-independent conversations and their RAG responses."""

    def __init__(self, *, rag_service: RAGService | None = None):
        self.rag_service = rag_service or RAGService()

    def create_or_reuse_ticket(
        self,
        db: Session,
        *,
        session_id: str | None,
        channel: str,
        subject: str | None = None,
        customer: ConversationCustomerInput | None = None,
    ) -> TicketDetailResponse:
        if session_id is not None:
            ticket = TicketService.get_by_session(db, session_id)
            return self.to_detail(db, ticket)

        customer_id = self._create_customer(db, customer)
        ticket = TicketService.create(
            db,
            channel=channel,
            customer_id=customer_id,
            subject=subject,
        )
        return self.to_detail(db, ticket)

    def get_conversation(
        self,
        db: Session,
        session_id: str,
    ) -> TicketDetailResponse:
        return self.to_detail(
            db,
            TicketService.get_by_session(db, session_id),
        )

    def get_ticket_detail(
        self,
        db: Session,
        ticket_id: str,
    ) -> TicketDetailResponse:
        return self.to_detail(db, TicketService.get(db, ticket_id))

    def list_messages(
        self,
        db: Session,
        session_id: str,
    ) -> list[TicketMessageResponse]:
        ticket = TicketService.get_by_session(db, session_id)
        return self._message_responses(db, ticket.id)

    async def append_customer_message(
        self,
        db: Session,
        *,
        session_id: str,
        content: str,
    ) -> TicketDetailResponse:
        ticket = TicketService.get_by_session(db, session_id)
        normalized_content = self._normalize_message(content)
        current_status = self._ticket_status(ticket)

        if current_status == TicketStatus.AI_PROCESSING:
            raise ConversationBusyError(
                "This conversation is already processing a message."
            )

        if current_status in {
            TicketStatus.RESOLVED,
            TicketStatus.CLOSED,
        }:
            raise TicketConflictError(
                "Reopen the ticket before sending a new message."
            )

        if current_status == TicketStatus.HUMAN_REVIEW:
            ticket = TicketService.reopen(db, ticket.id)

        self._append_message(
            db,
            ticket=ticket,
            sender_type=MessageSenderType.CUSTOMER,
            content=normalized_content,
        )
        TicketService.update_status(
            db,
            ticket.id,
            TicketStatus.AI_PROCESSING,
        )

        try:
            response = await self.rag_service.answer(
                db,
                normalized_content,
                ticket_id=ticket.id,
            )
        except RAGError as exc:
            self._mark_human_review(db, ticket.id)
            raise ConversationGenerationError(exc.user_message) from exc
        except LLMError as exc:
            self._mark_human_review(db, ticket.id)
            raise ConversationGenerationError(exc.user_message) from exc
        except Exception as exc:
            self._mark_human_review(db, ticket.id)
            logger.exception(
                "Conversation generation failed ticket_id=%s",
                ticket.id,
            )
            raise ConversationGenerationError(
                "The conversation response could not be generated."
            ) from exc

        target_status = (
            TicketStatus.HUMAN_REVIEW
            if response.insufficient_evidence
            else TicketStatus.WAITING_CUSTOMER
        )

        try:
            self._append_message(
                db,
                ticket=TicketService.get(db, ticket.id),
                sender_type=MessageSenderType.AI,
                content=response.answer,
            )
            TicketService.update_status(db, ticket.id, target_status)
        except (TicketServiceError, ConversationServiceError) as exc:
            self._mark_human_review(db, ticket.id)
            raise ConversationGenerationError(
                "The AI response could not be saved safely."
            ) from exc

        return self.get_ticket_detail(db, ticket.id)

    def append_ai_message(
        self,
        db: Session,
        *,
        session_id: str,
        content: str,
    ) -> TicketMessageResponse:
        ticket = TicketService.get_by_session(db, session_id)
        message = self._append_message(
            db,
            ticket=ticket,
            sender_type=MessageSenderType.AI,
            content=self._normalize_message(content),
        )
        return self._message_response(message)

    def to_detail(
        self,
        db: Session,
        ticket: Ticket,
    ) -> TicketDetailResponse:
        customer = (
            db.get(Customer, ticket.customer_id)
            if ticket.customer_id is not None
            else None
        )

        return TicketDetailResponse(
            id=ticket.id,
            session_id=ticket.session_id,
            subject=ticket.subject,
            category=ticket.category,
            status=self._ticket_status(ticket),
            priority=ticket.priority,
            channel=ticket.channel,
            customer=self._customer_response(customer),
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            messages=self._message_responses(db, ticket.id),
            agent_runs=self._trace_responses(db, ticket.id),
        )

    def _append_message(
        self,
        db: Session,
        *,
        ticket: Ticket,
        sender_type: MessageSenderType,
        content: str,
    ) -> Message:
        for attempt in range(3):
            current_ticket = TicketService.get(db, ticket.id)
            next_sequence = (
                db.scalar(
                    select(func.max(Message.sequence_number)).where(
                        Message.ticket_id == current_ticket.id
                    )
                )
                or 0
            ) + 1
            message = Message(
                ticket_id=current_ticket.id,
                sequence_number=next_sequence,
                sender_type=sender_type.value,
                content=content,
                channel=current_ticket.channel,
            )
            if (
                sender_type == MessageSenderType.CUSTOMER
                and not current_ticket.subject
            ):
                current_ticket.subject = content[:500]

            current_ticket.updated_at = datetime.now(timezone.utc)
            db.add(message)

            try:
                db.commit()
                db.refresh(message)
                return message
            except IntegrityError as exc:
                db.rollback()
                if attempt == 2:
                    raise ConversationServiceError(
                        "The message could not be ordered safely."
                    ) from exc
            except SQLAlchemyError as exc:
                db.rollback()
                raise ConversationServiceError(
                    "The message could not be saved."
                ) from exc

        raise ConversationServiceError("The message could not be saved.")

    def _create_customer(
        self,
        db: Session,
        customer: ConversationCustomerInput | None,
    ) -> str | None:
        if customer is None:
            return None

        if not any(
            (
                customer.name,
                customer.email,
                customer.external_customer_id,
            )
        ):
            return None

        model = Customer(
            name=customer.name,
            email=customer.email,
            external_customer_id=customer.external_customer_id,
        )
        db.add(model)
        try:
            db.flush()
        except SQLAlchemyError as exc:
            db.rollback()
            raise ConversationServiceError(
                "The customer could not be created."
            ) from exc

        return model.id

    def _mark_human_review(self, db: Session, ticket_id: str) -> None:
        try:
            ticket = TicketService.get(db, ticket_id)
            if self._ticket_status(ticket) == TicketStatus.AI_PROCESSING:
                TicketService.update_status(
                    db,
                    ticket.id,
                    TicketStatus.HUMAN_REVIEW,
                )
        except TicketServiceError:
            db.rollback()
            logger.exception(
                "Unable to move failed conversation to human review "
                "ticket_id=%s",
                ticket_id,
            )

    def _message_responses(
        self,
        db: Session,
        ticket_id: str,
    ) -> list[TicketMessageResponse]:
        messages = db.scalars(
            select(Message)
            .where(Message.ticket_id == ticket_id)
            .order_by(
                Message.sequence_number.asc(),
                Message.created_at.asc(),
                Message.id.asc(),
            )
        ).all()
        return [self._message_response(message) for message in messages]

    def _trace_responses(
        self,
        db: Session,
        ticket_id: str,
    ) -> list[AgentTraceSummary]:
        runs = db.scalars(
            select(AgentRun)
            .where(AgentRun.ticket_id == ticket_id)
            .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
        ).all()
        if not runs:
            return []

        run_ids = [run.id for run in runs]
        steps = db.scalars(
            select(AgentStep)
            .where(AgentStep.agent_run_id.in_(run_ids))
        ).all()
        steps_by_run: dict[str, list[AgentStep]] = defaultdict(list)
        for step in steps:
            steps_by_run[step.agent_run_id].append(step)

        return [
            self._trace_response(run, steps_by_run.get(run.id, []))
            for run in runs
        ]

    @staticmethod
    def _trace_response(
        run: AgentRun,
        steps: list[AgentStep],
    ) -> AgentTraceSummary:
        retrieval = next(
            (step for step in steps if step.step_type == "retrieval"),
            None,
        )
        retrieval_summary = None
        if retrieval is not None:
            metadata = (
                retrieval.step_metadata
                if isinstance(retrieval.step_metadata, dict)
                else {}
            )
            candidates = metadata.get("candidates")
            selected = metadata.get("selected_chunk_ids")
            retrieval_summary = AgentTraceRetrievalSummary(
                reason=(
                    metadata.get("reason")
                    if isinstance(metadata.get("reason"), str)
                    else None
                ),
                candidate_count=(
                    len(candidates) if isinstance(candidates, list) else 0
                ),
                selected_count=(
                    len(selected) if isinstance(selected, list) else 0
                ),
            )

        return AgentTraceSummary(
            trace_id=run.trace_id,
            status=run.status,
            provider=run.provider,
            model=run.model,
            latency_ms=run.latency_ms,
            error=run.error,
            started_at=run.started_at,
            finished_at=run.finished_at,
            retrieval=retrieval_summary,
        )

    @staticmethod
    def _message_response(message: Message) -> TicketMessageResponse:
        return TicketMessageResponse(
            id=message.id,
            sequence_number=message.sequence_number,
            sender_type=MessageSenderType(message.sender_type),
            content=message.content,
            channel=message.channel,
            created_at=message.created_at,
        )

    @staticmethod
    def _customer_response(
        customer: Customer | None,
    ) -> TicketCustomerResponse | None:
        if customer is None:
            return None

        return TicketCustomerResponse(
            id=customer.id,
            name=customer.name,
            email=customer.email,
            external_customer_id=customer.external_customer_id,
        )

    @staticmethod
    def _ticket_status(ticket: Ticket) -> TicketStatus:
        try:
            return TicketStatus(ticket.status)
        except ValueError as exc:
            raise TicketValidationError(
                "The ticket has an unsupported status."
            ) from exc

    @staticmethod
    def _normalize_message(content: str) -> str:
        if not isinstance(content, str):
            raise TicketValidationError("Message content must be a string.")

        normalized = content.strip()
        if not normalized:
            raise TicketValidationError("Message content must not be empty.")

        if len(normalized) > MAX_MESSAGE_LENGTH:
            raise TicketValidationError(
                "Message content exceeds the maximum supported length."
            )

        return normalized
