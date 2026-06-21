from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import mcp_server
from app.auth import CurrentUser
from mcp.types import EmbeddedResource

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
    """Fake cursor for `get_home_view`'s interleaved query pattern: one
    `fetchone` for the user row, one `fetchall` for the goal rows, then one
    `fetchone` per goal for its most recent update. Each entry in
    `responses` is consumed in order regardless of whether the caller calls
    `fetchone` or `fetchall` — the test supplies responses in the exact
    order the production code is expected to issue queries.
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
async def test_get_home_view_returns_embedded_resource_with_greeting_and_goal_cards(monkeypatch):
    user_row = ("Sam", "sam@example.com")
    goal_rows = [(GOAL_ID, "Run a 5k", 42)]
    update_row = (CREATED_AT,)
    fake_connection, captured = _patch_db_sequenced(
        monkeypatch, [user_row, goal_rows, update_row]
    )
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert isinstance(result, EmbeddedResource)
    assert result.resource.uri.scheme == "ui"
    assert result.resource.mimeType == "text/html"
    assert "Sam" in result.resource.text
    assert "Run a 5k" in result.resource.text
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_get_home_view_falls_back_to_email_when_no_display_name(monkeypatch):
    user_row = (None, "sam@example.com")
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [user_row, []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert "sam@example.com" in result.resource.text


@pytest.mark.asyncio
async def test_get_home_view_returns_empty_state_for_zero_active_goals(monkeypatch):
    user_row = ("Sam", "sam@example.com")
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [user_row, []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    assert 'class="card"' not in result.resource.text
    assert "Create a new goal" in result.resource.text


@pytest.mark.asyncio
async def test_get_home_view_goal_query_has_no_app_level_user_id_or_deleted_at_clause(monkeypatch):
    user_row = ("Sam", "sam@example.com")
    goal_rows = [(GOAL_ID, "Run a 5k", None)]
    update_row = None
    fake_connection, captured = _patch_db_sequenced(
        monkeypatch, [user_row, goal_rows, update_row]
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
    update_row = None
    _patch_db_sequenced(monkeypatch, [user_row, goal_rows, update_row])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_home_view(ctx=_fake_context("Bearer faketoken"))

    body = result.resource.text.split("<body>")[1]
    assert "no-estimate" in body
    assert "0%" not in body


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

    assert isinstance(result, EmbeddedResource)
    assert 'class="card"' not in result.resource.text
    assert "couldn" in result.resource.text.lower()


@pytest.mark.asyncio
async def test_get_home_view_returns_failure_resource_on_unhandled_db_error_instead_of_raising(monkeypatch):
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

    assert isinstance(result, EmbeddedResource)
    assert 'class="card"' not in result.resource.text
    assert "couldn" in result.resource.text.lower()


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
    fake_connection, captured = _patch_db_sequenced(monkeypatch, [goal_row, update_rows])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert isinstance(result, EmbeddedResource)
    assert result.resource.uri.scheme == "ui"
    assert result.resource.mimeType == "text/html"
    assert "Run a 5k" in result.resource.text
    assert "Train three times a week" in result.resource.text
    assert "42%" in result.resource.text
    assert "Ran 3 miles today" in result.resource.text
    assert "transcript" not in result.resource.text.lower()
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_get_goal_detail_view_query_selects_only_content_and_created_at_for_updates(monkeypatch):
    goal_row = (GOAL_ID, "Run a 5k", None, None)
    update_rows = []
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [goal_row, update_rows])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    updates_query, updates_params = fake_connection.cursor_instance.executed[1]
    assert "SELECT content, created_at" in updates_query
    assert "transcript" not in updates_query.lower()
    assert "LIMIT 5" in updates_query
    assert updates_params == (GOAL_ID,)


@pytest.mark.asyncio
async def test_get_goal_detail_view_renders_no_updates_yet_when_recent_updates_empty(monkeypatch):
    goal_row = (GOAL_ID, "Run a 5k", None, None)
    _patch_db_sequenced(monkeypatch, [goal_row, []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert "No updates yet." in result.resource.text


@pytest.mark.asyncio
async def test_get_goal_detail_view_renders_no_estimate_yet_when_progress_percent_is_null(monkeypatch):
    goal_row = (GOAL_ID, "Run a 5k", None, None)
    _patch_db_sequenced(monkeypatch, [goal_row, []])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    body = result.resource.text.split("<body>")[1]
    assert "no-estimate" in body
    assert "0%" not in body


@pytest.mark.asyncio
async def test_get_goal_detail_view_returns_failure_resource_when_goal_row_missing(monkeypatch):
    fake_connection, _ = _patch_db_sequenced(monkeypatch, [None])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.get_goal_detail_view(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert isinstance(result, EmbeddedResource)
    assert "Run a 5k" not in result.resource.text
    assert "isn't available" in result.resource.text or "isn&#x27;t available" in result.resource.text
    # Only one query (the goal lookup) was attempted — no second query for
    # updates is issued once the goal row comes back empty, and crucially
    # no title/progress/updates section is rendered alongside the error.
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

    assert isinstance(result, EmbeddedResource)
    assert "Run a 5k" not in result.resource.text
    assert "isn't available" in result.resource.text or "isn&#x27;t available" in result.resource.text


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
    _patch_db_sequenced(monkeypatch, [goal_row, []])
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
    fake_connection, captured = _patch_db_sequenced(monkeypatch, [goal_row, []])
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


def test_build_embedded_html_resource_helper_used_by_both_home_and_detail_view_builders():
    # Regression guard on the refactor: both resource builders must route
    # through the same shared helper rather than constructing
    # EmbeddedResource/TextResourceContents independently, so a future
    # change to the wrapping shape only needs to happen in one place.
    import inspect

    home_source = inspect.getsource(mcp_server._build_home_view_resource)
    detail_source = inspect.getsource(mcp_server._build_goal_detail_view_resource)

    assert "_build_embedded_html_resource" in home_source
    assert "_build_embedded_html_resource" in detail_source
