# Test Results: LFC-003-updates

## LFC-STORY-001

**Verdict: PASS WITH CAVEATS** — see "Environment limitation" below. No real
Postgres/Supabase instance was available to run the migration against; the
SQL-level acceptance criteria (AC1, AC2, AC3, AC4) were verified by
generating and inspecting the actual SQL Alembic would execute
(`alembic upgrade head --sql` / `alembic downgrade 8e5660ff9d7f:base --sql`),
not by running it against a live database. This is the same shape of work as
LFC-001-auth-infra-baseline's LFC-STORY-002 and LFC-002-goals's
LFC-STORY-001 (both table-creation migrations), and the same testing
approach is used here.

### Layers required

- Unit: not required beyond what already exists. This migration adds no new
  business logic in `migrations/env.py` — the DB-URL-sourcing wiring it
  relies on is unchanged and already covered by
  `tests/unit/test_migrations_env.py`. There is no other unit-testable
  surface in a hand-written DDL migration file.
- Feature: there is no HTTP/API surface in this story to drive a
  conventional feature test through; the "feature" is the migration itself,
  verified via dry-run SQL generation (below) rather than a pytest feature
  test — same precedent as LFC-002-goals's LFC-STORY-001.
- E2E (Playwright): **not required**. This is a backend/infrastructure-only
  story (an Alembic migration creating a table + RLS policies) with zero
  user-facing UI, no page, no rendered component, and no browser-driven
  flow. Per `rules/testing.md`, E2E is required only for stories that change
  user-facing behavior; a schema migration with no new UI is explicitly the
  kind of story called out as not needing it.

### Environment limitation (read before trusting "PASS")

No Docker daemon was running and no local Postgres/`psql` was available in
this sandbox (`docker ps` failed to connect to the daemon; `psql` not
found) — identical constraint to every prior migration story in this repo.
The migration also references `auth.users` (Supabase-managed) and `goals`
(created in LFC-002-goals), neither of which exists in a plain local
Postgres without the full migration chain and a stub `auth` schema. Given
that constraint, testing fell back to static/dry-run verification: the
migration was never executed against a real database, so things only a live
DB could catch — e.g. both FKs actually resolving against real `auth.users`
and `goals` rows, RLS policy behavior under an actual session with
`auth.uid()` set (including the `updates_insert_own` policy's `EXISTS`
subquery against `goals` actually evaluating correctly), the index actually
being used by the planner, runtime permission errors under the
`authenticated` role — are **not** verified here. This should be re-run
against a real Supabase/Postgres instance (with the `auth` schema present
and a seeded `goals` row) before being considered fully verified for
production.

### Dry-run SQL verification (executed for real via Alembic's offline mode, no DB needed)

Ran `alembic upgrade head --sql` against the actual migration file:
- Confirms AC1: generates `CREATE TABLE updates` with `id UUID DEFAULT
  gen_random_uuid() NOT NULL PRIMARY KEY`, `user_id UUID NOT NULL` with
  `CONSTRAINT updates_user_id_fkey FOREIGN KEY(user_id) REFERENCES
  auth.users (id) ON DELETE CASCADE`, `goal_id UUID NOT NULL` with
  `CONSTRAINT updates_goal_id_fkey FOREIGN KEY(goal_id) REFERENCES goals
  (id) ON DELETE CASCADE`, `content TEXT NOT NULL`, `transcript TEXT`
  (nullable), `source TEXT DEFAULT 'coaching_update' NOT NULL` with
  `CONSTRAINT updates_source_check CHECK (source IN ('coaching_update',
  'checkin'))`, and `created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT
  NULL` — matches the story's column spec exactly, including both FKs' `ON
  DELETE CASCADE` and the `source` column's default and CHECK constraint
  verbatim.
- Confirms AC2: generates `ALTER TABLE updates ENABLE ROW LEVEL SECURITY;`
  followed by `CREATE POLICY updates_select_own ... FOR SELECT USING
  (auth.uid() = user_id)` and `CREATE POLICY updates_insert_own ... FOR
  INSERT WITH CHECK (auth.uid() = user_id AND EXISTS (SELECT 1 FROM goals g
  WHERE g.id = goal_id AND g.user_id = auth.uid() AND g.deleted_at IS
  NULL))` — wording matches the AC verbatim, including the `EXISTS` subquery
  against `goals` for active-goal linkage. No `CREATE POLICY` for
  UPDATE/DELETE appears anywhere in the generated SQL, confirming no
  UPDATE/DELETE policy was created, per AC2.
- Confirms AC3: generates `CREATE INDEX ix_updates_goal_id_created_at ON
  updates (goal_id, created_at)` — column order matches the AC.

Ran `alembic downgrade 8e5660ff9d7f:base --sql` against the same migration:
- Confirms AC4: generates `DROP POLICY IF EXISTS updates_insert_own`, `DROP
  POLICY IF EXISTS updates_select_own`, then `DROP INDEX
  ix_updates_goal_id_created_at`, then `DROP TABLE updates`, in that order —
  policies first, then the index, then the table, with nothing left over.
  The downgrade continues on to drop `goals` (LFC-002-goals's migration)
  and then `users` (LFC-001's migration), confirming the full chain remains
  intact and reversible end-to-end back to base.

Also ran `alembic history --verbose`: confirms a single linear head
(`8e5660ff9d7f` → parent `2ae062d3817c` → parent `16b5eb4c9d06` → `<base>`)
— no branching, no chain issues.

### Static checks

- `py_compile` on the migration file: syntactically valid Python.
- No new dependencies required; `alembic`/`sqlalchemy` already installed.

### Unit tests — 0 new (no new unit-testable logic; existing
`tests/unit/test_migrations_env.py` coverage is unaffected and unchanged)

### Feature tests — not applicable; covered by dry-run SQL verification above

### E2E tests — not applicable (see rationale above)

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root: **78 passed, 0
failed** (all pre-existing tests; no new tests added by this story). No
regressions introduced by adding this migration file.

### Totals: 0 new automated tests (none applicable beyond what already
exists), 78/78 full suite passing, 0 failed. AC1–AC4 verified via dry-run
SQL generation, not live execution — see environment limitation above. In
particular, the `updates_insert_own` policy's `EXISTS`-against-`goals`
active-goal-linkage check (the part of AC2 specific to this story, beyond
the simpler ownership-only pattern used in LFC-002-goals) has only been
verified as syntactically correct SQL — its actual runtime correctness
against a real `goals` table and `auth.uid()` session is unverified.

## LFC-STORY-002

**Verdict: PASS WITH CAVEATS** — independently re-verified by `qa`, not just
taken on the backend agent's report. Given this story touched shared
infrastructure (`app/auth.py`, rate limiting) used by every existing REST
endpoint, the full suite was re-derived from source review plus three
separate full-suite runs, not a re-statement of the backend agent's claimed
numbers.

### Independent re-verification performed

- Read `app/main.py`, `app/auth.py`, `app/schemas.py`, `app/rate_limit.py`,
  `app/mcp_server.py` in full, and diffed `app/auth.py`/`app/main.py`
  against `HEAD` directly (`git diff HEAD -- app/auth.py app/main.py`)
  rather than trusting the backend agent's description of the refactor.
  Confirmed `get_current_user`'s function body is byte-for-byte unchanged —
  the diff only *adds* a new `verify_bearer_token` function above it
  (duplicating, not extracting, the verification logic); `get_current_user`
  itself was not touched. Existing REST routes (`/health`, `/users/me`,
  `/goals*`) carry zero regression risk from this refactor.
- Confirmed `mcp.mount("/")` (`app.mount("/", mcp_asgi_app)`) is registered
  in `app/main.py` strictly after every REST route decorator. Starlette
  matches routes in registration order, so this cannot shadow or alter any
  existing REST route's behavior — consistent with AC1.
- Confirmed `record_update`'s signature
  (`goal_id: str, content: str, ctx: Context, transcript: str | None = None`)
  has no `source` parameter anywhere, and the INSERT always supplies
  `current_user.id` (resolved from `verify_bearer_token`, never from
  `arguments`) as `user_id`. The SQL omits `source` entirely, so the
  table's `DEFAULT 'coaching_update'` always applies — there is no code
  path to produce a `checkin` row via this tool. Satisfies AC3.
- Confirmed the insert goes through `get_rls_connection(current_user.id)`,
  the same RLS-scoped-connection helper every other write path in this repo
  uses (`create_goal`, `update_goal`, `delete_goal`) — no bypass.
