import logging
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.db import check_connectivity, get_rls_connection
from app.mcp_server import mcp
from app.oauth_consent import render_oauth_consent_page
from app.rate_limit import get_client_ip, limiter, per_ip_rate_limit, settings
from app.schemas import GoalCreate, GoalResponse, GoalUpdate

logger = logging.getLogger(__name__)

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
    goal_id: UUID,
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

    row_id, title, description, created_at, updated_at = row
    return GoalResponse(
        id=str(row_id),
        title=title,
        description=description,
        created_at=created_at.isoformat(),
        updated_at=updated_at.isoformat(),
    )


@app.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: UUID,
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


@app.get("/.well-known/oauth-authorization-server")
async def oauth_metadata(request: Request) -> dict:
    """Mirror Supabase's real OAuth authorization server metadata.

    Previously hand-copied a subset of fields into a static dict, which
    silently omitted `token_endpoint_auth_methods_supported` and drifted
    from Supabase's actual metadata whenever it changed. Fetching live
    means this can never go stale and always reflects exactly what
    Supabase's real token endpoint actually accepts.
    """
    app_settings = get_settings()
    metadata_url = f"{app_settings.supabase_url}/auth/v1/.well-known/oauth-authorization-server"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(metadata_url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch Supabase OAuth metadata from %s: %s", metadata_url, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OAuth metadata is temporarily unavailable",
            ) from exc

    return response.json()


@app.get("/authorize")
async def authorize_redirect(request: Request) -> RedirectResponse:
    app_settings = get_settings()
    supabase_authorize_url = f"{app_settings.supabase_url}/auth/v1/oauth/authorize"
    query = request.url.query
    if query:
        supabase_authorize_url += "?" + query
    return RedirectResponse(url=supabase_authorize_url)


@app.get("/oauth/consent", response_class=HTMLResponse)
async def get_oauth_consent_page() -> str:
    app_settings = get_settings()
    return render_oauth_consent_page(app_settings.supabase_url, app_settings.supabase_anon_key)


mcp_asgi_app = mcp.streamable_http_app()
app.mount("/mcp", mcp_asgi_app)
app.router.lifespan_context = mcp_asgi_app.router.lifespan_context
