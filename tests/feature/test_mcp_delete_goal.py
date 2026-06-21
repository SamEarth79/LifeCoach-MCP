"""End-to-end feature test for the delete_goal MCP tool.

Drives the actual mounted ASGI app through the real MCP streamable-HTTP
wire protocol (initialize -> notifications/initialized -> tools/call), the
same way `test_mcp_get_home_view.py` exercises `get_home_view` — this proves
the Authorization header genuinely reaches the tool handler via the live
HTTP request the MCP SDK constructs from the ASGI scope, and that the
tool's refreshed-home-view `EmbeddedResource` response actually serializes
over the wire.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI

from app import auth, mcp_server

USER_ID = "11111111-1111-1111-1111-111111111111"
GOAL_ID = "33333333-3333-3333-3333-333333333333"
SURVIVING_GOAL_ID = "44444444-4444-4444-4444-444444444444"
EMAIL = "user@example.com"
CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)

_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC_KEY = _PRIVATE_KEY.public_key()


def _make_token(**overrides):
    payload = {"sub": USER_ID, "email": EMAIL, "aud": "authenticated"}
    payload.update(overrides)
    return jwt.encode(payload, _PRIVATE_KEY, algorithm="ES256")


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def get_signing_key_from_jwt(self, _token):
        return _FakeSigningKey(_PUBLIC_KEY)


class _DeleteThenRefreshCursor:
    """Mirrors `tests/unit/test_mcp_server.py::_DeleteThenRefreshCursor`:
    first `fetchone()` answers the `UPDATE ... RETURNING id` soft delete,
    subsequent calls answer the `_fetch_home_view_data` refresh queries.
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


@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch):
    monkeypatch.setattr(auth, "_get_jwks_client", lambda jwks_url: _FakeJWKSClient())


def _patch_db(monkeypatch, delete_row, refresh_responses=None):
    fake_connection = _DeleteThenRefreshConnection(delete_row, refresh_responses)
    captured = {}

    @asynccontextmanager
    async def fake_get_rls_connection(user_id):
        captured["user_id"] = user_id
        yield fake_connection

    monkeypatch.setattr(auth, "get_rls_connection", fake_get_rls_connection)
    monkeypatch.setattr(mcp_server, "get_rls_connection", fake_get_rls_connection)
    return fake_connection, captured


def _patch_user_upsert(monkeypatch):
    async def _noop_ensure_user_row_exists(_user_id, _email):
        return None

    monkeypatch.setattr(auth, "_ensure_user_row_exists", _noop_ensure_user_row_exists)


async def _call_delete_goal_tool(client: httpx.AsyncClient, authorization: str | None, arguments: dict):
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
    }
    if authorization is not None:
        headers["authorization"] = authorization

    init_response = await client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        },
    )
    session_id = init_response.headers["mcp-session-id"]
    session_headers = {**headers, "mcp-session-id": session_id}

    await client.post(
        "/mcp",
        headers=session_headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )

    return await client.post(
        "/mcp",
        headers=session_headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "delete_goal", "arguments": arguments},
        },
    )


@asynccontextmanager
async def _mcp_client():
    """See `test_mcp_get_home_view.py::_mcp_client` for why a fresh
    `FastMCP` instance is built per test rather than reusing the
    process-wide singleton, and why `base_url` needs an explicit port.
    """
    from mcp.server.fastmcp import FastMCP

    test_mcp = FastMCP("lifecoach-test")
    test_mcp.add_tool(
        mcp_server.delete_goal,
        name="delete_goal",
        description=mcp_server.mcp._tool_manager._tools["delete_goal"].description,
    )

    test_app = FastAPI()
    mcp_asgi_app = test_mcp.streamable_http_app()
    test_app.mount("/", mcp_asgi_app)
    test_app.router.lifespan_context = mcp_asgi_app.router.lifespan_context

    transport = httpx.ASGITransport(app=test_app)
    async with test_app.router.lifespan_context(test_app):
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
            yield client


@pytest.mark.asyncio
async def test_delete_goal_through_live_mcp_transport_returns_refreshed_home_view_excluding_deleted_goal(
    monkeypatch,
):
    refresh_responses = [
        ("Sam", EMAIL),
        [(SURVIVING_GOAL_ID, "Read a book", 10)],
        [],
    ]
    fake_connection, captured = _patch_db(monkeypatch, (GOAL_ID,), refresh_responses)
    _patch_user_upsert(monkeypatch)
    token = _make_token()

    async with _mcp_client() as client:
        response = await _call_delete_goal_tool(client, f"Bearer {token}", {"goal_id": GOAL_ID})

    assert response.status_code == 200
    body_text = response.text
    assert '"isError":true' not in body_text
    assert "text/html" in body_text
    assert "Read a book" in body_text
    assert GOAL_ID not in body_text
    assert fake_connection.committed is True
    assert captured["user_id"] == USER_ID

    delete_query, _ = fake_connection.cursor_instance.executed[0]
    assert "UPDATE goals" in delete_query
    assert "DELETE FROM" not in delete_query.upper()


@pytest.mark.asyncio
async def test_delete_goal_through_live_mcp_transport_rejects_missing_jwt_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_user_upsert(monkeypatch)

    async with _mcp_client() as client:
        response = await _call_delete_goal_tool(client, None, {"goal_id": GOAL_ID})

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_delete_goal_through_live_mcp_transport_rejects_expired_jwt_before_db_call(monkeypatch):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_user_upsert(monkeypatch)
    token = _make_token(exp=0)

    async with _mcp_client() as client:
        response = await _call_delete_goal_tool(client, f"Bearer {token}", {"goal_id": GOAL_ID})

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_delete_goal_through_live_mcp_transport_fails_cleanly_for_nonexistent_or_already_deleted_goal(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_user_upsert(monkeypatch)
    token = _make_token()

    async with _mcp_client() as client:
        response = await _call_delete_goal_tool(client, f"Bearer {token}", {"goal_id": GOAL_ID})

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.committed is False
    assert len(fake_connection.cursor_instance.executed) == 1


@pytest.mark.asyncio
async def test_delete_goal_through_live_mcp_transport_rejects_malformed_goal_id_before_db_call(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_user_upsert(monkeypatch)
    token = _make_token()

    async with _mcp_client() as client:
        response = await _call_delete_goal_tool(client, f"Bearer {token}", {"goal_id": "not-a-uuid"})

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []
