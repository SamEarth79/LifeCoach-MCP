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

## LFC-STORY-003

**Verdict: PASS WITH CAVEATS**

### Implementation verified against the reports (not trusted at face value)

Read `app/ui_templates.py` and `app/mcp_server.py::get_home_view` in full
before writing any test. Confirmed:

- `render_home_view` HTML-escapes `data.greeting_name`, every `card.title`,
  `card.id`, and `data.error` via `html.escape` (default `quote=True`)
  before interpolation — verified with an actual constructed XSS payload
  (`<script>alert(1)</script>`) in the greeting name, a card title, and the
  error message; the raw tag never appears in the rendered output and the
  HTML-entity-escaped form does.
- The progress ring renders a real `{percentage}%` label when
  `progress_percent` is an int (including `0`, rendered as a real `0%`, not
  a dashed/no-estimate state), and a distinct dashed `no-estimate` CSS class
  plus an em-dash label when `progress_percent is None` — never a misleading
  `0%` for the `None` case.
- `_updated_line` renders `Updated <date>` only when `last_updated_at is not
  None`; omitted entirely otherwise.
- `_CREATE_GOAL_ENTRY`/`_TALK_ENTRY` are visually distinct elements
  (different CSS classes, `entry-card` vs `talk-entry`) both wired to
  `lifecoachSendPrompt(...)`, never `lifecoachSendTool`.
- Each goal card's `onclick` calls
  `lifecoachSendTool('get_goal_detail_view', { goal_id: '<id>' })`, and the
  only value interpolated into that JS-string context is `card.id` — a
  server-generated UUID written by `get_home_view` from the `goals.id`
  column, never raw user-controlled text. `html.escape`'s default
  `quote=True` would HTML-entity-encode an embedded single quote in the
  attribute, but this does not fully neutralize a JS-string-context
  breakout for an arbitrary *untrusted* value (the browser HTML-decodes the
  attribute before the `onclick` body executes) — flagged explicitly as a
  risk that would matter only if a future change interpolates a non-UUID,
  user-controlled value into this same template. Confirmed no other value
  is currently interpolated into any `onclick`/script body.
- The empty-state (`data.goals == []`) renders the greeting and both
  entries, with zero `class="card"` markup.
