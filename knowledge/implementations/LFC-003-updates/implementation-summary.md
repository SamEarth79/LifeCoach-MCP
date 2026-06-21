# Implementation Summary: LFC-003-updates

## LFC-STORY-001

Tested the new `updates` table migration
(`migrations/versions/8e5660ff9d7f_create_updates_table.py`) entirely
through Alembic's offline SQL-generation mode, since no Docker daemon or
local Postgres/`psql` was available in this environment — the same
constraint documented for every prior migration story in this repo
(LFC-001's `users` table, LFC-002-goals's `goals` table).

Ran `alembic upgrade head --sql` and diffed the generated DDL against each
acceptance criterion line by line: the `CREATE TABLE updates` statement,
both foreign keys (`user_id` → `auth.users.id`, `goal_id` → `goals.id`,
both `ON DELETE CASCADE`), the `source` column's default and
`CHECK (source IN ('coaching_update', 'checkin'))` constraint, the
`ix_updates_goal_id_created_at` index, the `ENABLE ROW LEVEL SECURITY`
statement, and both `CREATE POLICY` statements (`updates_select_own`,
`updates_insert_own`) all matched the story's wording verbatim. Confirmed
no UPDATE/DELETE policy is created anywhere in the generated SQL, per AC2.

Ran `alembic downgrade 8e5660ff9d7f:base --sql` and confirmed the reverse
order is correct — both policies dropped, then the index, then the table —
and that the downgrade chain continues cleanly through `goals` and `users`
all the way to base, with nothing left over. Ran `alembic history
--verbose` to confirm a single linear head with no branching:
`8e5660ff9d7f` → `2ae062d3817c` → `16b5eb4c9d06` → base.

This is a backend/infra-only story (a database migration) with no
user-facing surface, so per `rules/testing.md` no E2E tests were required,
and no new unit/feature tests were written (there is no new business logic
or HTTP surface to test beyond the DDL itself, mirroring LFC-002-goals's
LFC-STORY-001). Ran the full existing suite
(`.venv/bin/python -m pytest -q`): 78 passed, 0 failed, no regressions.

