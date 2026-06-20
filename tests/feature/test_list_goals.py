from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import main
from app.auth import CurrentUser, get_current_user

USER_ID = "11111111-1111-1111-1111-111111111111"
EMAIL = "user@example.com"
GOAL_ID_1 = "33333333-3333-3333-3333-333333333333"
GOAL_ID_2 = "44444444-4444-4444-4444-444444444444"
CREATED_AT_1 = datetime(2026, 1, 2, tzinfo=timezone.utc)
UPDATED_AT_1 = datetime(2026, 1, 2, tzinfo=timezone.utc)
CREATED_AT_2 = datetime(2026, 1, 1, tzinfo=timezone.utc)
UPDATED_AT_2 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    async def execute(self, query, params=None):
        self.executed.append((query, params))
        return None

    async def fetchall(self):
        return self._rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class _FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = _FakeCursor(rows)

    def cursor(self):
        return self.cursor_instance


def _override_current_user(user_id=USER_ID, email=EMAIL):
    async def _fake_dependency():
        return CurrentUser(id=user_id, email=email)

    return _fake_dependency


def _patch_get_connection(monkeypatch, rows):
    from contextlib import asynccontextmanager

    fake_connection = _FakeConnection(rows)
    captured = {}

    @asynccontextmanager
    async def fake_get_rls_connection(user_id):
        captured["user_id"] = user_id
        yield fake_connection

    monkeypatch.setattr(main, "get_rls_connection", fake_get_rls_connection)
    return fake_connection, captured


def test_list_goals_returns_200_with_full_shape(monkeypatch):
    rows = [
        (GOAL_ID_1, "Run a marathon", "Train consistently", CREATED_AT_1, UPDATED_AT_1),
    ]
    _patch_get_connection(monkeypatch, rows)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.get("/goals", headers={"Authorization": "Bearer irrelevant"})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": GOAL_ID_1,
            "title": "Run a marathon",
            "description": "Train consistently",
            "created_at": CREATED_AT_1.isoformat(),
            "updated_at": UPDATED_AT_1.isoformat(),
        }
    ]


def test_list_goals_returns_200_with_empty_array_when_user_has_no_goals(monkeypatch):
    _patch_get_connection(monkeypatch, [])
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.get("/goals", headers={"Authorization": "Bearer irrelevant"})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []


def test_list_goals_issues_no_client_side_filter_that_would_conflict_with_rls(monkeypatch):
    """
    AC3/AC4 (soft-delete exclusion, cross-user isolation) are enforced by the
    `goals_select_own` RLS policy (`auth.uid() = user_id AND deleted_at IS
    NULL`) at the database layer, not by application code — this test
    environment has no live Postgres/Supabase instance, so the RLS policy
    itself is not exercised here (see test-results.md for the explicit
    caveat). What this test verifies instead, at the application boundary,
    is that the endpoint issues a plain, unfiltered SELECT and relies
    entirely on `get_rls_connection(current_user.id)` for scoping — i.e. it
    does not add its own `WHERE user_id = ...` or `WHERE deleted_at IS NULL`
    clause that could mask or duplicate the RLS policy's behavior, and it
    passes the verified user id into the RLS-scoped connection rather than
    any unscoped connection.
    """
    rows = [(GOAL_ID_1, "Run a marathon", None, CREATED_AT_1, UPDATED_AT_1)]
    fake_connection, captured = _patch_get_connection(monkeypatch, rows)
    main.app.dependency_overrides[get_current_user] = _override_current_user(user_id=USER_ID)
    client = TestClient(main.app)

    try:
        response = client.get("/goals", headers={"Authorization": "Bearer irrelevant"})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "WHERE" not in executed_query
    assert executed_params is None
    assert captured["user_id"] == USER_ID


def test_list_goals_requires_authentication(monkeypatch):
    _patch_get_connection(monkeypatch, [])
    client = TestClient(main.app)

    response = client.get("/goals")

    assert response.status_code == 401


def test_list_goals_returns_rows_in_the_order_the_cursor_yields_them_without_resorting(monkeypatch):
    """
    AC6 (application-side contract): the endpoint passes through whatever
    order `cursor.fetchall()` returns without re-sorting client-side. The
    SQL itself declares `ORDER BY created_at DESC`; whether Postgres
    actually executes that ordering correctly against a live database is
    not verified here (no live DB in this environment) — only that the
    handler does not undo or alter whatever order the cursor produced.
    """
    rows = [
        (GOAL_ID_1, "Newer goal", None, CREATED_AT_1, UPDATED_AT_1),
        (GOAL_ID_2, "Older goal", None, CREATED_AT_2, UPDATED_AT_2),
    ]
    fake_connection, _ = _patch_get_connection(monkeypatch, rows)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.get("/goals", headers={"Authorization": "Bearer irrelevant"})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [goal["id"] for goal in body] == [GOAL_ID_1, GOAL_ID_2]
    executed_query, _ = fake_connection.cursor_instance.executed[0]
    assert "ORDER BY created_at DESC" in executed_query
