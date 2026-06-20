from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from psycopg import AsyncConnection

from app.config import get_settings


@asynccontextmanager
async def get_connection() -> AsyncIterator[AsyncConnection]:
    settings = get_settings()
    conn = await psycopg.AsyncConnection.connect(settings.database_url)
    try:
        yield conn
    finally:
        await conn.close()


@asynccontextmanager
async def get_rls_connection(user_id: str) -> AsyncIterator[AsyncConnection]:
    """Connection scoped to one verified user, with RLS enforced.

    DATABASE_URL connects as the `postgres` role, which has BYPASSRLS.
    Switching to `authenticated` and setting `request.jwt.claim.sub` makes
    `auth.uid()` resolve correctly inside RLS policies, matching how
    PostgREST itself executes authenticated requests.
    """
    async with get_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SET LOCAL ROLE authenticated")
            await cursor.execute(
                "SELECT set_config('request.jwt.claim.sub', %s, true)", (user_id,)
            )
        yield conn


async def check_connectivity() -> bool:
    try:
        async with get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1")
                await cursor.fetchone()
        return True
    except psycopg.Error:
        return False
