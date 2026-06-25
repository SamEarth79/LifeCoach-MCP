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
