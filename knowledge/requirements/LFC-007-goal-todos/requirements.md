# Requirements: Goal Todos

> Filled in by `draft.md` during `/design`. Plain numbered requirements —
> no per-requirement code; stories reference these by number.

## Functional requirements

1. A todo belongs to exactly one goal (many-to-one), has `text`, a `done`
   boolean (default false), and a `sort_order` integer, and is owned by the
   same user as its parent goal.
2. `create_goal` accepts an optional `todos: list[str]` argument; when
   provided, each string is persisted as a todo for the newly created goal
   in the same call, with `sort_order` assigned by list position.
3. The LLM is instructed (via system instructions / tool descriptions) to
   suggest todos as subgoal-style steps toward the goal whenever a goal is
   created, populating the `todos` argument on `create_goal`.
4. A `create_todo` tool adds a single todo to an existing goal, appended
   after the current last `sort_order` for that goal.
5. An `update_todo` tool edits a todo's `text`.
6. A `toggle_todo` tool flips a todo's `done` status.
7. A `delete_todo` tool permanently removes a todo.
8. A `list_todos` tool returns all todos for a given goal, ordered by
   `sort_order`.
9. A `reorder_todos` tool accepts a goal id and an ordered list of todo ids
   belonging to that goal, and rewrites `sort_order` to match the given
   order.
10. The LLM is instructed to use `create_todo`/`update_todo`/`toggle_todo`/
    `delete_todo`/`reorder_todos` when the user conversationally asks to
    add, change, complete, remove, or reorder todos for a goal.
11. `get_goal_detail_view` includes the goal's todos (text, done state, in
    `sort_order`), rendered as a checklist.
12. Each rendered todo checkbox calls `toggle_todo` directly from the UI
    (via the existing MCP-UI tool-call bridge) when clicked, and the view
    reflects the resulting `done` state.
13. All other todo mutations (create, edit, reorder, delete) are exposed
    only as MCP tools, not as UI controls in `get_goal_detail_view`.
14. Every todo tool enforces that the requesting user owns the todo's
    parent goal — no tool accepts or trusts a client-supplied user id.
15. Deleting a goal deletes its todos (cascade), consistent with how
    `updates` already cascade-delete with their parent goal.

## Non-functional requirements

- **Security**: Per-user isolation for `todos` is enforced via Postgres RLS
  policies (SELECT/INSERT/UPDATE/DELETE), not solely application-level
  checks, consistent with every other table in this project.
- **Consistency**: New tools and schemas follow the exact code patterns
  already used for `goals`/`updates` (raw SQL in `mcp_server.py`, Pydantic
  validation in `schemas.py`, Alembic migration in `migrations/versions/`)
  — no new abstraction layer (ORM, repository) is introduced for this
  feature.

## Out of scope

- Auto-computing or auto-suggesting `progress_percent` from todo
  completion — progress stays fully manual via `set_goal_progress`.
- Due dates, reminders, priorities, or any field beyond `text`/`done`/
  `sort_order`.
- Nested todos / sub-todos (a todo cannot itself have child todos).
- Any UI control for creating, editing, reordering, or deleting todos
  (those remain conversational/tool-only); the UI exception covers only
  the `toggle_todo` checkbox.
- Notifications or reminders related to todos.
