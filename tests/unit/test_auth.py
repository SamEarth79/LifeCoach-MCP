import logging
from contextlib import asynccontextmanager

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app import auth
from app.config import get_settings

USER_ID = "11111111-1111-1111-1111-111111111111"
EMAIL = "user@example.com"

_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_OTHER_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


def _make_token(private_key=_PRIVATE_KEY, **overrides):
    payload = {"sub": USER_ID, "email": EMAIL, "aud": "authenticated"}
    payload.update(overrides)
    return jwt.encode(payload, private_key, algorithm="ES256")


def _credentials(token, scheme="Bearer"):
    return HTTPAuthorizationCredentials(scheme=scheme, credentials=token)


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def __init__(self, key=_PUBLIC_KEY):
        self._key = key

    def get_signing_key_from_jwt(self, _token):
        return _FakeSigningKey(self._key)


class _FakeCursor:
    def __init__(self, recorder):
        self._recorder = recorder

    async def execute(self, query, params):
        self._recorder.append((query, params))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class _FakeConnection:
    def __init__(self, recorder):
        self._recorder = recorder
        self.committed = False

    def cursor(self):
        return _FakeCursor(self._recorder)

    async def commit(self):
        self.committed = True


@pytest.fixture(autouse=True)
def _env_settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch):
    monkeypatch.setattr(auth, "_get_jwks_client", lambda jwks_url: _FakeJWKSClient())


def _patch_db(monkeypatch):
    executed_queries = []
    connections = []

    @asynccontextmanager
    async def fake_get_rls_connection(_user_id):
        conn = _FakeConnection(executed_queries)
        connections.append(conn)
        yield conn

    monkeypatch.setattr(auth, "get_rls_connection", fake_get_rls_connection)
    return executed_queries, connections


@pytest.mark.asyncio
async def test_valid_token_returns_current_user_and_upserts_row(monkeypatch):
    executed_queries, connections = _patch_db(monkeypatch)
    token = _make_token()

    user = await auth.get_current_user(_credentials(token))

    assert user.id == USER_ID
    assert user.email == EMAIL
    assert len(executed_queries) == 1
    query, params = executed_queries[0]
    assert "INSERT INTO users" in query
    assert "ON CONFLICT (id) DO NOTHING" in query
    assert params == (USER_ID, EMAIL)
    assert connections[0].committed is True


@pytest.mark.asyncio
async def test_expired_token_raises_401_before_any_db_call(monkeypatch):
    executed_queries, _ = _patch_db(monkeypatch)
    token = _make_token(exp=0)

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_credentials(token))

    assert exc_info.value.status_code == 401
    assert executed_queries == []


@pytest.mark.asyncio
async def test_malformed_token_raises_401(monkeypatch):
    executed_queries, _ = _patch_db(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_credentials("not-a-jwt"))

    assert exc_info.value.status_code == 401
    assert executed_queries == []


@pytest.mark.asyncio
async def test_missing_authorization_header_raises_401(monkeypatch):
    executed_queries, _ = _patch_db(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(None)

    assert exc_info.value.status_code == 401
    assert executed_queries == []


@pytest.mark.asyncio
async def test_tampered_signature_raises_401(monkeypatch):
    executed_queries, _ = _patch_db(monkeypatch)
    token = _make_token(private_key=_OTHER_PRIVATE_KEY)

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_credentials(token))

    assert exc_info.value.status_code == 401
    assert executed_queries == []


@pytest.mark.asyncio
async def test_non_bearer_scheme_raises_401(monkeypatch):
    executed_queries, _ = _patch_db(monkeypatch)
    token = _make_token()

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_credentials(token, scheme="Basic"))

    assert exc_info.value.status_code == 401
    assert executed_queries == []


@pytest.mark.asyncio
async def test_token_missing_sub_or_email_raises_401(monkeypatch):
    executed_queries, _ = _patch_db(monkeypatch)
    payload = {"aud": "authenticated"}
    token = jwt.encode(payload, _PRIVATE_KEY, algorithm="ES256")

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_credentials(token))

    assert exc_info.value.status_code == 401
    assert executed_queries == []


@pytest.mark.asyncio
async def test_unresolvable_signing_key_raises_401(monkeypatch):
    executed_queries, _ = _patch_db(monkeypatch)

    def _raise_jwks_error(_jwks_url):
        class _BrokenJWKSClient:
            def get_signing_key_from_jwt(self, _token):
                raise jwt.PyJWKClientError("no matching key")

        return _BrokenJWKSClient()

    monkeypatch.setattr(auth, "_get_jwks_client", _raise_jwks_error)
    token = _make_token()

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_credentials(token))

    assert exc_info.value.status_code == 401
    assert executed_queries == []


@pytest.mark.asyncio
async def test_failed_auth_does_not_log_token_value(monkeypatch, caplog):
    _patch_db(monkeypatch)
    token = _make_token(exp=0)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(HTTPException):
            await auth.get_current_user(_credentials(token))

    log_output = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in log_output


@pytest.mark.asyncio
async def test_failed_auth_does_not_log_email_or_pii(monkeypatch, caplog):
    _patch_db(monkeypatch)
    token = _make_token(private_key=_OTHER_PRIVATE_KEY)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(HTTPException):
            await auth.get_current_user(_credentials(token))

    log_output = "\n".join(record.getMessage() for record in caplog.records)
    assert EMAIL not in log_output
    assert token not in log_output
