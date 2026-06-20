from fastapi.testclient import TestClient

from app import main
from app.auth import CurrentUser, get_current_user

USER_ID = "11111111-1111-1111-1111-111111111111"
EMAIL = "user@example.com"
GOAL_ID = "33333333-3333-3333-3333-333333333333"


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


def test_delete_goal_returns_204_with_empty_body(monkeypatch):
    row = (GOAL_ID,)
    fake_connection, captured = _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.delete(
            f"/goals/{GOAL_ID}",
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert fake_connection.committed is True
    assert captured["user_id"] == USER_ID


def test_delete_goal_issues_no_sql_delete_statement_only_an_update(monkeypatch):
    """
    AC2, the story's explicit and most important requirement: deleting a
    goal must never issue a SQL DELETE against the goals table — only an
    UPDATE setting deleted_at. Asserts directly on the literal SQL string
    passed to the mocked cursor's execute(), not just on response shape,
    since a test that only checked the HTTP response could pass even if the
    handler issued a real DELETE under the hood.
    """
    row = (GOAL_ID,)
    fake_connection, _ = _patch_get_connection(monkeypatch, row)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        client.delete(
            f"/goals/{GOAL_ID}",
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    sql_keywords = executed_query.lower().split()
    assert "delete" not in sql_keywords
    assert "UPDATE" in executed_query
    assert "deleted_at" in executed_query
    assert executed_params == (GOAL_ID,)


def test_delete_goal_returns_404_when_no_row_returned(monkeypatch):
    """
    Verifies the application's handling of "RETURNING yielded no row" ->
    404. This exercises the app-level fallback for a nonexistent, not-owned,
    or already-soft-deleted goal id, not the `goals_update_own` RLS policy
    itself — no live Postgres/Supabase instance is available in this
    environment, so the mocked cursor simply returns no row regardless of
    why a real RLS policy would have hidden it (same caveat pattern as
    LFC-STORY-003 and LFC-STORY-004).
    """
    fake_connection, _ = _patch_get_connection(monkeypatch, None)
    main.app.dependency_overrides[get_current_user] = _override_current_user()
    client = TestClient(main.app)

    try:
        response = client.delete(
            f"/goals/{GOAL_ID}",
            headers={"Authorization": "Bearer irrelevant"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 404
    assert fake_connection.committed is False


def test_delete_goal_requires_authentication(monkeypatch):
    _patch_get_connection(monkeypatch, None)
    client = TestClient(main.app)

    response = client.delete(f"/goals/{GOAL_ID}")

    assert response.status_code == 401
