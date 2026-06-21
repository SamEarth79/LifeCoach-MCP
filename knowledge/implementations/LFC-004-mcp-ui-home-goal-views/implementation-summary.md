# Implementation Summary: LFC-004-mcp-ui-home-goal-views

## LFC-STORY-001: goals.progress_percent migration

**What was implemented:** `migrations/versions/66f94137137d_add_goals_progress_percent.py`
adds a nullable `progress_percent INTEGER` column to the existing `goals`
table, with a CHECK constraint
(`progress_percent IS NULL OR (progress_percent BETWEEN 0 AND 100)`) named
`goals_progress_percent_check`. `down_revision` points at `8e5660ff9d7f`
(the `updates` table migration from LFC-003-updates), correctly chaining
onto the current head. No application code, RLS policy, or test changes
were made — this is a pure schema-only story laying groundwork for a later
story to read/write the column.

**What was tested and why:** Per `rules/testing.md`, a hand-written DDL-only
Alembic migration with no application code has no unit-testable surface, no
HTTP/MCP feature surface, and no user-facing UI — so unit, feature, and E2E
layers were all assessed as not applicable, consistent with how
LFC-002-goals's LFC-STORY-001 and LFC-003-updates's LFC-STORY-001 (the two
prior migration-only stories in this repo) were tested. Verification
instead consisted of:

1. Generating the actual SQL Alembic would run via `--sql` dry-run mode for
   both `upgrade` and `downgrade`, and diffing it against the story's
   acceptance criteria line by line (column type/nullability, CHECK
   constraint text, drop order).
2. Confirming the migration chain (`alembic history --verbose`) is a single
   linear chain with no branching, and that `down_revision` correctly
   targets the real current head.
3. Reading the existing `goals_select_own`/`goals_update_own` RLS policy
   definitions directly from `2ae062d3817c_create_goals_table.py` to confirm
   they are row-level predicates with no per-column scoping, so no RLS
   change is needed for the new column — this is a structural fact about
   how Postgres RLS works, confirmable by reading the policy SQL without a
   live database.
4. Running the full existing test suite to confirm zero regression, since
   this story touches no application code path any existing test exercises.

No Docker/local Postgres was available in this sandbox, so the migration
was never executed against a real database — this is recorded explicitly as
a caveat in `test-results.md` (PASS WITH CAVEATS), not silently assumed
clean. The CHECK constraint's actual runtime enforcement (rejecting an
out-of-range value at INSERT/UPDATE time) is the one piece of AC2 that only
a live database can confirm and remains unverified.

**Test results:** 110/110 full suite passing (unchanged from
LFC-003-updates's final count — this story added 0 new tests). See
`test-results.md` for the full breakdown.
