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
