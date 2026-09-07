import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401

from app.core.tickets import TicketStatus
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.ticket import Ticket
from app.rag.errors import RAGGenerationError
from app.rag.schemas import RAGResponse
from app.schemas.widget import WidgetConfigUpdate
from app.services.conversation_service import ConversationService
from app.services.widget_service import WidgetService
from app.api.routes import widget as widget_route


ALLOWED_ORIGIN = "http://localhost:3002"
OTHER_PROJECT = "other-project"


class FakeRAGService:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.calls: list[dict[str, str | None]] = []

    async def answer(
        self,
        db: Session,
        question: str,
        *,
        ticket_id: str | None = None,
    ) -> RAGResponse:
        del db
        self.calls.append(
            {
                "question": question,
                "ticket_id": ticket_id,
            }
        )
        if self.error is not None:
            raise self.error

        return RAGResponse(
            answer="Refund requests can be made within 30 calendar days.",
            sources=[],
            retrieved_chunks=[],
            insufficient_evidence=False,
            latency_ms=5,
            trace_id=f"widget-test-{uuid.uuid4()}",
        )


@pytest.fixture()
def widget_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fake_rag = FakeRAGService()
    conversation_service = ConversationService(rag_service=fake_rag)
    service = WidgetService(conversation_service=conversation_service)

    previous_db_override = app.dependency_overrides.get(get_db)
    previous_widget_service = widget_route.widget_service

    def override_get_db():
        yield db

    with Session(engine) as db:
        app.dependency_overrides[get_db] = override_get_db
        widget_route.widget_service = service
        try:
            yield db, service, fake_rag
        finally:
            widget_route.widget_service = previous_widget_service
            if previous_db_override is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous_db_override

    Base.metadata.drop_all(engine)
    engine.dispose()


def configure_widget(
    service: WidgetService,
    db: Session,
    *,
    project_id: str = "local-default",
    enabled: bool = True,
    allowed_domains: list[str] | None = None,
):
    return service.update(
        db,
        WidgetConfigUpdate(
            project_id=project_id,
            display_name="AgentDesk Support",
            welcome_message="Hi! How can we help?",
            position="bottom-right",
            enabled=enabled,
            allowed_domains=allowed_domains or [ALLOWED_ORIGIN],
        ),
    )


def test_widget_config_is_persisted_and_public_response_is_redacted(
    widget_session,
):
    db, service, _ = widget_session
    configure_widget(
        service,
        db,
        allowed_domains=["HTTP://LOCALHOST:3002/"],
    )

    with TestClient(app) as client:
        admin_response = client.get("/api/settings/widget")
        public_response = client.get(
            "/api/widget/config/local-default",
            headers={"Origin": ALLOWED_ORIGIN},
        )

    assert admin_response.status_code == 200
    assert admin_response.json()["allowed_domains"] == [ALLOWED_ORIGIN]
    assert public_response.status_code == 200
    assert set(public_response.json()) == {
        "project_id",
        "display_name",
        "welcome_message",
        "position",
        "enabled",
    }
    assert "allowed_domains" not in public_response.json()
    assert "encrypted_api_key" not in public_response.text
    assert "GEMINI_API_KEY" not in public_response.text


def test_widget_origin_policy_is_exact_and_normalizes_default_ports(
    widget_session,
):
    db, service, _ = widget_session
    configure_widget(
        service,
        db,
        allowed_domains=["https://Example.com:443/"],
    )

    with TestClient(app) as client:
        allowed = client.get(
            "/api/widget/config/local-default",
            headers={"Origin": "https://example.com"},
        )
        suffix_attack = client.get(
            "/api/widget/config/local-default",
            headers={"Origin": "https://evil-example.com"},
        )
        missing_origin = client.get("/api/widget/config/local-default")
        malformed_config = client.put(
            "/api/settings/widget",
            json={
                "project_id": "local-default",
                "display_name": "AgentDesk Support",
                "welcome_message": "Hi!",
                "position": "bottom-right",
                "enabled": True,
                "allowed_domains": ["example.com"],
            },
        )
        malformed_origin = client.get(
            "/api/widget/config/local-default",
            headers={"Origin": "http://example.com:"},
        )

    assert allowed.status_code == 200
    assert suffix_attack.status_code == 403
    assert missing_origin.status_code == 403
    assert malformed_config.status_code == 422
    assert malformed_origin.status_code == 403


