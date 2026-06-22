"""End-to-end feature test for the get_goal_detail_view MCP tool.

Drives the actual mounted ASGI app through the real MCP streamable-HTTP
wire protocol (initialize -> notifications/initialized -> tools/call), the
same way `test_mcp_get_home_view.py` exercises `get_home_view` — this proves
the Authorization header genuinely reaches the tool handler via the live
HTTP request the MCP SDK constructs from the ASGI scope, and that the
tool's `dict` response serializes as `TextContent` over the wire.
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


class _SequencedCursor:
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


@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch):
    monkeypatch.setattr(auth, "_get_jwks_client", lambda jwks_url: _FakeJWKSClient())


def _patch_db(monkeypatch, responses):
    fake_connection = _SequencedConnection(responses)
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


async def _call_get_goal_detail_view_tool(
    client: httpx.AsyncClient, authorization: str | None, arguments: dict
):
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
            "params": {"name": "get_goal_detail_view", "arguments": arguments},
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
        mcp_server.get_goal_detail_view,
        name="get_goal_detail_view",
        description=mcp_server.mcp._tool_manager._tools["get_goal_detail_view"].description,
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
async def test_get_goal_detail_view_through_live_mcp_transport_returns_html_resource_with_goal_data(
    monkeypatch,
):
    goal_row = (GOAL_ID, "Run a 5k", "Train three times a week", 42)
    update_rows = [("Ran 3 miles today", CREATED_AT)]
    fake_connection, captured = _patch_db(monkeypatch, [goal_row, update_rows])
    _patch_user_upsert(monkeypatch)
    token = _make_token()

    async with _mcp_client() as client:
        response = await _call_get_goal_detail_view_tool(
            client, f"Bearer {token}", {"goal_id": GOAL_ID}
        )

    assert response.status_code == 200
    body_text = response.text
    assert '"isError":true' not in body_text
    assert "Run a 5k" in body_text
    assert "Train three times a week" in body_text
    assert "Ran 3 miles today" in body_text
    assert "transcript" not in body_text.lower()
    assert '"type":"text"' in body_text
    assert captured["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_get_goal_detail_view_through_live_mcp_transport_returns_failure_resource_for_missing_goal(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, [None])
    _patch_user_upsert(monkeypatch)
    token = _make_token()

    async with _mcp_client() as client:
        response = await _call_get_goal_detail_view_tool(
            client, f"Bearer {token}", {"goal_id": GOAL_ID}
        )

    assert response.status_code == 200
    body_text = response.text
    assert '"isError":true' not in body_text
    assert "Run a 5k" not in body_text
    assert "isn" in body_text.lower()


@pytest.mark.asyncio
async def test_get_goal_detail_view_through_live_mcp_transport_rejects_missing_jwt_before_db_call(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, [])
    _patch_user_upsert(monkeypatch)

    async with _mcp_client() as client:
        response = await _call_get_goal_detail_view_tool(client, None, {"goal_id": GOAL_ID})

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_get_goal_detail_view_through_live_mcp_transport_rejects_expired_jwt_before_db_call(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, [])
    _patch_user_upsert(monkeypatch)
    token = _make_token(exp=0)

    async with _mcp_client() as client:
        response = await _call_get_goal_detail_view_tool(
            client, f"Bearer {token}", {"goal_id": GOAL_ID}
        )

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []


@pytest.mark.asyncio
async def test_get_goal_detail_view_through_live_mcp_transport_rejects_malformed_goal_id_before_db_call(
    monkeypatch,
):
    fake_connection, _ = _patch_db(monkeypatch, [])
    _patch_user_upsert(monkeypatch)
    token = _make_token()

    async with _mcp_client() as client:
        response = await _call_get_goal_detail_view_tool(
            client, f"Bearer {token}", {"goal_id": "not-a-uuid"}
        )

    assert response.status_code == 200
    assert '"isError":true' in response.text
    assert fake_connection.cursor_instance.executed == []
