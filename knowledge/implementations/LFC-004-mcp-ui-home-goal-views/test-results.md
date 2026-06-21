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

## LFC-STORY-002

**Verdict: PASS WITH CAVEATS** — same caveat class as every other
RLS-dependent story in this repo (e.g. LFC-003-updates, list_updates'
ownership scoping): the absence of an app-level `WHERE user_id` clause is
confirmed by direct inspection of the executed SQL and the no-row-returned
path, but actual enforcement by the `goals_update_own` RLS policy was not
exercised against a live Postgres/Supabase instance.

### Implementation verified against the report

Read `app/mcp_server.py::set_goal_progress` and `app/schemas.py::GoalProgressUpdate`
in full before writing tests, rather than trusting the backend agent's report
at face value. Confirmed:

- `GoalProgressUpdate` validates `goal_id: UUID`, `percentage: int =
  Field(ge=0, le=100)`, `rationale: str | None = Field(default=None,
  max_length=500)` with a `field_validator` that blanks-to-`None`.
- `set_goal_progress` calls `enforce_mcp_rate_limit(request)` then
  `verify_bearer_token(...)` — identical ordering to `record_update`/
  `list_updates`.
- The SQL is `UPDATE goals SET progress_percent = %s WHERE id = %s
  RETURNING id`, executed through `get_rls_connection(current_user.id)`,
  with no app-level `user_id` predicate anywhere in the query string.
- No row returned raises `ValueError("goal_id does not exist, is not owned
  by the caller, or is deleted")` — identical wording/pattern to
  `record_update`'s RLS-rejection path.
- Returns a plain `{"goal_id": ..., "percentage": ...}` dict — no
  `UpdateResponse`-style schema, no UI-resource shape.
- The tool description text reads "This is for your own internal
  bookkeeping, not a user-facing action — the rendered UI never calls this
  tool directly..." — matches the claimed AI-only framing.
- Confirmed the known gap: `rationale` is validated by the schema but never
  referenced anywhere in the SQL/params tuple — there is no `rationale`
  column on `goals` per the LFC-STORY-001 migration. This is correctly out
  of scope per the AC and not flagged as a defect.

### Layers required

- Unit: required (new validation/ordering/RLS-reliance logic) — added to
  `tests/unit/test_mcp_server.py`, matching the established one-file
  convention for this module's unit tests.
- Feature: required (new MCP tool surface) — added
  `tests/feature/test_mcp_set_goal_progress.py`, mirroring
  `test_mcp_record_update.py`/`test_mcp_list_updates.py`'s real
  streamable-HTTP wire-protocol style (initialize -> notifications/initialized
  -> tools/call against a real `FastMCP` instance via `httpx.ASGITransport`).
- E2E (Playwright): **not required**. Per the story description and AC5,
  this tool is explicitly never called by the rendered UI — it is for the
  AI's own internal bookkeeping after a conversation. There is no
  user-facing flow to drive through a browser.

### Unit tests — 10 new, all passing

Added to `tests/unit/test_mcp_server.py`:

1. `test_set_goal_progress_updates_row_with_verified_user_id` — AC1: valid
   call updates `progress_percent`, connection opened with verified
   `current_user.id`, query contains `UPDATE goals` / `SET progress_percent`,
   params are `(42, GOAL_ID)`, commit happens.
2. `test_set_goal_progress_rejects_negative_percentage_before_db_call` — AC2
   (negative case): `percentage=-1` raises `ValueError` before any DB call;
   asserts `executed == []`.
3. `test_set_goal_progress_rejects_percentage_above_100_before_db_call` — AC2
   (above-100 case): `percentage=101` raises `ValueError` before any DB
   call; asserts `executed == []`.
4. `test_set_goal_progress_rejects_missing_authorization_before_db_call` —
   AC4 (auth-before-DB half): missing/invalid auth raises before any DB
   call.
5. `test_set_goal_progress_raises_when_no_row_updated_by_rls` — AC3: no row
   returned (simulating RLS exclusion of a nonexistent/not-owned/deleted
   goal) raises a clean `ValueError`, and `committed is False` — no silent
   partial success.
6. `test_set_goal_progress_query_has_no_app_level_user_id_clause` — AC3:
   confirms the executed query string contains no `user_id` predicate,
   i.e. ownership is enforced purely by RLS, not a duplicated app-level
   check — explicitly named caveat: this proves absence of an app-level
   check, not that RLS itself enforces it (no live Postgres in this
   sandbox).
7. `test_set_goal_progress_enforces_rate_limit_before_jwt_verification` —
   AC4: tracks call order via a shared list appended to by both the
   rate-limit and auth mocks' `side_effect`s, asserts
   `call_order == ["rate_limit", "auth"]`.
8. `test_set_goal_progress_enforces_jwt_verification_before_db_call` — AC4
   (auth-before-DB, restated with a `PermissionError` side effect):
   confirms zero DB calls when auth fails.
9. `test_set_goal_progress_tool_description_states_internal_use_not_user_facing`
   — AC5: reads `mcp_server.mcp._tool_manager._tools["set_goal_progress"].description`
   directly (same technique as `record_update`'s AC7 description test in
   LFC-003-updates), asserts it contains "your own"/"internal" framing and
   the literal "not a user-facing action" phrase plus a reference to "ui".
10. `test_set_goal_progress_returns_plain_dict_not_ui_resource` — AC6:
    asserts the result is a `dict` with exactly `{"goal_id", "percentage"}`
    keys and none of `type`/`resource`/`uri` (the markers of a UI/
    `EmbeddedResource` shape).

### Feature tests — 4 new, all passing

Added `tests/feature/test_mcp_set_goal_progress.py`, following
`test_mcp_record_update.py`'s real wire-protocol pattern (fresh `FastMCP`
instance per test, `httpx.ASGITransport`, full `initialize` ->
`notifications/initialized` -> `tools/call` handshake against the real
`set_goal_progress` function and its real registered description):

1. `test_set_goal_progress_through_live_mcp_transport_updates_with_verified_user_id`
   — AC1/AC4: full wire-protocol call with a valid signed JWT succeeds,
   `isError` absent/false, connection opened with the verified user id, the
   `UPDATE goals` query executed with `(42, GOAL_ID)` params, commit
   happens.
2. `test_set_goal_progress_through_live_mcp_transport_rejects_missing_jwt_before_db_call`
   — AC4: no `Authorization` header -> `isError:true`, zero DB calls.
3. `test_set_goal_progress_through_live_mcp_transport_rejects_expired_jwt_before_db_call`
   — AC4: expired JWT (`exp=0`) -> `isError:true`, zero DB calls.
4. `test_set_goal_progress_through_live_mcp_transport_rejects_out_of_range_percentage_before_db_call`
   — AC2, exercised through the real wire protocol rather than just the
   bare function: `percentage=101` -> `isError:true`, zero DB calls,
   confirming Pydantic validation rejects the value even when the call
   arrives via the actual MCP JSON-RPC `tools/call` path, not just a direct
   Python call.

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root twice in a row to
rule out flakiness:

- Run 1: **124 passed**, 0 failed, 36 warnings (same pre-existing
  deprecation warnings as before, unrelated to this story).
- Run 2: **124 passed**, 0 failed, 36 warnings — identical result, no
  flakiness.

124 = 110 (prior baseline from LFC-STORY-001) + 10 new unit tests + 4 new
feature tests = 124. The full suite run confirms this exactly: **124
passed, 0 failed**, across two consecutive runs.

### Totals: 14 new automated tests (10 unit + 4 feature), 124/124 full suite
passing across two consecutive runs, 0 failed, no flakiness. All 6
acceptance criteria are covered by at least one test each. AC3's RLS-reliance
is verified only at the app/query level (no `WHERE user_id` clause, clean
`ValueError` on no-row-returned) — not against a live Postgres/Supabase
instance, stated explicitly as a caveat rather than overclaimed as a full
pass.
