# Technical Deep Dive: Goal Todos (LFC-007)

## What this feature is

A per-goal checklist of small, concrete steps ("subgoals") that lives
alongside a goal's existing progress estimate and update history. Two ways
to populate it: the coaching AI suggests 3-5 todos in the same call that
creates a goal, or the user asks conversationally to add/edit/complete/
remove/reorder items later. The only interactive surface is the goal-detail
view's checkbox — every other mutation stays tool-only, consistent with this
repo's existing read-only-MCP-UI default.

Six new MCP tools, all mounted on the existing `FastMCP` instance in
`app/mcp_server.py`, all requiring the same Supabase JWT every other MCP
tool already requires: `create_todo`, `update_todo`, `toggle_todo`,
`delete_todo`, `list_todos`, `reorder_todos`. `create_goal` gains an
optional `todos: list[str] | None` argument, and `get_goal_detail_view`
gains a `todos` field in its response, rendered as a checklist by
`app/ui_templates.py`'s `renderGoalDetailView`.

## Components

| File | Responsibility |
|---|---|
| `app/mcp_server.py` | Six new MCP tools (`create_todo`, `update_todo`, `toggle_todo`, `delete_todo`, `list_todos`, `reorder_todos`); `create_goal` extended to accept `todos`; `get_goal_detail_view` extended to fetch and return todos; `_COACH_INSTRUCTIONS` and `create_goal`'s tool description extended to instruct the LLM to suggest todos at creation and manage them conversationally afterward. |
| `app/schemas.py` | New `TodoCreate`, `TodoUpdate`, `TodoResponse`, `TodoReorder` Pydantic models; `GoalCreate` gains a `todos: list[str] | None` field with a `reject_blank_todos` validator. |
| `app/ui_templates.py` | New `GoalDetailTodo` dataclass and `todos: list[GoalDetailTodo]` field on `GoalDetailViewData`; `goal_detail_data_to_dict` maps each todo to `{id, text, done, sortOrder}`; `renderGoalDetailView`'s embedded JS gains a `todoItem()`/`toggleTodo()` pair and `.todo-list`/`.todo-item`/`.todo-checkbox`/`.todo-text`/`.todo-done` CSS classes. |
| `migrations/versions/f024a0719f4a_create_todos_table.py` | Alembic migration creating the `todos` table, its index, and its four RLS policies. |

## The `todos` table

```
todos
  id           uuid        PRIMARY KEY, default gen_random_uuid()
  user_id      uuid        NOT NULL, FK -> auth.users.id ON DELETE CASCADE
  goal_id      uuid        NOT NULL, FK -> goals.id ON DELETE CASCADE
  text         text        NOT NULL  -- non-blank, app-level validation
  done         boolean     NOT NULL DEFAULT false
  sort_order   integer     NOT NULL
  created_at   timestamptz NOT NULL DEFAULT now()
  updated_at   timestamptz NOT NULL DEFAULT now()
```

Index: `ix_todos_goal_id_sort_order` on `(goal_id, sort_order)`, supporting
every tool's "list/reorder by sort position within a goal" query pattern.

Hard delete, no `deleted_at` column — unlike `goals`, a todo removed via
`delete_todo` is gone for good. This is a deliberate departure from `goals`'
soft-delete convention: todos are working-state checklist items, not a
record worth preserving after removal, and `delete_todo` issues a real SQL
`DELETE`.

### RLS policies

```sql
CREATE POLICY todos_select_own ON todos
  FOR SELECT USING (
    auth.uid() = user_id
    AND EXISTS (
      SELECT 1 FROM goals g
      WHERE g.id = goal_id AND g.user_id = auth.uid() AND g.deleted_at IS NULL
    )
  );

-- todos_insert_own (FOR INSERT WITH CHECK), todos_update_own
-- (FOR UPDATE USING + WITH CHECK), and todos_delete_own (FOR DELETE)
-- all repeat the exact same predicate.
```

This is the first table in the repo with all four CRUD policies present —
`updates` (LFC-003) only ever needed `SELECT`/`INSERT` because it's
append-only, but todos are mutable (edited, toggled, reordered, deleted), so
`UPDATE` and `DELETE` policies exist too. Every policy re-derives "is this
goal valid right now" via the same `EXISTS` subquery against `goals`,
following the precedent `updates_insert_own` established: a `goal_id` value
alone is never trusted, because `goals` itself only exposes active
(non-soft-deleted) rows through its own RLS. The `UPDATE` policy applies the
predicate to both `USING` and `WITH CHECK`, consistent with the
LFC-002-goals PR-review finding that an `UPDATE` policy missing an explicit
`WITH CHECK` can silently pass mocked-cursor tests while failing to actually
enforce ownership.

## The six new MCP tools

All six follow the same `enforce_mcp_rate_limit` → `verify_bearer_token` →
validate → `get_rls_connection`-scoped query → return shape every existing
MCP tool in this repo uses (see `LFC-003-updates/technical-doc.md` for the
underlying auth/rate-limit mechanism, unchanged here).

