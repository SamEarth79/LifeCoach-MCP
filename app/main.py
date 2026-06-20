from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.db import check_connectivity, get_rls_connection
from app.schemas import GoalCreate, GoalResponse, GoalUpdate

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


@app.post("/goals", status_code=status.HTTP_201_CREATED, response_model=GoalResponse)
async def create_goal(
    goal: GoalCreate,
    _rate_limit: None = Depends(enforce_rate_limit),
    current_user: CurrentUser = Depends(get_current_user),
) -> GoalResponse:
    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO goals (user_id, title, description)
                VALUES (%s, %s, %s)
                RETURNING id, title, description, created_at, updated_at
                """,
                (current_user.id, goal.title, goal.description),
            )
            row = await cursor.fetchone()
        await conn.commit()

    goal_id, title, description, created_at, updated_at = row
    return GoalResponse(
        id=str(goal_id),
        title=title,
        description=description,
        created_at=created_at.isoformat(),
        updated_at=updated_at.isoformat(),
    )


@app.get("/goals", response_model=list[GoalResponse])
async def list_goals(
    _rate_limit: None = Depends(enforce_rate_limit),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[GoalResponse]:
    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id, title, description, created_at, updated_at
                FROM goals
                ORDER BY created_at DESC
                """
            )
            rows = await cursor.fetchall()

    return [
        GoalResponse(
            id=str(goal_id),
            title=title,
            description=description,
            created_at=created_at.isoformat(),
            updated_at=updated_at.isoformat(),
        )
        for goal_id, title, description, created_at, updated_at in rows
    ]


@app.patch("/goals/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: str,
    goal_update: GoalUpdate,
    _rate_limit: None = Depends(enforce_rate_limit),
    current_user: CurrentUser = Depends(get_current_user),
) -> GoalResponse:
    update_fields = goal_update.model_dump(exclude_unset=True)

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            if not update_fields:
                await cursor.execute(
                    """
                    SELECT id, title, description, created_at, updated_at
                    FROM goals
                    WHERE id = %s
                    """,
                    (goal_id,),
                )
            else:
                set_clause = ", ".join(f"{column} = %s" for column in update_fields)
                await cursor.execute(
                    f"""
                    UPDATE goals
                    SET {set_clause}, updated_at = now()
                    WHERE id = %s
                    RETURNING id, title, description, created_at, updated_at
                    """,
                    (*update_fields.values(), goal_id),
                )
            row = await cursor.fetchone()
            if row is not None and update_fields:
                await conn.commit()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")

    goal_id, title, description, created_at, updated_at = row
    return GoalResponse(
        id=str(goal_id),
        title=title,
        description=description,
        created_at=created_at.isoformat(),
        updated_at=updated_at.isoformat(),
    )


@app.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: str,
    _rate_limit: None = Depends(enforce_rate_limit),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE goals
                SET deleted_at = now()
                WHERE id = %s AND deleted_at IS NULL
                RETURNING id
                """,
                (goal_id,),
            )
            row = await cursor.fetchone()
            if row is not None:
                await conn.commit()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