- Read the actual MCP-exposed description string passed to `@mcp.tool(...)`
  in `app/mcp_server.py` (not a code comment): it explicitly says "Call
  this tool only once you and the user have settled on something concrete
  to record — not after every message in the conversation" and "Write a
  concise summary of the agreed outcome into `content`; do not paste the
  raw conversation." Satisfies AC7 — verified against the real string, not
  just the test assertion that greps it.
- Traced FastMCP/MCP SDK's exception handling
  (`mcp/server/lowlevel/server.py`, `call_tool`, line ~589:
  `except Exception as e`) to confirm that any exception raised inside a
  tool handler — including the `HTTPException` raised by
  `verify_bearer_token` on a missing/malformed/expired JWT — is caught by
  the SDK itself and converted into a `CallToolResult(isError=True, ...)`
  response, not propagated as a raw 500 or left unhandled. This is real SDK
  behavior read from the installed package source, not assumed — it
  validates the claim in `test_mcp_record_update.py` rather than taking it
  on faith.

### Test suite — run three times independently, from repo root

Run 1: `96 passed, 0 failed` (36 warnings, pre-existing deprecation
warnings unrelated to this story).
Run 2: `96 passed, 0 failed`.
Run 3: `96 passed, 0 failed`.

No flakiness observed across three consecutive runs, including the
rate-limit tests that reload `app.rate_limit`/`app.main` via `importlib`
and reset module-level limiter state — the known fragile pattern flagged
in this repo's history (LFC-002-goals's LFC-STORY-004 test-pollution bug).
78 pre-existing + 18 new = 96, matching the backend agent's claimed count,
confirmed firsthand rather than repeated on trust.

### Layers required

- Unit: required (new business logic in `mcp_server.record_update`,
  `rate_limit.enforce_mcp_rate_limit`, `auth.verify_bearer_token`). Present:
  `tests/unit/test_mcp_server.py` (7 tests), `tests/unit/test_rate_limit.py`
  (4 tests), additions to `tests/unit/test_auth.py` (5 new
  `verify_bearer_token` tests), `tests/unit/test_main_rate_limit_key.py`
  (re-pointed import, no behavior change, still passing).
- Feature: required (MCP tool call end-to-end, rate limiting shared across
  REST/MCP). Present: `tests/feature/test_mcp_record_update.py` (3 tests),
  additions to `tests/feature/test_rate_limit.py`.
- E2E (Playwright): not required. There is no new user-facing UI/page in
  this story — `record_update` is an MCP tool consumed by an AI client, not
  a browser-driven flow, consistent with the testing rules' carve-out for
  infra/non-UI surfaces.

### Test quality assessment (per `rules/testing.md` external-contract-assumptions section)

