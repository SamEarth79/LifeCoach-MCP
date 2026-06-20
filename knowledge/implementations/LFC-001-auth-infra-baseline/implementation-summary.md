# Implementation Summary: LFC-001-auth-infra-baseline

## LFC-STORY-001

Tested the FastAPI app skeleton, environment-based settings module, and the
`GET /health` endpoint against all four acceptance criteria.

What was tested and why:

- Settings loading (`app/config.py`): unit tests confirm `Settings` reads
  all four required environment variables (Supabase URL, Supabase anon key,
  Supabase service role key, database URL) with no hardcoded values, and
  that missing variables fail loudly via `ValidationError` rather than
  silently defaulting — this backs AC2's "no secret values hardcoded, read
  from environment" requirement.
- DB connectivity check (`app/db.py`): unit tests mock the connection layer
  to verify `check_connectivity()` returns `True` on a successful query and
  `False` on both a connection-level error and a query-level error, without
  needing a real database — this isolates the logic AC4 depends on.
- Health endpoint (`app/main.py`): feature tests use FastAPI's `TestClient`
  with `check_connectivity` mocked to drive both branches directly — the
  200/healthy response (AC1) and the 503/unhealthy response (AC4) — plus a
  check that no authentication is required to reach the endpoint (AC1).
- `.env.example` / `.gitignore` (AC3) were verified by inspection rather
  than an automated test: `.env.example` contains placeholders for all four
  required variables, and `.gitignore` lists `.env`. This is a static
  config/file-presence check, not application logic, so no test layer
  applies per `rules/testing.md`'s scoping rules.
- E2E (Playwright) was explicitly skipped: this story has no user-facing
  UI, so there's no browser-driven user journey to cover. Per
  `rules/testing.md`, E2E is only required for stories that change
  user-facing behavior.

Beyond the automated suite, manually verified the app actually boots: ran
`pip install -e .` in a clean venv, imported `app.main` to confirm the
`/health` route registers without a live DB at import time, then started a
real `uvicorn` process against a deliberately unreachable
`DATABASE_URL` and issued a real HTTP request — got back `503` with the
expected unhealthy payload, confirming AC4 holds outside of test mocking
too. Server was torn down after the check.

Result: 9/9 tests passing (6 unit, 3 feature), all four acceptance criteria
verified. Verdict: PASS.

## LFC-STORY-002

Tested the Alembic scaffold (`migrations/env.py`, `alembic.ini`) and the
`create_users_table` migration (`16b5eb4c9d06`) against all four
acceptance criteria.

What was tested and why:

- AC1 (DB URL sourced from app settings, not hardcoded): wrote
  `tests/unit/test_migrations_env.py`, which loads the real `env.py` module
  with `alembic.context` mocked, and asserts `config.set_main_option`
  receives the exact value of `get_settings().database_url`. A second test
  changes `DATABASE_URL` in the environment and confirms the value Alembic
  receives changes accordingly — ruling out a hardcoded or cached URL
  anywhere in the wiring.
- AC2 (users table columns) and AC3 (RLS + policies): no live database was
  available in this environment (no Docker daemon running, no local
  Postgres/`psql` installed), and the migration's `auth.users` FK
  reference is Supabase-managed and wouldn't exist in a plain Postgres
  without a stub schema anyway. Instead of skipping these ACs, ran
  `alembic upgrade head --sql` — Alembic's offline mode, which generates
  the exact SQL it would execute without touching a database — and
  inspected the output directly. It matches the story's column spec and
  RLS/policy definitions exactly.
- AC4 (clean downgrade): ran `alembic downgrade 16b5eb4c9d06:base --sql`
  and confirmed the generated SQL drops both policies, then the table, in
  the correct order, with nothing left over.
- E2E (Playwright) was explicitly skipped: this is a backend/infra-only
  story (a database migration), with no UI, no page, and no browser flow
  to test. Per `rules/testing.md`, E2E is only required for stories that
  change user-facing behavior — this is the kind of story the rule's own
  carve-out example describes.

Important caveat: none of AC2/AC3/AC4 were verified against a real,
running database. The `--sql` dry-run proves the migration is internally
consistent and generates correct-looking DDL, but cannot catch issues that
only manifest at execution time against a real `auth.users` table and a
real Postgres RLS engine (e.g. FK resolution against actual rows, `auth.uid()`
behavior under a real session). This is a genuine gap, not a fabricated
pass — it should be re-verified against a real Supabase/Postgres instance
before being trusted in production. Also note: `alembic`/`sqlalchemy` were
declared in `pyproject.toml` but were not yet installed in the project's
venv; ran `pip install -e .` to install them before testing (no version
conflicts).

Result: 2/2 new unit tests passing, full suite 11/11 passing. SQL-level ACs
verified via dry-run generation only, not live execution. Verdict: PASS
WITH CAVEATS (see test-results.md for the full environment-limitation
writeup).

## LFC-STORY-003

Tested the `get_current_user` JWT verification dependency (`app/auth.py`)
and the `GET /users/me` endpoint (`app/main.py`) against all five
acceptance criteria.

What was tested and why:

- AC2 (JWT signature/expiry verification, 401 before handler logic): unit
  tests in `tests/unit/test_auth.py` exercise `get_current_user` directly
  with real PyJWT-encoded tokens (valid, expired, tampered-signature,
  malformed, missing claims, non-Bearer scheme, missing header) against the
  real `_decode_token` logic — no real DB needed for this layer, since
  rejection happens before any DB call, which the tests explicitly assert
  (zero DB calls recorded on every rejection path).
- AC3 (`/users/me` returns the row for the verified id, never a
  client-supplied id): feature tests in `tests/feature/test_users_me.py`
  override the `get_current_user` dependency with a fixed verified
  identity and mock the DB cursor's returned row, covering the 200 (shape
  matches the row), and a deliberate-mismatch case where the mocked row's
  id differs from the verified id — confirming the app-level guard in
  `app/main.py` (`if str(user_id) != current_user.id: raise 403`) actually
  fires rather than trusting the row blindly.
- AC4 (new auth user automatically gets a `users` row via first-request
  upsert): unit test asserts `get_current_user`'s upsert path issues
  exactly one `INSERT INTO users (id, email) VALUES (...) ON CONFLICT (id)
  DO NOTHING` with the verified `(sub, email)` as params, followed by a
  commit — this is the "first-request upsert" mechanism the story
  describes. The feature-level 404 test additionally confirms that if the
  row genuinely doesn't exist yet (e.g. upsert raced or hasn't landed),
  `/users/me` fails cleanly with 404 rather than crashing.
- AC5 (no token/PII in logs on failed auth): two tests capture log records
  via `caplog` during a rejection (expired token, tampered signature) and
  assert the raw token string and the user's email never appear in any
  captured log message.
- AC1 (Supabase Auth provider configuration for email/password + Google):
  not code — this is a manual Supabase dashboard configuration step, which
  the story itself documents as a manual prerequisite outside what code/
  tests can verify. No automated test applies.
- E2E (Playwright) was explicitly skipped: this story is backend-only (a
  FastAPI dependency and a JSON endpoint), with no frontend, page, or
  browser-driven flow in this repo yet. Per `rules/testing.md`, E2E is
  only required for stories that change user-facing behavior.

Bug check explicitly requested by the story (async/sync mismatch in DB
usage): re-read `app/db.py` and `app/auth.py` directly. `get_connection()`
is implemented as `@asynccontextmanager async def ... ->
AsyncIterator[AsyncConnection]` using `psycopg.AsyncConnection.connect`,
and both `app/auth.py` and `app/main.py` consume it consistently with
`async with` / `await cursor.execute(...)`. No async/sync mismatch exists —
this concern, carried over from STORY-002's writeup, does not apply to the
code as actually built here.