- **`create_todo(goal_id, text, ctx)`** — inserts a row with
  `sort_order = COALESCE((SELECT MAX(sort_order) + 1 FROM todos WHERE goal_id = %s), 0)`,
  so a new todo always lands at the end of the existing list and the first
  todo for a goal gets `sort_order = 0`. Raises if the RLS `WITH CHECK`
  rejects the insert (goal not owned, not found, or soft-deleted).
- **`update_todo(todo_id, text, ctx)`** — updates `text` and `updated_at`.
  Returns `{"found": false, "error": "..."}` rather than raising when no row
  comes back (not-owned or nonexistent) — the only one of the six tools that
  reports failure as a value instead of an exception, since "the todo you
  asked to edit doesn't exist" is an expected conversational outcome, not a
  programming error.
- **`toggle_todo(todo_id, ctx)`** — flips `done` via `SET done = NOT done`.
  Raises (does not return a found-false shape) when no row matches.
- **`delete_todo(todo_id, ctx)`** — issues a real `DELETE FROM todos`.
  Returns `{"deleted": false, "todo_id": ...}` as a no-op, never raises, when
  the todo doesn't exist or isn't owned by the caller.
- **`list_todos(goal_id, ctx)`** — returns `{"todos": [...]}`,
  `ORDER BY sort_order ASC`.
- **`reorder_todos(goal_id, todo_ids, ctx)`** — issues one
  `UPDATE todos SET sort_order = %s WHERE id = %s AND goal_id = %s` per
  `todo_ids` entry (position = index in the given list), all inside one
  transaction, then a single `commit()`. See "Key decisions" below for why
  this is a full-list rewrite rather than gap-based ordering.

All six return (or, for `create_todo`/`toggle_todo`, embed via
`_todo_row_to_response`) the same `TodoResponse` shape:

```json
{
  "id": "...", "goal_id": "...", "text": "...",
  "done": false, "sort_order": 0,
  "created_at": "...", "updated_at": "..."
}
```

None of the six declares a `_meta["ui"]["resourceUri"]` — unlike
`get_home_view`/`get_goal_detail_view`/`delete_goal`, they are plain
structured-data tools, never a trigger for a host-level page re-render. The
goal-detail view's checkbox calls `toggle_todo` directly via
`window.callTool` and patches its own DOM in place (see below) rather than
re-fetching the whole view.

## `create_goal`'s new `todos` argument

`create_goal(title, ctx, description=None, todos=None)` — when `todos` is a
non-empty list, the goal INSERT gains `RETURNING id`, and one
`INSERT INTO todos (user_id, goal_id, text, sort_order)` follows per list
item, with `sort_order` equal to the item's position in the list (0-indexed).
When `todos` is omitted or an empty list, the original single-INSERT query
(no `RETURNING`, no todo inserts) runs unchanged — `if goal.todos:` is falsy
for both `None` and `[]`, so existing callers are byte-for-byte unaffected.
Both paths run inside the same `get_rls_connection`-scoped transaction,
followed by one `commit()`.

`GoalCreate.todos` is validated by `reject_blank_todos`: each string in the
list is stripped, and a blank/whitespace-only entry raises `ValueError`
before any database call — the same `reject_blank_title`/`TodoCreate.text`
stripping-and-rejecting pattern used everywhere else in this schema file.

`_COACH_INSTRUCTIONS` and `create_goal`'s own tool `description=` were both
extended with prose telling the calling LLM to suggest 3-5 concrete,
subgoal-style todos in the same `create_goal` call whenever a goal is
created, grounded in what the user already shared (not generic filler), and
to use the five CRUD tools conversationally afterward whenever the user
asks to add/change/complete/remove/reorder a todo.

## Goal detail view: rendering and toggling

`get_goal_detail_view` runs a second query after the goal row succeeds:

```sql
SELECT id, text, done, sort_order FROM todos
WHERE goal_id = %s ORDER BY sort_order ASC
```

populating `GoalDetailViewData.todos: list[GoalDetailTodo]`, mapped to
`{"id", "text", "done", "sortOrder"}` (camelCase) by
`goal_detail_data_to_dict`. On the handled-failure path (goal missing/not
owned/soft-deleted, or any unhandled error), `todos` is set to `[]`
alongside the other now-empty fields — the same discipline already applied
to `recent_updates`.