Flagged as **PASS WITH CAVEATS**: the migration was never executed against
a real database, so the FKs' actual resolution, the RLS policies' runtime
behavior under `auth.uid()` (especially `updates_insert_own`'s `EXISTS`
subquery against `goals` for active-goal linkage — the one piece of logic
in this migration that's more involved than a plain ownership check), and
the index's actual use by the query planner remain unverified. This should
be re-run against a real Supabase/Postgres instance before being
considered production-verified, consistent with the same caveat already on
record for every other migration story in this repo.

## LFC-STORY-002

Independently re-verified (not just re-stated) the backend agent's
implementation of the MCP server scaffold and `record_update` tool, given
the unusually high regression risk of this story (it touched
`app/auth.py` and rate limiting, both shared by every existing REST
endpoint).

What was tested and why:

- **No REST regression risk** — confirmed via `git diff HEAD --
  app/auth.py app/main.py` that `get_current_user`'s body is genuinely
  unchanged (the story added a new `verify_bearer_token` function, it did
  not refactor `get_current_user` to call it), and that the MCP ASGI app
  is mounted strictly after every REST route, so Starlette's
  registration-order route matching can't shadow existing routes. This
  directly addresses the highest-risk part of the change.
- **No caller-controlled `user_id`/`source`** — read `record_update`'s
  full signature and SQL: no `source` parameter exists, and `user_id` in
  the INSERT always comes from `current_user.id` (resolved by
  `verify_bearer_token` from the verified JWT `sub` claim), never from
  `arguments`. Confirms AC3 at the code level.
- **RLS-consistent write path** — confirmed the insert goes through
  `get_rls_connection(current_user.id)`, the same helper used by every
  other write endpoint in this repo (`create_goal`, `update_goal`,
  `delete_goal`); no bypass.
- **AC7's description text** — read the literal string passed to
  `@mcp.tool(description=...)` in `app/mcp_server.py` (not a comment, not
  just the test that asserts on it): confirmed it instructs the caller to
  wait for a settled agreement and to write a concise summary rather than
  the raw transcript.
- **MCP SDK exception handling, read from source, not assumed** — traced
  `mcp/server/lowlevel/server.py`'s `call_tool` to confirm the SDK itself
  catches any exception a tool handler raises (including the
  `HTTPException` from a rejected JWT) and converts it to
  `isError: true`, rather than crashing the transport. This validates
  `test_mcp_record_update.py`'s claim about live SDK behavior instead of
  trusting the test's docstring.
- **Full suite run three times independently**: `96 passed, 0 failed` on
  every run, no flakiness — given this story's known-fragile area
  (module-reload-based rate-limit test isolation, which caused a real bug
  in LFC-002-goals's LFC-STORY-004), running once was not considered
  sufficient.
- **Test quality**: `tests/feature/test_mcp_record_update.py` drives the
  actual MCP wire protocol (`initialize` → `notifications/initialized` →
  `tools/call`) over `httpx.ASGITransport` against the real mounted ASGI
  app, including the SDK's own stateful-session enforcement. This is a
  genuine external-contract exercise of the SDK's `Context`/request
  mechanism, not a self-consistency mock — satisfying the bar in
  `rules/testing.md`'s external-contract-assumptions section, unlike the
  HS256-vs-ES256 incident this repo previously hit.

Caveats carried forward (not fixed in this story, flagged for visibility):

- **AC4 (RLS rejection of invalid/foreign/deleted `goal_id`)** is verified
  only at the application-code level (the no-row-returned-from-INSERT
  case is correctly turned into an error) — not against a live
  Postgres/Supabase instance, the same class of caveat already recorded
  for this feature's LFC-STORY-001 migration.
- **`TransportSecurityMiddleware`'s `allowed_hosts` defaults to `[]`**
  with DNS-rebinding protection on by default — confirmed by reading
  `mcp/server/transport_security.py` directly. In a real deployment behind
  a reverse proxy, this would 421-reject every `/mcp` request unless
  `allowed_hosts` is explicitly configured. Not a defect in this story
  (no AC requires production deployment config), but recorded here as a
  flagged risk for whichever story first deploys this behind a real proxy.

Verdict: **PASS WITH CAVEATS** (same two caveats as the backend agent
flagged; both independently confirmed, not newly discovered).

## LFC-STORY-003

Read `app/mcp_server.py`'s `list_updates` function and `app/schemas.py`'s
`UpdateListItem` model in full before writing any tests, to confirm the
backend agent's report matched the actual code rather than taking it on
trust: same `verify_bearer_token` → `enforce_mcp_rate_limit` sequence as
`record_update`; `goal_id` validated as a `UUID` at the boundary; the SQL
selects only `content, source, created_at` (never names `transcript`) via
`get_rls_connection(current_user.id)` with no `user_id` or `source`
filter; `UpdateListItem` declares exactly those three fields with no
`id`/`goal_id`/`transcript`; an empty result returns `[]`.

What was tested and why:

- **AC1 (never leaks transcript)** — tested at two levels for maximum
  confidence: a unit test asserts the executed SQL text never contains the
  word `transcript` (proving the query itself never fetches the column),
  and both a unit test and a live-wire-protocol feature test assert the
  returned item has exactly `{content, source, created_at}` as keys. This
  is the single most important assertion in this story per the story's
  own framing.
- **AC2 (no source filtering)** — a mocked row with `source='checkin'`
  alongside a `coaching_update` row for the same `goal_id` is returned in
  full by both a unit test and a feature test, confirming no filtering
  happens in practice (not just absent from the SQL text). As the story
  itself notes, this is only testable by inserting a `checkin` row
  directly via the mocked cursor — nothing in this feature can produce
  one.
- **AC3 (empty result, not an error)** — a goal with zero rows returns
  `[]` at both the unit and feature layer.
- **AC4 (cross-user isolation)** — tested only at the app/query level
  (confirms no `user_id` predicate exists in the SQL and that
  `get_rls_connection` is opened scoped to the verified caller's id, so
  the application correctly relies on the `updates_select_own` RLS policy
  rather than re-implementing the filter). Not verified against a live
  Postgres/Supabase instance — the same caveat already on record for every
  other RLS-dependent story in this feature.
- **AC5 (auth rejection before any DB call)** — missing, expired, and
  malformed JWTs are all rejected with zero executed queries, tested at
  both the unit layer (mocked `verify_bearer_token`) and the feature layer
  (real JWT signing/verification through the live wire protocol).
- **AC6 (rate limiting)** — a unit test confirms `enforce_mcp_rate_limit`
  is awaited once with the verified caller's id, the same wiring
  `record_update` uses. Consistent with there being no feature-layer
  429 test for `record_update` either, no new feature-layer rate-limit
  test was added for `list_updates` — the underlying `enforce_mcp_rate_limit`
  function (generic across both tools, keyed by IP/user not tool name) is
  already covered at the feature layer via `tests/feature/test_rate_limit.py`'s
  REST-endpoint tests and at the unit layer via `tests/unit/test_rate_limit.py`.
- **Feature-layer wire-protocol test** (`tests/feature/test_mcp_list_updates.py`,
  new file): drives the real `initialize` → `notifications/initialized` →
  `tools/call` handshake via `httpx.ASGITransport` against a `FastMCP`
  instance with the actual production `list_updates` function registered
  — the same pattern as `test_mcp_record_update.py`, not a weaker
  function-level mock. Discovered along the way that the streamable-HTTP
  transport's response body is SSE-framed
  (`event: message\r\ndata: {...}\r\n\r\n`), requiring a small
  `_parse_sse_json` test helper to extract the JSON payload — a
  test-harness detail, not an implementation defect.
- **Full suite run three times independently**: `110 passed, 0 failed` on
  every run (96 pre-existing + 14 new: 8 unit in `test_mcp_server.py` + 6
  feature in the new `test_mcp_list_updates.py`), no flakiness, in the
  same MCP/rate-limiting area that needed careful re-verification in
  LFC-STORY-002.

Caveats carried forward (not new, not fixed in this story):

- **AC4** verified only at the app-code level, not against a live
  Postgres/Supabase instance — same recurring class of caveat as
  LFC-STORY-001 and LFC-STORY-002.
- **MCP `allowed_hosts` deployment risk** (flagged in LFC-STORY-002,
  unresolved) remains unresolved — should be configured before this app
  is deployed behind a real reverse proxy.

Verdict: **PASS WITH CAVEATS** (no new caveat introduced; both carried
forward from earlier stories in this feature).
