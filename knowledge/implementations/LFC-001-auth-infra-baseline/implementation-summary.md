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