- The failure-state (`data.error` set) renders a non-technical message
  (the literal string `get_home_view` passes — "We couldn't load your home
  screen right now.") plus both entries, zero `class="card"` markup, and
  `data.error` itself is HTML-escaped — confirmed failure-state takes
  precedence over goals/empty-state when both `error` and a non-empty
  `goals` list are set on the same `HomeViewData` (defensive case, not
  reachable from `get_home_view` itself, but the renderer's own contract).
- No tab-bar markup (`tab-bar`, "Reflect", "Journey") and no "Total
  Days"/"Current Streak" markup anywhere in any rendered state — confirmed
  absent by direct string search of the full rendered output, matching
  architecture.md's explicit exclusions.
- Both `lifecoachSendTool` and `lifecoachSendPrompt` carry an inline
  `UNVERIFIED against a live MCP-UI host` comment in `_SCRIPT` — confirmed
  present by reading the file, not just claimed by the frontend agent's
  report.
- `get_home_view`: `enforce_mcp_rate_limit(request)` runs before
  `verify_bearer_token(...)`, identical ordering to every other MCP tool in
  this module. The goal query (`SELECT id, title, progress_percent FROM
  goals ORDER BY created_at DESC`) has no app-level `user_id` or
  `deleted_at` clause — relies entirely on the existing `goals_select_own`
  RLS policy, same pattern as `list_goals`. `_build_home_view_resource`
  constructs `EmbeddedResource(type="resource", resource=TextResourceContents(uri="ui://home-view",
  mimeType="text/html", text=...))` — confirmed this actually
  parses/serializes correctly via the installed `mcp` package (the
  resource's `uri.scheme == "ui"`, `mimeType == "text/html"`). On both a
  missing user row and any unhandled exception during the query, the tool
  catches the failure and returns the same `EmbeddedResource`-wrapped
  failure-state HTML instead of letting an exception propagate as a raw,
  unrenderable tool error.

### Layers required

- Unit: required for both `render_home_view` (pure rendering logic, no
  DB/MCP) and `get_home_view`'s tool logic (rate-limit/auth ordering,
  RLS-only query shape, `EmbeddedResource` construction, handled-failure
  path) — added to `tests/unit/test_ui_templates.py` (new file, one
  responsibility per file per `coding-style.md`) and appended to the
  existing `tests/unit/test_mcp_server.py`.
- Feature: required (new MCP tool surface) — added
  `tests/feature/test_mcp_get_home_view.py`, mirroring
  `test_mcp_set_goal_progress.py`'s real streamable-HTTP wire-protocol
  pattern.
- E2E (Playwright): **not added in this pass**. This story's UI is rendered
  HTML returned as MCP-UI content, displayed inside an MCP-UI host — there
  is no app route/page of this repo's own to drive with Playwright against
  a running instance, and no live MCP-UI host exists in this sandbox to
  drive a real `postMessage` round trip against (see AC5 caveat below). The
  rendering logic itself is fully covered at the unit layer instead.

### Unit tests — 19 new (18 render-level + ... see breakdown), all passing

`tests/unit/test_ui_templates.py` (18 tests) — `render_home_view` directly,
no DB/MCP:

1. XSS-escaping of `greeting_name`, `card.title`, and `data.error`
   (3 tests) — constructs an actual `<script>alert(1)</script>` payload and
   asserts the raw tag is absent and the escaped entity is present (AC2,
   AC8).
2. `progress_percent is None` renders `no-estimate` and never `0%`; a real
   percentage (`42`) renders `42%`; `progress_percent == 0` renders a real
   `0%` distinct from the `no-estimate` treatment (3 tests) — AC2.
3. `Updated <date>` line present when `last_updated_at` is set, absent when
   `None` (2 tests) — architecture.md's data-flow description.
4. Empty-state has greeting + both entries, zero `class="card"` (1 test) —
   AC4/Requirement 7.
5. Goals-state renders exactly one `class="card"` per goal (1 test) — AC2.
6. Failure-state has the message + both entries, zero cards, and takes
   precedence over a simultaneously-set non-empty goals list (2 tests) —
   AC8.
7. No tab-bar markup, no "Total Days"/"Current Streak"/"streak" markup in
   any state (2 tests) — architecture.md's explicit exclusions.
8. "Create a new goal"/"just want to talk" entries call
   `lifecoachSendPrompt`, never `lifecoachSendTool` (1 test) — AC3, AC6.
9. Goal card click calls `lifecoachSendTool('get_goal_detail_view', {
   goal_id: '<id>' })` with the goal's own id (1 test) — AC5.
10. Both `lifecoachSendTool`/`lifecoachSendPrompt` function bodies contain
    an `UNVERIFIED` comment (1 test) — confirms the disclaimer is actually
    present in source, not just claimed.
11. Documents `html.escape`'s single-quote-encoding behavior and its
    JS-string-context caveat for any future non-UUID interpolation
    (1 test) — risk-flagging, not a defect in the current code.

`tests/unit/test_mcp_server.py` (9 new tests appended) — `get_home_view`
tool logic with mocked DB/auth/rate-limit via a new `_SequencedCursor` (the
existing `_FakeCursor`/`_patch_db_for_list` helpers only support a single
`fetchall` or `fetchone` per test; `get_home_view` issues one `fetchone`
(user row), one `fetchall` (goal rows), then one `fetchone` per goal
(latest update) — `_SequencedCursor` consumes a list of canned responses in
call order to model this):

1. `test_get_home_view_returns_embedded_resource_with_greeting_and_goal_cards`
   — AC1/AC2: returns an `EmbeddedResource`, `ui://` scheme, `text/html`
   mimetype, greeting and goal title both present in the rendered text,
   connection opened with the verified caller's id.
2. `test_get_home_view_falls_back_to_email_when_no_display_name` — AC1's
   greeting fallback (`display_name or email`).
3. `test_get_home_view_returns_empty_state_for_zero_active_goals` — AC4.
4. `test_get_home_view_goal_query_has_no_app_level_user_id_or_deleted_at_clause`
   — AC1/Requirement 9: confirms the executed goal query string contains
   neither `user_id` nor `deleted_at`, relying purely on RLS — same caveat
   class as every other RLS-dependent story (see "RLS caveat" below).
5. `test_get_home_view_renders_no_estimate_yet_when_progress_percent_is_null`
   — AC2, exercised through the real tool function, not just the renderer
   directly.
6. `test_get_home_view_enforces_rate_limit_before_jwt_verification` — AC7,
   tracked via a shared `call_order` list, same technique as
   `set_goal_progress`'s equivalent test.
7. `test_get_home_view_enforces_jwt_verification_before_db_call` — AC7,
   confirms zero DB calls when auth fails.
8. `test_get_home_view_returns_failure_resource_when_user_row_missing` —
   AC8 (handled-failure path #1): no user row -> a non-raising
   `EmbeddedResource` with no cards and a "couldn't load" message.
9. `test_get_home_view_returns_failure_resource_on_unhandled_db_error_instead_of_raising`
   — AC8 (handled-failure path #2): an arbitrary `RuntimeError` raised
   mid-query is caught and converted to the same failure-state resource
   rather than propagating as an unhandled exception.

Plus one description-text sanity check
(`test_get_home_view_tool_description_mentions_home_screen`).

### Feature tests — 3 new, all passing

Added `tests/feature/test_mcp_get_home_view.py`, following
`test_mcp_set_goal_progress.py`'s real wire-protocol pattern (fresh
`FastMCP` instance, `httpx.ASGITransport`, full `initialize` ->
`notifications/initialized` -> `tools/call` handshake against the real
`get_home_view` function and its real registered description):

1. `test_get_home_view_through_live_mcp_transport_returns_html_resource_with_greeting`
   — AC1: full wire-protocol call with a valid signed JWT succeeds,
   `isError` absent/false, the response body contains the greeting name and
   `text/html`, connection opened with the verified user id.
2. `test_get_home_view_through_live_mcp_transport_rejects_missing_jwt_before_db_call`
   — AC7: no `Authorization` header -> `isError:true`, zero DB calls.
3. `test_get_home_view_through_live_mcp_transport_rejects_expired_jwt_before_db_call`
   — AC7: expired JWT (`exp=0`) -> `isError:true`, zero DB calls.

### RLS caveat (AC1/AC4, Requirement 9)

Same caveat class as every other RLS-dependent story in this repo (e.g.
`list_updates`, `set_goal_progress`): the absence of an app-level `WHERE
user_id`/`deleted_at` clause in the goal query is confirmed by direct
inspection of the executed SQL string, and the empty-goals path (AC4) is
exercised with a mocked zero-row result — neither proves the
`goals_select_own` RLS policy itself actually filters another user's rows
or excludes soft-deleted ones against a live Postgres/Supabase instance. No
Docker/local Postgres was available in this sandbox. This must be
considered an unverified assumption, not a settled fact, until exercised
against a real instance.

### AC5 caveat — untestable in this sandbox, recorded as an open item, not silently passed

AC5 (clicking a goal card invokes `get_goal_detail_view` directly via the
MCP-UI host's `postMessage` mechanism, with chat-message injection as the
documented fallback if unsupported) cannot be verified at all in this
sandbox: there is no live MCP-UI host to render the returned HTML and
observe a real `postMessage` round trip, and `get_goal_detail_view` itself
does not exist yet (a separate story in this feature). What was verified
instead: the rendered `onclick` JS calls `lifecoachSendTool(...)` (not
`lifecoachSendPrompt`) with the goal's id, and the function body carries an
explicit `UNVERIFIED against a live MCP-UI host` comment, matching
architecture.md's and requirements.md's own framing of this as an
unconfirmed external-contract assumption. Whether a real MCP-UI host
actually honors direct tool-invocation from a UI click — as opposed to only
supporting chat-message injection — remains an open verification item for
this feature, to be confirmed against a real host or the live MCP-UI spec
before this behavior is relied upon in production.

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root twice in a row to
rule out flakiness:

- Run 1: **155 passed**, 0 failed, 36 warnings (same pre-existing
  deprecation warnings as before, unrelated to this story).
- Run 2: **155 passed**, 0 failed, 36 warnings — identical result, no
  flakiness.

155 = 124 (prior baseline from LFC-STORY-002) + 18 new unit tests
(`test_ui_templates.py`) + 10 new unit tests appended to
`test_mcp_server.py` (9 `get_home_view` tests + 1 description test) + 3 new
feature tests = 155. The full suite run confirms this exactly: **155
passed, 0 failed**, across two consecutive runs.

### Totals: 31 new automated tests (18 + 10 unit, 3 feature), 155/155 full
suite passing across two consecutive runs, 0 failed, no flakiness. AC1–AC4,
AC6, AC7, AC8 are each covered by at least one test. AC4 (empty-state for
zero active goals) is verified at the app/render level using mocked query
results, not against a live Postgres/Supabase instance — same recurring
caveat class as every other RLS-dependent story in this repo. AC5 (whether
`get_goal_detail_view` actually fires from a real MCP-UI host click)
**cannot be tested at all in this sandbox** — no live MCP-UI host exists —
and is recorded here as an explicit open verification item rather than
silently passed.

## LFC-STORY-004

**Verdict: PASS WITH CAVEATS** — same RLS caveat class as every other
RLS-dependent story in this repo, plus the same untestable-in-sandbox
external-contract caveat already recorded for LFC-STORY-003's AC5
(`postMessage`-based tool invocation against a real MCP-UI host).

### Implementation verified against the reports (not trusted at face value)

Read `app/mcp_server.py::get_goal_detail_view` and
`app/ui_templates.py::GoalDetailUpdate`/`GoalDetailViewData`/
`render_goal_detail_view` in full before writing any test. Confirmed:

- `get_goal_detail_view` calls `enforce_mcp_rate_limit(request)` before
  `verify_bearer_token(...)` — identical ordering to every other tool in this
  module. `goal_id` is parsed via `UUID(goal_id)` (raising `ValueError`
  before any DB call) before the rate-limit/auth-then-DB-call sequence
  reaches `get_rls_connection`.
- The goal-row query is `SELECT id, title, description, progress_percent
  FROM goals WHERE id = %s` with no app-level `user_id`/`deleted_at` clause —
  relies entirely on the existing `goals_select_own` RLS policy, same
  pattern as `get_home_view`/`list_goals`.
- When the goal row is `None` (nonexistent/not-owned/soft-deleted), the tool
  returns a `GoalDetailViewData(id=None, title=None, description=None,
  progress_percent=None, recent_updates=[], error="This goal isn't
  available.")`-backed `EmbeddedResource` directly — it does not raise, and
  it does not issue the second (updates) query at all once the goal row
  comes back empty.
- The updates query is `SELECT content, created_at FROM updates WHERE
  goal_id = %s ORDER BY created_at DESC LIMIT 5` — `transcript` is never
  selected, identical discipline to `list_updates`.
- Any unhandled exception during the whole block is caught and converted to
  the same failure-state `EmbeddedResource`, never propagated raw.
- `_build_embedded_html_resource(uri, html_text)` is a new shared helper;
  both `_build_home_view_resource` and the new
  `_build_goal_detail_view_resource` call it rather than constructing
  `EmbeddedResource`/`TextResourceContents` independently — confirmed by
  reading both functions' source directly (also asserted by a dedicated
  regression test, see below).
- `render_goal_detail_view` HTML-escapes `title`, `description`, each
  update's `content`, and `error` via `html.escape` before interpolation.
  Reuses `_progress_ring(...)` unchanged — no second ring/no-estimate
  implementation exists in the detail-view code.
- An empty `recent_updates` list renders the literal `<p
  class="no-updates">No updates yet.</p>` line, not a blank/missing section.
- **Re-verified the "continue conversation" title-handling approach by
  direct code reading, then by an actual hostile-input test (see below):**
  the goal's title is rendered as `html.escape`d DOM text content inside
  `<p class="detail-title" id="goal-title-{safe_id}">{safe_title}</p>` — it
  is never placed inside any `onclick` attribute. The continue button's
  `onclick` is `lifecoachContinueGoal('{safe_id}')`, where `safe_id` is the
  goal's UUID (`html.escape`d, though a UUID has nothing to escape) — never
  any fragment of the title. At click time, `lifecoachContinueGoal` reads
  the title back via `document.getElementById("goal-title-" +
  goalId).textContent`, which returns the *decoded* text (browser undoes the
  HTML-entity-escaping when populating `textContent`'s source, i.e. a
  `&lt;script&gt;` entity in markup becomes the literal string
  `<script>...` in `.textContent`, never re-parsed as markup), then passes
  that as a string argument to `lifecoachSendPrompt(...)` — a `postMessage`
  payload field, not an HTML/JS-string-literal-context insertion. This is
  the correct fix for the JS-string-breakout risk class flagged in
  LFC-STORY-003's test-results (where the *goal id*, not free text, was the
  only interpolated value) — here free text (the title) is involved, and the
  implementation avoids ever interpolating it into any onclick JS string by
  routing it through DOM `textContent` instead.
- The delete action is a genuine two-stage confirm: first click on
  `#delete-entry-{id}` (`lifecoachShowDeleteConfirm`) hides the delete button
  and reveals `#delete-confirm-{id}`; only its `confirm` button calls
  `lifecoachConfirmDelete('{id}')` -> `lifecoachSendTool("delete_goal", {
  goal_id: goalId })`, using only the trusted UUID — title is never involved
  in the delete path at all.
- No tab-bar or "Total Days"/"Current Streak" markup anywhere in the
  rendered output, matching architecture.md's explicit exclusions.

### Layers required

- Unit: required for both `render_goal_detail_view` (new pure rendering
  logic) and `get_goal_detail_view`'s tool logic (rate-limit/auth/UUID
  ordering, RLS-only query shape, handled-failure paths, shared-helper
  refactor) — appended to `tests/unit/test_ui_templates.py` and
  `tests/unit/test_mcp_server.py`, matching this feature's established
  one-file-per-concern convention.
- Feature: required (new MCP tool surface) — added
  `tests/feature/test_mcp_get_goal_detail_view.py`, mirroring
  `test_mcp_get_home_view.py`'s real streamable-HTTP wire-protocol pattern.
- E2E (Playwright): **not added in this pass**, same rationale as
  LFC-STORY-003: this view is HTML rendered for an MCP-UI host, not a page or
  route of this repo's own, and no live MCP-UI host exists in this sandbox to
  drive a real browser-based `postMessage` round trip against. The rendering
  logic, including the hostile-input/XSS path, is instead fully covered at
  the unit layer.

### Unit tests — 27 new, all passing

`tests/unit/test_ui_templates.py` (14 new tests) — `render_goal_detail_view`
directly, no DB/MCP:

1. `test_render_goal_detail_view_renders_title_description_progress_and_updates`
   — AC2: title, description, `42%`, an update's content and date all present.
2. `test_render_goal_detail_view_never_includes_transcript_field_name` — AC2:
   confirms `transcript` never appears anywhere in rendered output.
3. `test_render_goal_detail_view_renders_no_updates_yet_for_empty_recent_updates`
   — AC2 edge case: empty list renders "No updates yet." not a blank section.
4. `test_render_goal_detail_view_omits_description_block_when_none` — no
   empty description block rendered when `description is None`.
