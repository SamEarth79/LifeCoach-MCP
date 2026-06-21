from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import mcp_server
from app.auth import CurrentUser

USER_ID = "11111111-1111-1111-1111-111111111111"
GOAL_ID = "33333333-3333-3333-3333-333333333333"
CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeCursor:
    def __init__(self, row, rows=None):
        self._row = row
        self._rows = rows
        self.executed = []

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchone(self):
        return self._row

    async def fetchall(self):
        return self._rows if self._rows is not None else []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class _FakeConnection:
    def __init__(self, row=None, rows=None):
        self.cursor_instance = _FakeCursor(row, rows=rows)
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    async def commit(self):
        self.committed = True


def _fake_context(authorization_header: str | None):
    request = SimpleNamespace(headers={"authorization": authorization_header} if authorization_header else {})
    request_context = SimpleNamespace(request=request)
    return SimpleNamespace(request_context=request_context)


def _patch_db(monkeypatch, row):
    fake_connection = _FakeConnection(row)
    captured = {}

    @asynccontextmanager
    async def fake_get_rls_connection(user_id):
        captured["user_id"] = user_id
        yield fake_connection

    monkeypatch.setattr(mcp_server, "get_rls_connection", fake_get_rls_connection)
    return fake_connection, captured


def _patch_db_for_list(monkeypatch, rows):
    fake_connection = _FakeConnection(rows=rows)
    captured = {}

    @asynccontextmanager
    async def fake_get_rls_connection(user_id):
        captured["user_id"] = user_id
        yield fake_connection

    monkeypatch.setattr(mcp_server, "get_rls_connection", fake_get_rls_connection)
    return fake_connection, captured


def _patch_auth(monkeypatch, user=None, side_effect=None):
    mock = AsyncMock()
    if side_effect is not None:
        mock.side_effect = side_effect
    else:
        mock.return_value = user or CurrentUser(id=USER_ID, email="user@example.com")
    monkeypatch.setattr(mcp_server, "verify_bearer_token", mock)
    return mock


def _patch_rate_limit(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(mcp_server, "enforce_mcp_rate_limit", mock)
    return mock


@pytest.mark.asyncio
async def test_record_update_inserts_row_with_verified_user_id(monkeypatch):
    row = (GOAL_ID, GOAL_ID, "Agreed to run 3x/week", "coaching_update", CREATED_AT)
    fake_connection, captured = _patch_db(monkeypatch, row)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.record_update(
        goal_id=GOAL_ID,
        content="Agreed to run 3x/week",
        ctx=_fake_context("Bearer faketoken"),
    )

    assert result["content"] == "Agreed to run 3x/week"
    assert result["source"] == "coaching_update"
    assert captured["user_id"] == USER_ID
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "INSERT INTO updates" in executed_query
    assert executed_params[0] == USER_ID
    assert fake_connection.committed is True


@pytest.mark.asyncio
async def test_record_update_rejects_missing_authorization_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.record_update(
            goal_id=GOAL_ID,
            content="Agreed to run 3x/week",
            ctx=_fake_context(None),
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_record_update_rejects_blank_content_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.record_update(
            goal_id=GOAL_ID,
            content="   ",
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_record_update_raises_when_rls_insert_check_rejects_the_row(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.record_update(
            goal_id=GOAL_ID,
            content="Agreed to run 3x/week",
            ctx=_fake_context("Bearer faketoken"),
        )


@pytest.mark.asyncio
async def test_record_update_never_accepts_a_source_parameter():
    import inspect

    signature = inspect.signature(mcp_server.record_update)

    assert "source" not in signature.parameters


def test_record_update_tool_description_instructs_caller_on_when_and_what_to_record():
    tool = mcp_server.mcp._tool_manager._tools["record_update"]

    description = tool.description.lower()

    assert "once" in description
    assert "settled" in description or "concrete" in description
    assert "summary" in description
    assert "raw" in description or "transcript" in description


@pytest.mark.asyncio
async def test_list_updates_returns_only_content_source_created_at_never_transcript(monkeypatch):
    # The underlying row only contains the columns the SQL actually
    # selects (content, source, created_at) — the absence of `transcript`
    # in the result is enforced by the SELECT itself, not by the response
    # schema dropping an extra field. This proves the query never fetches
    # transcript in the first place, the strongest form of "never leaks".
    rows = [("Agreed to run 3x/week", "coaching_update", CREATED_AT)]
    fake_connection, captured = _patch_db_for_list(monkeypatch, rows)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.list_updates(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert len(result) == 1
    assert set(result[0].keys()) == {"content", "source", "created_at"}
    assert "transcript" not in result[0]
    assert result[0]["content"] == "Agreed to run 3x/week"
    assert result[0]["source"] == "coaching_update"
    assert captured["user_id"] == USER_ID
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "SELECT content, source, created_at" in executed_query
    assert "transcript" not in executed_query.lower()
    assert executed_params[0] == GOAL_ID


@pytest.mark.asyncio
async def test_list_updates_returns_checkin_and_coaching_update_rows_together(monkeypatch):
    rows = [
        ("Logged a check-in", "checkin", CREATED_AT),
        ("Agreed to run 3x/week", "coaching_update", CREATED_AT),
    ]
    _patch_db_for_list(monkeypatch, rows)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.list_updates(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    sources = {item["source"] for item in result}
    assert sources == {"checkin", "coaching_update"}


@pytest.mark.asyncio
async def test_list_updates_returns_empty_list_for_goal_with_no_updates(monkeypatch):
    _patch_db_for_list(monkeypatch, [])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.list_updates(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert result == []


@pytest.mark.asyncio
async def test_list_updates_scopes_query_through_rls_connection_for_verified_user(monkeypatch):
    # No explicit user_id filter exists in the SQL; the query relies on
    # `get_rls_connection(current_user.id)` so Postgres RLS (the
    # `updates_select_own` policy) excludes other users' rows. This test
    # only confirms the connection is opened with the verified caller's
    # id — it cannot prove RLS itself rejects another user's rows without
    # a live Postgres instance (same caveat as every other RLS-dependent
    # story in this repo).
    rows = [("Agreed to run 3x/week", "coaching_update", CREATED_AT)]
    fake_connection, captured = _patch_db_for_list(monkeypatch, rows)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.list_updates(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert captured["user_id"] == USER_ID
    executed_query, _ = fake_connection.cursor_instance.executed[0]
    assert "user_id" not in executed_query.lower()


@pytest.mark.asyncio
async def test_list_updates_rejects_missing_authorization_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_for_list(monkeypatch, [])
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.list_updates(goal_id=GOAL_ID, ctx=_fake_context(None))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_list_updates_rejects_malformed_goal_id_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_for_list(monkeypatch, [])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.list_updates(goal_id="not-a-uuid", ctx=_fake_context("Bearer faketoken"))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_list_updates_enforces_rate_limit_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_for_list(monkeypatch, [])
    _patch_auth(monkeypatch)
    rate_limit_mock = _patch_rate_limit(monkeypatch)

    await mcp_server.list_updates(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    rate_limit_mock.assert_awaited_once()
    assert rate_limit_mock.await_args.args[0] is not None


def test_list_updates_tool_description_promises_no_transcript():
    tool = mcp_server.mcp._tool_manager._tools["list_updates"]

    description = tool.description.lower()

    assert "transcript" in description
    assert "never" in description or "not" in description
