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
