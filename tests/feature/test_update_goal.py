from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import main
from app.auth import CurrentUser, get_current_user

USER_ID = "11111111-1111-1111-1111-111111111111"
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


def test_update_goal_title_only_updates_only_title(monkeypatch):
    row = (GOAL_ID, "New title", "Original description", CREATED_AT, UPDATED_AT)
    fake_connection, _ = _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.patch(
            f"/goals/{GOAL_ID}",
            json={"title": "New title"},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": GOAL_ID,
        "title": "New title",
        "description": "Original description",
        "created_at": CREATED_AT.isoformat(),
        "updated_at": UPDATED_AT.isoformat(),
    }

    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "UPDATE goals" in executed_query
    assert "title = %s" in executed_query
    assert "description" not in executed_query.split("SET", 1)[1].split(",")[0]
    assert executed_params == ("New title", GOAL_ID)
    assert fake_connection.committed is True


def test_update_goal_description_only_updates_only_description(monkeypatch):
    row = (GOAL_ID, "Original title", "New description", CREATED_AT, UPDATED_AT)
    fake_connection, _ = _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.patch(
            f"/goals/{GOAL_ID}",
            json={"description": "New description"},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["description"] == "New description"

    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "UPDATE goals" in executed_query
    set_clause = executed_query.split("SET", 1)[1].split("updated_at", 1)[0]
    assert "description = %s" in set_clause
    assert "title" not in set_clause
    assert executed_params == ("New description", GOAL_ID)
    assert fake_connection.committed is True


def test_update_goal_both_fields_updates_both(monkeypatch):
    row = (GOAL_ID, "New title", "New description", CREATED_AT, UPDATED_AT)
    fake_connection, _ = _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.patch(
            f"/goals/{GOAL_ID}",
            json={"title": "New title", "description": "New description"},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "title = %s" in executed_query
    assert "description = %s" in executed_query
    assert executed_params == ("New title", "New description", GOAL_ID)


def test_update_goal_returns_404_when_no_row_returned(monkeypatch):
    """
    Verifies the application's handling of "RETURNING yielded no row" ->
    404. This exercises the app-level fallback for a nonexistent, not-owned,
    or soft-deleted goal id, not the `goals_update_own` RLS policy itself —
    no live Postgres/Supabase instance is available in this environment, so
    the mocked cursor simply returns no row regardless of why a real RLS
    policy would have hidden it (same caveat pattern as LFC-STORY-003).
    """
    fake_connection, _ = _patch_get_connection(monkeypatch, None)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.patch(
            f"/goals/{GOAL_ID}",
            json={"title": "New title"},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 404
    assert fake_connection.committed is False


def test_update_goal_rejects_explicitly_empty_title_with_422(monkeypatch):
    fake_connection, _ = _patch_get_connection(monkeypatch, None)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.patch(
            f"/goals/{GOAL_ID}",
            json={"title": ""},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert fake_connection.cursor_instance.executed == []


def test_update_goal_rejects_whitespace_only_title_with_422(monkeypatch):
    fake_connection, _ = _patch_get_connection(monkeypatch, None)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.patch(
            f"/goals/{GOAL_ID}",
            json={"title": "   "},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert fake_connection.cursor_instance.executed == []


def test_update_goal_allows_explicit_null_description(monkeypatch):
    row = (GOAL_ID, "Existing title", None, CREATED_AT, UPDATED_AT)
    fake_connection, _ = _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.patch(
            f"/goals/{GOAL_ID}",
            json={"description": None},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["description"] is None

    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "description = %s" in executed_query
    assert executed_params == (None, GOAL_ID)


def test_update_goal_omitting_title_does_not_touch_it(monkeypatch):
    """
    Core partial-update distinction: omitting `title` from the body entirely
    (vs sending `title: null`, which `GoalUpdate` would reject as not a
    valid str | None... actually title=None is allowed by the type, but
    business-wise here we confirm omission excludes it from the SQL SET
    clause and its params, proving `exclude_unset=True` semantics rather
    than a None-default that would null it out.
    """
    row = (GOAL_ID, "Untouched title", "New description", CREATED_AT, UPDATED_AT)
    fake_connection, _ = _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.patch(
            f"/goals/{GOAL_ID}",
            json={"description": "New description"},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "title" not in executed_query.split("SET", 1)[1].split("updated_at")[0]
    assert "Untouched title" not in executed_params
    assert "New description" in executed_params


def test_update_goal_requires_authentication(monkeypatch):
    _patch_get_connection(monkeypatch, None)
    client = TestClient(main.app)

    response = client.patch(f"/goals/{GOAL_ID}", json={"title": "New title"})

    assert response.status_code == 401


def test_update_goal_empty_body_is_a_no_op_select_and_returns_200_without_bumping_updated_at(
    monkeypatch,
):
    row = (GOAL_ID, "Existing title", "Existing description", CREATED_AT, UPDATED_AT)
    fake_connection, _ = _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.patch(
            f"/goals/{GOAL_ID}",
            json={},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": GOAL_ID,
        "title": "Existing title",
        "description": "Existing description",
        "created_at": CREATED_AT.isoformat(),
        "updated_at": UPDATED_AT.isoformat(),
    }

    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "SELECT" in executed_query
    assert "UPDATE" not in executed_query
    assert "updated_at = now()" not in executed_query
    assert executed_params == (GOAL_ID,)
    assert fake_connection.committed is False


def test_update_goal_empty_body_returns_404_when_goal_does_not_exist(monkeypatch):
    fake_connection, _ = _patch_get_connection(monkeypatch, None)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.patch(
            f"/goals/{GOAL_ID}",
            json={},
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 404
    executed_query, _ = fake_connection.cursor_instance.executed[0]
    assert "SELECT" in executed_query
    assert fake_connection.committed is False
