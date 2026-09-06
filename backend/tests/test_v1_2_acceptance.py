import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401

from app.core.secrets import decrypt_secret
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.ai_provider import AIProvider
from app.services.config_service import ConfigService


@pytest.fixture()
def setup_client():
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

    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override

        Base.metadata.drop_all(engine)
        engine.dispose()


def company_payload(name: str = "AgentDesk Demo") -> dict[str, str | None]:
    return {
        "name": name,
        "website": "https://example.com",
        "industry": "Software",
        "support_name": "AgentDesk Support",
        "default_language": "en",
        "timezone": "UTC",
    }


def ai_payload(
    api_key: str | None = "synthetic-gemini-key",
) -> dict[str, object]:
    payload = {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "embedding_provider": "local",
        "embedding_model": None,
        "enabled": True,
    }

    if api_key is not None:
        payload["api_key"] = api_key

    return payload


def test_first_config_status_is_unconfigured(setup_client):
    client, _ = setup_client

    response = client.get("/api/config/status")

    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_ai_settings_persist_without_returning_the_key(setup_client):
    client, engine = setup_client
    synthetic_key = "synthetic-gemini-key"

    response = client.put(
        "/api/settings/ai",
        json=ai_payload(synthetic_key),
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "gemini"
    assert response.json()["api_key_configured"] is True
    assert synthetic_key not in response.text
    assert "encrypted_api_key" not in response.text

    with Session(engine) as db:
        provider = db.query(AIProvider).one()

        assert decrypt_secret(provider.encrypted_api_key) == synthetic_key

    response = client.get("/api/settings/ai")

    assert response.status_code == 200
    assert response.json()["api_key_configured"] is True
    assert synthetic_key not in response.text


def test_existing_ai_key_is_preserved_when_field_is_empty(setup_client):
    client, engine = setup_client
    synthetic_key = "synthetic-gemini-key"

    first_response = client.put(
        "/api/settings/ai",
        json=ai_payload(synthetic_key),
    )
    second_response = client.put(
        "/api/settings/ai",
        json=ai_payload(""),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    with Session(engine) as db:
        provider = db.query(AIProvider).one()

        assert decrypt_secret(provider.encrypted_api_key) == synthetic_key


def test_invalid_ai_configuration_is_rejected(setup_client):
    client, _ = setup_client

    unsupported_provider = client.put(
        "/api/settings/ai",
        json={
            **ai_payload(),
            "provider": "openai",
        },
    )
    missing_key = client.put(
        "/api/settings/ai",
        json=ai_payload(None),
    )

    assert unsupported_provider.status_code == 422
    assert missing_key.status_code == 400
    assert missing_key.json()["detail"] == "A Gemini API key is required."


def test_gemini_connection_test_is_server_side_and_redacts_the_key(
    setup_client,
    monkeypatch,
    caplog,
):
    client, _ = setup_client
    synthetic_key = "synthetic-gemini-key"
    observed: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "OK"}],
                        }
                    }
                ]
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            del args

        async def post(self, url, headers, json):
            observed["url"] = url
            observed["headers"] = headers
            observed["json"] = json
            return FakeResponse()

    monkeypatch.setattr(
        "app.services.ai_connection_service.httpx.AsyncClient",
        FakeAsyncClient,
    )
    caplog.set_level(logging.INFO, logger="agentdesk")

    response = client.post(
        "/api/settings/ai/test",
        json={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "api_key": synthetic_key,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Gemini connection successful.",
    }
    assert synthetic_key not in response.text
    assert synthetic_key not in caplog.text
    assert observed["url"] == (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/gemini-2.5-flash:generateContent"
    )
    assert observed["headers"] == {
        "x-goog-api-key": synthetic_key,
        "content-type": "application/json",
    }
    assert observed["json"] == {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": "Reply with exactly OK."}],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 256,
        },
    }


def test_completion_requires_company_and_ai_provider(setup_client):
    client, _ = setup_client

    response = client.post("/api/config/complete")

    assert response.status_code == 400
    assert response.json()["detail"] == "Company configuration is required."

    response = client.put(
        "/api/settings/company",
        json=company_payload(),
    )
    assert response.status_code == 200

    response = client.post("/api/config/complete")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "AI provider configuration is required."
    )


def test_completion_sets_and_persists_configured_state(setup_client):
    client, engine = setup_client

    assert client.put(
        "/api/settings/company",
        json=company_payload(),
    ).status_code == 200
    assert client.put(
        "/api/settings/ai",
        json=ai_payload(),
    ).status_code == 200

    before_completion = client.get("/api/config/status")
    assert before_completion.json()["configured"] is False

    response = client.post("/api/config/complete")

    assert response.status_code == 200
    assert response.json()["configured"] is True

    after_completion = client.get("/api/config/status")
    assert after_completion.json()["configured"] is True

    with Session(engine) as reopened_session:
        config = ConfigService.get_status(reopened_session)
        assert config.configured is True
