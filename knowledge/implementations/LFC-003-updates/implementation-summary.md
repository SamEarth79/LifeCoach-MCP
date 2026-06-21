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
