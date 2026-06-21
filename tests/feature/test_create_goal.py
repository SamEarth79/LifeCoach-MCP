from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import main
from app.auth import CurrentUser, get_current_user

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
EMAIL = "user@example.com"
GOAL_ID = "33333333-3333-3333-3333-333333333333"
CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
UPDATED_AT = datetime(2026, 1, 2, tzinfo=timezone.utc)


class _FakeCursor:
    def __init__(self, row):
        self._row = row
        self.executed = []

    async def execute(self, query, params=None):
        self.executed.append((query, params))
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
        self.cursor_instance = _FakeCursor(row)
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    async def commit(self):
        self.committed = True


def _override_current_user(user_id=USER_ID, email=EMAIL):
    async def _fake_dependency():
        return CurrentUser(id=user_id, email=email)

    return _fake_dependency


def _patch_get_connection(monkeypatch, row):
    from contextlib import asynccontextmanager

    fake_connection = _FakeConnection(row)
    captured = {}

    @asynccontextmanager
    async def fake_get_rls_connection(user_id):
        captured["user_id"] = user_id
        yield fake_connection

    monkeypatch.setattr(main, "get_rls_connection", fake_get_rls_connection)
    return fake_connection, captured


def test_create_goal_returns_201_with_full_shape(monkeypatch):
    row = (GOAL_ID, "Run a marathon", "Train consistently", CREATED_AT, UPDATED_AT)
    _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.post(
            "/goals",
            json={"title": "Run a marathon", "description": "Train consistently"},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json() == {
        "id": GOAL_ID,
        "title": "Run a marathon",
        "description": "Train consistently",
        "created_at": CREATED_AT.isoformat(),
        "updated_at": UPDATED_AT.isoformat(),
    }


def test_create_goal_allows_omitted_description(monkeypatch):
    row = (GOAL_ID, "Run a marathon", None, CREATED_AT, UPDATED_AT)
    _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.post(
            "/goals",
            json={"title": "Run a marathon"},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["description"] is None


def test_create_goal_rejects_missing_title_with_422_and_no_db_write(monkeypatch):
    fake_connection, _ = _patch_get_connection(monkeypatch, None)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.post(
            "/goals",
            json={"description": "no title here"},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert fake_connection.cursor_instance.executed == []


def test_create_goal_rejects_empty_title_with_422_and_no_db_write(monkeypatch):
    fake_connection, _ = _patch_get_connection(monkeypatch, None)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.post(
            "/goals",
            json={"title": "   "},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert fake_connection.cursor_instance.executed == []


def test_create_goal_uses_verified_jwt_subject_as_user_id_for_insert(monkeypatch):
    row = (GOAL_ID, "Run a marathon", None, CREATED_AT, UPDATED_AT)
    fake_connection, captured = _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user(user_id=USER_ID)
    client = TestClient(main.app)

    try:
        response = client.post(
            "/goals",
            json={"title": "Run a marathon"},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 201
    assert captured["user_id"] == USER_ID
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "INSERT INTO goals" in executed_query
    assert executed_params[0] == USER_ID


def test_create_goal_ignores_client_supplied_user_id_in_request_body(monkeypatch):
    row = (GOAL_ID, "Run a marathon", None, CREATED_AT, UPDATED_AT)
    fake_connection, captured = _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user(user_id=USER_ID)
    client = TestClient(main.app)

    try:
        response = client.post(
            "/goals",
            json={"title": "Run a marathon", "user_id": OTHER_USER_ID},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 201
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert executed_params[0] == USER_ID
    assert OTHER_USER_ID not in executed_params
    assert captured["user_id"] == USER_ID


def test_create_goal_requires_authentication(monkeypatch):
    _patch_get_connection(monkeypatch, None)
    client = TestClient(main.app)

    response = client.post("/goals", json={"title": "Run a marathon"})

    assert response.status_code == 401
