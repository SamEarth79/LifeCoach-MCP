from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app import main


def test_health_returns_200_and_healthy_payload_when_db_is_reachable(monkeypatch):
    monkeypatch.setattr(main, "check_connectivity", AsyncMock(return_value=True))
    client = TestClient(main.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "reachable"}


def test_health_returns_503_and_unhealthy_payload_when_db_is_unreachable(monkeypatch):
    monkeypatch.setattr(main, "check_connectivity", AsyncMock(return_value=False))
    client = TestClient(main.app)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "database": "unreachable"}


def test_health_requires_no_authentication(monkeypatch):
    monkeypatch.setattr(main, "check_connectivity", AsyncMock(return_value=True))
    client = TestClient(main.app)

    response = client.get("/health")

    assert "WWW-Authenticate" not in response.headers
    assert response.status_code == 200
