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
