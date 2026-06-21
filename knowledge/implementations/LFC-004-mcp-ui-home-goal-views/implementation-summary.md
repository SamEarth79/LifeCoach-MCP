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

## LFC-STORY-002: set_goal_progress MCP tool

**What was implemented:** `app/mcp_server.py::set_goal_progress` and
`app/schemas.py::GoalProgressUpdate`, added by the backend agent. The tool
accepts `goal_id` (str, validated as `UUID`), `percentage` (int, validated
via `Field(ge=0, le=100)`), and an optional `rationale` (str, max 500 chars,
blank-to-`None`). It follows the same `enforce_mcp_rate_limit(request)` ->
`verify_bearer_token(...)` ordering as `record_update`/`list_updates`, then
runs `UPDATE goals SET progress_percent = %s WHERE id = %s RETURNING id`
through `get_rls_connection(current_user.id)` with no app-level `WHERE
user_id` clause — ownership is enforced entirely by the existing
`goals_update_own` RLS policy. A `None` row (RLS exclusion) raises a clean
`ValueError`. The tool's description explicitly frames this as the AI's own
internal bookkeeping, never something the rendered UI calls, and the
successful return value is a plain `{"goal_id": ..., "percentage": ...}`
dict, not a UI resource. `rationale` is validated but never persisted —
correctly out of scope per the AC and the LFC-STORY-001 migration, which
added no corresponding column.

**What was tested and why:** Read `app/mcp_server.py` and `app/schemas.py`
in full before writing any test, rather than trusting the backend agent's
report — confirmed the SQL, ordering, validation bounds, no-row-returned
handling, description text, and return shape all matched the report
exactly. Per `rules/testing.md`, this story introduces new validation logic,
rate-limit/auth ordering, and a new MCP tool surface, so both unit and
feature layers were required; E2E was assessed as not required because the
story (and AC5) explicitly state the rendered UI never calls this tool —
there is no user-facing flow to drive through a browser.

- **Unit tests** (`tests/unit/test_mcp_server.py`, appended to the existing
  file per this module's established one-file convention): validate the
  happy path, both out-of-range percentage rejections (negative and >100)
  before any DB call, missing-auth rejection before any DB call, the
  no-row-returned -> clean `ValueError` path with no commit, absence of an
  app-level `user_id` predicate in the executed query, rate-limit-before-auth
  ordering (tracked via a shared `call_order` list populated by both mocks'
  `side_effect`s), auth-before-DB-call ordering, the literal tool
  description text (read directly off
  `mcp_server.mcp._tool_manager._tools["set_goal_progress"].description`,
  the same technique used for `record_update`'s AC7 in LFC-003-updates), and
  the plain-dict (non-UI-resource) return shape.
- **Feature tests** (`tests/feature/test_mcp_set_goal_progress.py`, new
  file mirroring `test_mcp_record_update.py`'s structure): drive the real
  MCP streamable-HTTP wire protocol (`initialize` ->
  `notifications/initialized` -> `tools/call`) against a fresh `FastMCP`
  instance with the production `set_goal_progress` function and its real
  registered description, proving the Authorization header and JSON-RPC
  arguments genuinely reach the tool handler through the live HTTP request
  the SDK constructs — not just that the code is internally self-consistent.
  Covers the successful-update path, missing-JWT rejection, expired-JWT
  rejection, and out-of-range-percentage rejection, all asserting zero DB
  calls on the rejection paths.
- AC3 (RLS reliance) is verified only at the app/query level — the absence
  of a `WHERE user_id` clause and the clean `ValueError` on no-row-returned
  are both confirmed, but actual enforcement by the `goals_update_own`
  policy was not exercised against a live Postgres/Supabase instance. This
  is the same caveat class as every other RLS-dependent story in this repo
  and is recorded explicitly in `test-results.md` rather than overclaimed.

**Test results:** 14 new tests (10 unit + 4 feature), 124/124 full suite
passing across two consecutive runs with no flakiness (up from the 110
baseline carried over from LFC-STORY-001). See `test-results.md` for the
full breakdown per acceptance criterion.
