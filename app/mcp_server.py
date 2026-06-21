import logging
from uuid import UUID

from mcp.server.fastmcp import Context, FastMCP
from pydantic import ValidationError

from app.auth import verify_bearer_token
from app.config import get_settings
from app.db import get_rls_connection
from app.rate_limit import enforce_mcp_rate_limit
from app.schemas import GoalProgressUpdate, UpdateCreate, UpdateListItem

logger = logging.getLogger(__name__)

settings = get_settings()

mcp = FastMCP("lifecoach", streamable_http_path="/")


@mcp.tool(
    description=(
        "Record a coaching update for one of the user's goals. Call this "
        "tool only once you and the user have settled on something "
        "concrete to record — not after every message in the "
        "conversation. Write a concise summary of the agreed outcome "
        "into `content`; do not paste the raw conversation. Optionally "
        "include a `transcript` only when full fidelity is genuinely "
        "needed."
    )
)
async def record_update(
    goal_id: str,
    content: str,
    ctx: Context,
    transcript: str | None = None,
) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        update = UpdateCreate(goal_id=goal_id, content=content, transcript=transcript)
    except ValidationError as exc:
        logger.warning("record_update validation failed: %s", exc)
        raise ValueError(str(exc)) from exc

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO updates (user_id, goal_id, content, transcript)
                VALUES (%s, %s, %s, %s)
                RETURNING id, goal_id, content, source, created_at
                """,
                (current_user.id, str(update.goal_id), update.content, update.transcript),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError(
                    "goal_id does not exist, is not owned by the caller, or is deleted"
                )
        await conn.commit()

    update_id, returned_goal_id, returned_content, source, created_at = row
    return {
        "id": str(update_id),
        "goal_id": str(returned_goal_id),
        "content": returned_content,
        "source": source,
        "created_at": created_at.isoformat(),
    }


@mcp.tool(
    description=(
        "Retrieve past updates recorded for one of the user's goals, for "
        "use as context in an ongoing coaching conversation. Returns each "
        "update's `content`, `source`, and `created_at` — never the full "
        "transcript, so this stays cheap to call repeatedly regardless of "
        "how many updates have accumulated."
    )
)
async def list_updates(goal_id: str, ctx: Context) -> list[dict]:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        validated_goal_id = UUID(goal_id)
    except ValueError as exc:
        logger.warning("list_updates validation failed: %s", exc)
        raise ValueError("goal_id must be a valid UUID") from exc

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT content, source, created_at
                FROM updates
                WHERE goal_id = %s
                ORDER BY created_at DESC
                """,
                (str(validated_goal_id),),
            )
            rows = await cursor.fetchall()

    return [
        UpdateListItem(
            content=content,
            source=source,
            created_at=created_at.isoformat(),
        ).model_dump()
        for content, source, created_at in rows
    ]


@mcp.tool(
    description=(
        "Record your own periodic self-assessment of progress (0-100) on "
        "one of the user's goals, after a conversation where you judge "
        "progress changed. This is for your own internal bookkeeping, not "
        "a user-facing action — the rendered UI never calls this tool "
        "directly, and you should not present calling it as something the "
        "user asked for or needs to confirm."
    )
)
async def set_goal_progress(
    goal_id: str,
    percentage: int,
    ctx: Context,
    rationale: str | None = None,
) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        progress_update = GoalProgressUpdate(
            goal_id=goal_id, percentage=percentage, rationale=rationale
        )
    except ValidationError as exc:
        logger.warning("set_goal_progress validation failed: %s", exc)
        raise ValueError(str(exc)) from exc

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE goals
                SET progress_percent = %s
                WHERE id = %s
                RETURNING id
                """,
                (progress_update.percentage, str(progress_update.goal_id)),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError(
                    "goal_id does not exist, is not owned by the caller, or is deleted"
                )
        await conn.commit()

    return {
        "goal_id": str(progress_update.goal_id),
        "percentage": progress_update.percentage,
    }
