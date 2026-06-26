"""Unit/feature tests for the todo MCP tools (create_todo, update_todo,
toggle_todo, delete_todo, list_todos, reorder_todos).

Follows the exact mocking approach used in `tests/unit/test_mcp_server.py`
for `record_update`/`set_goal_progress`/`delete_goal`/`list_updates`: tools
are called directly as plain async functions with a fake `ctx`, and
`verify_bearer_token`/`enforce_mcp_rate_limit`/`get_rls_connection` are all
monkeypatched so no real Postgres/Supabase instance is required.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import mcp_server
from app.auth import CurrentUser

USER_ID = "11111111-1111-1111-1111-111111111111"
GOAL_ID = "33333333-3333-3333-3333-333333333333"
TODO_ID = "55555555-5555-5555-5555-555555555555"
TODO_ID_2 = "66666666-6666-6666-6666-666666666666"
TODO_ID_3 = "77777777-7777-7777-7777-777777777777"
CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
UPDATED_AT = datetime(2026, 1, 2, tzinfo=timezone.utc)


def _todo_row(todo_id=TODO_ID, goal_id=GOAL_ID, text="Buy running shoes", done=False, sort_order=0):
    return (todo_id, goal_id, text, done, sort_order, CREATED_AT, UPDATED_AT)


class _FakeCursor:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows
        self.executed = []
        self.rowcount = 1

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


class _SequentialCursor:
    """Returns a different `fetchone()` row on each call, in order — used
    for `reorder_todos`, which issues one `UPDATE ... WHERE id = %s` per
    todo_id rather than a single statement.

    `rowcounts`, when given, supplies the `cursor.rowcount` to expose after
    each `execute()` call, in order (one per UPDATE) — used to simulate a
    todo_id that doesn't exist/belong to the goal (rowcount 0).
    """

    def __init__(self, rows, rowcounts=None):
        self._rows = list(rows)
        self._rowcounts = list(rowcounts) if rowcounts is not None else None
        self.executed = []
        self.rowcount = 1

    async def execute(self, query, params=None):
        self.executed.append((query, params))
        if self._rowcounts is not None:
            self.rowcount = self._rowcounts.pop(0) if self._rowcounts else 1

    async def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class _SequentialConnection:
    def __init__(self, rows, rowcounts=None):
        self.cursor_instance = _SequentialCursor(rows, rowcounts=rowcounts)
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    async def commit(self):
        self.committed = True


def _fake_context(authorization_header: str | None):
    request = SimpleNamespace(headers={"authorization": authorization_header} if authorization_header else {})
    request_context = SimpleNamespace(request=request)
    return SimpleNamespace(request_context=request_context)


def _patch_db(monkeypatch, row=None, rows=None):
    fake_connection = _FakeConnection(row=row, rows=rows)
    captured = {}

    @asynccontextmanager
    async def fake_get_rls_connection(user_id):
        captured["user_id"] = user_id
        yield fake_connection

    monkeypatch.setattr(mcp_server, "get_rls_connection", fake_get_rls_connection)
    return fake_connection, captured


def _patch_sequential_db(monkeypatch, rows, rowcounts=None):
    fake_connection = _SequentialConnection(rows, rowcounts=rowcounts)
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


# --- create_todo --------------------------------------------------------


@pytest.mark.asyncio
async def test_create_todo_inserts_row_with_verified_user_id_and_returns_created_todo(monkeypatch):
    row = _todo_row(text="Buy running shoes", sort_order=0)
    fake_connection, captured = _patch_db(monkeypatch, row=row)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.create_todo(
        goal_id=GOAL_ID,
        text="Buy running shoes",
        ctx=_fake_context("Bearer faketoken"),
    )

    assert result["id"] == TODO_ID
    assert result["goal_id"] == GOAL_ID
    assert result["text"] == "Buy running shoes"
    assert result["done"] is False
    assert result["sort_order"] == 0
    assert captured["user_id"] == USER_ID
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "INSERT INTO todos" in executed_query
    assert executed_params[0] == USER_ID
    assert fake_connection.committed is True


@pytest.mark.asyncio
async def test_create_todo_computes_sort_order_via_max_plus_one_with_coalesce_to_zero(monkeypatch):
    # The SQL itself (not app code) assigns sort_order via
    # `COALESCE((SELECT MAX(sort_order) + 1 FROM todos WHERE goal_id = %s), 0)`
    # — this asserts the query text contains that expression so the
    # first-todo-for-a-goal-gets-0 behavior (AC1) is backed by the actual
    # statement sent, not just a returned row that happens to say 0.
    row = _todo_row(sort_order=0)
    fake_connection, _ = _patch_db(monkeypatch, row=row)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    await mcp_server.create_todo(
        goal_id=GOAL_ID,
        text="First todo for this goal",
        ctx=_fake_context("Bearer faketoken"),
    )

    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "COALESCE" in executed_query
    assert "MAX(sort_order) + 1" in executed_query
    assert ", 0" in executed_query or "0\n" in executed_query
    assert executed_params[-1] == GOAL_ID


@pytest.mark.asyncio
async def test_create_todo_rejects_blank_text_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.create_todo(
            goal_id=GOAL_ID,
            text="   ",
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_create_todo_rejects_missing_authorization_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.create_todo(
            goal_id=GOAL_ID,
            text="Buy running shoes",
            ctx=_fake_context(None),
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_create_todo_raises_when_rls_insert_check_rejects_the_goal(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.create_todo(
            goal_id=GOAL_ID,
            text="Buy running shoes",
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.committed is False


# --- update_todo ---------------------------------------------------------


@pytest.mark.asyncio
async def test_update_todo_updates_text_and_returns_found_true_with_updated_todo(monkeypatch):
    row = _todo_row(text="Buy trail running shoes")
    fake_connection, captured = _patch_db(monkeypatch, row=row)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.update_todo(
        todo_id=TODO_ID,
        text="Buy trail running shoes",
        ctx=_fake_context("Bearer faketoken"),
    )

    assert result["found"] is True
    assert result["text"] == "Buy trail running shoes"
    assert result["id"] == TODO_ID
    assert captured["user_id"] == USER_ID
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "UPDATE todos" in executed_query
    assert executed_params[0] == "Buy trail running shoes"
    assert fake_connection.committed is True


@pytest.mark.asyncio
async def test_update_todo_returns_found_false_without_raising_when_no_row_matches(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.update_todo(
        todo_id=TODO_ID,
        text="Some new text",
        ctx=_fake_context("Bearer faketoken"),
    )

    assert result == {"found": False, "error": "todo not found or not owned by the caller"}
    assert fake_connection.committed is True


@pytest.mark.asyncio
async def test_update_todo_rejects_blank_text_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.update_todo(
            todo_id=TODO_ID,
            text="   ",
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_update_todo_rejects_malformed_todo_id_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.update_todo(
            todo_id="not-a-uuid",
            text="Some new text",
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_update_todo_rejects_missing_authorization_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.update_todo(
            todo_id=TODO_ID,
            text="Some new text",
            ctx=_fake_context(None),
        )

    assert fake_connection.cursor_instance.executed == []


# --- toggle_todo -----------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_todo_flips_incomplete_to_complete(monkeypatch):
    row = _todo_row(done=True)
    fake_connection, captured = _patch_db(monkeypatch, row=row)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.toggle_todo(todo_id=TODO_ID, ctx=_fake_context("Bearer faketoken"))

    assert result["done"] is True
    assert captured["user_id"] == USER_ID
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "UPDATE todos" in executed_query
    assert "NOT done" in executed_query
    assert executed_params == (TODO_ID,)
    assert fake_connection.committed is True


@pytest.mark.asyncio
async def test_toggle_todo_flips_complete_to_incomplete(monkeypatch):
    row = _todo_row(done=False)
    fake_connection, _ = _patch_db(monkeypatch, row=row)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.toggle_todo(todo_id=TODO_ID, ctx=_fake_context("Bearer faketoken"))

    assert result["done"] is False
    assert fake_connection.committed is True


@pytest.mark.asyncio
async def test_toggle_todo_raises_when_no_row_matches(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.toggle_todo(todo_id=TODO_ID, ctx=_fake_context("Bearer faketoken"))

    assert fake_connection.committed is False


@pytest.mark.asyncio
async def test_toggle_todo_rejects_malformed_todo_id_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.toggle_todo(todo_id="not-a-uuid", ctx=_fake_context("Bearer faketoken"))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_toggle_todo_rejects_missing_authorization_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.toggle_todo(todo_id=TODO_ID, ctx=_fake_context(None))

    assert fake_connection.cursor_instance.executed == []


# --- delete_todo -----------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_todo_returns_deleted_true_when_row_removed(monkeypatch):
    fake_connection, captured = _patch_db(monkeypatch, row=(TODO_ID,))
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.delete_todo(todo_id=TODO_ID, ctx=_fake_context("Bearer faketoken"))

    assert result == {"deleted": True, "todo_id": TODO_ID}
    assert captured["user_id"] == USER_ID
    executed_query, _ = fake_connection.cursor_instance.executed[0]
    assert "DELETE FROM todos" in executed_query
    assert fake_connection.committed is True


@pytest.mark.asyncio
async def test_delete_todo_is_a_no_op_and_returns_deleted_false_when_not_owned_or_missing(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.delete_todo(todo_id=TODO_ID, ctx=_fake_context("Bearer faketoken"))

    assert result == {"deleted": False, "todo_id": TODO_ID}
    # No effect: the only statement issued is the DELETE itself, and it
    # affected no row (None returned), but commit still runs as a no-op —
    # there is nothing left to roll back.
    assert len(fake_connection.cursor_instance.executed) == 1


@pytest.mark.asyncio
async def test_delete_todo_rejects_malformed_todo_id_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.delete_todo(todo_id="not-a-uuid", ctx=_fake_context("Bearer faketoken"))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_delete_todo_rejects_missing_authorization_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, row=None)
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.delete_todo(todo_id=TODO_ID, ctx=_fake_context(None))

    assert fake_connection.cursor_instance.executed == []


# --- list_todos ------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_todos_returns_todos_ordered_by_sort_order_ascending(monkeypatch):
    rows = [
        _todo_row(todo_id=TODO_ID, text="First", sort_order=0),
        _todo_row(todo_id=TODO_ID_2, text="Second", sort_order=1),
        _todo_row(todo_id=TODO_ID_3, text="Third", sort_order=2),
    ]
    fake_connection, captured = _patch_db(monkeypatch, rows=rows)
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.list_todos(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert [todo["text"] for todo in result["todos"]] == ["First", "Second", "Third"]
    assert [todo["sort_order"] for todo in result["todos"]] == [0, 1, 2]
    assert captured["user_id"] == USER_ID
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "ORDER BY sort_order ASC" in executed_query
    assert executed_params[0] == GOAL_ID


@pytest.mark.asyncio
async def test_list_todos_returns_empty_list_for_goal_with_no_todos(monkeypatch):
    _patch_db(monkeypatch, rows=[])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    result = await mcp_server.list_todos(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert result == {"todos": []}


@pytest.mark.asyncio
async def test_list_todos_rejects_malformed_goal_id_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, rows=[])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.list_todos(goal_id="not-a-uuid", ctx=_fake_context("Bearer faketoken"))

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_list_todos_rejects_missing_authorization_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, rows=[])
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.list_todos(goal_id=GOAL_ID, ctx=_fake_context(None))

    assert fake_connection.cursor_instance.executed == []


# --- reorder_todos ----------------------------------------------------------


@pytest.mark.asyncio
async def test_reorder_todos_rewrites_sort_order_to_match_given_order_in_one_transaction(monkeypatch):
    fake_connection, captured = _patch_sequential_db(monkeypatch, rows=[None, None, None])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    new_order = [TODO_ID_3, TODO_ID, TODO_ID_2]
    result = await mcp_server.reorder_todos(
        goal_id=GOAL_ID,
        todo_ids=new_order,
        ctx=_fake_context("Bearer faketoken"),
    )

    assert result == {"goal_id": GOAL_ID, "todo_ids": new_order}
    assert captured["user_id"] == USER_ID
    assert len(fake_connection.cursor_instance.executed) == 3
    for position, (executed_query, executed_params) in enumerate(fake_connection.cursor_instance.executed):
        assert "UPDATE todos" in executed_query
        assert "SET sort_order" in executed_query
        assert executed_params[0] == position
        assert executed_params[1] == new_order[position]
        assert executed_params[2] == GOAL_ID
    assert fake_connection.committed is True


@pytest.mark.asyncio
async def test_reorder_todos_subsequent_list_todos_reflects_the_new_order(monkeypatch):
    # Simulates the AC6 "subsequent list_todos reflects the new order"
    # requirement end-to-end: reorder_todos is called first (against its
    # own fake connection), then list_todos is called against a second
    # fake connection pre-seeded with rows already in the new order — the
    # same way the real `sort_order ASC` query would return them after a
    # real reorder commit.
    reorder_connection, _ = _patch_sequential_db(monkeypatch, rows=[None, None])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    new_order = [TODO_ID_2, TODO_ID]
    await mcp_server.reorder_todos(goal_id=GOAL_ID, todo_ids=new_order, ctx=_fake_context("Bearer faketoken"))
    assert reorder_connection.committed is True

    reordered_rows = [
        _todo_row(todo_id=TODO_ID_2, text="Second", sort_order=0),
        _todo_row(todo_id=TODO_ID, text="First", sort_order=1),
    ]
    _patch_db(monkeypatch, rows=reordered_rows)

    listed = await mcp_server.list_todos(goal_id=GOAL_ID, ctx=_fake_context("Bearer faketoken"))

    assert [todo["id"] for todo in listed["todos"]] == [TODO_ID_2, TODO_ID]


@pytest.mark.asyncio
async def test_reorder_todos_raises_and_does_not_commit_when_a_todo_id_does_not_match(monkeypatch):
    # The second UPDATE affects zero rows (todo_id not found / belongs to a
    # different goal) — reorder_todos must raise rather than silently
    # reporting success with a partially-applied reorder.
    fake_connection, _ = _patch_sequential_db(monkeypatch, rows=[None, None, None], rowcounts=[1, 0, 1])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.reorder_todos(
            goal_id=GOAL_ID,
            todo_ids=[TODO_ID, TODO_ID_2, TODO_ID_3],
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.committed is False
    # Stops at the first mismatch — the third id's UPDATE is never issued.
    assert len(fake_connection.cursor_instance.executed) == 2


@pytest.mark.asyncio
async def test_reorder_todos_rejects_missing_authorization_before_db_call(monkeypatch):
    fake_connection, _ = _patch_sequential_db(monkeypatch, rows=[])
    _patch_auth(monkeypatch, side_effect=PermissionError("unauthorized"))
    _patch_rate_limit(monkeypatch)

    with pytest.raises(PermissionError):
        await mcp_server.reorder_todos(
            goal_id=GOAL_ID,
            todo_ids=[TODO_ID],
            ctx=_fake_context(None),
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_reorder_todos_rejects_malformed_goal_id_before_db_call(monkeypatch):
    fake_connection, _ = _patch_sequential_db(monkeypatch, rows=[])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.reorder_todos(
            goal_id="not-a-uuid",
            todo_ids=[TODO_ID],
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_reorder_todos_rejects_malformed_todo_id_in_list_before_db_call(monkeypatch):
    fake_connection, _ = _patch_sequential_db(monkeypatch, rows=[])
    _patch_auth(monkeypatch)
    _patch_rate_limit(monkeypatch)

    with pytest.raises(ValueError):
        await mcp_server.reorder_todos(
            goal_id=GOAL_ID,
            todo_ids=[TODO_ID, "not-a-uuid"],
            ctx=_fake_context("Bearer faketoken"),
        )

    assert fake_connection.cursor_instance.executed == []


# --- Pydantic schema validation (TodoCreate / TodoUpdate) ------------------


def test_todo_create_rejects_blank_text():
    from pydantic import ValidationError

    from app.schemas import TodoCreate

    with pytest.raises(ValidationError):
        TodoCreate(goal_id=GOAL_ID, text="   ")


def test_todo_create_strips_surrounding_whitespace():
    from app.schemas import TodoCreate

    todo = TodoCreate(goal_id=GOAL_ID, text="  Buy running shoes  ")

    assert todo.text == "Buy running shoes"


def test_todo_update_rejects_blank_text():
    from pydantic import ValidationError

    from app.schemas import TodoUpdate

    with pytest.raises(ValidationError):
        TodoUpdate(text="")


def test_todo_update_strips_surrounding_whitespace():
    from app.schemas import TodoUpdate

    todo = TodoUpdate(text="  Buy trail shoes  ")

    assert todo.text == "Buy trail shoes"


# --- tool descriptions / signatures -----------------------------------


def test_all_six_todo_tools_are_registered_on_the_mcp_singleton():
    tools = mcp_server.mcp._tool_manager._tools

    for tool_name in ("create_todo", "update_todo", "toggle_todo", "delete_todo", "list_todos", "reorder_todos"):
        assert tool_name in tools
