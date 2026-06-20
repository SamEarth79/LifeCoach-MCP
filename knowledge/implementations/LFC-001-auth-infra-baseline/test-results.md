# Test Results: LFC-001-auth-infra-baseline

## LFC-STORY-001

**Verdict: PASS**

### Layers required

- Unit: required (settings loading/validation, DB connectivity check logic).
- Feature: required (`GET /health` endpoint behavior, the story's
  feature-level surface).
- E2E (Playwright): not required. This story has no user-facing UI — it
  ships a backend health-check endpoint with no frontend, browser flow, or
  rendered page. Per `rules/testing.md`, E2E is required only for stories
  that change user-facing behavior; this one is purely internal/infra.

### Unit tests — 6 passed, 0 failed

`tests/unit/test_config.py` (3 tests):
- loads `Settings` from environment variables (Supabase URL/keys,
  `DATABASE_URL`)
- raises `ValidationError` when required environment variables are missing
- `get_settings()` is cached (`lru_cache`) across calls

`tests/unit/test_db.py` (3 tests):
- `check_connectivity()` returns `True` when the query succeeds
- `check_connectivity()` returns `False` when the connection raises
  `psycopg.OperationalError`
- `check_connectivity()` returns `False` when the query itself raises a
  `psycopg.Error`

### Feature tests — 3 passed, 0 failed

`tests/feature/test_health.py` (FastAPI `TestClient`, DB check mocked):
- `GET /health` returns `200` with `{"status": "healthy", "database":
  "reachable"}` when the DB is reachable (AC1)
- `GET /health` returns `503` with `{"status": "unhealthy", "database":
  "unreachable"}` when the DB is unreachable (AC4)
- `GET /health` requires no authentication — no `WWW-Authenticate` header,
  `200` on a plain unauthenticated request (AC1)

### E2E tests — not applicable (see rationale above)

### Totals: 9 passed, 0 failed

### Additional manual verification (not part of the automated suite)

- `pip install -e .` succeeded in a fresh venv with no dependency errors.
- `python -c "from app.main import app"` imported cleanly with `/health`
  registered in `app.routes`, confirming the app instantiates without
  needing a live DB at import/startup time.
- Started the real app with `uvicorn app.main:app` against a `DATABASE_URL`
  pointing at a non-existent database. The server booted successfully
  (`Application startup complete`), and a real HTTP `GET /health` request
  against the running server returned `503` with
  `{"status":"unhealthy","database":"unreachable"}` — confirming AC4 holds
  end-to-end, not just under TestClient mocking. Process was killed after
  verification; no servers left running.

### Notes on test infrastructure

This is a greenfield repo with no prior test setup. Established conventions
for this story:
- Test runner: `pytest` (idiomatic default for FastAPI), with
  `pytest-asyncio` in `auto` mode (configured in
  `pyproject.toml[tool.pytest.ini_options]`) and `httpx`/FastAPI's
  `TestClient` for feature tests.
- Layout: `tests/unit/` and `tests/feature/` parallel directories, mirroring
  the unit/feature split in `rules/testing.md`. No E2E directory created
  since this story doesn't require one.
- `pytest`, `pytest-asyncio`, and `httpx` added as a `dev` dependency group
  in `pyproject.toml`.

## LFC-STORY-002

**Verdict: PASS WITH CAVEATS** — see "Environment limitation" below. No
real Postgres/Supabase instance was available to run the migration against;
the SQL-level acceptance criteria (AC2, AC3, AC4) were verified by
generating and inspecting the actual SQL Alembic would execute
(`alembic upgrade head --sql` / `alembic downgrade <rev>:base --sql`), not
by running it against a live database.

### Layers required

- Unit: required (Alembic's DB-URL-sourcing wiring in `migrations/env.py`
  is non-trivial logic — it pulls from `app.config.get_settings()` rather
  than a hardcoded value — and is mockable without a real DB).
- Feature: there is no HTTP/API surface in this story to drive a
  conventional feature test through; the "feature" is the migration
  itself, verified via dry-run SQL generation (below) rather than a pytest
  feature test.
- E2E (Playwright): **not required**. This is a backend/infrastructure-only
  story (Alembic migration + RLS policy on a database table) with zero
  user-facing UI, no page, no rendered component, and no browser-driven
  flow. Per `rules/testing.md`, E2E is required only for stories that
  change user-facing behavior; a schema migration with no new UI is
  explicitly the kind of story called out as not needing it.

