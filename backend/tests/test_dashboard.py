from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.knowledge_document import KnowledgeDocument
from app.models.ticket import Ticket
from app.services.dashboard_service import DashboardService, DashboardServiceError


def create_dashboard_client():
    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as session:
            yield session

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db

    return engine, previous_override


def close_dashboard_client(engine, previous_override):
    if previous_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_override

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_dashboard_overview_reports_real_unconfigured_state():
    engine, previous_override = create_dashboard_client()

    try:
        with TestClient(app) as client:
            company_response = client.get("/api/settings/company")
            ai_response = client.get("/api/settings/ai")
            response = client.get("/api/dashboard/overview")

        assert company_response.status_code == 200
        assert company_response.json() is None
        assert ai_response.status_code == 200
        assert ai_response.json() is None
        assert response.status_code == 200
        payload = response.json()

        assert payload["ai_provider"] == {
            "configured": False,
            "provider": None,
            "model": None,
        }
        assert payload["storage"] == {
            "type": "sqlite",
            "status": "ready",
        }
        assert payload["knowledge"] == {"document_count": 0}
        assert payload["tickets"] == {"open_count": 0}
        assert payload["widget"] == {"configured": False}
        assert payload["system"] == {"status": "healthy"}
    finally:
        close_dashboard_client(engine, previous_override)


def test_dashboard_overview_reports_configured_ai_and_open_ticket_count():
    engine, previous_override = create_dashboard_client()

    try:
        with TestClient(app) as client:
            ai_response = client.put(
                "/api/settings/ai",
                json={
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
                    "api_key": "synthetic-gemini-key",
                    "embedding_provider": "local",
                    "embedding_model": None,
                    "enabled": True,
                },
            )

            assert ai_response.status_code == 200

            with Session(engine) as db:
                db.add_all(
                    [
                        Ticket(channel="email", status="open"),
                        Ticket(channel="web", status="closed"),
                        KnowledgeDocument(
                            filename="faq.txt",
                            original_filename="faq.txt",
                            file_type="txt",
                            file_size=10,
                            status="ready",
                        ),
                    ]
                )
                db.commit()

            response = client.get("/api/dashboard/overview")

        assert response.status_code == 200
        payload = response.json()

        assert payload["ai_provider"] == {
            "configured": True,
            "provider": "gemini",
            "model": "gemini-2.5-flash",
        }
        assert payload["tickets"] == {"open_count": 1}
        assert "synthetic-gemini-key" not in response.text
        assert "encrypted_api_key" not in response.text
        assert payload["knowledge"] == {"document_count": 1}
        assert payload["tickets"]["open_count"] >= 0
    finally:
        close_dashboard_client(engine, previous_override)


def test_dashboard_overview_returns_safe_error_when_data_is_unavailable(
    monkeypatch,
):
    engine, previous_override = create_dashboard_client()

    def fail_overview(_db):
        raise DashboardServiceError(
            "Dashboard data is currently unavailable."
        )

    monkeypatch.setattr(
        DashboardService,
        "get_overview",
        fail_overview,
    )

    try:
        with TestClient(app) as client:
            response = client.get("/api/dashboard/overview")

        assert response.status_code == 503
        assert response.json() == {
            "detail": "Dashboard data is currently unavailable."
        }
    finally:
        close_dashboard_client(engine, previous_override)
