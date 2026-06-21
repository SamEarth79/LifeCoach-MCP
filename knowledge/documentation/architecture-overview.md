# Architecture Overview

## System summary

LifeCoach's backend is a FastAPI application backed by Supabase, which
provides both the identity provider (Supabase Auth) and the Postgres
database. There is no backend-managed user store, password storage, or
session mechanism of its own — Supabase owns identity end-to-end, and the
backend's only job is to verify the tokens Supabase issues and enforce
per-user data access on top of Postgres.

```
            ┌───────────────┐        email/password,
   Client → │ Supabase Auth │ ←────  Google OAuth sign-in
            └──────┬────────┘
                    │ issues JWT (ES256, verified via JWKS)
                    ▼
            ┌───────────────┐
   Client → │   FastAPI     │ → Postgres (Supabase-hosted)
            │   backend     │      - RLS-enforced per-user access
            └───────────────┘      - schema via Alembic migrations
```

## Components

### FastAPI backend (`app/`)

- `app/config.py` — environment-driven settings (`Settings`, pydantic-settings).
  All configuration (Supabase URL/keys, DB URL, rate-limit thresholds) comes
  from environment variables / `.env`; nothing is hardcoded. Settings are
  cached process-wide via `lru_cache`.
- `app/auth.py` — `get_current_user`, the single FastAPI dependency every
  authenticated endpoint uses. Verifies the bearer JWT against Supabase's
  JWKS endpoint and exposes the verified user id/email to the handler. This
  is the only place in the codebase that establishes "who is making this
  request."
- `app/db.py` — async Postgres access via `psycopg`. Exposes
  `get_connection()` (raw connection, used only for infra-level operations
  like the health check) and `get_rls_connection(user_id)` (a connection
  switched to the `authenticated` Postgres role with the user's id set as
  a session claim, so Row Level Security policies actually apply). All
  per-user data access goes through `get_rls_connection`, never the raw
  connection.
- `app/main.py` — the FastAPI app instance, route definitions, and the
  rate limiter.
- `app/schemas.py` — Pydantic request/response models for body-validated
  endpoints (first introduced for the `goals` resource). Request validation
  happens once, at this boundary; handlers trust validated input rather than
  re-checking it deeper in the call stack.

### Identity: Supabase Auth

Supabase Auth handles sign-up and sign-in (email/password and Google
OAuth) entirely outside the FastAPI backend. The backend never sees a
password and never issues its own tokens — it only receives the JWT
Supabase already issued, on each request, and verifies it. Verification is
local (no per-request network call to Supabase) once Supabase's public
signing key is fetched and cached from its JWKS endpoint
(`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`), using ES256.

### Data: Postgres (Supabase-hosted) with Row Level Security

Every table that stores user-owned data is expected to:

- Have its primary key (or a `user_id` column) tied to `auth.users.id`.
- Have Row Level Security enabled, with policies scoped to
  `auth.uid() = <owning column>`.
- Only ever be queried through `get_rls_connection`, which runs the query
  as the `authenticated` Postgres role with the verified user id set as a
  session-local claim — the same mechanism Supabase's own PostgREST layer
  uses, so `auth.uid()` resolves correctly inside policies.

The app-level connection used for infrastructure tasks (migrations, health
checks) connects as `postgres`, which bypasses RLS by design — this role is
deliberately never used for per-user data queries.

This repo additionally layers an explicit app-level ownership check after
RLS-enforced queries (e.g. `GET /users/me` re-checks the fetched row's id
against the verified JWT id before returning it). RLS and the app-level
check are intentionally redundant: RLS guards against bugs in application
code, the app-level check guards against RLS misconfiguration — the
combination is "defense in depth" for an app storing personal
goal/coaching data.

### Schema management: Alembic

All schema changes go through versioned Alembic migrations
(`migrations/versions/`), starting from the very first table. `migrations/env.py`
sources its database URL from `app.config.get_settings()` rather than a
separate hardcoded config, so migrations always run against whichever
database the app itself is configured for. There is no path for applying
schema changes outside of Alembic.

### Operational concerns

- **Health checks**: `GET /health` is unauthenticated and unthrottled,
  reporting app/database liveness for the hosting platform's deploy and
  restart checks.
- **Rate limiting**: per-IP rate limiting (via `slowapi`) is applied to
  authenticated, auth-adjacent endpoints (currently `GET /users/me`), with
  thresholds driven by settings rather than hardcoded. `/health` is
  explicitly exempt, since the hosting platform must always be able to
  reach it.
- **Secrets**: Supabase URL/keys and the database connection string are
  read only from environment variables; `.env` is gitignored, and
  `.env.example` documents the required variables with placeholder values.

### Soft delete as an RLS-enforced pattern

The `goals` table (added in LFC-002) is the first user-owned table beyond
`users`, and establishes a second reusable pattern on top of the base RLS
template: soft delete enforced inside the RLS policies themselves
(`deleted_at IS NULL` baked into the `SELECT`/`UPDATE` `USING` clauses)
rather than relied upon as a query-level filter, with no `DELETE` policy
created at all — making hard-delete structurally impossible for any code
path that goes through `get_rls_connection`. Any future user-owned table
that needs soft delete (e.g. a later suggestions/check-ins feature) should
follow this same approach rather than re-deriving it.

## What's deliberately not built yet

Per `knowledge/strategy.md`: no notifications/reminders, no analytics, no
admin dashboard, no monitoring/alerting stack, and no frontend at all —
this feature is backend/infra only. The `users` table and its RLS pattern
exist specifically to be the template every future user-owned table
(goals, suggestions, check-ins) repeats.