5/6. `test_render_goal_detail_view_renders_no_estimate_yet_for_none_progress_not_zero_percent`
   / `..._renders_zero_percent_distinctly_from_no_estimate` — AC2: confirms
   `_progress_ring` reuse renders the same "no estimate yet" treatment as the
   home view, and that `0` is rendered as a real `0%`, never conflated with
   `None`.
7/8. `test_render_goal_detail_view_failure_state_has_message_and_no_title_or_updates`
   / `..._failure_state_takes_precedence_over_content` — AC5: error-state
   renders the message only, with no title/progress/updates/actions
   alongside it, and failure takes precedence even when content fields are
   simultaneously populated on the same data object.
9. `test_render_goal_detail_view_continue_action_injects_prompt_not_tool_call`
   — AC3: confirms `lifecoachContinueGoal` calls `lifecoachSendPrompt`, not
   any tool.
10. `test_render_goal_detail_view_delete_action_gated_behind_two_stage_confirm`
    — AC4: confirms the `delete-entry`/`delete-confirm` two-stage markup and
    that only the confirm button calls
    `lifecoachSendTool("delete_goal", { goal_id: goalId })`.
11. `test_render_goal_detail_view_has_no_tab_bar_or_streak_markup` —
    architecture.md's explicit exclusions, re-verified for this view.
12-14. The hostile-input re-verification trio (see dedicated section below).

`tests/unit/test_mcp_server.py` (13 new tests appended):

1. `test_get_goal_detail_view_returns_embedded_resource_with_title_description_progress_and_updates`
   — AC1/AC2: full happy path through the real tool function.
2. `test_get_goal_detail_view_query_selects_only_content_and_created_at_for_updates`
   — AC2/Requirement 5: confirms the updates query selects exactly
   `content, created_at` with a `LIMIT 5`, no `transcript`.
3. `test_get_goal_detail_view_renders_no_updates_yet_when_recent_updates_empty`
   — AC2 edge case, through the real tool function.
4. `test_get_goal_detail_view_renders_no_estimate_yet_when_progress_percent_is_null`
   — AC2, through the real tool function.
5. `test_get_goal_detail_view_returns_failure_resource_when_goal_row_missing`
   — AC5: no goal row -> failure-state `EmbeddedResource`, and confirms only
   one query (the goal lookup) was ever issued — the updates query never
   runs once the goal row comes back empty.
6. `test_get_goal_detail_view_returns_failure_resource_on_unhandled_db_error_instead_of_raising`
   — AC5: an arbitrary `RuntimeError` mid-query is caught and converted to
   the same failure-state resource, never propagated raw.
7. `test_get_goal_detail_view_rejects_malformed_goal_id_before_db_call` —
   AC6: a non-UUID `goal_id` raises `ValueError` with zero DB calls.
8/9. `test_get_goal_detail_view_enforces_rate_limit_before_jwt_verification`
   / `..._enforces_jwt_verification_before_db_call` — AC6: call-order tracked
   via a shared list, and zero DB calls on auth failure.
10. `test_get_goal_detail_view_jwt_verification_before_uuid_validation_only_matters_after_db_call_check`
    — AC6 edge case: a malformed `goal_id` combined with a failing auth mock
    still surfaces the auth failure (not a UUID parse error) with zero DB
    calls either way — the two checks are independent gates that both must
    pass before any DB call, not strictly ordered relative to each other.
11. `test_get_goal_detail_view_query_has_no_app_level_user_id_clause` —
    Requirement 9: confirms the goal query has no app-level `user_id`
    predicate.
12. `test_get_goal_detail_view_tool_description_mentions_goal_detail` —
    sanity check on the registered tool description.
13. `test_build_embedded_html_resource_helper_used_by_both_home_and_detail_view_builders`
    — regression guard on the `_build_embedded_html_resource` refactor:
    confirms both `_build_home_view_resource` and
    `_build_goal_detail_view_resource` route through the shared helper by
    inspecting their source directly, rather than constructing
    `EmbeddedResource` independently.

### Hostile-input re-verification (explicitly requested, done as a real test, not a code-reading claim)

Built a title containing a double-quote, a single-quote, and a raw
`<script>` tag: `Evil" Goal' <script>alert(1)</script>`. Rendered it through
`render_goal_detail_view` and asserted, on the actual rendered string (not on
an assumption):

- `test_render_goal_detail_view_continue_button_onclick_contains_only_uuid_never_hostile_title_text`
  — the raw `<script>alert(1)</script>` tag never appears anywhere in the
  output; the HTML-entity-escaped form does. The continue button's `onclick`
  attribute value is extracted by string slicing and asserted to be byte-for-byte
  `lifecoachContinueGoal('{GOAL_ID}')` — the UUID and nothing else; no
  fragment of `Evil`, no quote character, no `script` substring.
- `test_render_goal_detail_view_delete_button_onclick_contains_only_uuid_never_hostile_title_text`
  — both the show-confirm and confirm-delete `onclick` attributes contain
  only the UUID, confirming the hostile title never reaches the delete path
  either (expected, since delete never references the title at all).
- `test_render_goal_detail_view_title_rendered_as_escaped_dom_text_not_inside_any_onclick`
  — extracts every `onclick="..."` attribute value present anywhere in the
  full rendered document via a small helper (`_all_onclick_values`) and
  asserts none of them contain any fragment of the hostile title or the word
  "script"; separately extracts the title `<p>` element's inner text and
  confirms it is the HTML-entity-escaped form
  (`&lt;script&gt;alert(1)&lt;/script&gt;`), proving the title is rendered as
  escaped markup text content, never as raw markup and never inside any
  inline-JS attribute.

This is a genuine behavioral test against the actual hostile string, not a
restatement of the implementation's own assumption — it would fail if a
future change ever interpolated the title into any onclick string.

### Feature tests — 5 new, all passing

Added `tests/feature/test_mcp_get_goal_detail_view.py`, following
`test_mcp_get_home_view.py`'s real wire-protocol pattern (fresh `FastMCP`
instance, `httpx.ASGITransport`, full `initialize` ->
`notifications/initialized` -> `tools/call` handshake against the real
`get_goal_detail_view` function and its real registered description):

1. `test_get_goal_detail_view_through_live_mcp_transport_returns_html_resource_with_goal_data`
   — AC1/AC2: valid JWT + valid goal -> non-error response containing title,
   description, the update's content, `text/html`, and confirms `transcript`
   never appears in the wire-level response body.
2. `test_get_goal_detail_view_through_live_mcp_transport_returns_failure_resource_for_missing_goal`
   — AC5: missing goal row -> non-error response (not an MCP-level error) with
   no title and a failure message, through the real wire protocol.
3. `test_get_goal_detail_view_through_live_mcp_transport_rejects_missing_jwt_before_db_call`
   — AC6: no `Authorization` header -> `isError:true`, zero DB calls.
4. `test_get_goal_detail_view_through_live_mcp_transport_rejects_expired_jwt_before_db_call`
   — AC6: expired JWT -> `isError:true`, zero DB calls.
5. `test_get_goal_detail_view_through_live_mcp_transport_rejects_malformed_goal_id_before_db_call`
   — AC6: non-UUID `goal_id` argument, delivered through the real JSON-RPC
   `tools/call` path -> `isError:true`, zero DB calls.

### `get_home_view` regression check (refactor verification)

`tests/feature/test_mcp_get_home_view.py` and the `get_home_view`-specific
tests in `tests/unit/test_mcp_server.py` were **not modified** in this pass
(confirmed via `git diff --stat` showing zero changes to
`test_mcp_get_home_view.py`) and were re-run as part of every full-suite run
below — all still pass unmodified, confirming the `_build_embedded_html_resource`
extraction did not change `get_home_view`'s actual behavior. Additionally
added `test_build_embedded_html_resource_helper_used_by_both_home_and_detail_view_builders`
as a permanent regression guard so a future change that reintroduces
divergent resource-building logic between the two tools is caught
immediately.

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root twice in a row to
rule out flakiness:

- Run 1: **187 passed**, 0 failed, 36 warnings (same pre-existing
  deprecation warnings as before, unrelated to this story).
- Run 2: **187 passed**, 0 failed, 36 warnings — identical result, no
  flakiness.

187 = 155 (prior baseline from LFC-STORY-003) + 14 new unit tests
(`test_ui_templates.py`) + 13 new unit tests appended to
`test_mcp_server.py` + 5 new feature tests = 187. The full suite run
confirms this exactly: **187 passed, 0 failed**, across two consecutive
runs.

### RLS caveat (AC1/AC5, Requirement 5/8/9) — same recurring caveat class

Same caveat class as every other RLS-dependent story in this repo: the
absence of an app-level `user_id` clause in the goal-row query is confirmed
by direct inspection of the executed SQL string, and the missing/foreign/
soft-deleted-goal path (AC5) is exercised with a mocked zero-row result —
neither proves the `goals_select_own` RLS policy itself actually excludes
another user's row or a soft-deleted one against a live Postgres/Supabase
instance. No Docker/local Postgres was available in this sandbox. This must
be considered an unverified assumption, not a settled fact, until exercised
against a real instance — identical framing to LFC-STORY-003's equivalent
caveat for `get_home_view`.

### Totals: 32 new automated tests (14 + 13 unit, 5 feature), 187/187 full
suite passing across two consecutive runs, 0 failed, no flakiness. All 6
acceptance criteria are covered by at least one test each, including a
genuine hostile-input behavioral test for the "continue conversation"
title-handling approach (re-verified safe: title is rendered as escaped DOM
text content read back via `textContent`, never interpolated into any
`onclick` JS string; the delete and continue `onclick` attributes contain
only the trusted UUID, confirmed against an actual payload containing a
double-quote, single-quote, and raw `<script>` tag). The `get_home_view`
refactor regression check confirms the shared `_build_embedded_html_resource`
helper introduced no behavior change: its existing test files were left
unmodified and still pass. AC5's RLS-exclusion path is verified only at the
app/render level (no live Postgres/Supabase instance) — same recurring
caveat class as every other story in this repo.

## LFC-STORY-005

**Verdict: PASS WITH CAVEATS**

Backend added `delete_goal` to `app/mcp_server.py` and extracted
`_fetch_home_view_data(user_id)` out of `get_home_view`'s body (now the
second real call site, shared with `delete_goal`). Read `delete_goal`,
`get_home_view`, and `_fetch_home_view_data` in full directly rather than
trusting the backend report, per this story's instruction to verify
carefully given the LFC-003 PR-review precedent about careless refactor
claims.

### Direct source verification (before writing any test)

- `delete_goal`'s ordering is `enforce_mcp_rate_limit(request)` ->
  `verify_bearer_token(...)` -> `UUID(goal_id)` parse -> DB call, identical
  to every other tool in this file.
- The soft-delete SQL is exactly
  `UPDATE goals SET deleted_at = now() WHERE id = %s AND deleted_at IS NULL
  RETURNING id`, through `get_rls_connection(current_user.id)`, with no
  app-level `WHERE user_id` clause — confirmed byte-for-byte against the
  existing REST `DELETE /goals/{id}` handler's SQL. **It is a genuine
  `UPDATE`, never a `DELETE FROM` statement.**
- When `fetchone()` returns `None` (no row matched: nonexistent, not owned,
  or already soft-deleted), the code does **not** call `conn.commit()` and
  raises `ValueError` before ever calling `_fetch_home_view_data` or
  `_build_home_view_resource` — confirmed by reading the control flow
  (`if row is not None: await conn.commit()` followed by
  `if row is None: raise ValueError(...)`, both inside the same `async
  with` block, before the refresh call below it).
- On success, the code commits, then calls
  `_fetch_home_view_data(current_user.id)` followed by
  `_build_home_view_resource(...)` — the exact same two functions
  `get_home_view` itself calls, not a parallel ad-hoc implementation.
- `get_home_view`'s own body was reduced to
  `home_view_data = await _fetch_home_view_data(current_user.id)` followed
  by `_build_home_view_resource(home_view_data)`, wrapped in the same
  try/except it always had. The extracted helper's SQL (user row lookup,
  goal rows, per-goal latest-update lookup) is character-for-character what
  used to live inline in `get_home_view`, confirmed by diffing the
  extracted function body against the pre-extraction version inferred from
  the existing passing test expectations (e.g. exact `SELECT` column lists,
  `ORDER BY created_at DESC`, no `user_id`/`deleted_at` clause).

### Regression check: existing `get_home_view` tests, run unmodified

`tests/unit/test_mcp_server.py`'s `get_home_view`-specific tests and the
entirety of `tests/feature/test_mcp_get_home_view.py` were **not modified**
in this pass (confirmed via `git diff --stat` showing zero changes to
`test_mcp_get_home_view.py`). Ran them in isolation before writing any new
test:

```
.venv/bin/python -m pytest -q tests/unit/test_mcp_server.py tests/feature/test_mcp_get_home_view.py
50 passed in 1.22s
```

