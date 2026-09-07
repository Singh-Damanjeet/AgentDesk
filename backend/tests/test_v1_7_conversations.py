import asyncio
from datetime import datetime, timezone
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401

from app.api.routes import conversations as conversations_route
from app.api.routes import tickets as tickets_route
from app.core.tickets import MessageSenderType, TicketStatus
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.message import Message
from app.models.ticket import Ticket
from app.rag.errors import RAGGenerationError
from app.rag.schemas import RAGResponse
from app.services.conversation_service import (
    ConversationBusyError,
    ConversationGenerationError,
    ConversationService,
)
from app.services.dashboard_service import DashboardService
from app.services.ticket_service import (
    InvalidTicketStatusTransitionError,
    TicketService,
)
from app.schemas.tickets import ConversationCustomerInput


def run(coroutine):
    return asyncio.run(coroutine)


class FakeRAGService:
    def __init__(
        self,
        *,
        insufficient_evidence: bool = False,
        error: Exception | None = None,
        write_trace: bool = False,
    ):
        self.insufficient_evidence = insufficient_evidence
        self.error = error
        self.write_trace = write_trace
        self.calls: list[dict[str, str | None]] = []

    async def answer(
        self,
        db: Session,
        question: str,
        *,
        ticket_id: str | None = None,
    ) -> RAGResponse:
        self.calls.append(
            {
                "question": question,
                "ticket_id": ticket_id,
            }
        )

        if self.error is not None:
            raise self.error

        trace_id = f"test-trace-{len(self.calls)}-{uuid.uuid4()}"
        if self.write_trace:
            run_record = AgentRun(
                ticket_id=ticket_id,
                trace_id=trace_id,
                status="completed",
                provider="gemini",
                model="gemini-3.6-flash",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                latency_ms=12,
            )
            db.add(run_record)
            db.commit()
            db.refresh(run_record)
            db.add(
                AgentStep(
                    agent_run_id=run_record.id,
                    step_type="retrieval",
                    input_summary="test input",
                    output_summary="test output",
                    step_metadata={
                        "reason": "relevance_threshold",
                        "candidates": [{"chunk_id": "chunk-1"}],
                        "selected_chunk_ids": ["chunk-1"],
                    },
                    duration_ms=4,
                )
            )
            db.commit()

        return RAGResponse(
            answer=(
                "I do not have enough information to answer that."
                if self.insufficient_evidence
                else "The grounded answer is available."
            ),
            sources=[],
            retrieved_chunks=[],
            insufficient_evidence=self.insufficient_evidence,
            latency_ms=12,
            trace_id=trace_id,
        )


@pytest.fixture()
def conversation_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fake_rag = FakeRAGService(write_trace=True)
    service = ConversationService(rag_service=fake_rag)

    try:
        with Session(engine) as db:
            yield db, service, fake_rag
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_conversation(
    db: Session,
    service: ConversationService,
    *,
    customer: ConversationCustomerInput | None = None,
):
    return service.create_or_reuse_ticket(
        db,
        session_id=None,
        channel="web",
        customer=customer,
    )


def test_create_reuse_and_list_support_anonymous_and_known_customers(
    conversation_session,
):
    db, service, _ = conversation_session

    anonymous = create_conversation(db, service)
    reused = service.create_or_reuse_ticket(
        db,
        session_id=anonymous.session_id,
        channel="email",
    )
    known = create_conversation(
        db,
        service,
        customer=ConversationCustomerInput(
            name="Jane Doe",
            email="jane@example.com",
        ),
    )

    assert anonymous.customer is None
    assert reused.id == anonymous.id
    assert reused.channel == "web"
    assert known.customer is not None
    assert known.customer.name == "Jane Doe"

    listing = TicketService.list_tickets(db, limit=1)
    assert listing.total == 2
    assert len(listing.items) == 1
    assert listing.limit == 1


