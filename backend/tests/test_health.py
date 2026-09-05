from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok",
        "service": "agentdesk-backend",
    }

    assert "X-Request-ID" in response.headers


def test_health_preserves_request_id():
    request_id = "test-request-123"

    response = client.get(
        "/api/health",
        headers={"X-Request-ID": request_id},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id