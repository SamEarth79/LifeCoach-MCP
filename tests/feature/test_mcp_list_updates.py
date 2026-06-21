"""End-to-end feature tests for the list_updates MCP tool.

These drive the actual mounted ASGI app through the real MCP
streamable-HTTP wire protocol (initialize -> notifications/initialized ->
tools/call), the same way `test_mcp_record_update.py` exercises
record_update — this proves the Authorization header genuinely reaches the
tool handler via the live HTTP request the MCP SDK constructs from the ASGI
scope, not just that our own code is internally self-consistent with an
assumption about the SDK.
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI

from app import auth, mcp_server
from app.auth import CurrentUser

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
    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    async def execute(self, query, params=None):
        self.executed.append((query, params))

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


@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch):
    monkeypatch.setattr(auth, "_get_jwks_client", lambda jwks_url: _FakeJWKSClient())


def _patch_db(monkeypatch, rows):
    fake_connection = _FakeConnection(rows)
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


def _parse_sse_json(response_text: str) -> dict:
    """Extract the JSON payload from a `text/event-stream` response body.

    The streamable-HTTP transport responds with an SSE-framed body
    (`event: message\\r\\ndata: {...}\\r\\n\\r\\n`) rather than a bare JSON
    document, so `httpx.Response.json()` can't parse it directly.
    """
    for line in response_text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    raise ValueError(f"no SSE data line found in response: {response_text!r}")


async def _call_list_updates_tool(client: httpx.AsyncClient, authorization: str | None, arguments: dict):
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
            "params": {"name": "list_updates", "arguments": arguments},
        },
    )


@asynccontextmanager
async def _mcp_client():
    """An httpx client driving a fresh FastMCP instance through the real
    streamable-HTTP transport, with the production `list_updates` function
    registered on it exactly the way `app.mcp_server` registers it on the
    process-wide `mcp` singleton.

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
        mcp_server.list_updates,
        name="list_updates",
        description=mcp_server.mcp._tool_manager._tools["list_updates"].description,
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
async def test_list_updates_through_live_mcp_transport_returns_content_source_created_at_only(
    monkeypatch,
):
    # The mocked row deliberately contains only the three columns the
    # production SQL selects (content, source, created_at) — there is no
    # transcript column in the row at all, because the real SELECT never
    # fetches it. The tool's JSON-RPC response is asserted to contain
    # exactly those three keys per item and never the word "transcript".
    rows = [("Agreed to run 3x/week", "coaching_update", CREATED_AT)]
    fake_connection, captured = _patch_db(monkeypatch, rows)
    _patch_user_upsert(monkeypatch)
    token = _make_token()

    async with _mcp_client() as client:
        response = await _call_list_updates_tool(client, f"Bearer {token}", {"goal_id": GOAL_ID})

    assert response.status_code == 200
    assert "isError" not in response.text or '"isError":false' in response.text
    assert captured["user_id"] == USER_ID
    assert "transcript" not in response.text.lower()

    body = _parse_sse_json(response.text)
    items = body["result"]["structuredContent"]["result"]
    assert len(items) == 1
    assert set(items[0].keys()) == {"content", "source", "created_at"}
    assert items[0]["content"] == "Agreed to run 3x/week"
    assert items[0]["source"] == "coaching_update"

    executed_query, executed_params = fake_connection.cursor_instance.executed[0]
    assert "SELECT content, source, created_at" in executed_query
    assert executed_params[0] == GOAL_ID


@pytest.mark.asyncio
async def test_list_updates_through_live_mcp_transport_returns_checkin_and_coaching_update_rows(
    monkeypatch,
):
    rows = [
        ("Logged a check-in", "checkin", CREATED_AT),
        ("Agreed to run 3x/week", "coaching_update", CREATED_AT),
    ]
    _patch_db(monkeypatch, rows)
    _patch_user_upsert(monkeypatch)
    token = _make_token()

    async with _mcp_client() as client:
        response = await _call_list_updates_tool(client, f"Bearer {token}", {"goal_id": GOAL_ID})

    assert response.status_code == 200
    body = _parse_sse_json(response.text)
    items = body["result"]["structuredContent"]["result"]
    sources = {item["source"] for item in items}
    assert sources == {"checkin", "coaching_update"}


@pytest.mark.asyncio
async def test_list_updates_through_live_mcp_transport_returns_empty_list_for_goal_with_no_updates(
    monkeypatch,
):
    _patch_db(monkeypatch, [])
    _patch_user_upsert(monkeypatch)
    token = _make_token()

    async with _mcp_client() as client:
        response = await _call_list_updates_tool(client, f"Bearer {token}", {"goal_id": GOAL_ID})

    assert response.status_code == 200
    body = _parse_sse_json(response.text)
    items = body["result"]["structuredContent"]["result"]
    assert items == []


@pytest.mark.asyncio
async def test_list_updates_through_live_mcp_transport_rejects_missing_jwt_before_db_call(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, [])
    _patch_user_upsert(monkeypatch)

    async with _mcp_client() as client:
        response = await _call_list_updates_tool(client, None, {"goal_id": GOAL_ID})

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_list_updates_through_live_mcp_transport_rejects_expired_jwt_before_db_call(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, [])
    _patch_user_upsert(monkeypatch)
    token = _make_token(exp=0)

    async with _mcp_client() as client:
        response = await _call_list_updates_tool(client, f"Bearer {token}", {"goal_id": GOAL_ID})

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_list_updates_through_live_mcp_transport_rejects_malformed_jwt_before_db_call(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, [])
    _patch_user_upsert(monkeypatch)

    async with _mcp_client() as client:
        response = await _call_list_updates_tool(
            client, "Bearer not-a-real-jwt", {"goal_id": GOAL_ID}
        )

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []
