"""End-to-end feature tests for the set_goal_progress MCP tool.

These drive the actual mounted ASGI app through the real MCP
streamable-HTTP wire protocol (initialize -> notifications/initialized ->
tools/call), the same way `test_mcp_record_update.py` and
`test_mcp_list_updates.py` exercise their respective tools — this proves the
Authorization header genuinely reaches the tool handler via the live HTTP
request the MCP SDK constructs from the ASGI scope, not just that our own
code is internally self-consistent with an assumption about the SDK.
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


class _FakeCursor:
    def __init__(self, row):
        self._row = row
        self.executed = []

    async def execute(self, query, params=None):
        self.executed.append((query, params))

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


@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch):
    monkeypatch.setattr(auth, "_get_jwks_client", lambda jwks_url: _FakeJWKSClient())


def _patch_db(monkeypatch, row):
    fake_connection = _FakeConnection(row)
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


async def _call_set_goal_progress_tool(client: httpx.AsyncClient, authorization: str | None, arguments: dict):
    """Drive the real MCP stateful handshake, then call the tool.

    Mirrors `_call_record_update_tool` in `test_mcp_record_update.py`: the
    streamable-HTTP transport is stateful, so a `tools/call` made without
    first completing `initialize` + `notifications/initialized` is
    rejected, the same way a real MCP client must complete the handshake.
    """
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
            "params": {"name": "set_goal_progress", "arguments": arguments},
        },
    )


@asynccontextmanager
async def _mcp_client():
    """An httpx client driving a fresh FastMCP instance through the real
    streamable-HTTP transport, with the production `set_goal_progress`
    function registered on it exactly the way `app.mcp_server` registers it
    on the process-wide `mcp` singleton.

    See `test_mcp_record_update.py::_mcp_client` for why a fresh `FastMCP`
    is built per test rather than reusing the process-wide singleton
    (`StreamableHTTPSessionManager.run()` can only be entered once per
    instance), and why `base_url` must include an explicit port (FastMCP's
    DNS-rebinding `allowed_hosts` patterns only match a `Host` header with
    a literal `:<port>` suffix).
    """
    from mcp.server.fastmcp import FastMCP

    test_mcp = FastMCP("lifecoach-test")
    test_mcp.add_tool(
        mcp_server.set_goal_progress,
        name="set_goal_progress",
        description=mcp_server.mcp._tool_manager._tools["set_goal_progress"].description,
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
async def test_set_goal_progress_through_live_mcp_transport_updates_with_verified_user_id(
    monkeypatch,
):
    row = (GOAL_ID,)
    fake_connection, captured = _patch_db(monkeypatch, row)
    _patch_user_upsert(monkeypatch)
    token = _make_token()

    async with _mcp_client() as client:
        response = await _call_set_goal_progress_tool(
            client,
            f"Bearer {token}",
            {"goal_id": GOAL_ID, "percentage": 42},
        )

    assert response.status_code == 200
    assert "isError" not in response.text or '"isError":false' in response.text
    assert captured["user_id"] == USER_ID
    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "UPDATE goals" in executed_query
    assert executed_params[0] == 42
    assert executed_params[1] == GOAL_ID
    assert fake_connection.committed is True


@pytest.mark.asyncio
async def test_set_goal_progress_through_live_mcp_transport_rejects_missing_jwt_before_db_call(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_user_upsert(monkeypatch)

    async with _mcp_client() as client:
        response = await _call_set_goal_progress_tool(
            client,
            None,
            {"goal_id": GOAL_ID, "percentage": 42},
        )

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_set_goal_progress_through_live_mcp_transport_rejects_expired_jwt_before_db_call(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_user_upsert(monkeypatch)
    token = _make_token(exp=0)

    async with _mcp_client() as client:
        response = await _call_set_goal_progress_tool(
            client,
            f"Bearer {token}",
            {"goal_id": GOAL_ID, "percentage": 42},
        )

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_set_goal_progress_through_live_mcp_transport_rejects_out_of_range_percentage_before_db_call(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, None)
    _patch_user_upsert(monkeypatch)
    token = _make_token()

    async with _mcp_client() as client:
        response = await _call_set_goal_progress_tool(
            client,
            f"Bearer {token}",
            {"goal_id": GOAL_ID, "percentage": 101},
        )

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []
