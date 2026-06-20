from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.db import check_connectivity, get_rls_connection

settings = get_settings()
per_ip_rate_limit = f"{settings.rate_limit_requests}/{settings.rate_limit_window_seconds}second"


def get_client_ip(request: Request) -> str:
    """Resolve the client IP for rate limiting.

    The app runs behind the PaaS host's reverse proxy, so the raw TCP peer
    (`request.client.host`) is the proxy, not the client — every request
    would otherwise collapse into a single shared rate-limit bucket.

    The leftmost `X-Forwarded-For` entry is client-supplied and can be
    spoofed (a proxy that appends rather than overwrites would let a
    client inject its own value ahead of the real chain). Only the
    rightmost `trusted_proxy_hops` entries are appended by infrastructure
    we trust; the client IP is the one just before those, which cannot be
    forged because it's appended by our own trusted proxy, not the client.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
        trusted_index = len(hops) - settings.trusted_proxy_hops
        if 0 <= trusted_index < len(hops):
            return hops[trusted_index]
    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip, default_limits=[per_ip_rate_limit])

app = FastAPI(title="LifeCoach API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@limiter.limit(per_ip_rate_limit)
async def enforce_rate_limit(request: Request) -> None:
    """Rate-limit dependency, resolved before any other dependency.

    Applying this as the first `Depends` (rather than `@limiter.limit` on
    the route) ensures the limit is checked before `get_current_user`'s
    DB upsert runs — FastAPI resolves dependencies in declaration order,
    while a route-level decorator only wraps the call after all
    dependencies, including DB-writing ones, have already resolved.
    """
    return None


@app.get("/health")
async def health(response: Response) -> dict:
    is_db_reachable = await check_connectivity()
    if not is_db_reachable:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "database": "unreachable"}

    return {"status": "healthy", "database": "reachable"}


@app.get("/users/me")
async def get_my_profile(
    _rate_limit: None = Depends(enforce_rate_limit),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id, email, display_name, created_at, updated_at
                FROM users
                WHERE id = %s
                """,
                (current_user.id,),
            )
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user_id, email, display_name, created_at, updated_at = row
    if str(user_id) != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return {
        "id": str(user_id),
        "email": email,
        "display_name": display_name,
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }
