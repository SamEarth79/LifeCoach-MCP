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

## LFC-STORY-003: get_home_view tool

**What was implemented:** Backend added `get_home_view` to
`app/mcp_server.py` plus `HomeGoalCard`/`HomeViewData` dataclasses and a
`render_home_view` function in a new `app/ui_templates.py`. The tool runs
`enforce_mcp_rate_limit(request)` then `verify_bearer_token(...)` (same
ordering as every other tool), queries `users.display_name`/`email` and the
caller's goals (`id`, `title`, `progress_percent`) with RLS-only filtering —
no app-level `user_id`/`deleted_at` clause, same pattern as `list_goals` —
then looks up each goal's most recent `updates.created_at`. Everything is
wrapped into an `EmbeddedResource(type="resource",
resource=TextResourceContents(uri="ui://home-view", mimeType="text/html",
text=render_home_view(data)))`. On a missing user row or any unhandled
exception during the query, the tool catches the failure and returns the
same `EmbeddedResource`-wrapped failure-state HTML instead of letting an
exception propagate. Frontend implemented `render_home_view`'s real
HTML/CSS/inline JS body: HTML-escapes the greeting name, every goal title,
and the error message via `html.escape`; renders a circular progress
indicator with a real percentage or a dashed "no estimate yet" treatment
when `progress_percent is None` (never a misleading `0%`); shows an
"Updated <date>" line only when a goal has a recorded update; renders
distinct "create a new goal" and "just want to talk?" entries wired to
`lifecoachSendPrompt` (chat-message injection); wires each goal card's click
to `lifecoachSendTool('get_goal_detail_view', { goal_id: '<id>' })`; and
includes both an empty-state and a failure-state variant, neither of which
render any goal cards. Both `postMessage`-calling JS functions carry an
inline comment marking them `UNVERIFIED against a live MCP-UI host`. No tab
bar or "Total Days"/"Current Streak" markup was added, per architecture.md's
explicit exclusions.

**What was tested and why:** Read `app/ui_templates.py` and
`app/mcp_server.py::get_home_view` in full before writing any test, rather
than trusting either agent's report at face value. Per `rules/testing.md`,
this story introduces new rendering logic (`render_home_view`) and a new
MCP tool surface (`get_home_view`), so unit tests were required for both,
plus a feature-level wire-protocol test for the tool. E2E was not added in
this pass: this story's UI is HTML rendered for an MCP-UI host, not a page
or route of this repo's own, and no live MCP-UI host exists in this sandbox
to drive a real browser-based `postMessage` round trip against; the
rendering logic is instead fully covered at the unit layer.

- **Unit tests** (`tests/unit/test_ui_templates.py`, new file — one
  responsibility per file, since `render_home_view` is a distinct rendering
  concern from `get_home_view`'s tool logic): an actual constructed
  `<script>alert(1)</script>` XSS payload in the greeting name, a card
  title, and the error message, asserting the raw tag is absent and the
  escaped entity is present in each case; `progress_percent is None` vs a
  real percentage vs `progress_percent == 0` rendering distinctly (never a
  misleading `0%` for the `None` case); the "Updated" line's
  presence/absence tied exactly to `last_updated_at`; empty-state and
  failure-state both rendering zero goal cards, with failure-state taking
  precedence even when a non-empty goals list is simultaneously set;
  absence of any tab-bar/streak/"Total Days" markup; the create-goal/talk
  entries calling `lifecoachSendPrompt` (never `lifecoachSendTool`); the
  goal card's `onclick` calling `lifecoachSendTool` with the goal's own id;
  and confirmation that the `UNVERIFIED against a live MCP-UI host` comment
  is actually present in both `postMessage`-calling functions' source, not
  just claimed in the report.
- **Unit tests** (appended to `tests/unit/test_mcp_server.py`): a new
  `_SequencedCursor` fake (the existing `_FakeCursor` helpers only support
  one `fetchall`-or-`fetchone` per test; `get_home_view` issues one
  `fetchone`, one `fetchall`, then one `fetchone` per goal) drives tests for
  the successful greeting+cards path, the display-name-to-email fallback,
  the empty-goals path, absence of `user_id`/`deleted_at` in the executed
  goal query, the `None`-progress rendering path through the real tool
  function, rate-limit-before-auth ordering, auth-before-DB-call ordering,
  and both handled-failure paths (missing user row, and an arbitrary
  `RuntimeError` raised mid-query) returning a non-raising failure
  `EmbeddedResource` instead of propagating.
- **Feature tests** (`tests/feature/test_mcp_get_home_view.py`, new file
  mirroring `test_mcp_set_goal_progress.py`'s real wire-protocol pattern):
  drives the actual MCP streamable-HTTP handshake against a fresh `FastMCP`
  instance with the production `get_home_view` function, confirming a valid
  JWT yields a non-error response containing the greeting and `text/html`,
  and that a missing or expired JWT is rejected with zero DB calls.
- A risk was identified and recorded, not fixed silently: the goal card's
  `onclick` interpolates `card.id` into a JS-string context inside an HTML
  attribute. `html.escape`'s default `quote=True` HTML-entity-encodes an
  embedded single quote, which prevents breaking out of the HTML attribute,
  but does not fully neutralize a JS-string-context breakout for an
  arbitrary *untrusted* string in all cases, since the browser HTML-decodes
  the attribute before the `onclick` body executes. This is not an
  exploitable defect today — `card.id` is always a server-generated UUID
  from the `goals.id` column, never user-controlled text, and no other
  value is interpolated into any `onclick`/script body anywhere in this
  template — but is flagged explicitly so it is not silently assumed safe
  if a future change ever interpolates a different, non-UUID value into
  this same template.
- AC5 (card-click invoking `get_goal_detail_view` via the MCP-UI host's
  `postMessage` mechanism) **cannot be tested in this sandbox at all** — no
  live MCP-UI host exists to observe a real `postMessage` round trip, and
  `get_goal_detail_view` itself is a separate, not-yet-implemented story.
  This is recorded as an explicit open verification item, consistent with
  architecture.md's and requirements.md's own framing of this as an
  unconfirmed external-contract assumption — not silently treated as
  passing.
- AC1/AC4's RLS reliance is verified only at the app/query level (absence of
  an app-level `user_id`/`deleted_at` clause, and an empty-goals path
  exercised with a mocked zero-row result) — not against a live
  Postgres/Supabase instance. Same recurring caveat class as every other
  RLS-dependent story in this repo.

**Test results:** 31 new tests (18 + 10 unit, 3 feature), 155/155 full
suite passing across two consecutive runs with no flakiness (up from the
124 baseline carried over from LFC-STORY-002). See `test-results.md` for
the full breakdown per acceptance criterion, including the AC4 RLS caveat
and the AC5 untestable-in-sandbox open item.
