import json
import logging
from uuid import UUID

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.prompts.base import UserMessage
from mcp.server.transport_security import TransportSecuritySettings

from pydantic import ValidationError

from app.auth import verify_bearer_token
from app.config import get_settings
from app.db import get_rls_connection
from app.rate_limit import enforce_mcp_rate_limit
from app.schemas import (
    GoalCreate,
    GoalProgressUpdate,
    TodoCreate,
    TodoReorder,
    TodoResponse,
    TodoUpdate,
    UpdateCreate,
    UpdateListItem,
)
from app.ui_templates import (
    GoalDetailTodo,
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

_COACH_INSTRUCTIONS = (
    "You are this user's personal life coach. Be warm, curious, and "
    "non-judgmental — a coach having a conversation, not a tracker "
    "logging data points. Ask follow-up questions before assuming you "
    "understand what happened. Only call record_update once you and the "
    "user have actually settled on something concrete; never log "
    "preemptively or after every message. Goals have no numeric target, "
    "so progress_percent is never computed automatically — it stays "
    "blank forever unless you call set_goal_progress yourself. Whenever "
    "you call record_update for a goal, also call set_goal_progress "
    "for that same goal in the same turn with your own best-judgment "
    "estimate (0-100) and a short rationale, even a rough one — a "
    "blank progress ring is worse than an imperfect estimate. Don't "
    "show a UI view (get_home_view/get_goal_detail_view) just to "
    "narrate progress mid-conversation — show it when the user is "
    "navigating between goals, not as a substitute for talking. "
    "Whenever you create a goal, suggest 3-5 concrete, subgoal-style "
    "todos for it in the same create_goal call, so the user starts with "
    "a checklist of next steps instead of a blank goal — ground them in "
    "whatever the user already told you, not generic filler. Once a "
    "goal has todos, treat them as a living checklist: whenever the "
    "user conversationally asks to add, change, complete, remove, or "
    "reorder a todo for an existing goal, use create_todo, update_todo, "
    "toggle_todo, delete_todo, or reorder_todos to keep it in sync — "
    "don't just acknowledge the request in conversation without "
    "actually updating the checklist."
)

mcp = FastMCP(
    "lifecoach",
    instructions=_COACH_INSTRUCTIONS,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        allowed_hosts=settings.mcp_allowed_hosts_list,
        allowed_origins=settings.mcp_allowed_origins_list,
    ),
)


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


def _todo_row_to_response(row: tuple) -> dict:
    todo_id, goal_id, text, done, sort_order, created_at, updated_at = row
    return TodoResponse(
        id=str(todo_id),
        goal_id=str(goal_id),
        text=text,
        done=done,
        sort_order=sort_order,
        created_at=created_at.isoformat(),
        updated_at=updated_at.isoformat(),
    ).model_dump()


@mcp.tool(
    description=(
        "Add a todo (subgoal step) to one of the user's goals. Call this "
        "when you and the user agree on a concrete next step worth "
        "tracking as a checklist item. The new todo is appended to the "
        "end of the goal's existing todo list. Returns the created todo."
    )
)
async def create_todo(goal_id: str, text: str, ctx: Context) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        todo = TodoCreate(goal_id=goal_id, text=text)
    except ValidationError as exc:
        logger.warning("create_todo validation failed: %s", exc)
        raise ValueError(str(exc)) from exc

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO todos (user_id, goal_id, text, sort_order)
                VALUES (
                    %s,
                    %s,
                    %s,
                    COALESCE(
                        (SELECT MAX(sort_order) + 1 FROM todos WHERE goal_id = %s),
                        0
                    )
                )
                RETURNING id, goal_id, text, done, sort_order, created_at, updated_at
                """,
                (current_user.id, str(todo.goal_id), todo.text, str(todo.goal_id)),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError(
                    "goal_id does not exist, is not owned by the caller, or is deleted"
                )
        await conn.commit()

    return _todo_row_to_response(row)


@mcp.tool(
    description=(
        "Update the text of one of the user's existing todos. Call this "
        "when the user wants to rephrase or correct a checklist item, not "
        "to mark it complete — use toggle_todo for that. Returns the "
        "updated todo, or a clear not-found result if the todo doesn't "
        "exist or isn't owned by the user."
    )
)
async def update_todo(todo_id: str, text: str, ctx: Context) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        validated_todo_id = UUID(todo_id)
        todo = TodoUpdate(text=text)
    except (ValueError, ValidationError) as exc:
        logger.warning("update_todo validation failed: %s", exc)
        raise ValueError(str(exc)) from exc

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE todos
                SET text = %s, updated_at = now()
                WHERE id = %s
                RETURNING id, goal_id, text, done, sort_order, created_at, updated_at
                """,
                (todo.text, str(validated_todo_id)),
            )
            row = await cursor.fetchone()
        await conn.commit()

    if row is None:
        return {"found": False, "error": "todo not found or not owned by the caller"}

    return {"found": True, **_todo_row_to_response(row)}


