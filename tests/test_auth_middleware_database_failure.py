import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth import middleware as auth_middleware


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(auth_middleware.AuthMiddleware)

    @app.get("/v1/protected")
    async def protected():
        return {"ok": True}

    return TestClient(app)


def test_auth_returns_service_unavailable_when_key_store_fails(client, monkeypatch):
    async def fail_list_keys(limit: int):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(auth_middleware.key_repository, "list_keys", fail_list_keys)

    response = client.get(
        "/v1/protected",
        headers={"Authorization": "Bearer aip_live_example"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "authentication_backend_unavailable"
    assert response.json()["error"]["retryable"] is True


def test_auth_returns_unauthorized_when_key_store_has_no_matching_key(client, monkeypatch):
    async def list_no_keys(limit: int):
        return []

    monkeypatch.setattr(auth_middleware.key_repository, "list_keys", list_no_keys)

    response = client.get(
        "/v1/protected",
        headers={"Authorization": "Bearer aip_live_example"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"
