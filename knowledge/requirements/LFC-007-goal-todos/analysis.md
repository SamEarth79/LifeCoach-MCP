# Analysis: Goal Todos

> Filled in by `analyze.md` during `/design`. Summarizes what already exists
> in the codebase that is relevant to this feature, before any architecture
> or requirements are drafted.

## Summary

Add a `todos` table linked many-to-one to `goals`, with full CRUD exposed as
MCP tools. Each todo is a subgoal-style step toward its parent goal: text +
`done` boolean + `sort_order`. The LLM can suggest todos at goal-creation
time and the user can also direct the LLM to add/edit/reorder/delete/toggle
todos conversationally at any time. Todos render in the existing
`get_goal_detail_view` MCP-UI screen. Goal `progress_percent` stays fully
manual (per `set_goal_progress`) — todo completion does not auto-update it.

## Relevant existing code

- `app/schemas.py` — Pydantic request/response models for `goals`/`updates`
  (`GoalCreate`, `GoalUpdate`, `GoalResponse`, `UpdateCreate`,
  `UpdateResponse`, `UpdateListItem`, `GoalProgressUpdate`). No ORM layer —
  these are validation-only; persistence is raw SQL. New `TodoCreate`,
  `TodoUpdate`, `TodoResponse`, `TodoReorder`-style schemas belong here,
  following the same naming/shape conventions.
- `migrations/versions/2ae062d3817c_create_goals_table.py` — `goals` table:
  UUID `id` (`gen_random_uuid()`), `user_id` FK to `auth.users.id` (`ON
  DELETE CASCADE`), `title`, `description`, `created_at`/`updated_at`
  (`now()` server defaults), `deleted_at` (nullable, soft-delete: queries
  filter `WHERE deleted_at IS NULL`, delete just sets `deleted_at = now()`).
- `migrations/versions/66f94137137d_add_goals_progress_percent.py` — example
  of an additive migration (`op.add_column` + `op.create_check_constraint`)
  for a later schema change to an existing table; same pattern would apply
  if `todos` needs a follow-up column later.
- `migrations/versions/8e5660ff9d7f_create_updates_table.py` — `updates`
  table is the closest sibling: child-of-goal, `id`, `user_id`, `goal_id`
  (FK to `goals.id`, `ON DELETE CASCADE`), hard-deleted rows (no
  `deleted_at`), index `ix_updates_goal_id_created_at`. RLS policies check
  ownership transitively via `EXISTS (SELECT 1 FROM goals g WHERE g.id =
  goal_id AND g.user_id = auth.uid() AND g.deleted_at IS NULL)` on INSERT.
  `todos` should mirror this child-table shape and RLS approach, but
  additionally needs `UPDATE`/`DELETE` policies (todos are mutable —
  `done`, `sort_order`, text edits — unlike append-only `updates`).
- `app/mcp_server.py` (552 lines) — all MCP tools live in this single file.
  Every tool follows the same pattern: rate limit → bearer token auth via
  `verify_bearer_token` (`app/auth.py`) → Pydantic validation → RLS-scoped
  DB connection via `get_rls_connection(current_user.id)` (`app/db.py`,
  sets `request.jwt.claim.sub` so Postgres RLS enforces isolation) → inline
  raw SQL (no repository layer) → plain dict return (camelCase keys for
  UI-facing tools). `create_goal` and `delete_goal` both end by refreshing
  and returning the home view. New todo tools (`create_todo`,
  `update_todo`, `toggle_todo`, `delete_todo`, `list_todos`,
  `reorder_todos`) should follow this exact pattern in the same file.
- `app/ui_templates.py` (645 lines) — MCP-UI HTML/JS is hand-built string
  concatenation (no templating library), registered as an MCP resource
  (`ui://goal-detail-view`). `GoalDetailViewData`/`GoalDetailUpdate`
  dataclasses define the server-side shape; `goal_detail_data_to_dict`
  maps to camelCase JS keys consumed by `renderGoalDetailView(data)` in
  `_RENDER_JS`, which loops over `data.recentUpdates` to build the update
  list. Adding todos means: add a `todos: list[GoalDetailTodo]` field +
  dataclass, add a `todos` key in `goal_detail_data_to_dict`, fetch todos
  in `get_goal_detail_view`'s query block in `mcp_server.py`, and extend
  `renderGoalDetailView` to render a todo list (checkboxes calling
  `window.callTool('toggle_todo', ...)` via the existing `_BRIDGE_JS`
  postMessage bridge).
- `_COACH_INSTRUCTIONS` system prompt in `app/mcp_server.py` (~lines 31-47)
  — the only existing mechanism for steering LLM behavior across tool
  calls (e.g. already instructs the LLM to pair `record_update` with
  `set_goal_progress`). The "LLM suggests todos at goal creation" behavior
  has no existing scaffolding — there is no structured-suggestion tool or
  schema field anywhere in the codebase today. It must be added as either
  (a) an optional `todos: list[str]` argument on `create_goal` itself, or
  (b) a new `create_todo`/batch-create tool the LLM is instructed (via
  `_COACH_INSTRUCTIONS` plus `create_goal`'s tool description) to call
  immediately after `create_goal`.

## Constraints and risks

- No ORM and no repository/service layer exists anywhere in this codebase —
  todo persistence must be raw SQL inline in `mcp_server.py`, consistent
  with `goals`/`updates`, even though this means six new tool functions
  each carrying their own SQL. Introducing a repository abstraction now
  would break from established convention for a single new feature and is
  out of scope.
- RLS is the actual enforcement boundary (the app layer trusts
  `auth.uid()`, not application code, for per-row isolation) — every new
  todo policy (SELECT/INSERT/UPDATE/DELETE) must be written and migrated
  correctly, or todos could leak across users despite app-level code
  looking correct.
- `sort_order` plus concurrent edits (LLM reordering while user also
  reorders conversationally) has no existing concurrency pattern to copy
  from `updates` (append-only, no reordering precedent in this codebase).
  Need a simple, race-tolerant reorder approach (e.g. integer gaps or
  full-list rewrite per `reorder_todos` call) decided in `draft.md`.
- Strategy doc (`knowledge/strategy.md`) lists "goal templates/categories"
  as explicitly out of scope for v1, but does not mention todos/subgoals —
  no conflict found. Strategy also states progress is fully manual via
  `set_goal_progress`, which matches the user's decision (during `gather`)
  to keep progress fully manual and unrelated to todo completion.
- MCP-UI for this project was documented as "read-only displays" in
  strategy.md. The user has confirmed (resolved below) that todos
  intentionally expand this: the goal detail view gets interactive
  checkboxes that call `toggle_todo` directly via `window.callTool`.
  `strategy.md` is being updated to record this as an intentional, scoped
  expansion (todo completion toggling only — other input, e.g. creating or
  editing todo text, stays conversational).

## Open questions

(none — the MCP-UI read-only-vs-interactive question was resolved during
analysis: interactive checkboxes are intentional and `strategy.md` has been
updated accordingly.)
