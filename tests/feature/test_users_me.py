from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import main
from app.auth import CurrentUser, get_current_user

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
EMAIL = "user@example.com"
CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
UPDATED_AT = datetime(2026, 1, 2, tzinfo=timezone.utc)


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


def _override_current_user(user_id=USER_ID, email=EMAIL):
    async def _fake_dependency():
        return CurrentUser(id=user_id, email=email)

    return _fake_dependency


def _patch_get_connection(monkeypatch, row):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_get_rls_connection(_user_id):
        yield _FakeConnection(row)

    monkeypatch.setattr(main, "get_rls_connection", fake_get_rls_connection)


def test_get_users_me_returns_user_profile_for_authenticated_user(monkeypatch):
    row = (USER_ID, EMAIL, "Test User", CREATED_AT, UPDATED_AT)
    _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.get("/users/me", headers={"Authorization": "Bearer irrelevant"})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": USER_ID,
        "email": EMAIL,
        "display_name": "Test User",
        "created_at": CREATED_AT.isoformat(),
        "updated_at": UPDATED_AT.isoformat(),
    }


def test_get_users_me_returns_404_when_row_missing(monkeypatch):
    _patch_get_connection(monkeypatch, None)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.get("/users/me", headers={"Authorization": "Bearer irrelevant"})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 404


def test_get_users_me_returns_403_when_row_id_does_not_match_verified_id(monkeypatch):
    row = (OTHER_USER_ID, EMAIL, "Test User", CREATED_AT, UPDATED_AT)
    _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user(user_id=USER_ID)
    client = TestClient(main.app)

    try:
        response = client.get("/users/me", headers={"Authorization": "Bearer irrelevant"})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 403


def test_get_users_me_requires_authentication(monkeypatch):
    _patch_get_connection(monkeypatch, None)
    client = TestClient(main.app)

    response = client.get("/users/me")

    assert response.status_code == 401
