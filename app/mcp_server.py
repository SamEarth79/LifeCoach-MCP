import logging
from uuid import UUID

from mcp.server.fastmcp import Context, FastMCP

from pydantic import ValidationError

from app.auth import verify_bearer_token
from app.config import get_settings
from app.db import get_rls_connection
from app.rate_limit import enforce_mcp_rate_limit
from app.schemas import GoalProgressUpdate, UpdateCreate, UpdateListItem
from app.ui_templates import (
    GoalDetailUpdate,
    GoalDetailViewData,
    HomeGoalCard,
    HomeViewData,
    goal_detail_data_to_dict,
    home_view_data_to_dict,
    render_goal_detail_view,
    render_home_view,
)

logger = logging.getLogger(__name__)

settings = get_settings()

mcp = FastMCP("lifecoach", streamable_http_path="/", transport_security=None)


@mcp.resource(
    uri="ui://home-view",
    mime_type="text/html;profile=mcp-app",
    name="LifeCoach Home View",
)
async def home_view_resource() -> str:
    return render_home_view()


@mcp.resource(
    uri="ui://goal-detail-view",
    mime_type="text/html;profile=mcp-app",
    name="LifeCoach Goal Detail View",
)
async def goal_detail_view_resource() -> str:
    return render_goal_detail_view()


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


async def _fetch_home_view_data(user_id: str) -> HomeViewData:
    async with get_rls_connection(user_id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT display_name, email
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            user_row = await cursor.fetchone()

            if user_row is None:
                logger.warning("_fetch_home_view_data: no user row for caller %s", user_id)
                return HomeViewData(
                    greeting_name=None,
                    goals=[],
                    error="We couldn't load your home screen right now.",
                )

            display_name, email = user_row

            await cursor.execute(
                """
                SELECT id, title, progress_percent
                FROM goals
                ORDER BY created_at DESC
                """
            )
            goal_rows = await cursor.fetchall()

            goal_ids = [str(goal_id) for goal_id, _, _ in goal_rows]
            last_updated_by_goal_id: dict[str, str] = {}
            if goal_ids:
                await cursor.execute(
                    """
                    SELECT goal_id, MAX(created_at)
                    FROM updates
                    WHERE goal_id = ANY(%s)
                    GROUP BY goal_id
                    """,
                    (goal_ids,),
                )
                last_updated_by_goal_id = {
                    str(goal_id): last_created_at.isoformat()
                    for goal_id, last_created_at in await cursor.fetchall()
                }

            goals = [
                HomeGoalCard(
                    id=str(goal_id),
                    title=title,
                    progress_percent=progress_percent,
                    last_updated_at=last_updated_by_goal_id.get(str(goal_id)),
                )
                for goal_id, title, progress_percent in goal_rows
            ]

    return HomeViewData(greeting_name=display_name or email, goals=goals)


@mcp.tool(
    description=(
        "Return the home screen UI for the signed-in user: a greeting, a "
        "card per active goal with its progress, and distinct entries to "
        "start a new goal or just talk. Call this to show the user their "
        "home screen, not as a source of goal data for your own reasoning "
        "— use list_updates/other tools for that."
    )
)
async def get_home_view(ctx: Context) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        home_view_data = await _fetch_home_view_data(current_user.id)
    except Exception:
        logger.exception("get_home_view failed for caller %s", current_user.id)
        return {
            "greetingName": None,
            "goals": [],
            "error": "We couldn't load your home screen right now.",
        }

    return home_view_data_to_dict(home_view_data)


@mcp.tool(
    description=(
        "Return the goal-detail screen UI for one of the user's goals: "
        "its full title and description, progress, a short list of "
        "recent updates, a 'continue this conversation' action, and a "
        "delete action behind a confirm step. Call this when the user "
        "taps into a specific goal, not as a source of goal data for "
        "your own reasoning — use list_updates/other tools for that."
    )
)
async def get_goal_detail_view(goal_id: str, ctx: Context) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        validated_goal_id = UUID(goal_id)
    except ValueError as exc:
        logger.warning("get_goal_detail_view validation failed: %s", exc)
        raise ValueError("goal_id must be a valid UUID") from exc

    try:
        async with get_rls_connection(current_user.id) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, title, description, progress_percent
                    FROM goals
                    WHERE id = %s
                    """,
                    (str(validated_goal_id),),
                )
                goal_row = await cursor.fetchone()

                if goal_row is None:
                    return goal_detail_data_to_dict(
                        GoalDetailViewData(
                            id=None,
                            title=None,
                            description=None,
                            progress_percent=None,
                            recent_updates=[],
                            error="This goal isn't available.",
                        )
                    )

                returned_id, title, description, progress_percent = goal_row

                await cursor.execute(
                    """
                    SELECT content, created_at
                    FROM updates
                    WHERE goal_id = %s
                    ORDER BY created_at DESC
                    LIMIT 5
                    """,
                    (str(returned_id),),
                )
                update_rows = await cursor.fetchall()
    except Exception:
        logger.exception("get_goal_detail_view failed for caller %s", current_user.id)
        return goal_detail_data_to_dict(
            GoalDetailViewData(
                id=None,
                title=None,
                description=None,
                progress_percent=None,
                recent_updates=[],
                error="This goal isn't available.",
            )
        )

    recent_updates = [
        GoalDetailUpdate(content=content, created_at=created_at.isoformat())
        for content, created_at in update_rows
    ]

    return goal_detail_data_to_dict(
        GoalDetailViewData(
            id=str(returned_id),
            title=title,
            description=description,
            progress_percent=progress_percent,
            recent_updates=recent_updates,
        )
    )


@mcp.tool(
    description=(
        "Soft-delete one of the user's own goals. This is intended to be "
        "called from the goal-detail view's confirm-delete UI action after "
        "the user has explicitly confirmed, not something you should "
        "invoke proactively mid-conversation. On success, returns a "
        "refreshed home screen UI resource reflecting the deletion."
    )
)
async def delete_goal(goal_id: str, ctx: Context) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        validated_goal_id = UUID(goal_id)
    except ValueError as exc:
        logger.warning("delete_goal validation failed: %s", exc)
        raise ValueError("goal_id must be a valid UUID") from exc

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE goals
                SET deleted_at = now()
                WHERE id = %s AND deleted_at IS NULL
                RETURNING id
                """,
                (str(validated_goal_id),),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError(
                    "goal_id does not exist, is not owned by the caller, or is already deleted"
                )
        await conn.commit()

    try:
        home_view_data = await _fetch_home_view_data(current_user.id)
    except Exception:
        logger.exception("delete_goal: refreshing home view failed for caller %s", current_user.id)
        return {
            "greetingName": None,
            "goals": [],
            "error": "We couldn't load your home screen right now.",
        }

    return home_view_data_to_dict(home_view_data)


mcp._tool_manager._tools["get_home_view"].meta = {"ui": {"resourceUri": "ui://home-view"}}
mcp._tool_manager._tools["get_goal_detail_view"].meta = {"ui": {"resourceUri": "ui://goal-detail-view"}}
mcp._tool_manager._tools["delete_goal"].meta = {"ui": {"resourceUri": "ui://home-view"}}