All 50 pre-existing `get_home_view`-related tests pass unmodified — the
`_fetch_home_view_data` extraction is confirmed behavior-preserving for
`get_home_view`, the main regression risk flagged for this story.

### New tests written, mapped to acceptance criteria

**Unit tests** (`tests/unit/test_mcp_server.py`, 11 new, using a new
`_DeleteThenRefreshCursor`/`_DeleteThenRefreshConnection` fake modeling the
tool's two-phase query pattern — first the delete `UPDATE`, then the
refresh queries only on success):

1. **AC1** — `test_delete_goal_soft_deletes_via_update_never_a_hard_delete`:
   asserts the executed SQL text contains `UPDATE goals`, contains no
   `DELETE FROM` and does not start with `DELETE`, contains
   `SET deleted_at = now()` and the exact `WHERE` clause, with `goal_id` as
   the only parameter; confirms `conn.commit()` was called.
   `test_delete_goal_query_has_no_app_level_user_id_clause` confirms no
   `user_id` substring anywhere in the query text.
2. **AC2** — `test_delete_goal_raises_cleanly_when_no_row_matches_and_builds_no_home_view`:
   mocks zero rows back from the `UPDATE` (covers nonexistent/not-owned/
   already-deleted alike, since all three collapse to "no row returned"
   given the RLS-scoped `WHERE deleted_at IS NULL`), asserts a clean
   `ValueError`, `committed is False`, exactly one query executed (the
   `UPDATE` itself, no refresh queries attempted), and — using
   `AsyncMock(wraps=...)` on the real `_fetch_home_view_data` — asserts it
   was **never awaited** in this failure path, directly verifying "no home
   view returned/built" rather than just inferring it from query count.
3. **AC3** — `test_delete_goal_enforces_rate_limit_before_jwt_verification`
   (records call order via side-effecting mocks, asserts
   `["rate_limit", "auth"]`) and
   `test_delete_goal_enforces_jwt_verification_before_db_call` (auth raises
   `PermissionError`, asserts zero queries executed). Also
   `test_delete_goal_rejects_malformed_goal_id_before_db_call` and
   `test_delete_goal_rejects_missing_authorization_before_db_call` for the
   surrounding ordering.
4. **AC4** — `test_delete_goal_on_success_returns_refreshed_home_view_resource_excluding_deleted_goal`:
   mocks the post-delete refresh query to return only a surviving goal
   (`"Read a book"`, a different UUID), asserts the rendered HTML contains
   the surviving goal's title and does **not** contain the deleted goal's
   id anywhere in the text. `test_delete_goal_returns_same_resource_shape_as_get_home_view`
   calls both `delete_goal` and `get_home_view` against equivalent mocked
   data in the same test and asserts `delete_result.resource.uri ==
   home_view_result.resource.uri` (`ui://home-view` for both),
   `mimeType` equality, and `type(...)` equality — proving this is the same
   resource shape, not an ad-hoc one built independently.
   `test_delete_goal_success_path_uses_shared_fetch_home_view_data_helper`
   inspects `delete_goal`'s source directly and asserts it references both
   `_fetch_home_view_data` and `_build_home_view_resource` by name, as a
   permanent regression guard against a future change silently
   reintroducing a parallel ad-hoc refresh implementation.