def test_widget_cors_preflight_and_actual_response_are_narrowly_scoped(
    widget_session,
):
    db, service, _ = widget_session
    configure_widget(service, db)

    with TestClient(app) as client:
        preflight = client.options(
            "/api/widget/sessions?project_id=local-default",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        allowed = client.get(
            "/api/widget/config/local-default",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        denied = client.get(
            "/api/widget/config/local-default",
            headers={"Origin": "https://evil.example"},
        )

    assert preflight.status_code == 204
    assert preflight.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert allowed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert denied.status_code == 403
    assert denied.headers["access-control-allow-origin"] == "https://evil.example"


def test_widget_session_is_anonymous_persistent_and_project_scoped(
    widget_session,
):
    db, service, fake_rag = widget_session
    configure_widget(service, db)
    configure_widget(
        service,
        db,
        project_id=OTHER_PROJECT,
    )

    with TestClient(app) as client:
        created = client.post(
            "/api/widget/sessions?project_id=local-default",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        session_id = created.json()["session_id"]
        message = client.post(
            f"/api/widget/sessions/{session_id}/messages?project_id=local-default",
            headers={"Origin": ALLOWED_ORIGIN},
            json={"content": "How long do refunds take?"},
        )
        reloaded = client.get(
            f"/api/widget/sessions/{session_id}?project_id=local-default",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        wrong_project = client.get(
            f"/api/widget/sessions/{session_id}?project_id={OTHER_PROJECT}",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        trusted_identity = client.post(
            "/api/widget/sessions?project_id=local-default",
            headers={"Origin": ALLOWED_ORIGIN},
            json={"user_id": "admin"},
        )

    assert created.status_code == 201
    assert uuid.UUID(session_id)
    assert created.json()["messages"] == []
    assert "ticket_id" not in created.json()
    assert message.status_code == 200
    assert reloaded.status_code == 200
    assert [item["sequence_number"] for item in reloaded.json()["messages"]] == [
        1,
        2,
    ]
    assert reloaded.json()["messages"][0]["sender_type"] == "customer"
    assert reloaded.json()["messages"][1]["sender_type"] == "ai"
    assert wrong_project.status_code == 404
    assert trusted_identity.status_code == 422
    assert fake_rag.calls[0]["ticket_id"] is not None

    ticket = db.scalar(select(Ticket).where(Ticket.session_id == session_id))
    assert ticket is not None
    assert ticket.customer_id is None
    assert ticket.widget_project_id == "local-default"
    assert ticket.status == TicketStatus.WAITING_CUSTOMER.value


def test_disabled_widget_rejects_new_sessions_and_loader_is_safe(
    widget_session,
):
    db, service, _ = widget_session
    configure_widget(service, db, enabled=False)

    with TestClient(app) as client:
        public_config = client.get(
            "/api/widget/config/local-default",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        session = client.post(
            "/api/widget/sessions?project_id=local-default",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        loader = client.get("/widget.js")

    assert public_config.status_code == 200
    assert public_config.json()["enabled"] is False
    assert session.status_code == 403
    assert loader.status_code == 200
    assert loader.headers["content-type"].startswith("application/javascript")
    assert "GEMINI_API_KEY" not in loader.text
    assert "encrypted_api_key" not in loader.text


def test_widget_failure_preserves_customer_message_and_returns_safe_error(
    widget_session,
):
    db, _, _ = widget_session
    failing_rag = FakeRAGService(
        error=RAGGenerationError("The provider returned a temporary error.")
    )
    service = WidgetService(
        conversation_service=ConversationService(rag_service=failing_rag)
    )
    configure_widget(service, db)
    widget_route.widget_service = service

    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/widget/sessions?project_id=local-default",
                headers={"Origin": ALLOWED_ORIGIN},
            )
            session_id = created.json()["session_id"]
            failed = client.post(
                f"/api/widget/sessions/{session_id}/messages?project_id=local-default",
                headers={"Origin": ALLOWED_ORIGIN},
                json={"content": "Please help."},
            )
            history = client.get(
                f"/api/widget/sessions/{session_id}?project_id=local-default",
                headers={"Origin": ALLOWED_ORIGIN},
            )
    finally:
        widget_route.widget_service = service

    assert failed.status_code == 503
    assert failed.json()["detail"] == (
        "We could not complete your message. A support teammate will review it."
    )
    assert "provider" not in failed.json()["detail"].lower()
    assert history.json()["status"] == TicketStatus.HUMAN_REVIEW.value
    assert len(history.json()["messages"]) == 1
    assert history.json()["messages"][0]["sender_type"] == "customer"


def test_widget_message_validation_is_bounded(widget_session):
    db, service, _ = widget_session
    configure_widget(service, db)

    with TestClient(app) as client:
        created = client.post(
            "/api/widget/sessions?project_id=local-default",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        session_id = created.json()["session_id"]
        empty = client.post(
            f"/api/widget/sessions/{session_id}/messages?project_id=local-default",
            headers={"Origin": ALLOWED_ORIGIN},
            json={"content": "   "},
        )
        oversized = client.post(
            f"/api/widget/sessions/{session_id}/messages?project_id=local-default",
            headers={"Origin": ALLOWED_ORIGIN},
            json={"content": "x" * 10_001},
        )

    assert empty.status_code == 422
    assert oversized.status_code == 422


def test_dashboard_reports_widget_as_configured_only_when_enabled_and_allowed(
    widget_session,
):
    db, service, _ = widget_session
    configure_widget(service, db)

    with TestClient(app) as client:
        response = client.get("/api/dashboard/overview")

    assert response.status_code == 200
    assert response.json()["widget"] == {"configured": True}