`tests/feature/test_mcp_record_update.py` genuinely drives the real MCP
wire protocol: `initialize` → `notifications/initialized` → `tools/call`,
through `httpx.ASGITransport` against the actual mounted
`mcp.streamable_http_app()`, with a stateful session handshake the SDK
itself enforces (a `tools/call` without a prior `initialize` is rejected
with 400 per the SDK's own session manager). This is not a
self-consistency test — it exercises the SDK's real session-management and
real `Context.request_context.request` mechanism for surfacing the
Authorization header to a tool handler, the same mechanism the production
code path (`app/mcp_server.py`) relies on. The test docstring's claim to
this effect was independently confirmed by reading the SDK source
(`call_tool`, `transport_security.py`) rather than taken at face value.
`tests/unit/test_mcp_server.py` separately uses a hand-built
`SimpleNamespace` fake `Context` for narrower unit-level isolation, which
is appropriate given the feature test already covers the real-transport
case — using mocks at the unit layer once the SDK mechanism is verified
once at the feature layer is consistent with the testing rules, not a
violation of them.

### Regression check on existing REST behavior

Re-read `tests/unit/test_auth.py`'s existing tests for `get_current_user`
(expired token, malformed token, missing header, tampered signature,
non-bearer scheme, missing sub/email claim, unresolvable signing key, no
PII/token leakage in logs) — all still present, unmodified, and passing.
Combined with the `git diff` confirmation that `get_current_user`'s body
was not touched, this is not a case of tests being quietly weakened to
mask a regression — the function under test is identical to before this
story. `tests/unit/test_main_rate_limit_key.py` still imports
`get_client_ip` from `app.main` (re-exported via `from app.rate_limit
import get_client_ip` in `app/main.py`), so the import surface contract is
preserved even though the implementation moved modules.

### AC4 (RLS rejection of invalid/foreign/deleted goal_id)

Same caveat as every other RLS-dependent story in this repo
(`LFC-STORY-001`'s migration, and the precedent set by prior features):
**not verifiable against a live Postgres/Supabase instance in this
sandbox.** `tests/unit/test_mcp_server.py::test_record_update_raises_when_rls_insert_check_rejects_the_row`
only verifies that the application code correctly raises `ValueError` when
the INSERT returns no row (i.e., correctly handles RLS's `WITH CHECK`
silently filtering the insert) — it does not verify that the
`updates_insert_own` policy's `EXISTS` subquery against `goals` (ownership
+ not-deleted) actually behaves this way under a real `auth.uid()` session.
This is a continuation of the same unverified-RLS-against-live-DB
assumption flagged in `LFC-STORY-001`'s test results above, not a new gap
introduced by this story.

### Deployment risk flagged by backend agent — independently confirmed

Read `mcp/server/transport_security.py` directly:
`TransportSecuritySettings.allowed_hosts` defaults to `[]`, and
`enable_dns_rebinding_protection` defaults to `True`. With an empty
allow-list and protection enabled, `TransportSecurityMiddleware` would
reject any request whose `Host` header isn't in that (empty) list with a
421 — meaning, as currently configured, `/mcp` would reject every request
in a real deployment behind a reverse proxy with any hostname other than
`localhost`/`127.0.0.1`. This is accurately described by the backend
agent and is a real, not sandbox-only, future-deployment risk — recorded
here explicitly as a flagged risk for follow-up before this app is
deployed behind a real reverse proxy, the same way the unverified-RLS
caveat is carried forward story to story. Not a blocker for this story
(no story AC requires production deployment configuration), but should not
be silently forgotten.

### Totals: 18 new automated tests (7 unit `test_mcp_server.py` + 4 unit
`test_rate_limit.py` + 5 unit `test_auth.py` additions + 3 feature
`test_mcp_record_update.py` + feature `test_rate_limit.py` additions),
96/96 full suite passing across 3 independent runs, 0 failed, 0 flaky.
AC1, AC3, AC5, AC6, AC7 fully verified at the app/code level. AC2 verified
via direct SDK-source confirmation (not guessed) consistent with
`JWT-VERIFICATION-INCIDENT.md`'s precedent. AC4 verified only at the
app-code level (RLS's empty-row-on-INSERT behavior is correctly handled by
the application), not against a live Postgres/Supabase instance — carried
forward as the same class of caveat already on record for this feature's
LFC-STORY-001.

## LFC-STORY-003

**Verdict: PASS WITH CAVEATS** — same recurring RLS-against-live-DB caveat
as every other story in this feature; no new caveat introduced.

### Implementation verified against source before writing tests

Read `app/mcp_server.py` and `app/schemas.py` in full. The backend agent's
report matched the actual code:

- `list_updates(goal_id: str, ctx: Context) -> list[dict]` follows the same
  `verify_bearer_token` → `enforce_mcp_rate_limit(request, current_user.id)`
  sequence as `record_update`, both pulled from
  `ctx.request_context.request`.
- `goal_id` is validated as a `UUID` at the boundary (`UUID(goal_id)`),
  raising `ValueError` on failure before any DB call.
