from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401

from app.db.base import Base
from app.db.session import get_db
from app.main import app


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


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def test_config_status():
    response = client.get(
        "/api/config/status"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["configured"] is False
    assert data["installation_id"]


def test_company_settings_create_and_read():
    response = client.put(
        "/api/settings/company",
        json={
            "name": "AgentDesk Demo",
            "website": "https://example.com",
            "industry": "Software",
            "support_name": "Support Team",
            "default_language": "en",
            "timezone": "UTC",
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "AgentDesk Demo"

    response = client.get(
        "/api/settings/company"
    )

    assert response.status_code == 200
    assert response.json()["name"] == "AgentDesk Demo"


def test_ai_settings_secret_is_not_returned():
    secret = "super-secret-test-key"

    response = client.put(
        "/api/settings/ai",
        json={
            "provider": "test-provider",
            "model": "test-model",
            "api_key": secret,
            "embedding_provider": "local",
            "embedding_model": "test-embedding",
            "enabled": True,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["api_key_configured"] is True
    assert "api_key" not in data
    assert "encrypted_api_key" not in data
    assert secret not in response.text


def test_invalid_company_name_is_rejected():
    response = client.put(
        "/api/settings/company",
        json={
            "name": "",
        },
    )

    assert response.status_code == 422