import logging
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import get_settings
from app.db import get_rls_connection

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, id: str, email: str):
        self.id = id
        self.email = email


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache
def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def _decode_token(token: str) -> dict:
    settings = get_settings()
    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        signing_key = _get_jwks_client(jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
    except jwt.PyJWKClientError:
        logger.warning("JWT verification failed: could not resolve signing key")
        raise _unauthorized()
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT verification failed: %s", type(exc).__name__)
        raise _unauthorized()


async def _ensure_user_row_exists(user_id: str, email: str) -> None:
    async with get_rls_connection(user_id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO users (id, email)
                VALUES (%s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (user_id, email),
            )
        await conn.commit()


async def verify_bearer_token(authorization_header: str | None) -> CurrentUser:
    """Verify a raw `Authorization` header value and resolve the calling user.

    Shared by both the REST `get_current_user` dependency and the MCP tool
    layer, so JWT verification logic exists in exactly one place.
    """
    if authorization_header is None:
        logger.warning("JWT verification failed: missing Authorization header")
        raise _unauthorized()

    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        logger.warning("JWT verification failed: missing or malformed Authorization header")
        raise _unauthorized()

    payload = _decode_token(token)

    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id or not email:
        logger.warning("JWT verification failed: missing sub or email claim")
        raise _unauthorized()

    await _ensure_user_row_exists(user_id, email)

    return CurrentUser(id=user_id, email=email)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        logger.warning("JWT verification failed: missing Authorization header")
        raise _unauthorized()

    return await verify_bearer_token(f"{credentials.scheme} {credentials.credentials}")
