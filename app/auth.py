import logging

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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


def _decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        logger.warning("JWT verification failed: expired token")
        raise _unauthorized()
    except jwt.InvalidSignatureError:
        logger.warning("JWT verification failed: invalid signature")
        raise _unauthorized()
    except jwt.InvalidTokenError:
        logger.warning("JWT verification failed: malformed or invalid token")
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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        logger.warning("JWT verification failed: missing or malformed Authorization header")
        raise _unauthorized()

    payload = _decode_token(credentials.credentials)

    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id or not email:
        logger.warning("JWT verification failed: missing sub or email claim")
        raise _unauthorized()

    await _ensure_user_row_exists(user_id, email)

    return CurrentUser(id=user_id, email=email)
