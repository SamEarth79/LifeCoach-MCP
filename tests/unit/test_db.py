from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import psycopg
import pytest

from app import db


class _FakeCursor:
    async def execute(self, *_args, **_kwargs):
        return None

    async def fetchone(self):
        return (1,)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class _FakeConnection:
    def cursor(self):
        return _FakeCursor()


class _RecordingCursor:
    def __init__(self, recorder):
        self._recorder = recorder

    async def execute(self, query, params=None):
        self._recorder.append((query, params))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class _RecordingConnection:
    def __init__(self, recorder):
        self._recorder = recorder

    def cursor(self):
        return _RecordingCursor(self._recorder)


@pytest.mark.asyncio
async def test_check_connectivity_returns_true_when_query_succeeds(monkeypatch):
    @asynccontextmanager
    async def fake_get_connection():
        yield _FakeConnection()

    monkeypatch.setattr(db, "get_connection", fake_get_connection)

    assert await db.check_connectivity() is True


@pytest.mark.asyncio
async def test_check_connectivity_returns_false_when_connection_fails(monkeypatch):
    @asynccontextmanager
    async def failing_get_connection():
        raise psycopg.OperationalError("connection refused")
        yield  # pragma: no cover - unreachable, satisfies generator shape

    monkeypatch.setattr(db, "get_connection", failing_get_connection)

    assert await db.check_connectivity() is False


@pytest.mark.asyncio
async def test_check_connectivity_returns_false_on_query_error(monkeypatch):
    class _FailingCursor(_FakeCursor):
        async def execute(self, *_args, **_kwargs):
            raise psycopg.errors.UndefinedTable("relation does not exist")

    class _FailingConnection:
        def cursor(self):
            return _FailingCursor()

    @asynccontextmanager
    async def fake_get_connection():
        yield _FailingConnection()

    monkeypatch.setattr(db, "get_connection", fake_get_connection)

    assert await db.check_connectivity() is False


@pytest.mark.asyncio
async def test_get_rls_connection_sets_role_and_jwt_claim_before_yielding(monkeypatch):
    executed_queries = []
    user_id = "11111111-1111-1111-1111-111111111111"

    @asynccontextmanager
    async def fake_get_connection():
        yield _RecordingConnection(executed_queries)

    monkeypatch.setattr(db, "get_connection", fake_get_connection)

    async with db.get_rls_connection(user_id) as conn:
        assert isinstance(conn, _RecordingConnection)

    assert executed_queries == [
        ("SET LOCAL ROLE authenticated", None),
        ("SELECT set_config('request.jwt.claim.sub', %s, true)", (user_id,)),
    ]
