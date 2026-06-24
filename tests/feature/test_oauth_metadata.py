import httpx
import pytest
from fastapi.testclient import TestClient

from app import main

SUPABASE_REAL_METADATA = {
    "issuer": "https://example.supabase.co",
    "authorization_endpoint": "https://example.supabase.co/auth/v1/oauth/authorize",
    "token_endpoint": "https://example.supabase.co/auth/v1/oauth/token",
    "jwks_uri": "https://example.supabase.co/auth/v1/.well-known/jwks.json",
    "response_types_supported": ["code"],
    "grant_types_supported": ["authorization_code", "refresh_token"],
    "code_challenge_methods_supported": ["S256", "plain"],
    "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
    "scopes_supported": ["openid", "email", "profile"],
}


class _FakeResponse:
    def __init__(self, json_body: dict, status_code: int = 200):
        self._json_body = json_body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self) -> dict:
        return self._json_body


class _FakeAsyncClient:
    def __init__(self, response=None, raise_exc=None, **_kwargs):
        self._response = response
        self._raise_exc = raise_exc
        self.requested_url = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False

    async def get(self, url, **_kwargs):
        self.requested_url = url
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response


def test_oauth_metadata_proxies_supabase_response_unchanged_not_a_hand_picked_subset(monkeypatch):
    # Real bug this guards against: the route used to hand-copy a subset of
    # fields into a static dict, silently dropping
    # token_endpoint_auth_methods_supported and anything else Supabase
    # actually returns. The response body must be Supabase's real metadata
    # verbatim, not a re-derived/partial dict.
    fake_response = _FakeResponse(SUPABASE_REAL_METADATA)
    monkeypatch.setattr(
        main.httpx, "AsyncClient", lambda **kwargs: _FakeAsyncClient(response=fake_response)
    )
    client = TestClient(main.app)

    response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    assert response.json() == SUPABASE_REAL_METADATA
    assert "token_endpoint_auth_methods_supported" in response.json()
    assert "scopes_supported" in response.json()


def test_oauth_metadata_fetches_from_the_configured_supabase_url(monkeypatch):
    fake_client = _FakeAsyncClient(response=_FakeResponse(SUPABASE_REAL_METADATA))
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake_client)
    client = TestClient(main.app)

    client.get("/.well-known/oauth-authorization-server")

    settings = main.get_settings()
    assert (
        fake_client.requested_url
        == f"{settings.supabase_url}/auth/v1/.well-known/oauth-authorization-server"
    )


def test_oauth_metadata_returns_502_when_supabase_is_unreachable(monkeypatch):
    monkeypatch.setattr(
        main.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(raise_exc=httpx.ConnectError("connection failed")),
    )
    client = TestClient(main.app)

    response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 502
    assert "temporarily unavailable" in response.json()["detail"]


def test_oauth_metadata_returns_502_when_supabase_responds_with_an_error_status(monkeypatch):
    fake_response = _FakeResponse({}, status_code=500)
    monkeypatch.setattr(
        main.httpx, "AsyncClient", lambda **kwargs: _FakeAsyncClient(response=fake_response)
    )
    client = TestClient(main.app)

    response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 502


def test_oauth_metadata_requires_no_authentication(monkeypatch):
    monkeypatch.setattr(
        main.httpx, "AsyncClient", lambda **kwargs: _FakeAsyncClient(response=_FakeResponse(SUPABASE_REAL_METADATA))
    )
    client = TestClient(main.app)

    response = client.get("/.well-known/oauth-authorization-server")

    assert "WWW-Authenticate" not in response.headers
    assert response.status_code == 200
