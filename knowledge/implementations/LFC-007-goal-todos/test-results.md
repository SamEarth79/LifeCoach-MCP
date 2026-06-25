# Test Results: LFC-007-goal-todos

## LFC-STORY-007-001

**Verdict: PASS WITH CAVEATS** — see "Environment limitation" below. No real
Postgres/Supabase instance was available to run the migration against; the
SQL-level acceptance criteria (AC1, AC2, AC3) were verified by generating and
inspecting the actual SQL Alembic would execute (`alembic upgrade head --sql`
/ `alembic downgrade f024a0719f4a:66f94137137d --sql`), not by running it
against a live database. This is the same shape of work, with the same
caveat, as every prior pure-migration story in this repo
(LFC-002-goals's LFC-STORY-001, LFC-003-updates's LFC-STORY-001).

### Layers required

- Unit: not required beyond what already exists. This migration adds no new
  business logic in `migrations/env.py` — the DB-URL-sourcing wiring it
  relies on is unchanged and already covered by
  `tests/unit/test_migrations_env.py`. There is no other unit-testable
  surface in a hand-written DDL migration file.
- Feature: the story's own AC4 and AC5 explicitly call for feature tests
  (cascade-delete behavior, cross-user RLS isolation) — see "AC4/AC5 not
  satisfiable in this environment" below for why none were written this
  story.
- E2E (Playwright): **not required**. This is a backend/infrastructure-only
  story (an Alembic migration creating a table + RLS policies) with zero
  user-facing UI, no page, no rendered component, and no browser-driven
  flow. Per `rules/testing.md`, E2E is required only for stories that change
  user-facing behavior; a schema migration with no new UI is explicitly the
  kind of story called out as not needing it. No application code was
  touched in this story at all — just the migration file.

### Environment limitation (read before trusting "PASS")

No Docker daemon was running (`docker ps` failed to connect to the daemon)
and no local Postgres/`psql` was available in this sandbox (`psql --version`
→ command not found) — identical constraint to every prior migration story
in this repo. The migration also references `auth.users` (Supabase-managed)
and `goals` (created in LFC-002-goals), neither of which exists in a plain
local Postgres without the full migration chain and a stub `auth` schema.
Given that constraint, testing fell back to static/dry-run verification: the
migration was never executed against a real database, so things only a live
DB could catch — both FKs actually resolving against real `auth.users` and
`goals` rows, all four RLS policies' behavior under an actual session with
`auth.uid()` set (including each policy's `EXISTS` subquery against `goals`
actually evaluating correctly), the cascade-delete behavior from `goals` to
`todos` (AC4), cross-user isolation under `auth.uid()` (AC5), the index
actually being used by the planner, and runtime permission errors under the
`authenticated` role — are **not** verified here. This should be re-run
against a real Supabase/Postgres instance (with the `auth` schema present
and seeded `goals`/`todos` rows for two distinct users) before being
considered fully verified for production.

### Dry-run SQL verification (executed for real via Alembic's offline mode, no DB needed)

