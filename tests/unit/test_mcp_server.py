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


@pytest.mark.asyncio
async def test_set_goal_progress_updates_row_with_verified_user_id(monkeypatch):
    row = (GOAL_ID,)
    fake_connection, captured = _patch_db(monkeypatch, row)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.set_goal_progress(
        goal_id=GOAL_ID,
        percentage=42,
        ctx=_fake_context("Bearer faketoken"),
    )

    assert result == {"goal_id": GOAL_ID, "percentage": 42}
    assert captured["user_id"] == USER_ID
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "UPDATE goals" in executed_query
    assert "SET progress_percent" in executed_query
    assert executed_params == (42, GOAL_ID)
    assert fake_connection.committed is True


@pytest.mark.asyncio
async def test_set_goal_progress_rejects_negative_percentage_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.set_goal_progress(
            goal_id=GOAL_ID,
            percentage=-1,
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_set_goal_progress_rejects_percentage_above_100_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.set_goal_progress(
            goal_id=GOAL_ID,
            percentage=101,
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_set_goal_progress_rejects_missing_authorization_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.set_goal_progress(
            goal_id=GOAL_ID,
            percentage=42,
            ctx=_fake_context(None),
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_set_goal_progress_raises_when_no_row_updated_by_rls(monkeypatch):
    # No row is returned by the fake cursor, simulating the RLS
    # `goals_update_own` policy excluding a goal_id that doesn't exist,
    # isn't owned by the caller, or is soft-deleted. The query itself has
    # no app-level `WHERE user_id` clause, so this only confirms the app
    # surfaces a clean ValueError and performs no partial write when no row
    # comes back — it cannot prove RLS itself rejects the row without a
    # live Postgres instance (same caveat as every other RLS-dependent
    # story in this repo, e.g. list_updates's
    # test_list_updates_scopes_query_through_rls_connection_for_verified_user).
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.set_goal_progress(
            goal_id=GOAL_ID,
            percentage=42,
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.committed is False


@pytest.mark.asyncio
async def test_set_goal_progress_query_has_no_app_level_user_id_clause(monkeypatch):
    row = (GOAL_ID,)
    fake_connection, _ = _patch_db(monkeypatch, row)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.set_goal_progress(
        goal_id=GOAL_ID,
        percentage=42,
        ctx=_fake_context("Bearer faketoken"),
    )

    executed_query, _ = fake_connection.cursor_instance.executed[0]
    assert "user_id" not in executed_query.lower()


@pytest.mark.asyncio
async def test_set_goal_progress_enforces_rate_limit_before_jwt_verification(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, (GOAL_ID,))
    call_order = []

    async def _record_rate_limit(*_args, **_kwargs):
        call_order.append("rate_limit")

    async def _record_auth(*_args, **_kwargs):
        call_order.append("auth")
        return CurrentUser(id=USER_ID, email="user@example.com")

    rate_limit_mock = AsyncMock(side_effect=_record_rate_limit)
    auth_mock = AsyncMock(side_effect=_record_auth)
    monkeypatch.setattr(mcp_server, "enforce_mcp_rate_limit", rate_limit_mock)
    monkeypatch.setattr(mcp_server, "verify_bearer_token", auth_mock)

    await mcp_server.set_goal_progress(
        goal_id=GOAL_ID,
        percentage=42,
        ctx=_fake_context("Bearer faketoken"),
    )

    assert call_order == ["rate_limit", "auth"]
    assert fake_connection.cursor_instance.executed != []


@pytest.mark.asyncio
async def test_set_goal_progress_enforces_jwt_verification_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.set_goal_progress(
            goal_id=GOAL_ID,
            percentage=42,
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.cursor_instance.executed == []


def test_set_goal_progress_tool_description_states_internal_use_not_user_facing():
    tool = mcp_server.mcp._tool_manager._tools["set_goal_progress"]

    description = tool.description.lower()

    assert "your own" in description or "internal" in description
    assert "not a user-facing action" in description or "not user-facing" in description
    assert "ui" in description


@pytest.mark.asyncio
async def test_set_goal_progress_returns_plain_dict_not_ui_resource(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, (GOAL_ID,))
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.set_goal_progress(
        goal_id=GOAL_ID,
        percentage=42,
        ctx=_fake_context("Bearer faketoken"),
    )

    assert isinstance(result, dict)
    assert set(result.keys()) == {"goal_id", "percentage"}
    assert "type" not in result
    assert "resource" not in result
    assert "uri" not in result


class _SequencedCursor:
    """Fake cursor for `get_home_view`'s query pattern: one `fetchone` for
    the user row, one `fetchall` for the goal rows, then (only if there are
    any goals) one `fetchall` for the batched per-goal most-recent-update
    lookup (`[(goal_id, last_created_at), ...]`). Each entry in `responses`
    is consumed in order regardless of whether the caller calls `fetchone`
    or `fetchall` — the test supplies responses in the exact order the
    production code is expected to issue queries.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.executed = []

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchone(self):
        return self._responses.pop(0)

    async def fetchall(self):
        return self._responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class _SequencedConnection:
    def __init__(self, responses):
        self.cursor_instance = _SequencedCursor(responses)
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    async def commit(self):
        self.committed = True


def _patch_db_sequenced(monkeypatch, responses):
    fake_connection = _SequencedConnection(responses)
    captured = {}

    @asynccontextmanager
    async def fake_get_rls_connection(user_id):
        captured["user_id"] = user_id
        yield fake_connection

    monkeypatch.setattr(mcp_server, "get_rls_connection", fake_get_rls_connection)
    return fake_connection, captured


@pytest.mark.asyncio
async def test_get_home_view_returns_dict_with_greeting_and_goal_cards(monkeypatch):
    user_row = ("Sam", "sam@example.com")
    goal_rows = [(GOAL_ID, "Run a 5k", 42)]
    last_updated_rows = [(GOAL_ID, CREATED_AT)]
    fake_connection, captured = _patch_db_sequenced(
        monkeypatch, [user_row, goal_rows, last_updated_rows]
    )
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert isinstance(result, dict)
    assert result["greetingName"] == "Sam"
    assert result["goals"][0]["title"] == "Run a 5k"
    assert result["error"] is None
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_get_home_view_falls_back_to_email_when_no_display_name(monkeypatch):
    user_row = (None, "sam@example.com")
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [user_row, []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert result["greetingName"] == "sam@example.com"


@pytest.mark.asyncio
async def test_get_home_view_returns_empty_state_for_zero_active_goals(monkeypatch):
    user_row = ("Sam", "sam@example.com")
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [user_row, []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert result["goals"] == []


@pytest.mark.asyncio
async def test_get_home_view_goal_query_has_no_app_level_user_id_or_deleted_at_clause(monkeypatch):
    user_row = ("Sam", "sam@example.com")
    goal_rows = [(GOAL_ID, "Run a 5k", None)]
    last_updated_rows: list[tuple] = []
    fake_connection, captured = _patch_db_sequenced(
        monkeypatch, [user_row, goal_rows, last_updated_rows]
    )
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    goal_query, goal_params = fake_connection.cursor_instance.executed[1]
    assert "user_id" not in goal_query.lower()
    assert "deleted_at" not in goal_query.lower()
    assert goal_params is None
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_get_home_view_renders_no_estimate_yet_when_progress_percent_is_null(monkeypatch):
    user_row = ("Sam", "sam@example.com")
    goal_rows = [(GOAL_ID, "Run a 5k", None)]
    last_updated_rows: list[tuple] = []
    _patch_db_sequenced(monkeypatch, [user_row, goal_rows, last_updated_rows])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert result["goals"][0]["progressPercent"] is None


@pytest.mark.asyncio
async def test_get_home_view_enforces_rate_limit_before_jwt_verification(monkeypatch):
    user_row = ("Sam", "sam@example.com")
    _patch_db_sequenced(monkeypatch, [user_row, []])
    call_order = []

    async def _record_rate_limit(*_args, **_kwargs):
        call_order.append("rate_limit")

    async def _record_auth(*_args, **_kwargs):
        call_order.append("auth")
        return CurrentUser(id=USER_ID, email="user@example.com")

    monkeypatch.setattr(mcp_server, "enforce_mcp_rate_limit", AsyncMock(side_effect=_record_rate_limit))
    monkeypatch.setattr(mcp_server, "verify_bearer_token", AsyncMock(side_effect=_record_auth))

    await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert call_order == ["rate_limit", "auth"]


@pytest.mark.asyncio
async def test_get_home_view_enforces_jwt_verification_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [])
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.get_home_view(ctx=_fake_context(None))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_get_home_view_returns_failure_resource_when_user_row_missing(monkeypatch):
    _patch_db_sequenced(monkeypatch, [None])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert isinstance(result, dict)
    assert result["goals"] == []
    assert "couldn" in (result.get("error") or "").lower()


@pytest.mark.asyncio
async def test_get_home_view_returns_failure_dict_on_unhandled_db_error_instead_of_raising(monkeypatch):
    class _BoomCursor:
        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("db exploded")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc_info):
            return False

    class _BoomConnection:
        def cursor(self):
            return _BoomCursor()

    @asynccontextmanager
    async def fake_get_rls_connection(_user_id):
        yield _BoomConnection()

    monkeypatch.setattr(mcp_server, "get_rls_connection", fake_get_rls_connection)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert isinstance(result, dict)
    assert result["goals"] == []
    assert result.get("error") is not None


def test_get_home_view_tool_description_mentions_home_screen():
    tool = mcp_server.mcp._tool_manager._tools["get_home_view"]

    description = tool.description.lower()

    assert "home" in description


@pytest.mark.asyncio
async def test_get_goal_detail_view_returns_embedded_resource_with_title_description_progress_and_updates(
    monkeypatch,
):
    goal_row = (GOAL_ID, "Run a 5k", "Train three times a week", 42)
    update_rows = [("Ran 3 miles today", CREATED_AT)]
    todo_id = "44444444-4444-4444-4444-444444444444"
    todo_rows = [(todo_id, "Buy running shoes", False, 0)]
    fake_connection, captured = _patch_db_sequenced(monkeypatch, [goal_row, update_rows, todo_rows])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert isinstance(result, dict)
    assert result["title"] == "Run a 5k"
    assert result["description"] == "Train three times a week"
    assert result["progressPercent"] == 42
    assert result["recentUpdates"][0]["content"] == "Ran 3 miles today"
    assert result["todos"][0]["text"] == "Buy running shoes"
    assert result["todos"][0]["done"] is False
    assert result["todos"][0]["sortOrder"] == 0
    assert "transcript" not in str(result).lower()
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_get_goal_detail_view_query_selects_only_content_and_created_at_for_updates(monkeypatch):
    goal_row = (GOAL_ID, "Run a 5k", None, None)
    update_rows = []
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [goal_row, update_rows, []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    updates_query, updates_params = fake_connection.cursor_instance.executed[1]
    assert "SELECT content, created_at" in updates_query
    assert "transcript" not in updates_query.lower()
    assert "LIMIT 5" in updates_query
    assert updates_params == (GOAL_ID,)


@pytest.mark.asyncio
async def test_get_goal_detail_view_query_selects_todos_ordered_by_sort_order(monkeypatch):
    goal_row = (GOAL_ID, "Run a 5k", None, None)
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [goal_row, [], []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    todos_query, todos_params = fake_connection.cursor_instance.executed[2]
    assert "SELECT id, text, done, sort_order" in todos_query
    assert "FROM todos" in todos_query
    assert "ORDER BY sort_order ASC" in todos_query
    assert todos_params == (GOAL_ID,)


@pytest.mark.asyncio
async def test_get_goal_detail_view_renders_no_updates_yet_when_recent_updates_empty(monkeypatch):
    goal_row = (GOAL_ID, "Run a 5k", None, None)
    _patch_db_sequenced(monkeypatch, [goal_row, [], []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert result["recentUpdates"] == []


@pytest.mark.asyncio
async def test_get_goal_detail_view_renders_empty_todos_list_when_goal_has_no_todos(monkeypatch):
    goal_row = (GOAL_ID, "Run a 5k", None, None)
    _patch_db_sequenced(monkeypatch, [goal_row, [], []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert result["todos"] == []


@pytest.mark.asyncio
async def test_get_goal_detail_view_renders_no_estimate_yet_when_progress_percent_is_null(monkeypatch):
    goal_row = (GOAL_ID, "Run a 5k", None, None)
    _patch_db_sequenced(monkeypatch, [goal_row, [], []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert result["progressPercent"] is None


@pytest.mark.asyncio
async def test_get_goal_detail_view_returns_failure_resource_when_goal_row_missing(monkeypatch):
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [None])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert isinstance(result, dict)
    assert result.get("error") is not None
    assert "isn't available" in result["error"].lower()
    # Only one query (the goal lookup) was attempted — no second query for
    # updates is issued once the goal row comes back empty.
    assert len(fake_connection.cursor_instance.executed) == 1


@pytest.mark.asyncio
async def test_get_goal_detail_view_returns_failure_resource_on_unhandled_db_error_instead_of_raising(
    monkeypatch,
):
    class _BoomCursor:
        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("db exploded")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc_info):
            return False

    class _BoomConnection:
        def cursor(self):
            return _BoomCursor()

    @asynccontextmanager
    async def fake_get_rls_connection(_user_id):
        yield _BoomConnection()

    monkeypatch.setattr(mcp_server, "get_rls_connection", fake_get_rls_connection)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert isinstance(result, dict)
    assert result.get("error") is not None
    assert "isn't available" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_goal_detail_view_rejects_malformed_goal_id_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.get_goal_detail_view(goal_id="not-a-uuid", ctx=_fake_context("Bearer faketoken"))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_get_goal_detail_view_enforces_rate_limit_before_jwt_verification(monkeypatch):
    goal_row = (GOAL_ID, "Run a 5k", None, None)
    _patch_db_sequenced(monkeypatch, [goal_row, [], []])
    call_order = []

    async def _record_rate_limit(*_args, **_kwargs):
        call_order.append("rate_limit")

    async def _record_auth(*_args, **_kwargs):
        call_order.append("auth")
        return CurrentUser(id=USER_ID, email="user@example.com")

    monkeypatch.setattr(mcp_server, "enforce_mcp_rate_limit", AsyncMock(side_effect=_record_rate_limit))
    monkeypatch.setattr(mcp_server, "verify_bearer_token", AsyncMock(side_effect=_record_auth))

    await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert call_order == ["rate_limit", "auth"]


@pytest.mark.asyncio
async def test_get_goal_detail_view_enforces_jwt_verification_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [])
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context(None))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_get_goal_detail_view_jwt_verification_before_uuid_validation_only_matters_after_db_call_check(
    monkeypatch,
):
    # goal_id UUID parsing must happen before any DB call, but per the
    # story's AC6 ordering (rate-limit -> auth -> uuid-validation-then-db),
    # auth failure with a malformed goal_id should still surface the auth
    # failure, not a UUID parse error, and no DB call should happen either way.
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [])
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.get_goal_detail_view(goal_id="not-a-uuid", ctx=_fake_context(None))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_get_goal_detail_view_query_has_no_app_level_user_id_clause(monkeypatch):
    goal_row = (GOAL_ID, "Run a 5k", None, None)
    fake_connection, captured = _patch_db_sequenced(monkeypatch, [goal_row, [], []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    goal_query, goal_params = fake_connection.cursor_instance.executed[0]
    assert "user_id" not in goal_query.lower()
    assert captured["user_id"] == USER_ID


def test_get_goal_detail_view_tool_description_mentions_goal_detail():
    tool = mcp_server.mcp._tool_manager._tools["get_goal_detail_view"]

    description = tool.description.lower()

    assert "detail" in description


class _DeleteThenRefreshCursor:
    """Fake cursor for `delete_goal`'s two-phase query pattern: first the
    `UPDATE ... RETURNING id` for the soft delete, then (only on success)
    the same interleaved user/goal/update queries `_fetch_home_view_data`
    issues. `delete_row` is consumed by the first `fetchone()`; the rest of
    `refresh_responses` is consumed in order by the subsequent calls.
    """

    def __init__(self, delete_row, refresh_responses=None):
        self._delete_row = delete_row
        self._refresh_responses = list(refresh_responses or [])
        self._delete_consumed = False
        self.executed = []

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchone(self):
        if not self._delete_consumed:
            self._delete_consumed = True
            return self._delete_row
        return self._refresh_responses.pop(0)

    async def fetchall(self):
        return self._refresh_responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class _DeleteThenRefreshConnection:
    def __init__(self, delete_row, refresh_responses=None):
        self.cursor_instance = _DeleteThenRefreshCursor(delete_row, refresh_responses)
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    async def commit(self):
        self.committed = True


def _patch_db_for_delete(monkeypatch, delete_row, refresh_responses=None):
    fake_connection = _DeleteThenRefreshConnection(delete_row, refresh_responses)
    captured = {}

    @asynccontextmanager
    async def fake_get_rls_connection(user_id):
        captured["user_id"] = user_id
        yield fake_connection

    monkeypatch.setattr(mcp_server, "get_rls_connection", fake_get_rls_connection)
    return fake_connection, captured


@pytest.mark.asyncio
async def test_delete_goal_soft_deletes_via_update_never_a_hard_delete(monkeypatch):
    delete_row = (GOAL_ID,)
    refresh_responses = [("Sam", "sam@example.com"), [], None]
    fake_connection, captured = _patch_db_for_delete(monkeypatch, delete_row, refresh_responses)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.delete_goal(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    delete_query, delete_params = fake_connection.cursor_instance.executed[0]
    assert "UPDATE goals" in delete_query
    assert "DELETE FROM" not in delete_query.upper()
    assert not delete_query.strip().upper().startswith("DELETE")
    assert "SET deleted_at = now()" in delete_query
    assert "WHERE id = %s AND deleted_at IS NULL" in delete_query
    assert delete_params == (GOAL_ID,)
    assert fake_connection.committed is True
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_delete_goal_query_has_no_app_level_user_id_clause(monkeypatch):
    delete_row = (GOAL_ID,)
    refresh_responses = [("Sam", "sam@example.com"), [], None]
    fake_connection, _ = _patch_db_for_delete(monkeypatch, delete_row, refresh_responses)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    # No app-level `WHERE user_id` filter exists in the SQL; the query
    # relies entirely on `get_rls_connection(current_user.id)` so Postgres
    # RLS (the `goals_update_own` policy) is what would actually enforce
    # ownership in production. This only confirms the connection opens with
    # the verified caller's id and the query text has no such clause — it
    # cannot prove RLS itself rejects another user's row without a live
    # Postgres instance (same caveat as every other RLS-dependent story in
    # this repo, e.g. set_goal_progress's
    # test_set_goal_progress_query_has_no_app_level_user_id_clause).
    await mcp_server.delete_goal(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    delete_query, _ = fake_connection.cursor_instance.executed[0]
    assert "user_id" not in delete_query.lower()


@pytest.mark.asyncio
async def test_delete_goal_raises_cleanly_when_no_row_matches_and_builds_no_home_view(monkeypatch):
    # Covers nonexistent / not-owned / already-soft-deleted goal_id alike,
    # since all three collapse to "no row returned" given the RLS-scoped
    # UPDATE ... WHERE deleted_at IS NULL.
    fake_connection, _ = _patch_db_for_delete(monkeypatch, None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)
    fetch_home_view_mock = AsyncMock(wraps=mcp_server._fetch_home_view_data)
    monkeypatch.setattr(mcp_server, "_fetch_home_view_data", fetch_home_view_mock)

    with pytest.raises(ValueError):
        await mcp_server.delete_goal(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert fake_connection.committed is False
    fetch_home_view_mock.assert_not_awaited()
    assert len(fake_connection.cursor_instance.executed) == 1


@pytest.mark.asyncio
async def test_delete_goal_rejects_malformed_goal_id_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_for_delete(monkeypatch, None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.delete_goal(goal_id="not-a-uuid", ctx=_fake_context("Bearer faketoken"))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_delete_goal_rejects_missing_authorization_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_for_delete(monkeypatch, None)
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.delete_goal(goal_id=GOAL_ID, ctx=_fake_context(None))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_delete_goal_enforces_rate_limit_before_jwt_verification(monkeypatch):
    delete_row = (GOAL_ID,)
    refresh_responses = [("Sam", "sam@example.com"), [], None]
    fake_connection, _ = _patch_db_for_delete(monkeypatch, delete_row, refresh_responses)
    call_order = []

    async def _record_rate_limit(*_args, **_kwargs):
        call_order.append("rate_limit")

    async def _record_auth(*_args, **_kwargs):
        call_order.append("auth")
        return CurrentUser(id=USER_ID, email="user@example.com")

    monkeypatch.setattr(mcp_server, "enforce_mcp_rate_limit", AsyncMock(side_effect=_record_rate_limit))
    monkeypatch.setattr(mcp_server, "verify_bearer_token", AsyncMock(side_effect=_record_auth))

    await mcp_server.delete_goal(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert call_order == ["rate_limit", "auth"]
    assert fake_connection.cursor_instance.executed != []


@pytest.mark.asyncio
async def test_delete_goal_enforces_jwt_verification_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_for_delete(monkeypatch, None)
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.delete_goal(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_delete_goal_on_success_returns_refreshed_home_view_resource_excluding_deleted_goal(
    monkeypatch,
):
    # Post-delete refresh query is mocked to return only the surviving
    # goal — the deleted goal's title/id must not appear in the rendered
    # HTML, proving the refresh reflects the deletion rather than the
    # pre-delete state.
    delete_row = (GOAL_ID,)
    surviving_goal_id = "44444444-4444-4444-4444-444444444444"
    refresh_responses = [
        ("Sam", "sam@example.com"),
        [(surviving_goal_id, "Read a book", 10)],
        [],
    ]
    fake_connection, captured = _patch_db_for_delete(monkeypatch, delete_row, refresh_responses)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.delete_goal(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert isinstance(result, dict)
    assert "Read a book" in str(result)
    assert GOAL_ID not in str(result)
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_delete_goal_returns_same_dict_shape_as_get_home_view(monkeypatch):
    delete_row = (GOAL_ID,)
    refresh_responses = [("Sam", "sam@example.com"), [], None]
    _patch_db_for_delete(monkeypatch, delete_row, refresh_responses)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    delete_result = await mcp_server.delete_goal(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    home_view_responses = [("Sam", "sam@example.com"), []]
    _patch_db_sequenced(monkeypatch, home_view_responses)

    home_view_result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert set(delete_result.keys()) == set(home_view_result.keys())
    assert type(delete_result) is type(home_view_result)


@pytest.mark.asyncio
async def test_delete_goal_success_path_uses_shared_fetch_home_view_data_helper(monkeypatch):
    import inspect

    delete_source = inspect.getsource(mcp_server.delete_goal)

    assert "_fetch_home_view_data" in delete_source
    assert "home_view_data_to_dict" in delete_source


def test_delete_goal_tool_description_states_called_from_ui_confirm_step_not_proactive():
    tool = mcp_server.mcp._tool_manager._tools["delete_goal"]

    description = tool.description.lower()

    assert "confirm" in description
    assert "not" in description
    assert "proactively" in description or "mid-conversation" in description


@pytest.mark.asyncio
async def test_create_goal_inserts_row_with_verified_user_id_title_and_description(monkeypatch):
    refresh_responses = [("Sam", "sam@example.com"), [(GOAL_ID, "Run a 5k", None)], []]
    fake_connection, captured = _patch_db_sequenced(monkeypatch, refresh_responses)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.create_goal(
        title="Run a 5k",
        description="Train three times a week",
        ctx=_fake_context("Bearer faketoken"),
    )

    insert_query, insert_params = fake_connection.cursor_instance.executed[0]
    assert "INSERT INTO goals" in insert_query
    assert insert_params == (USER_ID, "Run a 5k", "Train three times a week")
    assert fake_connection.committed is True
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_create_goal_rejects_blank_title_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.create_goal(title="   ", ctx=_fake_context("Bearer faketoken"))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_create_goal_allows_omitted_description(monkeypatch):
    refresh_responses = [("Sam", "sam@example.com"), [(GOAL_ID, "Run a 5k", None)], []]
    fake_connection, _ = _patch_db_sequenced(monkeypatch, refresh_responses)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.create_goal(title="Run a 5k", ctx=_fake_context("Bearer faketoken"))

    _, insert_params = fake_connection.cursor_instance.executed[0]
    assert insert_params == (USER_ID, "Run a 5k", None)


@pytest.mark.asyncio
async def test_create_goal_rejects_missing_authorization_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [])
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.create_goal(title="Run a 5k", ctx=_fake_context(None))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_create_goal_enforces_rate_limit_before_jwt_verification(monkeypatch):
    refresh_responses = [("Sam", "sam@example.com"), [(GOAL_ID, "Run a 5k", None)], []]
    _patch_db_sequenced(monkeypatch, refresh_responses)
    call_order = []

    async def _record_rate_limit(*_args, **_kwargs):
        call_order.append("rate_limit")

    async def _record_auth(*_args, **_kwargs):
        call_order.append("auth")
        return CurrentUser(id=USER_ID, email="user@example.com")

    monkeypatch.setattr(mcp_server, "enforce_mcp_rate_limit", AsyncMock(side_effect=_record_rate_limit))
    monkeypatch.setattr(mcp_server, "verify_bearer_token", AsyncMock(side_effect=_record_auth))

    await mcp_server.create_goal(title="Run a 5k", ctx=_fake_context("Bearer faketoken"))

    assert call_order == ["rate_limit", "auth"]


@pytest.mark.asyncio
async def test_create_goal_on_success_returns_refreshed_home_view_including_new_goal(monkeypatch):
    refresh_responses = [("Sam", "sam@example.com"), [(GOAL_ID, "Get 5000 LinkedIn followers", None)], []]
    fake_connection, captured = _patch_db_sequenced(monkeypatch, refresh_responses)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.create_goal(
        title="Get 5000 LinkedIn followers",
        ctx=_fake_context("Bearer faketoken"),
    )

    assert isinstance(result, dict)
    assert "Get 5000 LinkedIn followers" in str(result)
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_create_goal_returns_same_dict_shape_as_get_home_view(monkeypatch):
    refresh_responses = [("Sam", "sam@example.com"), [(GOAL_ID, "Run a 5k", None)], []]
    _patch_db_sequenced(monkeypatch, refresh_responses)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    create_result = await mcp_server.create_goal(title="Run a 5k", ctx=_fake_context("Bearer faketoken"))

    home_view_responses = [("Sam", "sam@example.com"), []]
    _patch_db_sequenced(monkeypatch, home_view_responses)

    home_view_result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert set(create_result.keys()) == set(home_view_result.keys())
    assert type(create_result) is type(home_view_result)


@pytest.mark.asyncio
async def test_create_goal_success_path_uses_shared_fetch_home_view_data_helper():
    import inspect

    create_source = inspect.getsource(mcp_server.create_goal)

    assert "_fetch_home_view_data" in create_source
    assert "home_view_data_to_dict" in create_source


@pytest.mark.asyncio
async def test_create_goal_with_todos_persists_each_todo_in_order_with_zero_indexed_sort_order(monkeypatch):
    # Covers AC1/AC2/AC6: a non-empty `todos` list results in that many
    # todo rows persisted for the new goal, in the given order, with
    # sort_order assigned by list position (0-indexed). The goal INSERT
    # uses RETURNING id (consumed by the first fetchone()), so the new
    # goal's id is fed back into each todo INSERT.
    refresh_responses = [("Sam", "sam@example.com"), [(GOAL_ID, "Run a 5k", None)], []]
    fake_connection, captured = _patch_db_sequenced(monkeypatch, [(GOAL_ID,), *refresh_responses])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.create_goal(
        title="Run a 5k",
        ctx=_fake_context("Bearer faketoken"),
        todos=["Buy running shoes", "Plan a route", "Schedule first run"],
    )

    insert_goal_query, insert_goal_params = fake_connection.cursor_instance.executed[0]
    assert "INSERT INTO goals" in insert_goal_query
    assert "RETURNING id" in insert_goal_query
    assert insert_goal_params == (USER_ID, "Run a 5k", None)

    todo_inserts = fake_connection.cursor_instance.executed[1:4]
    expected_todos = ["Buy running shoes", "Plan a route", "Schedule first run"]
    for sort_order, (todo_query, todo_params) in enumerate(todo_inserts):
        assert "INSERT INTO todos" in todo_query
        assert todo_params == (USER_ID, GOAL_ID, expected_todos[sort_order], sort_order)

    assert fake_connection.committed is True
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_create_goal_rejects_blank_todo_in_list_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.create_goal(
            title="Run a 5k",
            ctx=_fake_context("Bearer faketoken"),
            todos=["Buy running shoes", "   "],
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_create_goal_with_omitted_todos_runs_the_same_single_insert_as_before_this_story(monkeypatch):
    # AC3: when `todos` is omitted, behavior must be identical to the
    # pre-story query shape — a single INSERT with no RETURNING and no
    # todo inserts. Mirrors
    # test_create_goal_inserts_row_with_verified_user_id_title_and_description
    # exactly, just calling the function without the new parameter at all.
    refresh_responses = [("Sam", "sam@example.com"), [(GOAL_ID, "Run a 5k", None)], []]
    fake_connection, captured = _patch_db_sequenced(monkeypatch, refresh_responses)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.create_goal(
        title="Run a 5k",
        description="Train three times a week",
        ctx=_fake_context("Bearer faketoken"),
    )

    insert_query, insert_params = fake_connection.cursor_instance.executed[0]
    assert "INSERT INTO goals" in insert_query
    assert "RETURNING" not in insert_query
    assert insert_params == (USER_ID, "Run a 5k", "Train three times a week")
    assert not any("INSERT INTO todos" in query for query, _ in fake_connection.cursor_instance.executed)
    assert fake_connection.committed is True
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_create_goal_with_empty_todos_list_runs_the_same_single_insert_as_omitted(monkeypatch):
    # AC3 also covers an explicitly empty list, not just an omitted
    # argument — `if goal.todos:` is falsy for `[]` too.
    refresh_responses = [("Sam", "sam@example.com"), [(GOAL_ID, "Run a 5k", None)], []]
    fake_connection, _ = _patch_db_sequenced(monkeypatch, refresh_responses)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.create_goal(
        title="Run a 5k",
        ctx=_fake_context("Bearer faketoken"),
        todos=[],
    )

    insert_query, _ = fake_connection.cursor_instance.executed[0]
    assert "RETURNING" not in insert_query
    assert not any("INSERT INTO todos" in query for query, _ in fake_connection.cursor_instance.executed)


def test_goal_create_rejects_blank_todo_in_list():
    from pydantic import ValidationError

    from app.schemas import GoalCreate

    with pytest.raises(ValidationError):
        GoalCreate(title="Run a 5k", todos=["Buy running shoes", "   "])


def test_goal_create_strips_surrounding_whitespace_from_each_todo():
    from app.schemas import GoalCreate

    goal = GoalCreate(title="Run a 5k", todos=["  Buy running shoes  ", "Plan a route"])

    assert goal.todos == ["Buy running shoes", "Plan a route"]


def test_goal_create_allows_omitted_or_none_todos():
    from app.schemas import GoalCreate

    assert GoalCreate(title="Run a 5k").todos is None
    assert GoalCreate(title="Run a 5k", todos=None).todos is None


def test_create_goal_tool_description_instructs_caller_on_when_to_call_it():
    tool = mcp_server.mcp._tool_manager._tools["create_goal"]

    description = tool.description.lower()

    assert "title" in description
    assert "agreed" in description or "described" in description


def test_create_goal_tool_declares_home_view_ui_resource_uri_in_meta():
    tool = mcp_server.mcp._tool_manager._tools["create_goal"]

    assert tool.meta == {"ui": {"resourceUri": "ui://home-view"}}


@pytest.mark.asyncio
async def test_home_view_resource_is_registered_under_ui_home_view_uri():
    resources = await mcp_server.mcp.list_resources()
    resource_uris = {str(resource.uri) for resource in resources}

    assert "ui://home-view" in resource_uris


@pytest.mark.asyncio
async def test_goal_detail_view_resource_is_registered_under_ui_goal_detail_view_uri():
    resources = await mcp_server.mcp.list_resources()
    resource_uris = {str(resource.uri) for resource in resources}

    assert "ui://goal-detail-view" in resource_uris


@pytest.mark.asyncio
async def test_home_view_resource_has_mcp_app_html_mime_type():
    resources = await mcp_server.mcp.list_resources()
    home_resource = next(r for r in resources if str(r.uri) == "ui://home-view")

    assert home_resource.mimeType == "text/html;profile=mcp-app"


@pytest.mark.asyncio
async def test_goal_detail_view_resource_has_mcp_app_html_mime_type():
    resources = await mcp_server.mcp.list_resources()
    detail_resource = next(r for r in resources if str(r.uri) == "ui://goal-detail-view")

    assert detail_resource.mimeType == "text/html;profile=mcp-app"


@pytest.mark.asyncio
async def test_home_view_resource_function_returns_render_home_view_output():
    from app.ui_templates import render_home_view

    result = await mcp_server.home_view_resource()

    assert result == render_home_view()


@pytest.mark.asyncio
async def test_goal_detail_view_resource_function_returns_render_goal_detail_view_output():
    from app.ui_templates import render_goal_detail_view

    result = await mcp_server.goal_detail_view_resource()

    assert result == render_goal_detail_view()


def test_get_home_view_tool_declares_ui_resource_uri_in_meta():
    tool = mcp_server.mcp._tool_manager._tools["get_home_view"]

    assert tool.meta == {"ui": {"resourceUri": "ui://home-view"}}


def test_get_goal_detail_view_tool_declares_ui_resource_uri_in_meta():
    tool = mcp_server.mcp._tool_manager._tools["get_goal_detail_view"]

    assert tool.meta == {"ui": {"resourceUri": "ui://goal-detail-view"}}


def test_delete_goal_tool_declares_home_view_ui_resource_uri_in_meta():
    # delete_goal returns a refreshed home-view dict (not a goal-detail
    # dict) on success, so its UI resource link intentionally points at
    # ui://home-view, the same resource get_home_view declares — not at
    # ui://goal-detail-view.
    tool = mcp_server.mcp._tool_manager._tools["delete_goal"]

    assert tool.meta == {"ui": {"resourceUri": "ui://home-view"}}


def test_record_update_set_goal_progress_and_list_updates_tools_have_no_ui_meta():
    # Only the three tools that return view dicts declare a UI resource
    # link; record_update/list_updates/set_goal_progress are not rendered
    # by a UI template and must not carry stale or accidental _meta.
    for tool_name in ("record_update", "list_updates", "set_goal_progress"):
        tool = mcp_server.mcp._tool_manager._tools[tool_name]
        assert tool.meta is None or "ui" not in tool.meta


def test_mcp_transport_security_keeps_dns_rebinding_protection_enabled():
    # Regression test: a prior fix for a Render-deployment Host-header
    # rejection disabled DNS rebinding protection entirely
    # (enable_dns_rebinding_protection=False) instead of scoping
    # allowed_hosts/allowed_origins to the real deployed domain. That
    # disabled Host-header validation outright, not just for the
    # then-mismatched Render hostname. Protection must stay enabled.
    transport_security = mcp_server.mcp.settings.transport_security

    assert transport_security.enable_dns_rebinding_protection is True


def test_mcp_transport_security_allowed_hosts_come_from_settings():
    transport_security = mcp_server.mcp.settings.transport_security

    assert transport_security.allowed_hosts == mcp_server.settings.mcp_allowed_hosts_list
    assert transport_security.allowed_origins == mcp_server.settings.mcp_allowed_origins_list


def test_server_instructions_set_persona_and_logging_judgment_not_session_kickoff():
    # instructions apply to every connection with no way to gate them behind
    # explicit user action, so they must only carry passive tone/judgment
    # guidance - never a "call get_home_view at session start" directive,
    # which belongs to the explicit coach prompt instead.
    instructions = mcp_server.mcp.instructions

    assert instructions is not None
    assert "coach" in instructions.lower()
    assert "record_update" in instructions
    assert "set_goal_progress" in instructions
    assert "session start" not in instructions.lower()
    assert "every chat" not in instructions.lower()
    assert "every conversation" not in instructions.lower()


def test_server_instructions_tell_claude_to_set_progress_alongside_every_update():
    # Real gap: goals have no numeric target field, so progress_percent is
    # never computed automatically - it stays blank (rendered as a dash)
    # forever unless Claude calls set_goal_progress itself. Without an
    # explicit nudge here, Claude was observed not calling it reliably.
    instructions = mcp_server.mcp.instructions

    assert "whenever you call record_update" in instructions.lower()
    assert "also call set_goal_progress" in instructions.lower()
    assert "no numeric target" in instructions.lower()


def test_server_instructions_tell_claude_to_create_goal_first_then_discuss_todos():
    # AC4: instructions must direct the LLM to create the goal first with no
    # todos, then discuss next steps with the user before adding any via create_todo.
    instructions = mcp_server.mcp.instructions

    assert "no todos" in instructions.lower() or "without todos" in instructions.lower() or "first with no todos" in instructions.lower()
    assert "create_todo" in instructions
    assert "create a goal" in instructions.lower() or "create_goal" in instructions.lower()


def test_server_instructions_tell_claude_to_use_todo_crud_tools_conversationally():
    # AC5: instructions must direct the LLM to use create_todo/update_todo/
    # toggle_todo/delete_todo/reorder_todos whenever the user conversationally
    # asks to add, change, complete, remove, or reorder todos.
    instructions = mcp_server.mcp.instructions

    for tool_name in ("create_todo", "update_todo", "toggle_todo", "delete_todo", "reorder_todos"):
        assert tool_name in instructions


def test_create_goal_tool_description_instructs_no_todos_at_creation():
    # AC4 (alternate location): the create_goal tool description must say
    # not to include todos in the call — create the goal first, then discuss.
    tool = mcp_server.mcp._tool_manager._tools["create_goal"]

    description = tool.description.lower()

    assert "do not include" in description or "no todos" in description or "first" in description
    assert "create_todo" in description


def test_coach_prompt_is_registered_and_not_auto_invoked():
    prompt = mcp_server.mcp._prompt_manager._prompts["coach"]

    assert prompt.name == "coach"
    assert "explicit" in prompt.description.lower() or "not run automatically" in prompt.description.lower()


@pytest.mark.asyncio
async def test_coach_prompt_returns_user_message_embedding_real_home_view_data(monkeypatch):
    user_row = ("Sam", "user@example.com")
    goal_rows = [("33333333-3333-3333-3333-333333333333", "Run a 5k", 42)]
    last_updated_rows = [("33333333-3333-3333-3333-333333333333", datetime(2026, 1, 1, tzinfo=timezone.utc))]
    fake_connection = _SequencedConnection([user_row, goal_rows, last_updated_rows])

    @asynccontextmanager
    async def fake_get_rls_connection(_user_id):
        yield fake_connection

    monkeypatch.setattr(mcp_server, "get_rls_connection", fake_get_rls_connection)
    monkeypatch.setattr(
        mcp_server,
        "verify_bearer_token",
        AsyncMock(return_value=CurrentUser(id="11111111-1111-1111-1111-111111111111", email="user@example.com")),
    )
    monkeypatch.setattr(mcp_server, "enforce_mcp_rate_limit", AsyncMock(return_value=None))

    request = SimpleNamespace(headers={"authorization": "Bearer token"})
    ctx = SimpleNamespace(request_context=SimpleNamespace(request=request))

    message = await mcp_server.coach_prompt(ctx)

    assert message.role == "user"
    assert "Sam" in message.content.text
    assert "Run a 5k" in message.content.text


@pytest.mark.asyncio
async def test_coach_prompt_shows_generic_error_when_home_view_fetch_fails(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "verify_bearer_token",
        AsyncMock(return_value=CurrentUser(id="11111111-1111-1111-1111-111111111111", email="user@example.com")),
    )
    monkeypatch.setattr(mcp_server, "enforce_mcp_rate_limit", AsyncMock(return_value=None))

    async def _raise_fetch(_user_id):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(mcp_server, "_fetch_home_view_data", _raise_fetch)

    request = SimpleNamespace(headers={"authorization": "Bearer token"})
    ctx = SimpleNamespace(request_context=SimpleNamespace(request=request))

    message = await mcp_server.coach_prompt(ctx)

    assert "couldn't load your home screen" in message.content.text
    assert "Traceback" not in message.content.text