- The SQL is `SELECT content, source, created_at FROM updates WHERE
  goal_id = %s ORDER BY created_at DESC` via
  `get_rls_connection(current_user.id)` — no `user_id` filter (relies on
  the `updates_select_own` RLS policy from LFC-STORY-001's migration), no
  `source` filter, and critically, `transcript` is never named anywhere in
  the SELECT — so the column never reaches application memory, not just
  never reaches the response schema.
- `UpdateListItem` (`app/schemas.py`) declares exactly `content: str`,
  `source: str`, `created_at: str` — no `id`, `goal_id`, or `transcript`
  field exists on the model at all.
- An empty `fetchall()` result returns `[]` via the list comprehension,
  not an error path.

### Layers required

- Unit: required (new business logic in `mcp_server.list_updates`, mirrors
  `record_update`'s unit-test treatment in LFC-STORY-002).
- Feature: required (new MCP tool call surface, same as `record_update`).
- E2E (Playwright): not required — `list_updates` is an MCP tool consumed
  by an AI client, not a browser-driven UI flow, same rationale as
  LFC-STORY-002.

### Tests written

**Unit — `tests/unit/test_mcp_server.py` (8 new tests, 14 total in file
after this story):**

- `test_list_updates_returns_only_content_source_created_at_never_transcript`
  — AC1. The mocked DB row itself contains only `(content, source,
  created_at)` (no transcript value exists anywhere in the fixture), and
  the assertion checks `set(result[0].keys()) == {"content", "source",
  "created_at"}` plus an explicit `"transcript" not in result[0]`. Also
  asserts the executed SQL text contains `"SELECT content, source,
  created_at"` and never the word `"transcript"` — proving the query
  itself never fetches the column, the strongest form of "never leaks"
  available without a live DB.
- `test_list_updates_returns_checkin_and_coaching_update_rows_together` —
  AC2. Mocked rows include one `source='checkin'` row and one
  `source='coaching_update'` row for the same `goal_id`; asserts both
  sources come back. Per the story's own framing, this is testable only by
  inserting a `checkin` row directly via the mocked cursor, since nothing
  in this feature can produce a `checkin` row itself.
- `test_list_updates_returns_empty_list_for_goal_with_no_updates` — AC3.
  Empty `fetchall()` result returns `[]`, not an exception.
- `test_list_updates_scopes_query_through_rls_connection_for_verified_user`
  — AC4 (app-level only; see caveat below). Confirms
  `get_rls_connection` is opened with the verified caller's `current_user.id`
  and that the executed SQL contains no `user_id` predicate — relying
  entirely on `updates_select_own` RLS, the same as the backend agent's
  report.
- `test_list_updates_rejects_missing_authorization_before_db_call` — AC5.
  No DB call occurs when `verify_bearer_token` raises.
- `test_list_updates_rejects_malformed_goal_id_before_db_call` — AC5/AC1
  boundary validation. A non-UUID `goal_id` raises `ValueError` before any
  DB call.
- `test_list_updates_enforces_rate_limit_before_db_call` — AC6.
  `enforce_mcp_rate_limit` is awaited exactly once with the verified
  `current_user.id`, mirroring `record_update`'s rate-limit wiring.
- `test_list_updates_tool_description_promises_no_transcript` — confirms
  the literal MCP-exposed tool description (read from
  `mcp._tool_manager._tools["list_updates"].description`, not a comment)
  promises never returning the transcript.

**Feature — `tests/feature/test_mcp_list_updates.py` (6 new tests, new
file):**

Drives the real MCP wire protocol (`initialize` →
`notifications/initialized` → `tools/call`) via `httpx.ASGITransport`
against a `FastMCP` instance with the actual production `list_updates`
function registered, the same pattern as
`tests/feature/test_mcp_record_update.py` — not a weaker, function-level
mock. One implementation detail discovered while writing these tests: the
streamable-HTTP transport returns an SSE-framed body
(`event: message\r\ndata: {...}\r\n\r\n`), so a small `_parse_sse_json`
helper extracts the `data:` line before parsing JSON — `response.json()`
alone fails on this transport's response format. This was a test-harness
detail, not a defect in the implementation.

- `test_list_updates_through_live_mcp_transport_returns_content_source_created_at_only`
  — AC1 through the real transport. Asserts the literal response text
  never contains the substring `"transcript"`, and that the
  `structuredContent.result` items each have exactly the three expected
  keys.
- `test_list_updates_through_live_mcp_transport_returns_checkin_and_coaching_update_rows`
  — AC2 through the real transport.
- `test_list_updates_through_live_mcp_transport_returns_empty_list_for_goal_with_no_updates`
  — AC3 through the real transport.
- `test_list_updates_through_live_mcp_transport_rejects_missing_jwt_before_db_call`
  — AC5, missing JWT case.
- `test_list_updates_through_live_mcp_transport_rejects_expired_jwt_before_db_call`
  — AC5, expired JWT case.
- `test_list_updates_through_live_mcp_transport_rejects_malformed_jwt_before_db_call`
  — AC5, malformed JWT case.

AC6 (rate limiting) is covered at the unit layer only
(`test_list_updates_enforces_rate_limit_before_db_call` plus the
pre-existing `tests/unit/test_rate_limit.py` coverage of the shared
`enforce_mcp_rate_limit` function, which both `record_update` and
`list_updates` call identically). No feature-layer 429 test exists for
`list_updates`, consistent with there being none for `record_update`
either in LFC-STORY-002 — the rate-limiting mechanism itself is generic
(keyed by IP/user, not by tool name) and was already proven once at the
feature layer's level of confidence via the unit suite; this is not a new
testing gap introduced by this story.

### Full suite regression check — run three times independently

Run 1: `110 passed, 0 failed` (36 warnings, all pre-existing).
Run 2: `110 passed, 0 failed`.
Run 3: `110 passed, 0 failed`.

96 pre-existing (after LFC-STORY-002) + 14 new (8 unit + 6 feature) = 110,
confirmed by direct collection (`pytest --collect-only`), not just by
arithmetic. No flakiness across three consecutive runs, in the same
MCP/rate-limiting area that needed careful re-verification in
LFC-STORY-002.

### AC4 caveat (same recurring class as every other RLS-dependent story)

Verified only at the app/query level: the SQL correctly omits a `user_id`
predicate, and the connection is correctly opened scoped to the verified
caller's id via `get_rls_connection`, so the application is relying on
`updates_select_own` exactly as designed. Whether that RLS policy actually
excludes another user's rows for the same `goal_id` under a live
`auth.uid()` session was **not** verified against a real Postgres/Supabase
instance in this sandbox — same unresolved limitation carried since
LFC-STORY-001's migration testing.

### Totals: 14 new automated tests (8 unit + 6 feature), 110/110 full suite
passing across 3 independent runs, 0 failed, 0 flaky. AC1, AC2, AC3, AC5,
AC6 fully verified at the app/code level (AC1's "never transcript"
assertion verified both via the SQL-text check and the live-transport
response-text check). AC4 verified only at the app-code level, not against
a live Postgres/Supabase instance — same recurring caveat as every other
RLS-dependent story in this feature.

## Feature Summary — LFC-003-updates

All 3 stories in this feature (LFC-STORY-001 through LFC-STORY-003) are now
implemented and tested:

- LFC-STORY-001: `updates` table migration with RLS (PASS WITH CAVEATS)
- LFC-STORY-002: `record_update` MCP tool + MCP server scaffold (PASS WITH CAVEATS)
- LFC-STORY-003: `list_updates` MCP tool (PASS WITH CAVEATS)

**Total new automated tests across the feature: 32** (0 + 18 + 14). Final
full-suite run for the feature: **110 passed, 0 failed**, run three times
consecutively with identical results — no flakiness, no regressions across
the whole feature.

**Recurring caveats carried forward — neither resolved by this feature,
both should be revisited before production:**

1. **RLS policies unverified against a live database.** No Docker daemon
   and no local `psql` were available in this sandbox for any story in
   this feature, so `updates_select_own` and `updates_insert_own`'s actual
   runtime behavior under a real `auth.uid()` session (including
   `updates_insert_own`'s `EXISTS` subquery against `goals` for
   active-goal linkage, and `updates_select_own`'s cross-user exclusion
   exercised by this story's AC4) has never been exercised against a real
   Postgres/Supabase instance — only via Alembic `--sql` dry-run
   (LFC-STORY-001) and app-level mocked-cursor tests (LFC-STORY-002,
   LFC-STORY-003). Before production, re-run against a real
   Supabase/Postgres instance: seed two users' goals and updates (including
   a `checkin`-source row) and confirm `list_updates` for user A's goal
   never returns user B's rows, and that `record_update` is rejected for a
   `goal_id` not owned by the caller.
2. **MCP `TransportSecurityMiddleware.allowed_hosts` defaults to `[]` with
   DNS-rebinding protection on.** Flagged by the backend agent and
   independently confirmed by `qa` in LFC-STORY-002 by reading
   `mcp/server/transport_security.py` directly: in a real deployment
   behind a reverse proxy, this would 421-reject every `/mcp` request
   (including both `record_update` and `list_updates`) unless
   `allowed_hosts` is explicitly configured for the deployed hostname. Not
   a defect in any story's acceptance criteria, but unresolved — should be
   configured before this app is deployed behind a real reverse proxy.