def test_customer_and_ai_messages_are_ordered_and_trace_is_linked(
    conversation_session,
):
    db, service, fake_rag = conversation_session
    conversation = create_conversation(db, service)

    first = run(
        service.append_customer_message(
            db,
            session_id=conversation.session_id,
            content="How long do refunds take?",
        )
    )
    second = run(
        service.append_customer_message(
            db,
            session_id=conversation.session_id,
            content="Does that include weekends?",
        )
    )

    assert first.status == TicketStatus.WAITING_CUSTOMER
    assert second.status == TicketStatus.WAITING_CUSTOMER
    assert [message.sequence_number for message in second.messages] == [
        1,
        2,
        3,
        4,
    ]
    assert [message.sender_type for message in second.messages] == [
        MessageSenderType.CUSTOMER,
        MessageSenderType.AI,
        MessageSenderType.CUSTOMER,
        MessageSenderType.AI,
    ]
    assert fake_rag.calls[0]["ticket_id"] == conversation.id
    assert len(second.agent_runs) == 2
    assert second.agent_runs[0].retrieval is not None
    assert second.agent_runs[0].retrieval.selected_count == 1

    stored_messages = db.scalars(
        select(Message)
        .where(Message.ticket_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    ).all()
    assert [message.sequence_number for message in stored_messages] == [
        1,
        2,
        3,
        4,
    ]


def test_concurrent_customer_messages_are_serialized_without_duplicates(
    conversation_session,
):
    db, _, _ = conversation_session

    class YieldingRAGService(FakeRAGService):
        async def answer(
            self,
            db: Session,
            question: str,
            *,
            ticket_id: str | None = None,
        ) -> RAGResponse:
            await asyncio.sleep(0)
            return await super().answer(
                db,
                question,
                ticket_id=ticket_id,
            )

    service = ConversationService(rag_service=YieldingRAGService())
    conversation = create_conversation(db, service)

    async def send_messages():
        return await asyncio.gather(
            service.append_customer_message(
                db,
                session_id=conversation.session_id,
                content="First question",
            ),
            service.append_customer_message(
                db,
                session_id=conversation.session_id,
                content="Second question",
            ),
            return_exceptions=True,
        )

    results = run(send_messages())

    assert (
        sum(
            isinstance(result, ConversationBusyError)
            for result in results
        )
        == 1
    )
    detail = service.get_conversation(db, conversation.session_id)
    assert [message.sequence_number for message in detail.messages] == [1, 2]
    assert detail.messages[0].sender_type == MessageSenderType.CUSTOMER
    assert detail.messages[0].content == "First question"
    assert detail.messages[1].sender_type == MessageSenderType.AI


def test_insufficient_evidence_is_saved_and_moves_ticket_to_human_review(
    conversation_session,
):
    db, _, _ = conversation_session
    fake_rag = FakeRAGService(insufficient_evidence=True)
    service = ConversationService(rag_service=fake_rag)
    conversation = create_conversation(db, service)

    result = run(
        service.append_customer_message(
            db,
            session_id=conversation.session_id,
            content="Does the company provide free laptops?",
        )
    )

    assert result.status == TicketStatus.HUMAN_REVIEW
    assert [message.sender_type for message in result.messages] == [
        MessageSenderType.CUSTOMER,
        MessageSenderType.AI,
    ]
    assert result.messages[-1].content.startswith(
        "I do not have enough information"
    )


def test_ai_failure_keeps_customer_message_and_does_not_leave_processing(
    conversation_session,
):
    db, _, _ = conversation_session
    fake_rag = FakeRAGService(
        error=RAGGenerationError("The Gemini API is temporarily unavailable.")
    )
    service = ConversationService(rag_service=fake_rag)
    conversation = create_conversation(db, service)

    with pytest.raises(ConversationGenerationError) as error:
        run(
            service.append_customer_message(
                db,
                session_id=conversation.session_id,
                content="Please help me with my order.",
            )
        )

    detail = service.get_conversation(db, conversation.session_id)
    assert error.value.user_message == (
        "The Gemini API is temporarily unavailable."
    )
    assert detail.status == TicketStatus.HUMAN_REVIEW
    assert len(detail.messages) == 1
    assert detail.messages[0].sender_type == MessageSenderType.CUSTOMER


def test_status_transition_policy_is_explicit_and_reopen_is_supported(
    conversation_session,
):
    db, _, _ = conversation_session
    ticket = TicketService.create(db, channel="web")

    with pytest.raises(InvalidTicketStatusTransitionError):
        TicketService.update_status(db, ticket.id, TicketStatus.CLOSED)

    TicketService.update_status(db, ticket.id, TicketStatus.AI_PROCESSING)
    TicketService.update_status(db, ticket.id, TicketStatus.WAITING_CUSTOMER)
    TicketService.resolve(db, ticket.id)
    TicketService.close(db, ticket.id)
    TicketService.reopen(db, ticket.id)

    assert TicketService.get(db, ticket.id).status == TicketStatus.OPEN


def test_dashboard_counts_all_active_ticket_states(conversation_session):
    db, _, _ = conversation_session
    active_tickets = [
        TicketService.create(db, channel="web")
        for _ in range(4)
    ]
    TicketService.update_status(
        db,
        active_tickets[1].id,
        TicketStatus.AI_PROCESSING,
    )
    TicketService.update_status(
        db,
        active_tickets[2].id,
        TicketStatus.HUMAN_REVIEW,
    )
    TicketService.update_status(
        db,
        active_tickets[3].id,
        TicketStatus.RESOLVED,
    )

    assert DashboardService.get_overview(db).tickets.open_count == 3


def test_ticket_and_conversation_routes_are_bounded_and_backend_authoritative(
    conversation_session,
):
    db, service, _ = conversation_session
    previous_db_override = app.dependency_overrides.get(get_db)
    previous_conversation_route_service = conversations_route.conversation_service
    previous_ticket_route_service = tickets_route.conversation_service

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    conversations_route.conversation_service = service
    tickets_route.conversation_service = service

    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/conversations",
                json={"channel": "web"},
            )
            assert created.status_code == 201
            session_id = created.json()["session_id"]
            ticket_id = created.json()["id"]

            listed = client.get("/api/tickets?limit=1&offset=0")
            assert listed.status_code == 200
            assert listed.json()["total"] == 1
            assert len(listed.json()["items"]) == 1

            updated = client.patch(
                f"/api/tickets/{ticket_id}/status",
                json={"status": "human_review"},
            )
            assert updated.status_code == 200
            assert updated.json()["status"] == "human_review"

            invalid = client.patch(
                f"/api/tickets/{ticket_id}/status",
                json={"status": "closed"},
            )
            assert invalid.status_code == 409

            filtered = client.get("/api/tickets?status=human_review")
            assert filtered.status_code == 200
            assert filtered.json()["total"] == 1

            fetched = client.get(f"/api/conversations/{session_id}")
            assert fetched.status_code == 200
            assert fetched.json()["id"] == ticket_id
    finally:
        conversations_route.conversation_service = (
            previous_conversation_route_service
        )
        tickets_route.conversation_service = previous_ticket_route_service
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override