### Environment limitation (read before trusting "PASS")

No Docker daemon was running and no local Postgres/`psql` was available in
this sandbox (`docker ps` failed to connect to the daemon; `psql`/`pg_ctl`
not found). The migration also references `auth.users`, a Supabase-managed
table that doesn't exist in a plain local Postgres without a stub schema.
Spinning up a real Postgres + stub `auth` schema was not possible here.

Given that constraint, testing fell back to static/dry-run verification:
the migration was never executed against a real database, so things only
a live DB could catch — e.g. the FK actually resolving against a real
`auth.users` row, RLS policy behavior under an actual session with
`auth.uid()` set, runtime permission errors — are **not** verified here.
This should be re-run against a real Supabase/Postgres instance (with the
`auth` schema present) before being considered fully verified for
production.

### Unit tests — 2 passed, 0 failed (new)

`tests/unit/test_migrations_env.py`:
- `migrations/env.py` calls `config.set_main_option("sqlalchemy.url", ...)`
  with the exact value of `get_settings().database_url` — confirms AC1
  ("configured to read the DB connection string from the app's environment
  settings, not a separate hardcoded config") by loading the real
  `env.py` module with `alembic.context` mocked out, no real DB connection
  needed.
- Changing `DATABASE_URL` in the environment changes the URL Alembic
  receives — confirms the value isn't cached or hardcoded anywhere along
  the path from settings to Alembic config.

### Dry-run SQL verification (executed for real via Alembic's offline mode, no DB needed)

Ran `alembic upgrade head --sql` against the actual migration file:
- Confirms AC2: generates `CREATE TABLE users` with `id UUID NOT NULL
  PRIMARY KEY`, `email TEXT NOT NULL`, `display_name TEXT` (nullable),
  `created_at`/`updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT
  NULL` — matches the story's column spec exactly.
- Confirms AC3: generates `ALTER TABLE users ENABLE ROW LEVEL SECURITY;`
  followed by `CREATE POLICY users_select_own ... FOR SELECT USING
  (auth.uid() = id)` and `CREATE POLICY users_update_own ... FOR UPDATE
  USING (auth.uid() = id)`.

Ran `alembic downgrade 16b5eb4c9d06:base --sql` against the same migration:
- Confirms AC4: generates `DROP POLICY IF EXISTS users_update_own`, then
  `DROP POLICY IF EXISTS users_select_own`, then `DROP TABLE users`, in
  that order, with no other DDL — i.e. no leftover objects in the
  generated downgrade plan. (RLS itself is a flag on the table, not a
  separate object, so it's removed along with `DROP TABLE`.)

Also ran `alembic history --verbose`: confirms a single linear head
(`16b5eb4c9d06`, `down_revision = None`) — no branching, no chain issues.

### Static checks

- `ast.parse` on the migration file: syntactically valid Python.
- `pip install -e .` in the project's venv: `alembic` and `sqlalchemy`
  (added to `pyproject.toml`) install cleanly with no dependency conflicts.
- Confirmed `sa.dialects.postgresql.UUID` resolves correctly at runtime
  (SQLAlchemy lazily exposes dialect submodules as attributes of the
  top-level package) — a plausible-bug suspicion that did not pan out; the
  generated SQL shows `UUID` rendering correctly.

### E2E tests — not applicable (see rationale above)

### Totals: 2 new unit tests passed, 0 failed. Full suite: 11 passed, 0
failed (9 pre-existing + 2 new). SQL-level ACs (2, 3, 4) verified via
dry-run generation, not live execution — see environment limitation above.

## LFC-STORY-003

**Verdict: PASS**

### Layers required

- Unit: required (`get_current_user`'s JWT verification logic — signature,
  expiry, claim extraction, the upsert call shape — is non-trivial business
  logic and fully mockable at the DB boundary).
- Feature: required (`GET /users/me` end-to-end through its real FastAPI
  handler, with the DB layer mocked, to verify AC3's "verified id, never a
  client-supplied id" behavior and the 403/404 branches).
- E2E (Playwright): **not required**. This story is backend-only — a JWT
  verification dependency and a JSON API endpoint, with no page, no
  rendered component, and no browser-driven user journey in this repo (no
  frontend exists yet). Per `rules/testing.md`, E2E is required only for
  stories that change user-facing behavior (UI flows, pages, forms); this
  one has no such surface.

### Environment limitation

No live Supabase/Postgres instance was available in this sandbox (same
constraint as LFC-STORY-002). `get_connection`/the cursor were mocked at
the `app.auth` / `app.main` module boundary for all new tests, so DB
interaction (the `INSERT ... ON CONFLICT DO NOTHING` upsert, the `SELECT`
in `/users/me`) is verified by asserting the exact query/params passed to
the mocked cursor, not by executing against a real Postgres. Unlike
STORY-002's migration, this is squarely within what mocking can validate
deterministically — the dependency's control flow (token verified ahead of
any DB call, correct params passed to the upsert/select) doesn't require a
real database to prove correct. What is **not** verified here: that the
real `INSERT ... ON CONFLICT (id) DO NOTHING` actually succeeds against a
real Supabase Postgres instance under the project's actual role
permissions and RLS configuration — `app/auth.py`'s own design documents
this as an assumption ("assumes DATABASE_URL role has RLS-bypass
privileges"), not something verified by this test run. This should be
re-checked against a real Supabase project before considering AC4 fully
verified end-to-end.

### Unit tests — 10 passed, 0 failed (new)

`tests/unit/test_auth.py`:
- valid token → `get_current_user` returns a `CurrentUser` with the
  verified `sub`/`email`, and issues exactly one upsert call with
  `(user_id, email)` params against `INSERT INTO users ... ON CONFLICT
  (id) DO NOTHING`, followed by a commit (AC2, AC4)
- expired token → 401, and confirms zero DB calls happened (verification
  fails before reaching DB logic) (AC2)
- malformed (non-JWT) token → 401
- missing `Authorization` header → 401
- tampered signature (wrong secret) → 401
- non-Bearer auth scheme → 401
- token missing `sub`/`email` claims → 401
- failed-auth log output does not contain the raw token value (AC5)
- failed-auth log output does not contain the user's email/PII (AC5)

### Feature tests — 4 passed, 0 failed (new)

`tests/feature/test_users_me.py` (FastAPI `TestClient`, `get_current_user`
dependency overridden, DB cursor mocked):
- `GET /users/me` with a valid verified identity and a mocked matching DB
  row returns 200 with the exact `{"id","email","display_name",
  "created_at","updated_at"}` JSON shape (AC3)
- `GET /users/me` returns 404 when no row exists for the verified id (AC4
  follow-on: a new user with no row yet gets a clean 404, not a 500 or
  leaked DB error)
- `GET /users/me` returns 403 when the row returned by the (mocked) DB
  query has an id that doesn't match the verified id from the dependency —
  confirms the app-level id-match check exists and that the endpoint never
  trusts a client-supplied id (AC3)
- `GET /users/me` with no `Authorization` header returns 401 before
  reaching handler logic (AC2)

### Bug check: async/sync mismatch (none found)

STORY-002's writeup flagged a hypothetical class of bug to watch for here:
`app/db.py`'s `get_connection()` being sync `psycopg` while `app/auth.py`
calls it with `async with`. Re-read both files directly: `app/db.py`
defines `get_connection` as `@asynccontextmanager async def
get_connection() -> AsyncIterator[AsyncConnection]`, using
`psycopg.AsyncConnection.connect(...)` — it is async throughout, matching
how `app/auth.py`'s `_ensure_user_row_exists` and `app/main.py`'s
`get_my_profile` consume it (`async with get_connection()`, `async with
conn.cursor()`, `await cursor.execute(...)`). No async/sync mismatch exists
in the code as built for this story.

### Other observations (not blocking, no bug found)

- `app/main.py`'s `/users/me` handler does `str(user_id) != current_user.id`
  to detect an id mismatch, where `user_id` comes back from psycopg as a
  Python `uuid.UUID` (column is `UUID` type per the STORY-002 migration)
  and `current_user.id` is the JWT `sub` string. `str(uuid.UUID(...))`
  normalizes to the standard lowercase-hyphenated form, and Supabase JWTs'
  `sub` claim is already in that form, so the comparison is correct in
  practice — but it is implicitly relying on both sides normalizing to the
  same string representation. Not exercised against a real psycopg
  connection in this test run (the mocked cursor returns a plain string in
  the row tuple, which side-steps the `UUID`-vs-`str` comparison entirely).
  Flagging as a residual gap from the "no live DB" constraint, not a
  defect — should be confirmed once a real Supabase/Postgres instance is
  available.

### E2E tests — not applicable (see rationale above)

### Totals: 14 new tests passed (10 unit, 4 feature), 0 failed. Full suite:
25 passed, 0 failed (11 pre-existing + 14 new).

## LFC-STORY-004

**Verdict: PASS**

### Layers required

- Unit: required (rate limit settings — default values and env var
  overrides — new business logic in `app/config.py`).
- Feature: required (`/users/me` rate limiting end-to-end through the real
  FastAPI app + slowapi `Limiter`, and `/health` remaining unaffected).
- E2E (Playwright): not required. Backend-only change with no new UI or
  user-facing page; the existing user-facing surface is unchanged.

### Unit tests — 2 new passed, 0 failed

`tests/unit/test_config.py` (2 new tests, 5 total in file, all passing):
- `rate_limit_requests`/`rate_limit_window_seconds` default to 30/60 when
  not set in the environment (AC3)
- both fields are overridable via `RATE_LIMIT_REQUESTS`/
  `RATE_LIMIT_WINDOW_SECONDS` env vars (AC3)

### Feature tests — 5 new passed, 0 failed

`tests/feature/test_rate_limit.py` (new file):
- `GET /users/me` allows requests within a configured limit (AC1)
- the request exceeding the configured limit on `/users/me` is rejected
  (AC1)
- the rejection is exactly `429`, not `500` or an unhandled exception, and
  the response body contains an `error`/`detail` key (AC2)
- lowering `RATE_LIMIT_REQUESTS` to `1` via env var changes enforced
  behavior (second request now rejected), proving the threshold flows from
  `Settings` into the limiter rather than being a hardcoded magic number
  (AC3)
- `GET /health` stays unlimited (10 rapid requests, none `429`) and
  unauthenticated even while `/users/me`'s limit is set very low (hard
  architectural requirement, not itself an AC but explicitly called out as
  must-hold)

Approach: rather than burning through the real default of 30 requests/60s,
these tests set `RATE_LIMIT_REQUESTS`/`RATE_LIMIT_WINDOW_SECONDS` env vars
via `monkeypatch` to a low value (2/60s, or 1/60s for the AC3 test) and
`importlib.reload(app.main)` before constructing a fresh `TestClient`. This
is necessary because `app/main.py` builds the limiter and its
`per_ip_rate_limit` string once at module import time from `get_settings()`
— there's no per-request override hook, so the only way to exercise a
different threshold is to reload the module with different settings
already in the environment.

State leakage caught and fixed during this run: slowapi's in-memory
`Limiter` storage is local to each `Limiter` instance, but `app.main` is a
process-wide singleton module. The first version of the `low_limit_app`
fixture restored the module via `importlib.reload(main_module)` inside a
`monkeypatch`-backed env var context whose teardown (un-setting
`RATE_LIMIT_REQUESTS`/`RATE_LIMIT_WINDOW_SECONDS`) only runs *after*
pytest's fixture teardown finishes — so the restorative reload at the end
of the fixture was still reading the low-limit env vars, leaving
`app.main` permanently pointed at a 2-requests/60s limiter for every test
file that ran afterward in the same process. This surfaced as a real,
order-dependent failure: `tests/feature/test_users_me.py::
test_get_users_me_returns_403_when_row_id_does_not_match_verified_id`
passed in isolation but failed (`429` instead of `403`) whenever it ran
after `test_rate_limit.py`. Fixed by calling `monkeypatch.undo()` before
the final restorative `importlib.reload`, so the module is rebuilt against
the real `.env`-backed settings, not the test's overridden ones. Verified
by running the full suite in three different orderings (declared order,
reversed file order, and an interleaved order) plus running
`test_rate_limit.py` twice followed by `test_users_me.py` in the same
session — all 31 tests pass in every ordering with no leakage.

Environment note: this checkout had no local `.env` file (it's
gitignored, not committed, and apparently wasn't carried over from
whichever environment ran STORY-001–003's tests). Created a local-only
`.env` with placeholder Supabase/DB values — identical in shape to
`.env.example` — so `Settings()` can load at all; this file is not
committed (confirmed via `git status`, which shows no `.env` entry).

### Totals: 7 new tests passed (2 unit, 5 feature), 0 failed. Full suite:
31 passed, 0 failed (24 pre-existing + 7 new).
