# Test Results: LFC-002-goals

## LFC-STORY-001

**Verdict: PASS WITH CAVEATS** — see "Environment limitation" below. No real
Postgres/Supabase instance was available to run the migration against; the
SQL-level acceptance criteria (AC1, AC2, AC3, AC4) were verified by
generating and inspecting the actual SQL Alembic would execute
(`alembic upgrade head --sql` / `alembic downgrade 2ae062d3817c:base --sql`),
not by running it against a live database. This is the same shape of work
as LFC-001-auth-infra-baseline's LFC-STORY-002 (the users-table migration),
and the same testing approach is used here.

### Layers required

- Unit: not required beyond what already exists. This migration adds no new
  business logic in `migrations/env.py` — the DB-URL-sourcing wiring it
  relies on is unchanged and already covered by
  `tests/unit/test_migrations_env.py`. There is no other unit-testable
  surface in a hand-written DDL migration file.
- Feature: there is no HTTP/API surface in this story to drive a
  conventional feature test through; the "feature" is the migration itself,
  verified via dry-run SQL generation (below) rather than a pytest feature
  test — same precedent as LFC-STORY-002.
- E2E (Playwright): **not required**. This is a backend/infrastructure-only
  story (an Alembic migration creating a table + RLS policies) with zero
  user-facing UI, no page, no rendered component, and no browser-driven
  flow. Per `rules/testing.md`, E2E is required only for stories that change
  user-facing behavior; a schema migration with no new UI is explicitly the
  kind of story called out as not needing it.

### Environment limitation (read before trusting "PASS")

No Docker daemon was running and no local Postgres/`psql` was available in
this sandbox (`docker ps` failed to connect to the daemon; `psql` not
found) — identical constraint to LFC-STORY-002. The migration also
references `auth.users`, a Supabase-managed table that doesn't exist in a
plain local Postgres without a stub schema. Given that constraint, testing
fell back to static/dry-run verification: the migration was never executed
against a real database, so things only a live DB could catch — e.g. the FK
actually resolving against a real `auth.users` row, RLS policy behavior
under an actual session with `auth.uid()` set, the index actually being
used by the planner, runtime permission errors under the `authenticated`
role — are **not** verified here. This should be re-run against a real
Supabase/Postgres instance (with the `auth` schema present) before being
considered fully verified for production.

### Dry-run SQL verification (executed for real via Alembic's offline mode, no DB needed)

Ran `alembic upgrade head --sql` against the actual migration file:
- Confirms AC1: generates `CREATE TABLE goals` with `id UUID DEFAULT
  gen_random_uuid() NOT NULL PRIMARY KEY`, `user_id UUID NOT NULL` with
  `CONSTRAINT goals_user_id_fkey FOREIGN KEY(user_id) REFERENCES auth.users
  (id) ON DELETE CASCADE`, `title TEXT NOT NULL`, `description TEXT`
  (nullable), `created_at`/`updated_at TIMESTAMP WITH TIME ZONE DEFAULT
  now() NOT NULL`, and `deleted_at TIMESTAMP WITH TIME ZONE` (nullable) —
  matches the story's column spec exactly, including the FK's `ON DELETE
  CASCADE`.
- Confirms AC2: generates `ALTER TABLE goals ENABLE ROW LEVEL SECURITY;`
  followed by `CREATE POLICY goals_select_own ... FOR SELECT USING
  (auth.uid() = user_id AND deleted_at IS NULL)`, `CREATE POLICY
  goals_insert_own ... FOR INSERT WITH CHECK (auth.uid() = user_id)`, and
  `CREATE POLICY goals_update_own ... FOR UPDATE USING (auth.uid() =
  user_id AND deleted_at IS NULL)` — wording matches the AC verbatim. No
  `DROP`/`CREATE POLICY` for a DELETE policy appears anywhere in the
  generated SQL, confirming no DELETE policy was created, per AC2.
- Confirms AC3: generates `CREATE INDEX ix_goals_user_id_deleted_at ON
  goals (user_id, deleted_at)` — column order matches the AC.

Ran `alembic downgrade 2ae062d3817c:base --sql` against the same migration:
- Confirms AC4: generates `DROP POLICY IF EXISTS goals_update_own`, `DROP
  POLICY IF EXISTS goals_insert_own`, `DROP POLICY IF EXISTS
  goals_select_own`, then `DROP INDEX ix_goals_user_id_deleted_at`, then
  `DROP TABLE goals`, in that order — policies first, then the index, then
  the table, with nothing left over. The downgrade continues on to drop the
  `users` table from the prior migration, confirming the chain is intact
  and reversible end-to-end.

Also ran `alembic history --verbose`: confirms a single linear head
(`2ae062d3817c` → parent `16b5eb4c9d06` → `<base>`) — no branching, no
chain issues.

### Static checks

- `py_compile` on the migration file: syntactically valid Python.
- No new dependencies required; `alembic`/`sqlalchemy` already installed
  from LFC-STORY-002.

### Unit tests — 0 new (no new unit-testable logic; existing
`tests/unit/test_migrations_env.py` coverage is unaffected and unchanged)

### Feature tests — not applicable; covered by dry-run SQL verification above

### E2E tests — not applicable (see rationale above)

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root: **37 passed, 0
failed** (all pre-existing tests; no new tests added by this story). No
regressions introduced by adding this migration file.

### Totals: 0 new automated tests (none applicable beyond what already
exists), 37/37 full suite passing, 0 failed. AC1–AC4 verified via dry-run
SQL generation, not live execution — see environment limitation above.