One residual gap worth flagging (not a code defect, a test-environment
limitation): `app/main.py`'s id-match check compares `str(user_id) !=
current_user.id`, where in a real run `user_id` would come back from
psycopg as a `uuid.UUID` (the `users.id` column is `UUID` per the
STORY-002 migration) rather than the plain string used in this test's
mocked row. The comparison is expected to work correctly (`str(UUID(...))`
normalizes to the same lowercase-hyphenated form Supabase's JWT `sub`
claim uses), but this exact code path — `UUID` object coming back from a
real psycopg cursor — was not exercised here, since no live DB was
available. Should be confirmed against a real Supabase/Postgres instance.

Result: 14/14 new tests passing (10 unit, 4 feature). Full suite: 25/25
passing (11 pre-existing + 14 new). All five acceptance criteria verified
(AC1 by inspection/documentation, AC2–AC5 by test). Verdict: PASS.

## LFC-STORY-004

Tested rate limiting on `/users/me` (slowapi `Limiter`, per-IP via
`get_remote_address`) against all three acceptance criteria, plus the
architectural requirement that `/health` stays unauthenticated and
unlimited.

- AC1 (rate-limited per client): verified via `tests/feature/
  test_rate_limit.py`, reloading `app.main` with a low test-only limit
  (2 requests/60s) injected through `RATE_LIMIT_REQUESTS`/
  `RATE_LIMIT_WINDOW_SECONDS` env vars, then issuing real requests through
  a `TestClient` against the real `Limiter`/`FastAPI` app — no mocking of
  slowapi itself. Requests within the limit return `200`; the request past
  it is rejected.
- AC2 (429, not 500/unhandled): asserted the rejected response's status
  code is exactly `429` and explicitly not `500`, and that the body
  contains an `error`/`detail` key rather than an empty or malformed
  payload.
- AC3 (config-driven, not hardcoded): two unit tests on
  `app.config.Settings` confirm the rate limit fields default to 30/60 and
  are overridable via env vars; one feature test sets
  `RATE_LIMIT_REQUESTS=1` and confirms the *enforced* behavior changes
  (second request now rejected instead of the third), proving the value
  actually flows into the limiter, not just into an unused settings field.
- `/health` unaffected: confirmed 10 rapid unauthenticated requests to
  `/health` never return `429` even while `/users/me`'s limit is set to 2,
  and that no `WWW-Authenticate` header appears — `/health` remains usable
  by PaaS health checks regardless of `/users/me`'s limiter state.

Approach for testability: `app/main.py` builds the `Limiter` and the
`per_ip_rate_limit` string once at import time from `get_settings()`,
with no per-request/per-test override seam. Tests achieve a deterministic
low threshold by setting env vars via `monkeypatch` and
`importlib.reload(app.main)` before constructing a fresh `TestClient`,
avoiding the need to burn through 30 real requests against the production
default.

Bug found and fixed during test-writing (not in application code): the
first draft of the test fixture left `app.main` permanently pointed at the
test's low rate limit after the test finished, because `monkeypatch`'s env
var teardown runs after the fixture's own teardown, and the fixture's
final restorative `importlib.reload` was issued while the low-limit env
vars were technically still set. This caused
`tests/feature/test_users_me.py`'s 403 test to intermittently return `429`
instead, but only when run after `test_rate_limit.py` — a real, order-
dependent test pollution bug, exactly the kind `rules/testing.md` calls out
("tests must be runnable independently and in any order"). Fixed by calling
`monkeypatch.undo()` before the final reload. Re-verified the full 31-test
suite passes in three different run orders (declared, reversed, and
interleaved) with no leakage.

Environment note: no `.env` file existed in this checkout (gitignored, not
committed). Created a local-only `.env` with placeholder values mirroring
`.env.example` so `Settings()` could load; not committed.

Result: 7/7 new tests passing (2 unit, 5 feature). Full suite: 31/31
passing (24 pre-existing + 7 new). All three acceptance criteria verified
by test, plus the `/health` architectural requirement. Verdict: PASS.
