# Architecture: Auth & Infra Baseline

## Approach

Stand up the first version of the FastAPI backend with Supabase as the
identity and data provider. Supabase Auth handles sign-in (email/password
and Google OAuth) entirely on its side; FastAPI never sees a password — it
only receives the Supabase-issued JWT on each request, verifies its
signature and expiry against Supabase's public key, and extracts the user
id from the verified claims. That verified id is the only source of "who is
making this request" anywhere in the app — no endpoint accepts a
client-supplied user id as ground truth.

A `users` table mirrors each Supabase Auth user with app-specific profile
fields, with a Postgres RLS policy that restricts every row to its owning
`auth.uid()`. This table and its policy exist mainly to establish the
pattern (FastAPI dependency for "current authenticated user" + RLS policy
shape) that every future table (goals, suggestions, check-ins) will repeat.
Alembic is wired up from the start so every later schema change goes
through versioned migrations rather than ad hoc SQL.

A health check endpoint (`GET /health`) is added so the PaaS host can use it
for deploy/restart liveness checks, per `strategy.md`.

## Components touched

- **Frontend**: none — this feature is backend/infra only. No UI work in
  this story set.
- **Backend**: new FastAPI app skeleton; JWT-verification dependency;
  `/health` route; `/users/me` route (read own profile) to exercise the
  auth dependency end-to-end; rate limiting middleware on auth-adjacent
  endpoints.
- **Infrastructure**: Alembic initialized with first migration (`users`
  table + RLS policy); `.env.example` with placeholder Supabase
  keys/connection string; environment variable wiring for the FastAPI app
  and the chosen PaaS host.

## Data flow

1. User signs in via Supabase Auth (email/password or Google OAuth),
   handled entirely by Supabase — FastAPI is not involved in this step.
2. Client receives a Supabase JWT and sends it as a `Bearer` token on
   subsequent requests to the FastAPI backend.
3. FastAPI's auth dependency verifies the JWT's signature (against
   Supabase's JWKS/secret) and expiry, then extracts the user id from the
   `sub` claim.
4. The verified user id is injected into the request handler; the handler
   never reads a user id from the request body/query/path for
   authorization purposes.
5. Database queries run with RLS active, scoping rows to the verified user
   id as a second enforcement layer beyond the app-level check.
6. `GET /health` bypasses the auth dependency entirely (no user context
   needed) and returns a simple liveness response for the PaaS.

## Data model changes

- New table `users`:
  - `id` (uuid, primary key, equals Supabase `auth.users.id`)
  - `email` (text, not null) — denormalized copy from Supabase Auth for
    convenience in app queries
  - `display_name` (text, nullable)
  - `created_at` (timestamptz, not null, default now())
  - `updated_at` (timestamptz, not null, default now())
- RLS policy on `users`: a row is selectable/updatable only when
  `auth.uid() = id`.
- Alembic migration environment initialized (`alembic init`, `env.py`
  wired to the app's settings/connection string) with this table as the
  first versioned migration.

## Key decisions

- **Decision**: Verify Supabase JWTs directly in FastAPI via a dependency
  (e.g. `Depends(get_current_user)`) rather than proxying auth checks
  through a Supabase server-side call on every request.
  **Rationale**: JWT verification is local (no network round-trip per
  request) once Supabase's signing key is fetched/cached, which is faster
  and avoids making Supabase a single point of latency for every API call.
- **Decision**: Enforce both RLS (database layer) and an explicit
  app-level ownership check in the handler, rather than relying on RLS
  alone.
  **Rationale**: Matches `strategy.md`'s "defense in depth" requirement —
  RLS protects against bugs in app code, app-level checks protect against
  RLS misconfiguration; the redundancy is intentional for an app storing
  personal goal/coaching data.
- **Decision**: Add a `/users/me` endpoint in this baseline feature even
  though "users" isn't one of the explicit v1 product features.
  **Rationale**: There needs to be at least one real authenticated
  endpoint to prove the JWT-verification dependency and RLS policy work
  end-to-end; without it, this feature would ship unverifiable.