@mcp.tool(
    description=(
        "Flip the completion state of one of the user's todos (incomplete "
        "becomes complete, complete becomes incomplete). Call this when "
        "the user reports finishing or reopening a checklist item, or in "
        "response to the user tapping the todo's checkbox in the UI. "
        "Returns the updated todo."
    )
)
async def toggle_todo(todo_id: str, ctx: Context) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        validated_todo_id = UUID(todo_id)
    except ValueError as exc:
        logger.warning("toggle_todo validation failed: %s", exc)
        raise ValueError("todo_id must be a valid UUID") from exc

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE todos
                SET done = NOT done, updated_at = now()
                WHERE id = %s
                RETURNING id, goal_id, text, done, sort_order, created_at, updated_at
                """,
                (str(validated_todo_id),),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError("todo_id does not exist or is not owned by the caller")
        await conn.commit()

    return _todo_row_to_response(row)


@mcp.tool(
    description=(
        "Permanently remove one of the user's todos. Call this when the "
        "user wants a checklist item gone entirely, not just marked done "
        "— use toggle_todo for completion. Has no effect if the todo "
        "doesn't exist or isn't owned by the user. Returns confirmation."
    )
)
async def delete_todo(todo_id: str, ctx: Context) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        validated_todo_id = UUID(todo_id)
    except ValueError as exc:
        logger.warning("delete_todo validation failed: %s", exc)
        raise ValueError("todo_id must be a valid UUID") from exc

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                DELETE FROM todos
                WHERE id = %s
                RETURNING id
                """,
                (str(validated_todo_id),),
            )
            row = await cursor.fetchone()
        await conn.commit()

    return {"deleted": row is not None, "todo_id": str(validated_todo_id)}


