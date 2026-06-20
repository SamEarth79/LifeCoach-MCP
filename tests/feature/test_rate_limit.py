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

    async def fetchall(self):
        return [self._row] if self._row is not None else []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class _FakeConnection:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return _FakeCursor(self._row)

    async def commit(self):
        return None


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
    async def fake_get_rls_connection(_user_id):
        yield _FakeConnection(ROW)

    monkeypatch.setattr(reloaded_main, "get_rls_connection", fake_get_rls_connection)
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
    async def fake_get_rls_connection(_user_id):
        yield _FakeConnection(ROW)

    monkeypatch.setattr(reloaded_main, "get_rls_connection", fake_get_rls_connection)
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


def test_create_goal_allows_requests_within_the_configured_limit(low_limit_app):
    client = TestClient(low_limit_app.app)
    headers = {"Authorization": "Bearer irrelevant"}
    body = {"title": "Run a marathon"}

    first = client.post("/goals", json=body, headers=headers)
    second = client.post("/goals", json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201


def test_create_goal_rejects_request_exceeding_the_configured_limit(low_limit_app):
    client = TestClient(low_limit_app.app)
    headers = {"Authorization": "Bearer irrelevant"}
    body = {"title": "Run a marathon"}

    client.post("/goals", json=body, headers=headers)
    client.post("/goals", json=body, headers=headers)
    third = client.post("/goals", json=body, headers=headers)

    assert third.status_code == 429


def test_create_goal_and_users_me_enforce_the_same_configured_threshold(low_limit_app):
    """
    AC5: POST /goals is subject to the existing rate limiter, the same as
    /users/me — both routes use the shared `enforce_rate_limit` dependency
    and the same `per_ip_rate_limit` string derived from Settings, so both
    independently reject a client's 3rd request under the same RATE_LIMIT_*
    configuration (slowapi tracks each decorated route as its own bucket,
    so this asserts equivalent enforcement per route rather than a single
    shared counter across routes).
    """
    client = TestClient(low_limit_app.app)
    headers = {"Authorization": "Bearer irrelevant"}

    client.get("/users/me", headers=headers)
    client.get("/users/me", headers=headers)
    users_me_third = client.get("/users/me", headers=headers)

    body = {"title": "Run a marathon"}
    client.post("/goals", json=body, headers=headers)
    client.post("/goals", json=body, headers=headers)
    goals_third = client.post("/goals", json=body, headers=headers)

    assert users_me_third.status_code == 429
    assert goals_third.status_code == 429


def test_list_goals_allows_requests_within_the_configured_limit(low_limit_app):
    client = TestClient(low_limit_app.app)
    headers = {"Authorization": "Bearer irrelevant"}

    first = client.get("/goals", headers=headers)
    second = client.get("/goals", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200


def test_list_goals_rejects_request_exceeding_the_configured_limit(low_limit_app):
    client = TestClient(low_limit_app.app)
    headers = {"Authorization": "Bearer irrelevant"}

    client.get("/goals", headers=headers)
    client.get("/goals", headers=headers)
    third = client.get("/goals", headers=headers)

    assert third.status_code == 429


def test_list_goals_enforces_the_same_configured_threshold_as_other_routes(low_limit_app):
    """
    AC6 (LFC-STORY-003): GET /goals is subject to the existing rate limiter,
    the same as /users/me and POST /goals — all three routes use the shared
    `enforce_rate_limit` dependency and the same `per_ip_rate_limit` string
    derived from Settings, so each independently rejects a client's 3rd
    request under the same RATE_LIMIT_* configuration (slowapi tracks each
    decorated route as its own bucket, so this asserts equivalent
    enforcement per route rather than a single shared counter across
    routes).
    """
    client = TestClient(low_limit_app.app)
    headers = {"Authorization": "Bearer irrelevant"}

    client.get("/users/me", headers=headers)
    client.get("/users/me", headers=headers)
    users_me_third = client.get("/users/me", headers=headers)

    client.get("/goals", headers=headers)
    client.get("/goals", headers=headers)
    goals_third = client.get("/goals", headers=headers)

    assert users_me_third.status_code == 429
    assert goals_third.status_code == 429


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
