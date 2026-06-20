import importlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.auth import CurrentUser, get_current_user
from app.config import get_settings

USER_ID = "11111111-1111-1111-1111-111111111111"
EMAIL = "user@example.com"
CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
UPDATED_AT = datetime(2026, 1, 2, tzinfo=timezone.utc)
ROW = (USER_ID, EMAIL, "Test User", CREATED_AT, UPDATED_AT)


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    async def execute(self, *_args, **_kwargs):
        return None

    async def fetchone(self):
        return self._row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class _FakeConnection:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return _FakeCursor(self._row)


def _override_current_user():
    async def _fake_dependency():
        return CurrentUser(id=USER_ID, email=EMAIL)

    return _fake_dependency


def _reload_main_with_real_settings():
    """
    Restores app.main to a module state built from the real environment
    (the same .env-backed Settings every other test file expects), since
    app.main is a process-wide singleton module and tests that reload it
    with overridden env vars must put it back exactly as they found it.
    """
    get_settings.cache_clear()
    return importlib.reload(main_module)


@pytest.fixture
def low_limit_app(monkeypatch):
    """
    Reloads app.main with a low, deterministic rate limit so tests don't
    need to burn through the real default of 30 requests/60s, and so the
    limit module/decorator picks up the overridden Settings at import time.
    """
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    reloaded_main = importlib.reload(main_module)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_get_connection():
        yield _FakeConnection(ROW)

    monkeypatch.setattr(reloaded_main, "get_connection", fake_get_connection)
    reloaded_main.app.dependency_overrides[get_current_user] = _override_current_user()

    try:
        yield reloaded_main
    finally:
        reloaded_main.app.dependency_overrides.clear()
        reloaded_main.limiter.reset()
        monkeypatch.undo()
        _reload_main_with_real_settings()


def test_users_me_allows_requests_within_the_configured_limit(low_limit_app):
    client = TestClient(low_limit_app.app)
    headers = {"Authorization": "Bearer irrelevant"}

    first = client.get("/users/me", headers=headers)
    second = client.get("/users/me", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200


def test_users_me_rejects_request_exceeding_the_configured_limit(low_limit_app):
    client = TestClient(low_limit_app.app)
    headers = {"Authorization": "Bearer irrelevant"}

    client.get("/users/me", headers=headers)
    client.get("/users/me", headers=headers)
    third = client.get("/users/me", headers=headers)

    assert third.status_code == 429


def test_users_me_rate_limit_rejection_is_a_clean_429_not_a_server_error(low_limit_app):
    client = TestClient(low_limit_app.app)
    headers = {"Authorization": "Bearer irrelevant"}

    client.get("/users/me", headers=headers)
    client.get("/users/me", headers=headers)
    third = client.get("/users/me", headers=headers)

    assert third.status_code == 429
    assert third.status_code != 500
    body = third.json()
    assert "error" in body or "detail" in body


def test_users_me_rate_limit_threshold_is_driven_by_settings_not_hardcoded(monkeypatch):
    """
    AC3: changing RATE_LIMIT_REQUESTS changes enforced behavior. A 1/60s
    limit should reject the second request, proving the threshold flows
    from Settings into the limiter rather than being a fixed magic number.
    """
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    reloaded_main = importlib.reload(main_module)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_get_connection():
        yield _FakeConnection(ROW)

    monkeypatch.setattr(reloaded_main, "get_connection", fake_get_connection)
    reloaded_main.app.dependency_overrides[get_current_user] = _override_current_user()

    try:
        client = TestClient(reloaded_main.app)
        headers = {"Authorization": "Bearer irrelevant"}

        first = client.get("/users/me", headers=headers)
        second = client.get("/users/me", headers=headers)

        assert first.status_code == 200
        assert second.status_code == 429
    finally:
        reloaded_main.app.dependency_overrides.clear()
        reloaded_main.limiter.reset()
        monkeypatch.undo()
        _reload_main_with_real_settings()


def test_health_endpoint_is_never_rate_limited(low_limit_app):
    """
    AC4 (architectural requirement): /health must stay unlimited even when
    /users/me's limit is set very low, and must require no authentication.
    """
    client = TestClient(low_limit_app.app)

    responses = [client.get("/health") for _ in range(10)]

    assert all(response.status_code in (200, 503) for response in responses)
    assert all(response.status_code != 429 for response in responses)
    assert all("WWW-Authenticate" not in response.headers for response in responses)
