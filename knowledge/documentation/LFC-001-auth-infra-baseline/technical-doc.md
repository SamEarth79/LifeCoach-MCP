# Technical Deep Dive: Auth & Infra Baseline (LFC-001)

## What this feature is

This is the first backend feature in the repo. It stands up the FastAPI
application skeleton, wires it to Supabase for identity and Postgres for
data, and establishes the patterns every later feature (goals, suggestions,
check-ins) will reuse:

- A FastAPI dependency that verifies a Supabase-issued JWT on every
  authenticated request and exposes the verified user id to the handler.
- A `users` table with Row Level Security (RLS), mirroring each Supabase
  Auth user, as the first instance of the "RLS-protected, per-user table"
  pattern.
- Alembic wired up from the start so all schema changes are versioned
  migrations, not ad hoc SQL.
- A `GET /health` endpoint for the PaaS host's liveness checks.
- Per-IP rate limiting on the one real authenticated endpoint
  (`GET /users/me`).

Frontend is explicitly out of scope for this feature — there is no UI yet.

## Components

| File | Responsibility |
|---|---|
| `app/config.py` | `Settings` (pydantic-settings): reads `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL`, and the rate-limit fields from the environment/`.env`. No hardcoded secrets. Cached via `lru_cache`. |
| `app/db.py` | `get_connection()` (raw async Postgres connection), `get_rls_connection(user_id)` (connection scoped to one verified user with RLS enforced), `check_connectivity()` (used by `/health`). |
| `app/auth.py` | `get_current_user` FastAPI dependency: verifies the bearer JWT, extracts the verified identity, and upserts a `users` row for that identity on first contact. |
| `app/main.py` | FastAPI app instance, rate limiter setup, `GET /health`, `GET /users/me`. |
| `migrations/versions/16b5eb4c9d06_create_users_table.py` | First Alembic migration: creates `users` and its RLS policies. |

## JWT verification: how it actually works, and why

### The mechanism (ES256 via JWKS)

`get_current_user` (`app/auth.py`) is a FastAPI dependency that:

