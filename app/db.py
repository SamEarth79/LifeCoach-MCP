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


async def check_connectivity() -> bool:
    try:
        async with get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1")
                await cursor.fetchone()
        return True
    except psycopg.Error:
        return False
