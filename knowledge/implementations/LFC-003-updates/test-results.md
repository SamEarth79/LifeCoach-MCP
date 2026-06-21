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
