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

### Protocol surface: MCP tools, mounted in-process alongside REST

Starting with `updates` (LFC-003), the backend exposes a second protocol
surface beyond REST: MCP (Model Context Protocol) tools, callable by an
LLM-based MCP client rather than a conventional HTTP client. This is the
first feature with no REST endpoints at all — `record_update` and
`list_updates` (defined in `app/mcp_server.py`) exist only as MCP tools.

This is a same-process mount, not a separate service:

```
            ┌───────────────┐
   Client → │   FastAPI     │ → Postgres (Supabase-hosted)
  (REST)    │   backend     │
            └──────┬────────┘
                    │ app.mount("/", mcp_asgi_app)
                    │ (registered after all REST routes)
                    ▼
            ┌───────────────┐
  MCP client│  FastMCP app  │ → same Postgres pool, same auth, same
 (LLM tool  │ (app/mcp_     │    rate limiter as REST
   calls) → │  server.py)   │
            └───────────────┘
```

- **Mounting**: `app/main.py` builds the MCP ASGI app
  (`mcp.streamable_http_app()`) and mounts it via `app.mount("/", ...)`
  strictly after every REST route is already declared, so Starlette's
  registration-order route matching cannot let the mount shadow an existing
  REST route. `app.router.lifespan_context` is then reassigned to the
  mounted app's lifespan context, which is required for the MCP SDK's
  session manager to actually start up — not just a convenience wrapper.
- **Auth is reused, not reimplemented.** MCP tool handlers aren't FastAPI
  routes, so they have no access to `Depends(get_current_user)`. Instead,
  `app/auth.py` exposes `verify_bearer_token(authorization_header: str | None)`
  — the same JWKS/ES256 verification logic as `get_current_user`, callable
  from a raw header string. Each tool handler pulls the real `Authorization`
  header off the live request via the MCP SDK's `Context` object
  (`ctx.request_context.request`), confirmed against the installed SDK's
  source rather than assumed — this repo has previously shipped a real bug
  (see `JWT-VERIFICATION-INCIDENT.md`) from assuming a third-party
  integration's auth mechanism instead of verifying it.
- **Rate limiting is reused, not reimplemented.** `app/rate_limit.py`
  (logic extracted from `app/main.py` during this feature, not rewritten)
  exposes `enforce_mcp_rate_limit`, which calls the same underlying
  `limits`-package limiter REST routes use, keyed by the same per-IP
  resolution (`get_client_ip`). MCP and REST traffic from the same client IP
  share one rate-limit budget.
- **New third-party dependency**: the official MCP Python SDK (`mcp`,
  providing `mcp.server.fastmcp.FastMCP`) — the first dependency in this
  repo beyond FastAPI/Supabase tooling that defines its own protocol-level
  request lifecycle (sessions, its own exception-to-tool-result translation,
  its own transport security middleware) rather than just being a library
  called from within FastAPI's request/response cycle.
- **Known deployment risk, not yet resolved**: the MCP SDK's
  `TransportSecurityMiddleware` defaults `allowed_hosts` to `[]` with
  DNS-rebinding protection enabled, which would reject every MCP request
  behind a real reverse proxy with a 421 until `allowed_hosts` is
  explicitly configured for the deployed hostname. Tracked in
  `knowledge/documentation/LFC-003-updates/technical-doc.md` and in this
  feature's test results — must be addressed before production deployment
  behind a reverse proxy.

### UI-rendering layer: server-rendered HTML over MCP, not just structured tool results

Starting with the home and goal-detail views (LFC-004), some MCP tools
(`get_home_view`, `get_goal_detail_view`, and `delete_goal`'s success path)
return rendered HTML content instead of a plain JSON-like tool result —
this is the first feature where the MCP surface produces actual UI rather
than data for an LLM to reason over.

```
            ┌───────────────┐
  MCP host  │  FastMCP app  │ → app/ui_templates.py renders HTML
 (renders   │ (app/mcp_     │   from a plain dataclass (HomeViewData /
  the HTML  │  server.py)   │   GoalDetailViewData), server-side, no
  in an     └──────┬────────┘   client JS framework
  iframe/        EmbeddedResource(uri="ui://...", mimeType="text/html")
  webview) ←───────┘
```

- **Server-side rendering, no client build step.** `app/ui_templates.py`
  generates complete standalone HTML documents (inline `<style>` and
  `<script>`) as plain Python string templates from typed dataclasses
  (`HomeGoalCard`/`HomeViewData`, `GoalDetailUpdate`/`GoalDetailViewData`).
  There is no separate frontend framework, bundler, or TypeScript helper
  SDK — matching `strategy.md`'s "light UI needs" direction. Every
  user-controlled string (names, titles, descriptions, update content,
  error messages) is passed through `html.escape` before interpolation;
  this is the same XSS-escaping discipline already applied at every other
  user-input boundary in this repo, just applied to a new output context
  (HTML rendered for an embedded view rather than a JSON API response).
- **The `EmbeddedResource` wrapping mechanism.** `app/mcp_server.py`'s
  `_build_embedded_html_resource(uri, html_text)` wraps the rendered HTML
  in `EmbeddedResource(type="resource", resource=TextResourceContents(uri=...,
  mimeType="text/html", text=...))` — types imported directly from the
  installed `mcp` SDK (`mcp.types`), not hand-rolled. This is the standard
  MCP mechanism for a tool to return renderable content (as opposed to a
  plain dict/list result) to a host capable of displaying it; confirmed to
  actually parse/serialize correctly through the installed SDK rather than
  assumed from documentation alone.
- **Interaction model: two `postMessage` intents.** The rendered HTML's
  inline JS sends `window.parent.postMessage(...)` with one of two payload
  shapes: `{type: "tool", payload: {toolName, params}}` (direct tool
  invocation — used for goal-card-click navigation and the delete-confirm
  action) or `{type: "prompt", payload: {prompt}}` (chat-message injection
  — used for "create a new goal," "just want to talk," and "continue this
  conversation"). The split matches `strategy.md`: creation/conversation
  stay conversational, navigation/structured actions are direct tool
  calls.
- **Known architectural risk: the `postMessage` tool-invocation shape is
  unverified against any live MCP-UI host.** No real MCP-UI host was
  available in any implementation sandbox for this feature. Every direct
  tool-invocation interaction this feature ships rests on an assumption
  about the host-side `postMessage` convention that has not been confirmed
  against the actual MCP-UI spec or a real host. If unsupported, every
  such interaction must fall back to the chat-message-injection shape
  instead — a potential rework of this layer's interaction model, not a
  minor fix. Tracked in
  `knowledge/documentation/LFC-004-mcp-ui-home-goal-views/technical-doc.md`.

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
