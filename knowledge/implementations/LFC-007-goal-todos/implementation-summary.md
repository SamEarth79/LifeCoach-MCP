# Implementation Summary: LFC-007-goal-todos

## LFC-STORY-007-001

Tested the new `todos` table migration
(`migrations/versions/f024a0719f4a_create_todos_table.py`) entirely through
Alembic's offline SQL-generation mode, since no Docker daemon or local
Postgres/`psql` was available in this environment (`docker ps` failed to
connect; `psql --version` → command not found) — the same constraint
documented for every prior migration story in this repo (LFC-002-goals's
`goals` table, LFC-003-updates's `updates` table).

Ran `alembic upgrade head --sql` and diffed the generated DDL against each
acceptance criterion line by line: the `CREATE TABLE todos` statement, both
foreign keys (`user_id` → `auth.users.id`, `goal_id` → `goals.id`, both `ON
DELETE CASCADE`), the `ix_todos_goal_id_sort_order` index, the `ENABLE ROW
LEVEL SECURITY` statement, and all four `CREATE POLICY` statements
(`todos_select_own`, `todos_insert_own`, `todos_update_own`,
`todos_delete_own`) all matched the story's wording verbatim — including
confirming each policy's predicate is exactly `auth.uid() = user_id AND
EXISTS (SELECT 1 FROM goals g WHERE g.id = goal_id AND g.user_id =
auth.uid() AND g.deleted_at IS NULL)`, and that the `UPDATE` policy applies
that same predicate to both its `USING` and `WITH CHECK` clauses.

Ran `alembic downgrade f024a0719f4a:66f94137137d --sql` (down to the
migration's immediate parent, not all the way to base, since this story adds
exactly one migration on top of an existing chain) and confirmed the reverse
order is correct — all four policies dropped, then the index, then the
table, nothing left over. Ran `alembic heads` / `alembic history --verbose`
to confirm a single linear chain with no branching: `f024a0719f4a` →
`66f94137137d` → `8e5660ff9d7f` → `2ae062d3817c` → `16b5eb4c9d06` → base —
and that the full `alembic upgrade head --sql` run across the entire chain
completes without error, satisfying AC6.

AC4 (cascade delete from `goals` to `todos`) and AC5 (cross-user RLS
isolation) both explicitly call for feature tests in the story, but neither
is satisfiable in this environment: both require a real database session
(`auth.uid()` set under the `authenticated` role, and a real `ON DELETE
CASCADE` actually firing) that a mocked cursor or dry-run SQL cannot
exercise without just proving self-consistency with its own setup. No
application code exists yet in this story either (no CRUD tool reads or
writes `todos`), so there's nothing to host a feature test against. This
was flagged explicitly in `test-results.md` rather than skipped silently or
faked with a misleading mock-based test, consistent with
`rules/testing.md`'s treatment of internal RLS trust-boundary assumptions
in every prior story in this repo.

This is a backend/infra-only story (a database migration, no application
code touched) with no user-facing surface, so per `rules/testing.md` no E2E
tests were required, and no new unit tests were written (no new
unit-testable logic beyond the DDL itself). Ran the full existing suite
(`.venv/bin/python -m pytest -q`): 315 passed, 0 failed, no regressions —
expected, since this story added no test files and touched no application
code.

Flagged as **PASS WITH CAVEATS**: the migration was never executed against
a real database, so the FKs' actual resolution, all four RLS policies'
runtime behavior under `auth.uid()`, the cascade-delete behavior (AC4), and
cross-user isolation (AC5) remain unverified. This should be re-run against
a real Supabase/Postgres instance before being considered production-ready,
consistent with the same caveat already on record for every other migration
story in this repo.

## LFC-STORY-007-002

Tested the six new MCP tools (`create_todo`, `update_todo`, `toggle_todo`,
`delete_todo`, `list_todos`, `reorder_todos`) added to `app/mcp_server.py`,
plus the four new Pydantic schemas (`TodoCreate`, `TodoUpdate`,
`TodoResponse`, `TodoReorder`) added to `app/schemas.py`, by writing
`tests/unit/test_todo_tools.py` — 33 new tests following exactly the same
mocking approach already established in `tests/unit/test_mcp_server.py`
for `record_update`/`set_goal_progress`/`delete_goal`/`list_updates`: each
tool is called directly as a plain async function with a fake `ctx`
(`SimpleNamespace` wrapping `request_context.request.headers`), and
`verify_bearer_token`, `enforce_mcp_rate_limit`, and `get_rls_connection`
are all monkeypatched with fake async-context-manager connections/cursors,
so no real Postgres/Supabase instance is needed. No new test framework or
mocking pattern was introduced — `reorder_todos`, which issues one `UPDATE`
per todo_id rather than a single statement, needed one new small fixture
(`_SequentialCursor`/`_SequentialConnection`) that returns a different
`fetchone()` result per call, built the same way the existing
`_DeleteThenRefreshCursor` in `test_mcp_server.py` handles `delete_goal`'s
own two-phase query pattern.

Every acceptance criterion maps to at least one test: AC1's
first-todo-for-a-goal-gets-0 sort_order behavior is verified by asserting
the actual executed SQL contains
`COALESCE((SELECT MAX(sort_order) + 1 FROM todos WHERE goal_id = %s), 0)`,
not just by asserting a returned value; AC2's "no effect and a clear
not-found result" requirement for `update_todo` is verified by asserting
the tool returns `{"found": False, ...}` rather than raising when no row
comes back; AC3 covers both directions of the `toggle_todo` flip; AC4
verifies `delete_todo` issues a real `DELETE FROM todos` (never soft) and
returns `deleted: False` as a no-op when nothing matched; AC5 verifies
`list_todos`'s `ORDER BY sort_order ASC` both in the executed query text
and the returned order; AC6 verifies `reorder_todos` issues one `UPDATE
... SET sort_order = %s WHERE id = %s AND goal_id = %s` per todo_id with
the correct position before a single commit, plus a dedicated test that
calls `reorder_todos` then `list_todos` end-to-end (against two separate
fake connections, the second pre-seeded with rows already in the new
order) to directly exercise the AC's "a subsequent list_todos call
reflects the new order" wording; AC8 exercises `TodoCreate`/`TodoUpdate`
directly, confirming both follow the existing
`reject_blank_title`/`reject_blank_content` whitespace-stripping/
blank-rejection validator pattern verbatim.

AC7 (every tool rejecting another user's `goal_id`/`todo_id` via RLS) is
verified only at the app-behavior level — each tool's "no row comes back"
path (the RLS-insert-check test for `create_todo`, the found-false test
for `update_todo`, the raises-when-no-row test for `toggle_todo`, the
no-op test for `delete_todo`) is exercised and confirmed to fail closed
with no partial write. This cannot prove Postgres RLS itself is what
excludes the row without a live database session under `auth.uid()` — the
same recurring caveat already on record for every other RLS-dependent
story in this repo (LFC-STORY-007-001, LFC-002-goals's RLS stories).
Flagged explicitly in `test-results.md` rather than silently assumed
verified.

This is a backend/MCP-tool-only story with no new UI (the todo UI lands in
LFC-STORY-007-004), so per `rules/testing.md` and the same precedent
already on record for LFC-002-goals's `create_goal`/`delete_goal` stories
and LFC-003-updates's `record_update`/`list_updates` stories, no E2E
(Playwright) tests were required or written. Ran the full existing suite
(`.venv/bin/python -m pytest -q`): **348 passed, 0 failed** (315
pre-existing + 33 new), no regressions introduced.

Verdict: **PASS**. AC1–AC6 and AC8 are fully verified against mocked
DB/auth/rate-limit boundaries; AC7's underlying RLS enforcement remains an
unverified-against-a-live-database caveat, consistent with the rest of
this feature and repo.

## LFC-STORY-007-003

Tested the backend agent's change adding an optional `todos: list[str] |
None` argument to `create_goal` (`app/mcp_server.py`) and a matching
`todos` field with a `reject_blank_todos` validator to `GoalCreate`
(`app/schemas.py`), plus the accompanying prose updates to
`_COACH_INSTRUCTIONS` and `create_goal`'s tool `description=` instructing
the LLM to suggest 3-5 subgoal-style todos at goal creation and to use the
existing todo CRUD tools conversationally. Added 10 new tests to
`tests/unit/test_mcp_server.py`, following the file's existing
`_patch_db_sequenced`/`_fake_context`/`_patch_auth`/`_patch_rate_limit`
mocking pattern exactly — no new test fixture or mocking approach was
introduced.

First confirmed backward compatibility (AC3) by running the pre-existing
`create_goal` tests unchanged — they still pass with no modification,
since every existing caller invokes `create_goal` without `todos` and the
code path for that case (`else: await cursor.execute(...)` with the
original, unmodified single-INSERT query) is untouched.

Then added tests for the new behavior:
`test_create_goal_with_todos_persists_each_todo_in_order_with_zero_indexed_sort_order`
asserts, against the fake cursor's captured executed statements, that a
3-item `todos` list produces a goal INSERT with `RETURNING id` followed by
exactly 3 `INSERT INTO todos` statements with `sort_order` 0, 1, 2 matching
list position and order — covering AC1, AC2's persistence half, and AC6's
"results in that many todo rows persisted ... correctly ordered" wording
in one test.
`test_create_goal_rejects_blank_todo_in_list_before_db_call` and the
schema-level `test_goal_create_rejects_blank_todo_in_list` both confirm a
blank/whitespace-only entry in the `todos` list raises `ValueError`/
`ValidationError` before any DB call, mirroring the existing
`reject_blank_title`/`TodoCreate.text` precedent.
`test_create_goal_with_omitted_todos_runs_the_same_single_insert_as_before_this_story`
and `test_create_goal_with_empty_todos_list_runs_the_same_single_insert_as_omitted`
both assert the first executed query has no `RETURNING` and that no
`INSERT INTO todos` statement appears anywhere in the executed list,
directly proving AC3 for both the omitted and the explicitly-empty-list
case (`if goal.todos:` is falsy for both).
Three further tests
(`test_server_instructions_tell_claude_to_suggest_todos_on_goal_creation`,
`test_server_instructions_tell_claude_to_use_todo_crud_tools_conversationally`,
`test_create_goal_tool_description_instructs_suggesting_todos_at_creation`)
confirm the AC4/AC5 prose changes landed in both
`_COACH_INSTRUCTIONS` and the tool description.

This story changes no UI (the todo checklist's rendering is
LFC-STORY-007-004's scope), and `create_goal` itself has never carried E2E
coverage per this repo's existing backend-only-story precedent
(LFC-002-goals, LFC-STORY-007-002 above) — so per `rules/testing.md` no
E2E (Playwright) tests were required or written.

Ran the full existing suite (`.venv/bin/python -m pytest -q`): **358
passed, 0 failed** (348 pre-existing + 10 new), no regressions.

Verdict: **PASS**. AC1 through AC6 are all directly covered by the new
tests. The new todo INSERTs run inside the same `get_rls_connection`-scoped
transaction as the pre-existing goal INSERT, so no new RLS/live-database
caveat is introduced beyond the one already on record for this feature
(LFC-STORY-007-001, LFC-STORY-007-002).

## LFC-STORY-007-004

Tested the backend agent's change wiring a todo checklist into the goal
detail view: `GoalDetailTodo` (`id`/`text`/`done`/`sort_order`) and a
`todos` field on `GoalDetailViewData` in `app/ui_templates.py`, mapped to
camelCase by `goal_detail_data_to_dict`; a `todoItem()`/`toggleTodo()` JS
pair added to `renderGoalDetailView`'s embedded client-side script,
rendering a checkbox-plus-text checklist item per todo (struck-through when
done), omitted entirely when `data.todos` is empty; and a second query in
`get_goal_detail_view` (`SELECT id, text, done, sort_order FROM todos WHERE
goal_id = %s ORDER BY sort_order ASC`) populating that field. Read all three
pieces directly before writing any test rather than trusting the backend
report at face value.

First confirmed the backend agent's own claims: the existing unit/feature
tests it updated in `tests/unit/test_ui_templates.py`,
`tests/unit/test_mcp_server.py`, and
`tests/feature/test_mcp_get_goal_detail_view.py` to account for the new
required `todos` field and the new DB query all still pass unmodified, and
re-read the two genuinely new tests the backend agent had already added
(`test_get_goal_detail_view_query_selects_todos_ordered_by_sort_order` and
`..._renders_empty_todos_list_when_goal_has_no_todos` in
`test_mcp_server.py`; `test_goal_detail_data_to_dict_maps_multiple_todos_in_sort_order`
and `..._empty_todos_list` in `test_ui_templates.py`) to confirm they
actually assert at the SQL/mapping level (exact query text, exact list
order, the genuine empty-list case) rather than just "doesn't crash" — they
do.

Then added the new coverage this story specifically requires beyond that:
11 new tests in `tests/unit/test_ui_templates.py`, each mapped to one of
this story's acceptance criteria, asserting against `renderGoalDetailView`'s
embedded JS *source* (the rendering happens client-side inside an external
MCP-UI host's iframe, so there is no server-side HTML output left to assert
against data inputs — this is the same constraint every other
`render_goal_detail_view`/`render_home_view` test in this file already
operates under, established back in the MCP Apps re-architecture documented
in `LFC-004-mcp-ui-home-goal-views/test-results.md`):

- Checklist rendering gated behind `data.todos.length > 0`, iterating in
  given order with a plain ascending loop (AC3), and omitted entirely —
  both the label and the wrapper — when empty (AC7).
- The checkbox+text markup itself, `done`-conditioned `checked`/`todo-done`
  state, and — re-verifying the onclick-interpolation-discipline property
  this repo has enforced on every interactive element since LFC-004 — that
  only the trusted `safeId`, never the free-text `safeText`, is interpolated
  into the checkbox's `onchange` JS-string context.
- `toggleTodo`'s full round-trip (AC4): disables the checkbox before
  calling `window.callTool("toggle_todo", { todo_id: todoId })`, then
  reconciles `checkbox.checked`, `checkbox.disabled`, and the `todo-done`
  class from the resolved response.
- A full-document grep (both views, since the home view swaps in detail
  markup via client-side `innerHTML`) confirming no add/edit/reorder/delete
  todo control or reference to `create_todo`/`update_todo`/`delete_todo`/
  `reorder_todos` appears anywhere (AC5) — those tools remain
  conversational/tool-only, never wired to a rendered UI control.
- The new `.todo-list`/`.todo-item`/`.todo-checkbox`/`.todo-text`/
  `.todo-done` CSS classes are present in the shared stylesheet.
- AC6 (iframe size-reporting unaffected): confirmed `reportSize`/
  `ResizeObserver` live entirely in the independent, unmodified
  `_BRIDGE_JS` block — not inside `renderGoalDetailView`'s own function
  body — so the checklist addition could not have touched it; the
  pre-existing, data-independent
  `test_render_goal_detail_view_reports_size_changes_to_host` test was
  re-run unmodified and still passes.

### E2E (Playwright) decision

The story explicitly flags Playwright per `rules/testing.md`'s general
rule for user-facing changes, but this repo has direct, on-point precedent
overriding that generic rule for this specific surface:
`knowledge/implementations/LFC-004-mcp-ui-home-goal-views/test-results.md`
already determined, across every one of its UI stories, that
Playwright/browser E2E does not apply to MCP-UI views in this codebase —
`render_goal_detail_view()` returns a static HTML document whose embedded
JS is executed by an *external* MCP-UI host (Claude Desktop or equivalent)
inside a sandboxed iframe, not by any page or route this repo serves and
could drive with Playwright. That precedent's substitute — thorough
source-level JS testing — was followed here identically, the same way it
was already followed for `goalCard`'s onclick, `delete_goal`'s two-stage
confirm, and `continueGoal`'s DOM-`textContent` round-trip, none of which
ever had a Playwright test written for them either. No new justification
was needed beyond citing that already-decided precedent; no Playwright
tests were added. The toggle round-trip against a real MCP-UI host remains
an open verification item, the same class of caveat LFC-004's `postMessage`
bridge carried until it was confirmed working against a real Claude
Desktop client after that feature merged.

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root twice in a row:
**373 passed, 0 failed** both times, no flakiness. 373 = 358 (prior
baseline) + 2 backend-added tests in `test_mcp_server.py` + 2
backend-added tests in `test_ui_templates.py` + 11 new tests added by this
QA pass = 373.

Verdict: **PASS**. All 7 acceptance criteria are covered by at least one
test each. No new RLS/live-database caveat beyond what's already on record
for this feature; no Playwright/E2E gap, since this repo's own
already-established MCP-UI precedent determines it doesn't apply to this
surface.