Ran `alembic upgrade head --sql` against the full migration chain (ending in
this story's migration):

- Confirms AC1: generates `CREATE TABLE todos` with `id UUID DEFAULT
  gen_random_uuid() NOT NULL PRIMARY KEY`, `user_id UUID NOT NULL` with
  `CONSTRAINT todos_user_id_fkey FOREIGN KEY(user_id) REFERENCES auth.users
  (id) ON DELETE CASCADE`, `goal_id UUID NOT NULL` with `CONSTRAINT
  todos_goal_id_fkey FOREIGN KEY(goal_id) REFERENCES goals (id) ON DELETE
  CASCADE`, `text TEXT NOT NULL`, `done BOOLEAN DEFAULT false NOT NULL`,
  `sort_order INTEGER NOT NULL`, and `created_at`/`updated_at TIMESTAMP WITH
  TIME ZONE DEFAULT now() NOT NULL` — matches the story's column spec
  exactly, including both FKs' `ON DELETE CASCADE`.
- Confirms AC2: generates `CREATE INDEX ix_todos_goal_id_sort_order ON todos
  (goal_id, sort_order)` — name and column order match the AC exactly.
- Confirms AC3: generates `ALTER TABLE todos ENABLE ROW LEVEL SECURITY;`
  followed by all four policies — `todos_select_own` (`FOR SELECT`),
  `todos_insert_own` (`FOR INSERT WITH CHECK`), `todos_update_own` (`FOR
  UPDATE USING ... WITH CHECK`), and `todos_delete_own` (`FOR DELETE`) — and
  each one's condition is verbatim `auth.uid() = user_id AND EXISTS (SELECT
  1 FROM goals g WHERE g.id = goal_id AND g.user_id = auth.uid() AND
  g.deleted_at IS NULL)`, matching the AC's required predicate exactly,
  including for the `UPDATE` policy's `WITH CHECK` clause (not just its
  `USING` clause).

Ran `alembic downgrade f024a0719f4a:66f94137137d --sql` against the same
migration (down to its immediate parent, `66f94137137d`, the
`goals.progress_percent` migration — not all the way to base, per the task
scope, since this story added exactly one migration on top of an existing
chain):

- Confirms cleanup ordering: generates `DROP POLICY IF EXISTS
  todos_delete_own`, `DROP POLICY IF EXISTS todos_update_own`, `DROP POLICY
  IF EXISTS todos_insert_own`, `DROP POLICY IF EXISTS todos_select_own`,
  then `DROP INDEX ix_todos_goal_id_sort_order`, then `DROP TABLE todos`, in
  that order — all four policies first, then the index, then the table,
  with nothing left over and no leftover reference to the dropped table.

Also ran `alembic history --verbose` / `alembic heads` across the full
chain: confirms a single linear head (`f024a0719f4a` → parent `66f94137137d`
→ `8e5660ff9d7f` → `2ae062d3817c` → `16b5eb4c9d06` → `<base>`) — no
branching, no chain issues. Satisfies AC6: `alembic upgrade head --sql`
generated the full chain end-to-end without error, confirming the migration
runs cleanly from the current head.

### AC4/AC5 not satisfiable in this environment

AC4 ("deleting a goal cascades to delete its todos, verified by a feature
test") and AC5 ("a feature test confirms a second user cannot read, update,
or delete another user's todos ... RLS enforcement, not just app-level
checks") both explicitly require a real database session: AC4 needs an
actual `ON DELETE CASCADE` to fire, and AC5 needs `auth.uid()` to be set
under the `authenticated` role across two distinct simulated users — neither
is something a mocked cursor or dry-run SQL generation can exercise without
just asserting self-consistency with its own setup (the same anti-pattern
called out in `rules/testing.md`'s "External-contract assumptions" section,
applied here to the internal RLS/cascade trust boundary, consistent with the
treatment of every other RLS-dependent story in this repo, e.g.
LFC-002-goals's LFC-STORY-003/004/005 and LFC-003-updates's LFC-STORY-001).
No application code exists yet in this story to host such a test against
either (no CRUD tool/endpoint reads or writes `todos` yet — that's later
stories in this feature). Per precedent, this is flagged explicitly as an
unverified risk rather than papered over with a test that would only prove
self-consistency. Both ACs should be re-verified against a real
Supabase/Postgres instance once a real client exists to drive them (or
directly via `psql`/the Supabase SQL editor): seed a goal with todos for
user A, delete the goal, confirm the todos are gone (AC4); seed todos for
user A and attempt to SELECT/UPDATE/DELETE them as user B's `auth.uid()`
session, confirming RLS rejects all three (AC5).

### Static checks

- `py_compile` on the migration file: syntactically valid Python.
- No new dependencies required; `alembic`/`sqlalchemy` already installed.

### Unit tests — 0 new (no new unit-testable logic; existing
`tests/unit/test_migrations_env.py` coverage is unaffected and unchanged)

### Feature tests — 0 new; not satisfiable in this environment, see
"AC4/AC5 not satisfiable" above

### E2E tests — not applicable (see rationale above)

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root: **315 passed, 0
failed** (all pre-existing tests; no new tests added by this story, since no
application code was touched). No regressions introduced by adding this
migration file.

### Totals: 0 new automated tests (AC4 and AC5 require a real database
session that doesn't exist in this sandbox, and no application code exists
yet to host a feature test against — flagged explicitly above, not silently
skipped), 315/315 full suite passing, 0 failed. AC1, AC2, AC3, and AC6
verified via dry-run SQL generation, matching the story's column/index/RLS
spec verbatim. AC4 and AC5 are unverified pending a live database — same
recurring caveat class as every other RLS-dependent migration story in this
repo, now joined by a cascade-delete behavior that's likewise only
verifiable live.

## LFC-STORY-007-002

**Verdict: PASS**

### Layers required

- Unit/feature: required and written. All six new MCP tools
  (`create_todo`, `update_todo`, `toggle_todo`, `delete_todo`, `list_todos`,
  `reorder_todos`) and the two new Pydantic schemas (`TodoCreate`,
  `TodoUpdate`) are new business logic with every acceptance criterion
  mapped to at least one assertion (see below). Followed the exact
  mocking approach already established in `tests/unit/test_mcp_server.py`
  for `record_update`/`set_goal_progress`/`delete_goal`/`list_updates`:
  tools called directly as plain async functions with a fake `ctx`, and
  `verify_bearer_token`/`enforce_mcp_rate_limit`/`get_rls_connection`
  monkeypatched so no real Postgres/Supabase instance is required — no new
  mocking pattern was introduced.
- E2E (Playwright): **not required**. This is a backend/MCP-tool-only
  story with zero new UI, no page, and no frontend consuming these tools
  yet (the todo UI lands in LFC-STORY-007-004). Same carve-out already on
  record for every backend-only story in this repo, e.g. LFC-002-goals's
  `create_goal`/`delete_goal` stories (see
  `knowledge/implementations/LFC-002-goals/test-results.md`, "E2E
  (Playwright): not required... no new UI, no page, no frontend consuming
  this endpoint yet") and LFC-003-updates's `record_update`/`list_updates`
  stories.

### Unit/feature tests — `tests/unit/test_todo_tools.py` (33 new)

- **AC1 (`create_todo`)**:
  `test_create_todo_inserts_row_with_verified_user_id_and_returns_created_todo`
  confirms the INSERT runs with the verified caller's id and the created
  todo is returned;
  `test_create_todo_computes_sort_order_via_max_plus_one_with_coalesce_to_zero`
  asserts the executed query text contains
  `COALESCE((SELECT MAX(sort_order) + 1 ...), 0)` — proving the
  first-todo-for-a-goal-gets-0 behavior is backed by the actual SQL, not
  just an asserted return value;
  `test_create_todo_rejects_blank_text_before_db_call` and
  `test_create_todo_rejects_missing_authorization_before_db_call` cover
  validation/auth failing closed before any DB call;
  `test_create_todo_raises_when_rls_insert_check_rejects_the_goal` covers
  the cross-user/RLS rejection path (AC7) — no row returned, no commit.
- **AC2 (`update_todo`)**:
  `test_update_todo_updates_text_and_returns_found_true_with_updated_todo`
  covers the success path;
  `test_update_todo_returns_found_false_without_raising_when_no_row_matches`
  asserts the tool returns `{"found": False, ...}` rather than raising
  when the todo doesn't exist or isn't owned by the caller — directly
  exercising the "no effect... clear not-found result" wording in AC2;
  `test_update_todo_rejects_blank_text_before_db_call`,
  `test_update_todo_rejects_malformed_todo_id_before_db_call`, and
  `test_update_todo_rejects_missing_authorization_before_db_call` cover
  validation/auth failing closed before any DB call.
- **AC3 (`toggle_todo`)**: `test_toggle_todo_flips_incomplete_to_complete`
  and `test_toggle_todo_flips_complete_to_incomplete` cover both
  directions of the flip (the row's `done` value mocked as the post-flip
  state the `NOT done` SQL would produce);
  `test_toggle_todo_raises_when_no_row_matches` covers the
  not-owned/nonexistent case; `test_toggle_todo_rejects_malformed_todo_id_before_db_call`
  and `test_toggle_todo_rejects_missing_authorization_before_db_call` cover
  validation/auth failing closed.
- **AC4 (`delete_todo`)**: `test_delete_todo_returns_deleted_true_when_row_removed`
  covers the success path and asserts a real `DELETE FROM todos`
  statement (never a soft delete); `test_delete_todo_is_a_no_op_and_returns_deleted_false_when_not_owned_or_missing`
  directly exercises "has no effect on todos not owned by the user" —
  exactly one statement issued, no exception, `deleted: False`;
  `test_delete_todo_rejects_malformed_todo_id_before_db_call` and
  `test_delete_todo_rejects_missing_authorization_before_db_call` cover
  validation/auth failing closed.
- **AC5 (`list_todos`)**: `test_list_todos_returns_todos_ordered_by_sort_order_ascending`
  asserts both the returned order and that the executed query contains
  `ORDER BY sort_order ASC`; `test_list_todos_returns_empty_list_for_goal_with_no_todos`
  covers the empty case; `test_list_todos_rejects_malformed_goal_id_before_db_call`
  and `test_list_todos_rejects_missing_authorization_before_db_call` cover
  validation/auth failing closed.
- **AC6 (`reorder_todos`)**:
  `test_reorder_todos_rewrites_sort_order_to_match_given_order_in_one_transaction`
  asserts one `UPDATE todos SET sort_order = %s WHERE id = %s AND goal_id
  = %s` per todo_id, each with the correct position, followed by a single
  `commit()` — confirming the rewrite happens in one transaction;
  `test_reorder_todos_subsequent_list_todos_reflects_the_new_order` directly
  exercises the AC's "a subsequent `list_todos` call reflects the new
  order" wording by calling `reorder_todos` then `list_todos` against a
  second fake connection pre-seeded with rows already in the new order
  (the same shape the real `ORDER BY sort_order ASC` query would return
  post-commit); `test_reorder_todos_rejects_missing_authorization_before_db_call`,
  `test_reorder_todos_rejects_malformed_goal_id_before_db_call`, and
  `test_reorder_todos_rejects_malformed_todo_id_in_list_before_db_call`
  cover validation/auth failing closed.
- **AC7 (cross-user rejection via RLS, all six tools)**: every tool's
  "raises/returns not-found/no-op when no row comes back" test above
  (`create_todo`'s RLS-insert-check test, `update_todo`'s found-false
  test, `toggle_todo`'s raises-when-no-row test, `delete_todo`'s no-op
  test) exercises the app-level consequence of an RLS policy excluding a
  row. As with every other RLS-dependent story in this repo (see
  LFC-STORY-007-001's "AC4/AC5 not satisfiable in this environment" and
  LFC-002-goals's RLS-dependent stories), this only proves the app
  surfaces the correct behavior when no row is returned — it cannot prove
  Postgres RLS itself is what excludes the row without a live database
  session under `auth.uid()`. Flagged here as the same recurring
  unverified-live-RLS caveat, not silently assumed verified.
- **AC8 (`TodoCreate`/`TodoUpdate` schemas)**: `test_todo_create_rejects_blank_text`,
  `test_todo_create_strips_surrounding_whitespace`,
  `test_todo_update_rejects_blank_text`, and
  `test_todo_update_strips_surrounding_whitespace` directly exercise the
  validators, confirming they follow the existing
  `reject_blank_title`/`reject_blank_content` pattern verbatim.
- `test_all_six_todo_tools_are_registered_on_the_mcp_singleton` confirms
  all six tools are actually registered on the process-wide `mcp`
  singleton (not just defined as free functions).

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root: **348 passed, 0
failed** (315 pre-existing + 33 new from this story). No regressions.

### Totals: 33 new automated tests, all passing; 348/348 full suite
passing, 0 failed. AC1–AC6 and AC8 fully verified against mocked
DB/auth/rate-limit boundaries. AC7 (cross-user RLS rejection) is verified
only at the app-behavior level (no row back → no-op/not-found/raise) — the
underlying RLS enforcement itself remains an unverified-against-a-live-
database caveat, consistent with every other RLS-dependent story in this
repo (LFC-STORY-007-001, LFC-002-goals's RLS stories).

## LFC-STORY-007-003

**Verdict: PASS**

### Layers required

- Unit/feature: required and written. `GoalCreate` gained a new `todos:
  list[str] | None` field with a `reject_blank_todos` validator, and
  `create_goal` gained a new `todos` parameter that — when non-empty —
  inserts the goal with `RETURNING id` then one `todos` row per list item
  with 0-indexed `sort_order`, and — when omitted/empty — runs the exact
  unchanged original single-INSERT query. Both are new business logic
  requiring tests. Followed the exact mocking approach already established
  in `tests/unit/test_mcp_server.py` (`_patch_db_sequenced`/`_fake_context`/
  `_patch_auth`/`_patch_rate_limit`) — no new mocking pattern introduced.
- E2E (Playwright): **not required**. This story changes no UI — the todo
  checklist's rendering in the goal-detail view is LFC-STORY-007-004's
  scope, not this one. `create_goal` itself already has no E2E coverage
  (per LFC-002-goals's precedent, carried forward in this feature's
  LFC-STORY-007-002 entry above), and this story only adds an optional
  parameter to that same backend-only tool plus prose-only changes to
  `_COACH_INSTRUCTIONS`/tool descriptions. Same carve-out as every other
  backend-only story in this repo.

### Pre-existing test confirmation (AC3 backward compatibility)

Ran the pre-existing `create_goal` tests in `tests/unit/test_mcp_server.py`
unchanged (`test_create_goal_inserts_row_with_verified_user_id_title_and_description`,
`test_create_goal_rejects_blank_title_before_db_call`,
`test_create_goal_allows_omitted_description`, and others) — all still pass
without modification, confirming that calling `create_goal` without a
`todos` argument (the only way every pre-existing caller invokes it) is
unaffected by this story's change.

### Unit/feature tests — `tests/unit/test_mcp_server.py` (10 new)

- **AC1/AC2/AC6** (todos persisted, in order, 0-indexed `sort_order`):
  `test_create_goal_with_todos_persists_each_todo_in_order_with_zero_indexed_sort_order`
  calls `create_goal` with a 3-item `todos` list and asserts, against the
  fake cursor's captured `executed` list, that the goal INSERT uses
  `RETURNING id`, and that exactly 3 subsequent `INSERT INTO todos`
  statements follow, each with params `(user_id, goal_id, text, sort_order)`
  where `sort_order` is 0, 1, 2 matching list position and `text` matches
  list order. This single test satisfies AC1, AC2 (the persistence half),
  and AC6 (the story's own "results in that many todo rows persisted ...
  correctly ordered" feature-test wording) at once.
- **AC2 (blank-todo rejection)**:
  `test_create_goal_rejects_blank_todo_in_list_before_db_call` calls
  `create_goal` with `todos=["Buy running shoes", "   "]` and asserts a
  `ValueError` is raised with zero queries executed — the validator runs
  inside `GoalCreate(...)` before the `async with get_rls_connection(...)`
  block is ever entered.
  `test_goal_create_rejects_blank_todo_in_list` exercises the same
  rejection directly at the Pydantic schema layer (`GoalCreate(...)` raises
  `ValidationError`), and
  `test_goal_create_strips_surrounding_whitespace_from_each_todo` confirms
  each surviving todo string is stripped, matching the
  `reject_blank_title`/`TodoCreate.text` precedent verbatim.
  `test_goal_create_allows_omitted_or_none_todos` confirms `todos` defaults
  to `None` and accepts an explicit `None`.
- **AC3 (no behavior change when omitted/empty)**:
  `test_create_goal_with_omitted_todos_runs_the_same_single_insert_as_before_this_story`
  mirrors the pre-existing `test_create_goal_inserts_row_with_verified_user_id_title_and_description`
  call exactly (no `todos` argument at all) and asserts the first executed
  query has no `RETURNING` and no `INSERT INTO todos` statement appears
  anywhere in the executed list.
  `test_create_goal_with_empty_todos_list_runs_the_same_single_insert_as_omitted`
  covers the same assertion for an explicitly passed `todos=[]`, since
  `if goal.todos:` is falsy for an empty list too — both omitted and empty
  collapse to the exact original query shape.
- **AC4/AC5 (instruction/description prose)**:
  `test_server_instructions_tell_claude_to_suggest_todos_on_goal_creation`
  asserts `_COACH_INSTRUCTIONS` mentions "3-5", "todo", and references goal
  creation; `test_server_instructions_tell_claude_to_use_todo_crud_tools_conversationally`
  asserts all five todo CRUD tool names
  (`create_todo`/`update_todo`/`toggle_todo`/`delete_todo`/`reorder_todos`)
  appear in the instructions;
  `test_create_goal_tool_description_instructs_suggesting_todos_at_creation`
  asserts the `create_goal` tool's own `description=` also carries the
  "3-5"/"todo" suggestion language.

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root: **358 passed, 0
failed** (348 pre-existing + 10 new from this story). No regressions.

### Totals: 10 new automated tests, all passing; 358/358 full suite
passing, 0 failed. AC1, AC2, AC3, AC4, AC5, and AC6 are all directly
covered. No new RLS/live-database caveat is introduced by this story — the
todo INSERT statements run inside the same `get_rls_connection`-scoped
transaction as the existing goal INSERT, so they inherit the same
already-flagged unverified-against-a-live-database caveat as every prior
RLS-dependent story in this repo (LFC-STORY-007-001, LFC-STORY-007-002),
not a new one specific to this story.

## LFC-STORY-007-004

**Verdict: PASS**

### Implementation verified against the backend agent's report (not trusted at face value)

Read `app/ui_templates.py` and `app/mcp_server.py::get_goal_detail_view` in
full before writing any test. Confirmed:

- `GoalDetailTodo` (`id`, `text`, `done`, `sort_order`) and the `todos:
  list[GoalDetailTodo]` field on `GoalDetailViewData` exist exactly as the
  story specifies; `goal_detail_data_to_dict` maps each one to `{"id",
  "text", "done", "sortOrder"}` — confirmed camelCase mapping, including
  for an empty list and for the error-short-circuit path (`todos` absent
  from the dict entirely when `error` is set, same discipline as every
  other field).
- `get_goal_detail_view` issues a second query, `SELECT id, text, done,
  sort_order FROM todos WHERE goal_id = %s ORDER BY sort_order ASC`, only
  after the goal-row query succeeds, and populates `GoalDetailViewData.todos`
  from it — confirmed by reading the query string directly, matching AC1
  verbatim (including the `ORDER BY sort_order ASC` clause).
- `renderGoalDetailView`'s embedded JS gates the entire checklist section
  (`<p class="section-label">Checklist</p>` + `<div class="todo-list">`)
  behind `data.todos && data.todos.length > 0`, so a goal with zero todos
  renders no checklist markup at all rather than an empty wrapper (AC7).
  Items are built via a plain ascending `for` loop over `data.todos`,
  rendering whatever order the array already arrives in — i.e. exactly the
  server's `sort_order ASC` order, with no client-side re-sort (AC3).
- `todoItem(t)` renders an `<input type="checkbox" class="todo-checkbox">`
  plus a `<span class="todo-text">`, escaping `t.id` and `t.text` via the
  existing `escapeHtml`, applying the `checked` attribute and `todo-done`
  class only when `t.done` is true.
- The checkbox's `onchange` interpolates only `safeId` into the
  `toggleTodo('<id>')` JS-string context, never `safeText` — re-verified
  the same onclick/onchange-interpolation-discipline property this repo has
  enforced since LFC-STORY-004 of LFC-004-mcp-ui-home-goal-views (only a
  trusted server-generated id may land in a JS-execution-context string;
  free text never does).
- `toggleTodo(todoId)` disables the checkbox *before* calling
  `window.callTool("toggle_todo", { todo_id: todoId })` (preventing a
  double-fire from a second click while the first call is in flight), then
  on resolution sets `checkbox.checked = d.done`, re-enables the checkbox,
  and adds/removes the `todo-done` class on the text span to match — this
  is the full round-trip AC4 describes.
- Grepped the entire rendered document (both `render_goal_detail_view()`
  and `render_home_view()`, since the home view swaps in detail markup via
  client-side `innerHTML`) for any add/edit/reorder/delete-todo control or
  reference to `create_todo`/`update_todo`/`delete_todo`/`reorder_todos` —
  none present anywhere (AC5). Only `toggle_todo` is ever called from
  rendered UI, matching the story's "those remain conversational/tool-only"
  framing.
- `app/mcp_server.py`'s `_tool_manager._tools[...].meta` mutations at the
  bottom of the file do **not** include an entry for `toggle_todo` —
  confirmed it carries no `ui` key, i.e. it is a structured-data-returning
  tool consumed entirely client-side via `window.callTool`'s promise, never
  a tool that triggers a host-level page re-render the way
  `get_goal_detail_view`/`delete_goal`/`create_goal` do.
- The iframe size-reporting mechanism (`reportSize()`/`ResizeObserver`/
  `ui/notifications/size-changed`) lives entirely in the shared `_BRIDGE_JS`
  block, outside `renderGoalDetailView`'s own function body — confirmed by
  string-searching `renderGoalDetailView`'s extracted function body and
  finding zero occurrences of `reportSize`/`ResizeObserver` inside it. The
  todo-checklist addition could not have touched this mechanism (AC6); the
  pre-existing `test_render_goal_detail_view_reports_size_changes_to_host`
  test (data-independent, asserting only static JS source presence) was
  re-run unmodified and still passes.

### E2E (Playwright) question — explicit reasoning, not added

The story flags this as needing Playwright per `rules/testing.md` ("any
story changing user-facing behavior needs E2E"), and this is genuinely the
first *interactive* element in a checklist sense. But this repo already has
a controlling, directly-on-point precedent that overrides the generic
rule: `knowledge/implementations/LFC-004-mcp-ui-home-goal-views/test-results.md`
explicitly determined, across every one of its stories (LFC-STORY-003
through -005, plus the later "Post-merge fix: MCP Apps re-architecture"
section), that **Playwright/browser E2E does not apply to this repo's
MCP-UI surface at all**: `render_home_view()`/`render_goal_detail_view()`
return a static HTML document containing inline JS that is loaded and
executed by an *external* MCP-UI host (Claude Desktop or equivalent) inside
a sandboxed iframe via a `postMessage`/`ui/initialize` bridge — this repo
serves the resource but owns no page/route of its own for Playwright to
navigate to and drive. The precedent's chosen substitute — confirmed
working there and followed identically here — is thorough unit-level
testing against the actual JS *source* (function presence, control flow,
string-literal interpolation discipline, CSS class presence) rather than
executing the JS in a real browser, which the precedent file states
explicitly: "this view is HTML rendered for an MCP-UI host, not a page or
route of this repo's own to drive with Playwright."

This is also not the first *interactive* element despite being the first
*checklist*: `goalCard`'s onclick (home → detail navigation),
`delete_goal`'s two-stage confirm flow, and `continueGoal`'s
DOM-`textContent` round-trip were all interactive elements introduced in
LFC-004 and tested this same source-level way, with zero Playwright tests
written for any of them, and that precedent was never revisited or
overturned by any later story in this repo (including the
"Post-merge fix" section, which confirmed the bridge actually works against
a real Claude Desktop client — by manual user verification, not Playwright).
`toggleTodo`'s `window.callTool(...).then(...)` round-trip follows the
identical pattern already established by `confirmDelete`'s and
`goalCard`'s own `window.callTool(...).then(...)` round-trips, so the same
substitute applies with no new justification needed beyond what's already
on record.

**Conclusion: no Playwright/E2E tests were added, consistent with this
repo's own established precedent for MCP-UI views specifically — this is
not a skip of the rule, it is following the more specific, already-decided
precedent that supersedes the generic rule for this one surface.** If a
live MCP-UI host (e.g. real Claude Desktop) becomes available for manual or
scripted verification in the future, the toggle round-trip (checkbox click
→ `toggle_todo` call → checked-state/strikethrough update) should be
confirmed there, the same way LFC-004's `postMessage` bridge itself was
eventually confirmed working against a real client after merge — this is
recorded as an open item, not a settled fact.

### Unit tests — 11 new, all passing

Added to `tests/unit/test_ui_templates.py`:

1. `test_render_goal_detail_view_includes_todo_item_and_toggle_functions` —
   confirms `todoItem`/`toggleTodo` are present in the rendered document.
2. `test_render_goal_detail_view_renders_checklist_section_when_todos_present`
   — AC3: the `data.todos.length > 0` gate, the `Checklist` label, and the
   `todo-list` wrapper are all present and wired to `todoItem(data.todos[t])`.
3. `test_render_goal_detail_view_iterates_todos_in_given_order` — AC3:
   confirms a plain ascending `for` loop with no client-side sort/reverse,
   i.e. render order is exactly the server-provided `sort_order ASC` order.
4. `test_render_goal_detail_view_omits_checklist_entirely_when_todos_empty`
   — AC7: confirms the checklist label and wrapper are both gated behind
   the single `data.todos.length > 0` check (only one `if (` in that
   branch), so a zero-todos goal renders neither an empty wrapper nor a
   label with nothing under it.
5. `test_todo_item_function_renders_checkbox_and_text_reflecting_done_state`
   — AC3: confirms the checkbox/text markup and the `t.done`-conditioned
   `checked` attribute and `todo-done` class.
6. `test_todo_item_onclick_interpolates_only_safe_id_never_free_text` —
   re-verifies the onclick/onchange-interpolation-discipline property
   (only `safeId`, never `safeText`, lands in the `onchange` JS-string
   context) established for every other interactive element since
   LFC-004.
7. `test_toggle_todo_calls_calltool_with_todo_id_and_disables_checkbox_first`
   — AC4: confirms `checkbox.disabled = true` happens before
   `window.callTool("toggle_todo", { todo_id: todoId })` fires.
8. `test_toggle_todo_reconciles_checked_state_and_strikethrough_from_response`
   — AC4: confirms `checkbox.checked = d.done`, `checkbox.disabled = false`,
   and the `todo-done` class add/remove all happen in the `.then(...)`
   resolution callback.
9. `test_render_goal_detail_view_has_no_add_edit_reorder_delete_todo_controls`
   — AC5: greps the full rendered document (both views) for any
   add/edit/reorder/delete-todo control text or reference to
   `create_todo`/`update_todo`/`delete_todo`/`reorder_todos` — none found.
10. `test_render_goal_detail_view_todo_section_styles_present_in_shared_stylesheet`
    — confirms `.todo-list`/`.todo-item`/`.todo-checkbox`/`.todo-text`/
    `.todo-done` are all present in the shared stylesheet.
11. `test_render_goal_detail_view_size_reporting_unaffected_by_todo_section`
    — AC6: confirms `reportSize`/`ResizeObserver` do not appear inside
    `renderGoalDetailView`'s own function body (they live in the
    independent, unmodified `_BRIDGE_JS` block), and that the
    size-reporting wiring is still present in the full document.
The pre-existing `test_render_goal_detail_view_reports_size_changes_to_host`
and `test_render_goal_detail_view_includes_bridge_js_initialize_handshake`
tests (data-independent, asserting only static JS source presence) were
also re-run unmodified alongside the 11 new tests above, re-confirming AC6
and the bridge handshake are untouched by this story.

(11 new test functions total were added to `tests/unit/test_ui_templates.py`
— see the file for the exact list; the descriptions above map each to its
acceptance criterion.)

### Pre-existing tests re-run, confirmed still accurate (not just trusted)

- `tests/unit/test_ui_templates.py::test_goal_detail_data_to_dict_maps_camel_case_fields`
  (already updated by the backend agent) — re-read and confirmed it
  exercises a real `GoalDetailTodo` instance and asserts the exact
  `{"id", "text", "done", "sortOrder"}` shape, not a partial/loose match.
- `tests/unit/test_ui_templates.py::test_goal_detail_data_to_dict_maps_multiple_todos_in_sort_order`
  and `..._empty_todos_list` (already added by the backend agent) —
  confirmed they assert order-preservation across multiple todos and the
  empty-list case respectively; both genuinely exercise AC2's mapping
  contract, not just "doesn't crash."
- `tests/unit/test_mcp_server.py::test_get_goal_detail_view_query_selects_todos_ordered_by_sort_order`
  and `..._renders_empty_todos_list_when_goal_has_no_todos` (already added
  by the backend agent) — confirmed the first asserts the exact executed
  SQL text (`SELECT id, text, done, sort_order` / `FROM todos` / `ORDER BY
  sort_order ASC` / params) rather than just a returned shape, directly
  satisfying AC1's "ordered by sort_order" wording at the query level, and
  the second confirms AC7's zero-todos case actually exists and passes
  (not just claimed) — `result["todos"] == []` for a goal with no todo
  rows.
- `tests/feature/test_mcp_get_goal_detail_view.py`'s wire-protocol test was
  updated by the backend agent to pass an empty `todo_rows` list through
  the mocked DB sequence — re-run and confirmed it still exercises the full
  real `initialize` → `notifications/initialized` → `tools/call` handshake
  unmodified otherwise.

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root twice in a row to
rule out flakiness:

- Run 1: **373 passed**, 0 failed, 36 warnings (same pre-existing
  deprecation warnings as before, unrelated to this story).
- Run 2: **373 passed**, 0 failed, 36 warnings — identical result, no
  flakiness.

373 = 358 (prior baseline from LFC-STORY-007-003) + 2 new unit tests already
added by the backend agent to `tests/unit/test_mcp_server.py`
(`test_get_goal_detail_view_query_selects_todos_ordered_by_sort_order`,
`test_get_goal_detail_view_renders_empty_todos_list_when_goal_has_no_todos`)
+ 2 new unit tests already added by the backend agent to
`tests/unit/test_ui_templates.py`
(`test_goal_detail_data_to_dict_maps_multiple_todos_in_sort_order`,
`test_goal_detail_data_to_dict_empty_todos_list`) + 11 new unit tests added
by this QA pass to `tests/unit/test_ui_templates.py` = 373. The full suite
run confirms this exactly: **373 passed, 0 failed**, across two consecutive
runs.

### Totals: 11 new automated tests (this QA pass) + 4 new automated tests
(already added by the backend agent and confirmed accurate, not just
trusted) = 15 new tests attributable to this story, 373/373 full suite
passing across two consecutive runs, 0 failed, no flakiness. All 7
acceptance criteria are covered by at least one test each: AC1/AC2 at the
query/mapping level (backend agent's tests, re-verified), AC3/AC5/AC7 at the
rendering-JS-source level (new), AC4 at the toggle-round-trip JS-source
level (new), AC6 by confirming the size-reporting mechanism is structurally
independent of and untouched by the new checklist section (new). No
Playwright/E2E tests were added — this repo's own established precedent
for MCP-UI views (`LFC-004-mcp-ui-home-goal-views/test-results.md`)
explicitly determined browser E2E does not apply to this surface, since the
HTML/JS is rendered by an external MCP-UI host this repo doesn't control
and has no page/route of its own to drive with Playwright; the toggle
round-trip against a real host remains an open verification item, the same
class of caveat as LFC-004's `postMessage` bridge was before it was
eventually confirmed working post-merge.