Client-side, `renderGoalDetailView`'s embedded JS gates the entire checklist
section behind `data.todos && data.todos.length > 0` — a goal with zero
todos renders no `Checklist` label and no `.todo-list` wrapper at all, not
an empty one. Items render in array order (the server's `sort_order ASC`
order; no client-side re-sort) via `todoItem(t)`, which builds a checkbox +
text pair, applying `checked`/`todo-done` only when `t.done` is true.
Following the onclick/onchange-interpolation discipline this repo has
enforced on every interactive element since LFC-004 (`goalCard`,
`delete_goal`'s confirm step), only the trusted, server-generated `t.id`
(escaped as `safeId`) is interpolated into the checkbox's `onchange`
JS-string context — the free-text `safeText` never is.

`toggleTodo(todoId)` disables the checkbox, calls
`window.callTool("toggle_todo", { todo_id: todoId })`, and on resolution sets
`checkbox.checked`/`checkbox.disabled`/the `todo-done` class on the text
span from the response — a full client round-trip with no host-level
re-render. The iframe size-reporting mechanism (`reportSize`/
`ResizeObserver`) lives entirely in the independent `_BRIDGE_JS` block, not
inside `renderGoalDetailView`'s function body, so this addition could not
have affected it.

No add/edit/reorder/delete control for todos exists anywhere in the
rendered document — `create_todo`/`update_todo`/`delete_todo`/
`reorder_todos` are never referenced from rendered UI. Those four stay
conversational/tool-only.

## Key decisions

- **Reordering is a full-list rewrite, not gap-based ordering.**
  `reorder_todos` takes the goal id and every todo id in the desired order,
  and rewrites `sort_order = 0..n-1` for all of them in one transaction.
  There was no existing reorder precedent in this codebase to follow, and
  todo lists are expected to be small (a handful of subgoal steps), so the
  cost of rewriting every row on each reorder is negligible — simpler than
  maintaining integer gaps or fractional ordering for a payoff that doesn't
  matter at this scale.
- **`create_goal` takes an optional `todos` list instead of requiring a
  second tool call.** Piggybacking on `create_goal`'s existing single-call,
  single-transaction shape avoids coordinating two tool calls and avoids a
  goal ever existing with zero todos when the LLM actually intended to
  suggest some (a transient state a separate-call design would otherwise
  allow).
- **`toggle_todo`'s checkbox is the one explicitly scoped exception to this
  project's read-only-MCP-UI default.** Per a user decision recorded in
  `knowledge/strategy.md` (2026-06-25 entry): toggling completion is a
  single unambiguous action, unlike the freeform input the read-only rule
  exists to prevent. Every other todo mutation (create, edit, reorder,
  delete) stays conversational/tool-only — this is a narrow, named
  exception, not a relaxation of the general rule.
- **Todo completion does not feed `set_goal_progress`/`progress_percent`
  automatically.** Per an explicit user decision during `/design`'s gather
  step, progress stays fully manual — completing every todo on a goal has
  no effect on its progress estimate unless the coaching AI separately calls
  `set_goal_progress`.

## Two unresolved risks, carried forward explicitly

Both recorded as **PASS WITH CAVEATS** / explicit caveats in
`knowledge/implementations/LFC-007-goal-todos/test-results.md`, not silently
passed over:

1. **RLS policies and the cascade delete have never been exercised against a
   live database.** No Docker daemon or local Postgres was available during
   implementation. All four `todos` RLS policies, the `goals → todos`
   `ON DELETE CASCADE`, and cross-user isolation were verified only via
   `alembic --sql` dry-run output and mocked-cursor application tests —
   never a real `auth.uid()` session. Before trusting this in production:
   seed a goal with todos for user A, delete the goal, confirm the todos are
   gone; seed todos for user A and attempt to SELECT/UPDATE/DELETE them as
   user B, confirming RLS rejects all three.
2. **The toggle round-trip has not been confirmed against a real MCP-UI
   host.** Source-level JS testing (function presence, control flow,
   interpolation discipline) substitutes for Playwright here, per this
   repo's existing LFC-004 precedent that MCP-UI views have no page/route of
   their own for Playwright to drive. The actual checkbox-click →
   `toggle_todo` → checked-state/strikethrough round-trip against a real
   host (e.g. Claude Desktop) remains an open item, the same way LFC-004's
   `postMessage` bridge itself was only confirmed working after merge.

## Extending this safely

- **A new todo field or mutation** should follow the existing tool shape:
  validate via a new/extended Pydantic model in `app/schemas.py`, run inside
  `get_rls_connection(current_user.id)`, and return the existing
  `TodoResponse` shape (extended, not replaced) so every caller keeps
  working.
- **A new RLS-dependent child-of-goal table** (e.g. a future
  attachments/notes table) should copy `todos`' four-policy pattern verbatim
  — `SELECT`/`INSERT`/`UPDATE`/`DELETE`, each re-deriving goal ownership via
  the same `EXISTS` subquery — rather than `updates`' two-policy,
  append-only pattern, unless the new table is itself append-only.
- **Any new interactive MCP-UI control** must go through the same
  user-decision process `toggle_todo` did before being added — this repo's
  default is read-only UI, and `toggle_todo` is the one named, narrowly
  scoped exception on record. Don't treat its existence as license to wire
  up further controls without an equivalent explicit decision.
- **If todo completion is ever asked to influence `progress_percent`**, that
  is a deliberate reversal of an explicit decision recorded above and in
  `strategy.md` — treat it as a new design decision requiring sign-off, not
  a bug fix.