1. Extracts the bearer token from the `Authorization` header (via
   `HTTPBearer(auto_error=False)`, so a missing/malformed header is handled
   explicitly rather than raising FastAPI's default error).
2. Resolves the token's signing key from Supabase's public JWKS endpoint,
   `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, using PyJWT's
   `PyJWKClient`. The `PyJWKClient` instance is cached per JWKS URL
   (`lru_cache` on `_get_jwks_client`) so the keyset isn't re-fetched on
   every request.
3. Verifies the token's signature and expiry with
   `jwt.decode(token, signing_key.key, algorithms=["ES256"], audience="authenticated")`.
4. Extracts `sub` (the verified user id) and `email` from the decoded
   claims. Missing either claim, an expired token, an invalid signature, or
   a malformed token all result in a `401` with `WWW-Authenticate: Bearer`
   — raised before any database call.
5. On success, upserts a `users` row for `(sub, email)`
   (`INSERT ... ON CONFLICT (id) DO NOTHING`) so a newly-signed-up Supabase
   Auth user automatically gets an app-side profile row on their first
   authenticated request, with no separate "create profile" step.
6. Returns a `CurrentUser(id=sub, email=email)` — this verified id is the
   only identity any handler in this app trusts. No endpoint accepts a
   client-supplied user id for authorization.

This is entirely local verification once the JWKS key is cached — there is
no network round-trip to Supabase per request, only on first contact (or
after the cached client expires/is evicted).

### Why ES256/JWKS, not a shared HS256 secret

This matters enough to call out explicitly: an earlier version of this
implementation was built against the assumption that Supabase signs JWTs
with a static, project-specific HS256 secret. That assumption was wrong —
Supabase's current default is asymmetric ES256 signing, verified via the
public JWKS endpoint, and every token issued by a real Supabase project was
rejected with a 401 under the old implementation, despite all
self-consistency tests passing (tests had signed and verified tokens using
the same wrong assumption). The full writeup is in
`JWT-VERIFICATION-INCIDENT.md` at the repo root.

The fix removed `SUPABASE_JWT_SECRET` entirely (it's not needed for
JWKS-based verification) and replaced the shared-secret decode with the
`PyJWKClient`/ES256 flow described above. **The key lesson for anyone
extending auth in this codebase**: never assume an external identity
provider's signing scheme from memory or "what's typically standard" —
verify it against current documentation or, ideally, a real token from a
real instance of the provider before writing verification code. A
self-consistency test (sign with assumption X, verify with assumption X)
proves nothing about whether X matches the provider's actual behavior.

## The `users` table and RLS pattern

### Schema

```
users
  id           uuid        PRIMARY KEY, FK -> auth.users.id ON DELETE CASCADE
  email        text        NOT NULL
  display_name text        NULL
  created_at   timestamptz NOT NULL DEFAULT now()
  updated_at   timestamptz NOT NULL DEFAULT now()
```

Created via Alembic migration `16b5eb4c9d06_create_users_table.py`. The
`id` column is a foreign key into Supabase's own `auth.users.id` — this
table only ever holds one row per real Supabase Auth user, never an
independently-created id.

### RLS policies

Three policies, all scoped to `auth.uid() = id`:

- `users_select_own` — `FOR SELECT USING (auth.uid() = id)`
- `users_update_own` — `FOR UPDATE USING (auth.uid() = id)`
- `users_insert_own` — `FOR INSERT WITH CHECK (auth.uid() = id)`

RLS is enabled at the table level (`ALTER TABLE users ENABLE ROW LEVEL
SECURITY`), so without a matching policy no role other than a
RLS-bypassing one (e.g. `postgres`) can touch any row.

### How the app actually gets `auth.uid()` to resolve

`DATABASE_URL` connects to Postgres as the `postgres` role, which has
`BYPASSRLS` — necessary for Alembic migrations to run unrestricted, but it
means a connection from `get_connection()` directly would silently bypass
RLS rather than test it.

`get_rls_connection(user_id)` (`app/db.py`) is the pattern every
RLS-protected query in this app must go through instead: it opens a normal
connection, then within that session runs:

```sql
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claim.sub', %s, true);
```

This switches the session to the same `authenticated` role Supabase's own
PostgREST layer uses, and sets the same session-local claim
(`request.jwt.claim.sub`) that Supabase's `auth.uid()` helper function
reads from. The net effect: queries issued through `get_rls_connection`
are subject to the real RLS policies, scoped to the verified user id, not
the elevated `postgres` role — this is what makes RLS an actual enforcement
layer rather than a no-op the app connection bypasses.

### Defense in depth: RLS + app-level check

`GET /users/me` (`app/main.py`) queries through `get_rls_connection`
(database-layer enforcement), and *also* explicitly checks
`str(row_id) != current_user.id` after fetching the row, raising `403` if
they don't match. This redundancy is intentional, not leftover caution: RLS
protects against bugs in application code; the app-level check protects
against RLS being misconfigured or accidentally bypassed. Per
`knowledge/strategy.md`, this app stores personal coaching/goal data, so
both layers are kept rather than relying on either alone.

## `GET /health`

Returns liveness status without authentication, for the PaaS host's
deploy/restart checks (see API reference for the exact response shape).
It calls `check_connectivity()` (`app/db.py`), which opens a real DB
connection and runs `SELECT 1`; any `psycopg.Error` (connection-level or
query-level) is caught and turned into a `503` response rather than
propagating as an unhandled exception. It is intentionally excluded from
rate limiting and from the auth dependency, since the PaaS needs to be able
to call it freely and without credentials.

## Rate limiting

`GET /users/me` is rate-limited per client IP using `slowapi`'s `Limiter`
with `get_remote_address` as the key function. The limit
(`{rate_limit_requests}/{rate_limit_window_seconds}second`) is built once
at import time in `app/main.py` from `Settings` (`RATE_LIMIT_REQUESTS`,
`RATE_LIMIT_WINDOW_SECONDS`, defaulting to 30/60), not hardcoded. Exceeding
the limit returns `429` (via slowapi's built-in
`_rate_limit_exceeded_handler`), never a `500` or unhandled exception.
`GET /health` is deliberately not behind this limiter or any future one —
the PaaS must always be able to reach it.

Because the limiter and its limit string are built once at module import
time, changing the rate limit at runtime requires restarting the process
(or, in tests, reloading the module after setting the environment
variables) — there is no per-request override hook.

## Extending this safely: adding the next RLS-protected table

Every future user-owned table (goals, suggestions, check-ins, ...) should
follow exactly the pattern this feature establishes:

1. **Migration**: add a new Alembic migration (`alembic revision`), never
   hand-written SQL applied outside of Alembic. Give the new table a
   foreign key to `users.id` (not directly to `auth.users.id`) so it
   inherits the same identity the `users` table already mirrors.
2. **RLS**: enable RLS on the new table and add `SELECT`/`INSERT`/`UPDATE`
   (and `DELETE` if applicable) policies scoped to the owning user — e.g.
   `USING (auth.uid() = user_id)` for a table with a `user_id` column, or
   `USING (auth.uid() = id)` if the table's primary key is itself the user
   id (as `users` does).
3. **Queries**: always query the new table through `get_rls_connection`,
   never through the raw `get_connection()` (which runs as the
   RLS-bypassing `postgres` role).
4. **App-level check**: keep the defense-in-depth pattern — after fetching
   a row by id, explicitly verify it belongs to `current_user.id` before
   returning it, the same way `GET /users/me` does.
5. **Auth**: gate the new endpoint with `Depends(get_current_user)`; do not
   write a new JWT-verification path. There is exactly one verified
   identity source in this app.
6. **Rate limiting**: if the new endpoint is auth-adjacent or otherwise
   warrants it, reuse `limiter.limit(per_ip_rate_limit)` (or define a
   separate settings-driven limit if it needs a different threshold) —
   don't hardcode a new magic number.
7. **External-contract caution**: if the new feature talks to another
   third-party system's actual wire format (a webhook signature scheme, a
   different OAuth provider, etc.), do not assume its protocol from memory.
   Verify against current documentation or a live instance before writing
   verification code — this is the exact mistake `JWT-VERIFICATION-INCIDENT.md`
   documents for this feature's own JWT handling.

## Known gaps / unverified assumptions carried into this PR

Per `knowledge/implementations/LFC-001-auth-infra-baseline/test-results.md`:

- The `create_users_table` migration (RLS policies, `auth.users` FK) was
  verified via Alembic's `--sql` dry-run output, not by executing against a
  live Postgres/Supabase instance, due to no local Postgres/Docker being
  available during implementation. This should be re-verified against a
  real Supabase project before being fully trusted.
- The JWT verification scheme (ES256/JWKS) *was* subsequently verified
  against a real Supabase project and a real signed-in user, after the
  HS256 assumption was found to be wrong (see incident doc above).
