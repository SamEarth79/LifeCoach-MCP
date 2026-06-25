# Architecture: Goal Todos

> Filled in by `draft.md` during `/design`, informed by `analysis.md`.
> Describes the technical approach before any code is written.

## Approach

Add a `todos` child table (many-to-one to `goals`), following the existing
`updates` table's pattern: raw-SQL persistence (no ORM), RLS-enforced
per-user isolation via ownership checks through the parent `goals` row, and
MCP tools in `app/mcp_server.py` that mirror the existing
auth-validate-RLS-query-return shape. Six new tools cover full CRUD plus
reorder/toggle: `create_todo`, `update_todo`, `toggle_todo`, `delete_todo`,
`list_todos`, `reorder_todos`. `create_goal` gains an optional `todos: list[str]`
argument so the LLM can persist its suggested subgoal steps in the same
call that creates the goal, rather than requiring a separate round-trip.
`get_goal_detail_view` is extended to fetch and render the todo list, with
interactive checkboxes wired to `toggle_todo` via the existing MCP-UI
postMessage bridge (a narrowly scoped, strategy-approved exception to the
read-only-UI default — see `knowledge/strategy.md`, 2026-06-25 entry).

## Components touched

- **Frontend**: none (no separate frontend framework in this repo — see
  Backend/MCP-UI below).
- **Backend**:
  - `migrations/versions/` — new migration creating `todos` table + RLS
    policies.
  - `app/schemas.py` — new Pydantic models: `TodoCreate`, `TodoUpdate`,
    `TodoResponse`, `TodoReorder`.
  - `app/mcp_server.py` — six new MCP tools (`create_todo`, `update_todo`,
    `toggle_todo`, `delete_todo`, `list_todos`, `reorder_todos`); extend
    `create_goal` to accept optional `todos: list[str]`; extend
    `get_goal_detail_view`'s query block to fetch todos for the goal;
    extend `_COACH_INSTRUCTIONS` to instruct the LLM to suggest todos at
    goal creation and to use the CRUD tools when the user asks to manage
    todos conversationally.
  - `app/ui_templates.py` — add `GoalDetailTodo` dataclass + `todos` field
    on `GoalDetailViewData`; extend `goal_detail_data_to_dict`; extend
    `renderGoalDetailView` JS to render the todo list with checkboxes that
    call `window.callTool('toggle_todo', {...})`.
- **Infrastructure**: none.

## Data flow

**Goal creation with suggested todos:**
1. LLM calls `create_goal` with `title`, `description`, and optional
   `todos: list[str]` (its suggested subgoal steps).
2. Tool validates input, inserts the goal row, then inserts one `todos` row
   per suggested string (RLS-scoped connection, `sort_order` assigned by
   insertion order).
3. Tool returns the refreshed home view, same as today.

**Conversational todo management:**
1. User asks the LLM (in chat) to add/edit/reorder/remove a todo.
2. LLM calls the matching CRUD tool (`create_todo`, `update_todo`,
   `delete_todo`, `reorder_todos`) with the goal id and todo fields.
3. Tool validates, runs the RLS-scoped query, returns the updated todo (or
   list).

**Interactive toggle from the UI:**
1. User taps a todo checkbox in the rendered `get_goal_detail_view` HTML.
2. Client JS bridge (`_BRIDGE_JS`) calls `window.callTool('toggle_todo',
   {todoId})`.
3. `toggle_todo` flips `done` for that row (RLS-scoped, ownership verified
   transitively through the parent goal) and returns the updated todo;
   host re-renders or the view's JS patches the row in place.

## Data model changes

New `todos` table (migration mirrors `updates`' shape):

| column      | type        | notes                                              |
|-------------|-------------|-----------------------------------------------------|
| id          | UUID        | PK, `gen_random_uuid()`                             |
| user_id     | UUID        | FK `auth.users.id`, `ON DELETE CASCADE`             |
| goal_id     | UUID        | FK `goals.id`, `ON DELETE CASCADE`                  |
| text        | text        | not null, non-blank (app-level validation)          |
| done        | boolean     | not null, default `false`                           |
| sort_order  | integer     | not null                                             |
| created_at  | timestamptz | `now()` server default                               |
| updated_at  | timestamptz | `now()` server default, updated on mutation          |

- Index `ix_todos_goal_id_sort_order` (goal_id, sort_order) for ordered
  listing.
- Hard delete (no soft-delete column) — matches `updates`' child-table
  convention; todos are working-state checklist items, not a record worth
  preserving after removal, unlike top-level `goals`.
- RLS: `ENABLE ROW LEVEL SECURITY`; `SELECT`/`INSERT`/`UPDATE`/`DELETE`
  policies all check `auth.uid() = user_id AND EXISTS (SELECT 1 FROM goals
  g WHERE g.id = goal_id AND g.user_id = auth.uid() AND g.deleted_at IS
  NULL)`, mirroring `updates_insert_own` but extended to all four
  operations since todos are mutable.

## Key decisions

- **Decision**: Reordering is implemented as a full-list rewrite —
  `reorder_todos` takes the goal id and an ordered list of todo ids, and
  assigns `sort_order = 0..n-1` in a single transaction.
  **Rationale**: No existing reorder precedent in this codebase to follow.
  A full-list rewrite is simpler than maintaining integer gaps or
  fractional ordering, and todo lists are expected to be small (a handful
  of subgoal steps per goal), so the cost of rewriting all rows is
  negligible. Avoids the complexity of gap-based ordering for a
  vanishingly small payoff at this scale.
- **Decision**: `create_goal` gains an optional `todos: list[str]` argument
  rather than requiring a separate tool call right after goal creation.
  **Rationale**: Analysis found no existing structured-suggestion
  scaffolding; piggybacking on `create_goal`'s existing single-call,
  single-transaction shape is simpler than coordinating two tool calls and
  avoids a goal ever existing transiently with zero todos when the LLM
  intended to suggest some.
- **Decision**: Interactive `toggle_todo` checkbox in `get_goal_detail_view`
  is the one explicitly scoped exception to this project's read-only-MCP-UI
  default.
  **Rationale**: Per user decision during `/design`'s gather step and the
  resulting `knowledge/strategy.md` update (2026-06-25) — toggling
  completion is a single unambiguous action, unlike freeform input the
  read-only rule was meant to avoid. All other todo mutations (create,
  edit, reorder, delete) stay conversational/tool-only, consistent with the
  existing strategy.
- **Decision**: Todo completion does not feed into `set_goal_progress` or
  `progress_percent` automatically.
  **Rationale**: Explicit user decision during `/design`'s gather step —
  progress stays fully manual, matching the existing behavior described in
  `knowledge/strategy.md` and the LifeCoach MCP server instructions.