5. **AC5** — `test_delete_goal_tool_description_states_called_from_ui_confirm_step_not_proactive`:
   asserts the registered tool's description contains "confirm" and
   ("not"+"proactively"/"mid-conversation"), matching the actual shipped
   description text ("intended to be called from the goal-detail view's
   confirm-delete UI action after the user has explicitly confirmed, not
   something you should invoke proactively mid-conversation").

**Feature tests** (`tests/feature/test_mcp_delete_goal.py`, 5 new, mirroring
`test_mcp_get_home_view.py`'s/`test_mcp_get_goal_detail_view.py`'s real
wire-protocol pattern — `initialize` -> `notifications/initialized` ->
`tools/call` over `httpx.ASGITransport`):

1. The successful-delete path through the live MCP transport: asserts
   `isError` absent, `text/html` present, the surviving goal's title
   present, the deleted goal's id absent anywhere in the wire-level
   response body, `committed is True`, and the executed delete SQL is a
   genuine `UPDATE` (not `DELETE FROM`) — re-verifying AC1 and AC4 at the
   wire level, not just the in-process unit level.
2. Missing-JWT rejection before any DB call.
3. Expired-JWT rejection before any DB call.
4. Nonexistent/already-deleted `goal_id` (zero rows from the `UPDATE`)
   failing cleanly through the live transport: `isError:true`,
   `committed is False`, exactly one query executed.
5. Malformed (`"not-a-uuid"`) `goal_id` rejected before any DB call,
   delivered through the real JSON-RPC `tools/call` arguments.

### RLS caveat (AC2, Requirement 3/9) — same recurring caveat class

Same caveat class as every other RLS-dependent story in this repo: the
absence of an app-level `user_id` clause is confirmed by direct inspection
of the executed SQL string, and the not-owned/already-deleted path (AC2) is
exercised only with a mocked zero-row result. Neither proves the
`goals_update_own` RLS policy itself actually rejects another user's goal
or an already-soft-deleted row against a live Postgres/Supabase instance —
no Docker/local Postgres was available in this sandbox. This must be
considered an unverified assumption, not a settled fact, until exercised
against a real instance — identical framing to every prior story's
equivalent caveat (e.g. LFC-STORY-002's `set_goal_progress`,
LFC-STORY-003's `get_home_view`, LFC-STORY-004's `get_goal_detail_view`).

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root twice in a row to
rule out flakiness:

- Run 1: **203 passed**, 0 failed, 36 warnings (same pre-existing
  deprecation warnings as before, unrelated to this story).
- Run 2: **203 passed**, 0 failed, 36 warnings — identical result, no
  flakiness.

203 = 187 (prior baseline from LFC-STORY-004) + 11 new unit tests
(`test_mcp_server.py`) + 5 new feature tests (`test_mcp_delete_goal.py`) =
203. The full suite run confirms this exactly: **203 passed, 0 failed**,
across two consecutive runs.

### Totals: 16 new automated tests (11 unit, 5 feature), 203/203 full suite
passing across two consecutive runs, 0 failed, no flakiness. All 5
acceptance criteria are covered by at least one test each. The
`get_home_view` regression check confirms `_fetch_home_view_data`'s
extraction is fully behavior-preserving: all 50 of its pre-existing,
unmodified tests still pass. AC2's RLS-rejection path is verified only at
the app/query level (no live Postgres/Supabase instance) — same recurring
caveat class as every other story in this repo.

## Feature Summary — LFC-004-mcp-ui-home-goal-views

All 5 stories in this feature (LFC-STORY-001 through LFC-STORY-005) are now
implemented and tested:

- LFC-STORY-001: `goals.progress_percent` migration (PASS WITH CAVEATS)
- LFC-STORY-002: `set_goal_progress` MCP tool (PASS WITH CAVEATS)
- LFC-STORY-003: `get_home_view` tool (PASS WITH CAVEATS)
- LFC-STORY-004: `get_goal_detail_view` MCP tool (PASS WITH CAVEATS)
- LFC-STORY-005: `delete_goal` MCP tool (PASS WITH CAVEATS)

**Total new automated tests across the whole feature: 0 + 14 + 31 + 32 + 16
= 93** (LFC-STORY-001: 0 new automated tests per its test-results section;
LFC-STORY-002: 14; LFC-STORY-003: 31; LFC-STORY-004: 32; LFC-STORY-005: 16).
Final full-suite run for the feature: **203 passed, 0 failed**, run twice
consecutively with identical results — no flakiness, no regressions across
the entire feature, on top of the pre-existing suite carried over from
LFC-003-updates and earlier auth/infra stories.

**All recurring caveats carried forward across this entire feature — none
resolved by this feature, all should be revisited before this feature is
considered production-ready:**

1. **TOP ITEM — AC5 of LFC-STORY-003 (can a UI click in a real MCP-UI host
   actually invoke a tool call via `postMessage`, or only inject a chat
   message?) is still completely unverified.** No live MCP-UI host was
   ever available in any sandbox across all five stories of this feature.
   Every card-click (home -> detail), every delete-confirm action, and
   every "continue this conversation"/"create a new goal"/"just want to
   talk" entry was implemented and tested only against the assumption that
   the MCP-UI host-side `postMessage` convention supports a UI element
   invoking a tool call directly. This is the single biggest open risk in
   the entire feature: if direct tool-invocation from rendered HTML turns
   out unsupported by the actual MCP-UI spec/a real host, **every
   interactive element shipped by this feature** (card-click navigation,
   `delete_goal`'s confirm action, and any other structured UI action) must
   fall back to chat-message injection instead of a direct tool call. This
   must be verified against a real MCP-UI host before this feature is
   considered done — it is not a routine caveat like the RLS items below,
   it is a potential rework of this feature's core interaction model.
2. **RLS policies unverified against a live database, across every story
   in this feature.** No Docker daemon and no local `psql` were available
   in any sandbox session for any of the five stories. Every RLS-dependent
   behavior — `goals_update_own`'s enforcement for `set_goal_progress` and
   `delete_goal`, `goals_select_own`'s cross-user/soft-delete exclusion for
   `get_home_view` and `get_goal_detail_view` — was verified only by
   inspecting the executed SQL text (confirming no app-level `user_id`
   filter exists) and by mocking zero-row responses to simulate RLS
   rejection. None of this proves the actual Postgres RLS policies behave
   as assumed against a real instance. Before production: seed two users'
   goals, soft-delete one, and confirm `get_home_view`/`get_goal_detail_view`
   never return another user's or a soft-deleted goal, and that
   `set_goal_progress`/`delete_goal` are rejected for a `goal_id` not owned
   by the caller.
3. **MCP `TransportSecurityMiddleware.allowed_hosts` deployment risk,
   carried over unresolved from LFC-003-updates.** Still defaults to `[]`
   with DNS-rebinding protection on; in a real deployment behind a reverse
   proxy this would 421-reject every `/mcp` request (including every tool
   added by this feature) unless `allowed_hosts` is explicitly configured
   for the deployed hostname. Unchanged by this feature — still unresolved.
4. **`strategy.md`'s "MCP-UI is read-only" statement is now actively
   contradicted by this feature's shipped behavior.** This feature ships
   interactive cards (card-click navigates to a detail view via a direct
   tool call, pending verification of item 1 above) and an interactive
   delete-confirm action (`delete_goal`, a write operation invoked directly
   from rendered UI) — this is no longer read-only by any reasonable
   definition. `strategy.md` has not been updated via `/strategize` to
   reflect this across any story in this feature. This is flagged as an
   outstanding documentation/process item, not a code defect: the
   implementation matches what `architecture.md`/`requirements.md` for this
   feature actually specify, but the project's standing strategic record is
   now stale and should be revisited via `/strategize` before this feature
   (or a similar one) ships further interactive surface.
