# Test Results: LFC-004-mcp-ui-home-goal-views

## LFC-STORY-001

**Verdict: PASS WITH CAVEATS** — verified only via Alembic dry-run SQL
generation, not against a live database. No Docker daemon or local
Postgres/`psql` was available in this sandbox, identical constraint to
every prior migration-only story in this repo (LFC-001-auth-infra-baseline's
LFC-STORY-002, LFC-002-goals's LFC-STORY-001, LFC-003-updates's
LFC-STORY-001). Same dry-run verification approach used here.

### Layers required

- Unit: not required beyond what already exists. This migration adds no
  new business logic — there is no hand-written Python logic in a pure DDL
  migration file beyond the Alembic `op.*` calls themselves, which are
  exercised by the dry-run verification below, not a unit test.
- Feature: there is no HTTP/API/MCP surface introduced by this story to
  drive a conventional feature test through; the "feature" is the migration
  itself, verified via dry-run SQL generation — same precedent as
  LFC-002-goals's LFC-STORY-001 and LFC-003-updates's LFC-STORY-001.
- E2E (Playwright): **not required**. This is a backend-only story (an
  Alembic migration adding a column + CHECK constraint to `goals`) with
  zero user-facing UI, no page, no rendered component, and no browser-driven
  flow. Per `rules/testing.md`, E2E is required only for stories that change
  user-facing behavior; a schema migration with no new UI is explicitly the
  kind of story called out as not needing it.

### Environment limitation (read before trusting "PASS")

No Docker daemon was running and no local Postgres/`psql` was available in
this sandbox — identical constraint to every prior migration story in this
repo. The migration only touches the existing `goals` table (created in
LFC-002-goals), so resolving the migration chain itself required no stub
schema, but actually executing the `ALTER TABLE`/`ADD CONSTRAINT` statements
against a live table with real rows, and confirming the CHECK constraint is
actually enforced by Postgres at INSERT/UPDATE time, was **not** done — only
the SQL Alembic would generate was inspected. This should be re-run against
a real Supabase/Postgres instance before being considered fully verified for
production.

### Dry-run SQL verification (executed for real via Alembic's offline mode, no DB needed)

Ran `.venv/bin/python -m alembic upgrade 8e5660ff9d7f:66f94137137d --sql`:

```sql
ALTER TABLE goals ADD COLUMN progress_percent INTEGER;

ALTER TABLE goals ADD CONSTRAINT goals_progress_percent_check CHECK (progress_percent IS NULL OR (progress_percent BETWEEN 0 AND 100));
```

- Confirms AC1: `progress_percent` is added as `INTEGER`, with no `NOT NULL`
  clause (i.e. nullable) and no `DEFAULT` clause — matches "nullable, no
  default" exactly.
- Confirms AC2: the generated `CHECK` constraint text is byte-for-byte
  `progress_percent IS NULL OR (progress_percent BETWEEN 0 AND 100)` —
  matches the AC's required expression verbatim.
- Confirms AC3: no `UPDATE`/backfill statement appears anywhere in the
  generated SQL — existing rows are untouched and will read back as
  `progress_percent IS NULL`, consistent with the column being added with
  no default and no backfill.

Ran `.venv/bin/python -m alembic downgrade 66f94137137d:8e5660ff9d7f --sql`:

```sql
ALTER TABLE goals DROP CONSTRAINT goals_progress_percent_check;

ALTER TABLE goals DROP COLUMN progress_percent;
```

- Confirms AC5: `downgrade()` drops the CHECK constraint first, then the
  column, in that order — the constraint cannot outlive the column it
  constrains, and nothing is left over after downgrade. This is the correct
  reverse order of `upgrade()`'s add-column-then-add-constraint sequence.

Ran `.venv/bin/python -m alembic history --verbose`: confirms a single
linear chain, `66f94137137d` (head) → parent `8e5660ff9d7f` → parent
`2ae062d3817c` → parent `16b5eb4c9d06` → `<base>`. No branching, no chain
issues; `down_revision="8e5660ff9d7f"` correctly points at the actual
current head before this story.

### RLS — confirmed no change needed (AC4)

Read `migrations/versions/2ae062d3817c_create_goals_table.py` in full. The
existing policies are:

- `goals_select_own`: `FOR SELECT USING (auth.uid() = user_id AND deleted_at IS NULL)`
- `goals_update_own`: `FOR UPDATE USING (auth.uid() = user_id AND deleted_at IS NULL) WITH CHECK (auth.uid() = user_id)`

Both predicates operate purely on `user_id`/`deleted_at` at the row level —
Postgres RLS policies apply uniformly to every column of a row they admit;
there is no per-column RLS mechanism that would need to separately list
`progress_percent`. Once a row passes these `USING`/`WITH CHECK` clauses,
all of its columns — including the newly added `progress_percent` — are
visible/writable exactly as before. No new policy, and no edit to an
existing policy, is required. This confirms the backend agent's claim and
AC4.

### Static checks

- `py_compile` on the migration file: syntactically valid Python (implicit
  in the dry-run `--sql` invocation succeeding, which requires importing
  the module).
- No new dependencies required; `alembic`/`sqlalchemy` already installed.

### Unit tests — 0 new (no new unit-testable logic introduced by this story)

### Feature tests — not applicable; covered by dry-run SQL verification above

### E2E tests — not applicable (see rationale above)

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root: **110 passed, 0
failed** (36 warnings, all pre-existing deprecation warnings unrelated to
this story). Matches the full suite count carried over from
LFC-003-updates's final total — this story added no new tests and no
application code, so the count is expected to be unchanged. No regressions
introduced by adding this migration file.

### Totals: 0 new automated tests (none applicable beyond what already
exists), 110/110 full suite passing, 0 failed. AC1, AC2, AC3, AC5 verified
via dry-run SQL generation, not live execution — see environment limitation
above. AC4 verified by direct inspection of the existing RLS policy
definitions, confirming row-level (not column-level) scoping already covers
the new column; this is a structural/architectural fact about Postgres RLS
that does not require a live database to confirm, but the CHECK
constraint's actual runtime enforcement (rejecting an out-of-range INSERT/
UPDATE) has not been exercised against a real Postgres instance.
