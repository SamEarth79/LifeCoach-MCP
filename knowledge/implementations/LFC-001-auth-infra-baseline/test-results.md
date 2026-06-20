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