@mcp.tool(
    description=(
        "List all todos for one of the user's goals, ordered to match the "
        "order shown in the UI. Use this to check what subgoal steps "
        "already exist before adding more, or to ground a conversation "
        "about what's left to do."
    )
)
async def list_todos(goal_id: str, ctx: Context) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        validated_goal_id = UUID(goal_id)
    except ValueError as exc:
        logger.warning("list_todos validation failed: %s", exc)
        raise ValueError("goal_id must be a valid UUID") from exc

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id, goal_id, text, done, sort_order, created_at, updated_at
                FROM todos
                WHERE goal_id = %s
                ORDER BY sort_order ASC
                """,
                (str(validated_goal_id),),
            )
            rows = await cursor.fetchall()

    return {"todos": [_todo_row_to_response(row) for row in rows]}


@mcp.tool(
    description=(
        "Rewrite the display order of one of the user's goal's todos to "
        "match the given order. Call this when the user wants to "
        "reprioritize or reorder their checklist. `todo_ids` must list "
        "every todo id for the goal, in the desired new order."
    )
)
async def reorder_todos(goal_id: str, todo_ids: list[str], ctx: Context) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        reorder = TodoReorder(goal_id=goal_id, todo_ids=todo_ids)
    except ValidationError as exc:
        logger.warning("reorder_todos validation failed: %s", exc)
        raise ValueError(str(exc)) from exc

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            for position, todo_id in enumerate(reorder.todo_ids):
                await cursor.execute(
                    """
                    UPDATE todos
                    SET sort_order = %s, updated_at = now()
                    WHERE id = %s AND goal_id = %s
                    """,
                    (position, str(todo_id), str(reorder.goal_id)),
                )
                if cursor.rowcount != 1:
                    raise ValueError(
                        f"todo {todo_id} does not exist or does not belong to goal_id"
                    )
        await conn.commit()

    return {"goal_id": str(reorder.goal_id), "todo_ids": [str(tid) for tid in reorder.todo_ids]}


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


@mcp.prompt(
    name="coach",
    description=(
        "Start a coaching session grounded in the user's real goal state. "
        "Invoke this explicitly when the user wants to begin a coaching "
        "conversation — it is not run automatically at the start of every "
        "chat."
    ),
)
async def coach_prompt(ctx: Context) -> UserMessage:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        home_view_data = await _fetch_home_view_data(current_user.id)
    except Exception:
        logger.exception("coach_prompt failed for caller %s", current_user.id)
        home_view_data = HomeViewData(
            greeting_name=None,
            goals=[],
            error="We couldn't load your home screen right now.",
        )

    home_view_json = json.dumps(home_view_data_to_dict(home_view_data))
    return UserMessage(
        "Let's start a coaching session. Here is my current home screen "
        f"data: {home_view_json}\n\nGreet me by name if you have it, "
        "reflect on where I'm at across my goals, and let's talk."
    )


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
                            todos=[],
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

                await cursor.execute(
                    """
                    SELECT id, text, done, sort_order
                    FROM todos
                    WHERE goal_id = %s
                    ORDER BY sort_order ASC
                    """,
                    (str(returned_id),),
                )
                todo_rows = await cursor.fetchall()
    except Exception:
        logger.exception("get_goal_detail_view failed for caller %s", current_user.id)
        return goal_detail_data_to_dict(
            GoalDetailViewData(
                id=None,
                title=None,
                description=None,
                progress_percent=None,
                recent_updates=[],
                todos=[],
                error="This goal isn't available.",
            )
        )

    recent_updates = [
        GoalDetailUpdate(content=content, created_at=created_at.isoformat())
        for content, created_at in update_rows
    ]
    todos = [
        GoalDetailTodo(id=str(todo_id), text=text, done=done, sort_order=sort_order)
        for todo_id, text, done, sort_order in todo_rows
    ]

    return goal_detail_data_to_dict(
        GoalDetailViewData(
            id=str(returned_id),
            title=title,
            description=description,
            progress_percent=progress_percent,
            recent_updates=recent_updates,
            todos=todos,
        )
    )


@mcp.tool(
    description=(
        "Create a new goal for the user. Call this once you and the user "
        "have actually agreed on a clear title for what they want to work "
        "on — not before they've described it. Optionally include a short "
        "`description` capturing what they want to achieve, their "
        "timeline, or why it matters, if they shared that. Also suggest 3-5 "
        "concrete, subgoal-style first steps in `todos` so the user starts "
        "with a checklist instead of a blank goal — base them on whatever "
        "the user has already shared, and keep each one short and "
        "actionable. On success, returns a refreshed home screen UI "
        "resource reflecting the new goal."
    )
)
async def create_goal(
    title: str, ctx: Context, description: str | None = None, todos: list[str] | None = None
) -> dict:
    request = ctx.request_context.request
    await enforce_mcp_rate_limit(request)

    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)

    try:
        goal = GoalCreate(title=title, description=description, todos=todos)
    except ValidationError as exc:
        logger.warning("create_goal validation failed: %s", exc)
        raise ValueError(str(exc)) from exc

    async with get_rls_connection(current_user.id) as conn:
        async with conn.cursor() as cursor:
            if goal.todos:
                await cursor.execute(
                    """
                    INSERT INTO goals (user_id, title, description)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (current_user.id, goal.title, goal.description),
                )
                (new_goal_id,) = await cursor.fetchone()
                for sort_order, todo_text in enumerate(goal.todos):
                    await cursor.execute(
                        """
                        INSERT INTO todos (user_id, goal_id, text, sort_order)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (current_user.id, str(new_goal_id), todo_text, sort_order),
                    )
            else:
                await cursor.execute(
                    """
                    INSERT INTO goals (user_id, title, description)
                    VALUES (%s, %s, %s)
                    """,
                    (current_user.id, goal.title, goal.description),
                )
        await conn.commit()

    try:
        home_view_data = await _fetch_home_view_data(current_user.id)
    except Exception:
        logger.exception("create_goal: refreshing home view failed for caller %s", current_user.id)
        return {
            "greetingName": None,
            "goals": [],
            "error": "We couldn't load your home screen right now.",
        }

    return home_view_data_to_dict(home_view_data)


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
mcp._tool_manager._tools["create_goal"].meta = {"ui": {"resourceUri": "ui://home-view"}}
