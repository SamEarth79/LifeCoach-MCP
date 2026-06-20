from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.db import check_connectivity, get_connection

settings = get_settings()
per_ip_rate_limit = f"{settings.rate_limit_requests}/{settings.rate_limit_window_seconds}second"

limiter = Limiter(key_func=get_remote_address, default_limits=[per_ip_rate_limit])

app = FastAPI(title="LifeCoach API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/health")
async def health(response: Response) -> dict:
    is_db_reachable = await check_connectivity()
    if not is_db_reachable:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "database": "unreachable"}

    return {"status": "healthy", "database": "reachable"}


@app.get("/users/me")
@limiter.limit(per_ip_rate_limit)
async def get_my_profile(
    request: Request, current_user: CurrentUser = Depends(get_current_user)
) -> dict:
    async with get_connection() as conn:
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
