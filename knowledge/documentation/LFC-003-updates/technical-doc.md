# Technical Deep Dive: Updates (LFC-003)

## What this feature is

A goal-linked record of what an AI coach and a user actually agreed on —
not raw AI output, not a transcript dump, not a one-sided log of suggestions.
Either party can originate the underlying idea in conversation; what gets
stored is the settled outcome, and there is deliberately no field
distinguishing who proposed it first. This is the first feature in the repo
with no REST surface at all — the entire feature is exposed as two MCP
(Model Context Protocol) tools, callable by an MCP client (e.g. Claude)
acting on behalf of a signed-in user during a coaching conversation. There
is no UI; the "client" is the conversational AI itself.

Two tools, both mounted on the existing FastAPI app, both requiring the same
Supabase JWT every REST endpoint already requires:

- `record_update` — store a new update linked to one of the caller's own
  active goals: a required short `content` summary, an optional full
  `transcript`.
- `list_updates` — retrieve a goal's past updates, for the calling LLM to
  re-inject as conversational context.

## Components

| File | Responsibility |
|---|---|
| `app/mcp_server.py` | New module: builds the `FastMCP` instance, defines `record_update` and `list_updates`, and is mounted into the existing FastAPI app. |
| `app/main.py` | Mounts the MCP ASGI app (`mcp.streamable_http_app()`) after every existing REST route, and wires its lifespan into the FastAPI app's own. |
| `app/auth.py` | New `verify_bearer_token` function — the same JWT verification logic as `get_current_user`, but taking a raw header string rather than a FastAPI-injected `HTTPAuthorizationCredentials`, since MCP tool handlers aren't FastAPI route handlers and have no dependency injection. |
| `app/rate_limit.py` | New module (logic extracted from `app/main.py`, not rewritten): `get_client_ip`, `limiter`, `per_ip_rate_limit`, and a new `enforce_mcp_rate_limit` that applies the same per-IP limit to MCP tool calls. |
| `app/schemas.py` | New `UpdateCreate`, `UpdateResponse`, `UpdateListItem` Pydantic models. |
| `migrations/versions/8e5660ff9d7f_create_updates_table.py` | Alembic migration creating the `updates` table, its RLS policies, and a supporting index. |

## The `updates` table

```
updates
  id           uuid        PRIMARY KEY, default gen_random_uuid()
  user_id      uuid        NOT NULL, FK -> auth.users.id ON DELETE CASCADE
  goal_id      uuid        NOT NULL, FK -> goals.id ON DELETE CASCADE
  content      text        NOT NULL  -- short, required summary of the agreed update
  transcript   text        NULL      -- optional full conversation, only when fidelity matters
  source       text        NOT NULL DEFAULT 'coaching_update'
                            CHECK (source IN ('coaching_update', 'checkin'))
  created_at   timestamptz NOT NULL DEFAULT now()
```

No `updated_at`/`deleted_at` — updates are append-only in this feature's
scope; there is no edit/delete capability and no RLS `UPDATE`/`DELETE`
policy at all, the same "structurally impossible to violate" posture
already established for `goals`' soft-delete-only design.

Index: `ix_updates_goal_id_created_at` on `(goal_id, created_at)`, supporting
`list_updates`' query pattern (filter by `goal_id`, order by `created_at`).

### RLS policies

```sql
CREATE POLICY updates_select_own ON updates
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY updates_insert_own ON updates
  FOR INSERT WITH CHECK (
    auth.uid() = user_id
    AND EXISTS (
      SELECT 1 FROM goals g
      WHERE g.id = goal_id
      AND g.user_id = auth.uid()
      AND g.deleted_at IS NULL
    )
  );
```

`updates_insert_own`'s `WITH CHECK` does two things in one clause: it
confirms the inserted `user_id` matches the caller (the standard ownership
check every table in this repo applies), and it confirms `goal_id` actually
refers to a goal owned by that same caller and not soft-deleted. This is the
first RLS policy in the repo that reaches into a second table from inside a
`WITH CHECK` — a direct consequence of `goals` itself only exposing active
rows through its own RLS, so `updates` has to re-derive "is this goal valid
right now" rather than trusting a `goal_id` value alone. Enforcing this at
the database layer (not just in `app/mcp_server.py`) follows this repo's
established defense-in-depth posture, and was specifically chosen because of
a prior PR-review finding on `goals` (LFC-002) that an `UPDATE` policy
without an explicit `WITH CHECK` can silently fail in a way mocked-cursor
unit tests can't catch.

There is no `source` filter on `updates_select_own` — RLS scopes by
ownership only, never by `source`. Filtering by `source` is purely an
application-layer decision (see "Why `list_updates` never filters by
`source`" below).

## The MCP tool server: how it's mounted

`app/mcp_server.py` builds a single module-level `FastMCP("lifecoach")`
instance and registers both tools on it via the `@mcp.tool(...)` decorator.
`app/main.py` then does, after every existing REST route is already
declared:

```python
mcp_asgi_app = mcp.streamable_http_app()
app.mount("/", mcp_asgi_app)
app.router.lifespan_context = mcp_asgi_app.router.lifespan_context
```

Two things matter about this mounting:

1. **Registration order, not configuration, protects existing REST routes.**
   Starlette matches routes in the order they were registered. Because the
   MCP ASGI app is mounted strictly after `/health`, `/users/me`, and all
   four `/goals` routes are already declared, none of those routes can be
   shadowed by the mount — there's no explicit precedence rule to get wrong,
   just an ordering invariant that must be preserved if `app/main.py` is
   ever restructured.
2. **Lifespan wiring is required, not optional.** The MCP SDK's
   streamable-HTTP ASGI app owns its own startup/shutdown lifecycle (it
   manages the session manager that tracks stateful MCP sessions).
   Overwriting `app.router.lifespan_context` with the mounted app's lifespan
   context is what makes FastAPI actually run that startup/shutdown
   alongside its own — skipping this line would mean MCP sessions are never
   properly initialized, and tool calls would fail or behave inconsistently
   depending on timing.

This is a same-process mount, not a separate service: one FastAPI app, one
deployed process, REST and MCP sharing the same Postgres connection pool,
the same settings, and the same auth/rate-limiting logic.

## MCP auth: how `verify_bearer_token` gets the JWT

This is the part of the design explicitly flagged as a risk in
`architecture.md` before implementation — "the exact mechanism by which an
MCP tool handler receives and verifies the caller's JWT is not assumed
here." It was resolved by reading the installed MCP SDK's source directly,
not by guessing at a "standard-sounding" convention. This matters because
this repo has already shipped one real bug from doing exactly that —
see `JWT-VERIFICATION-INCIDENT.md`, where Supabase's actual signing
algorithm (ES256 via JWKS) was assumed to be the more common HS256
shared-secret scheme, and the assumption passed every self-consistency test
while rejecting 100% of real tokens. The lesson carried into this feature
was explicit: do not assume a third-party integration's wire mechanism;
confirm it against the real SDK or documentation before relying on it.

In practice, both tools follow the same pattern:

```python
async def record_update(goal_id: str, content: str, ctx: Context, transcript: str | None = None) -> dict:
    request = ctx.request_context.request
    authorization_header = request.headers.get("authorization") if request is not None else None
    current_user = await verify_bearer_token(authorization_header)
    await enforce_mcp_rate_limit(request, current_user.id)
    ...
```

`Context` is the MCP SDK's own object, injected into any tool handler that
declares a `ctx: Context` parameter. `ctx.request_context.request` exposes
the real underlying Starlette `Request` for the current tool call —
confirmed against the SDK's source
(`mcp/server/lowlevel/server.py`'s `call_tool`, and the streamable-HTTP
transport's request handling) during implementation, and independently
re-confirmed by `qa` rather than taken on the backend agent's word alone
(see `knowledge/implementations/LFC-003-updates/test-results.md`,
LFC-STORY-002). From that real `Request`, the raw `Authorization` header is
read exactly the way an MCP client is expected to authenticate any request
to this server — the same header REST clients already send.

`app/auth.py`'s `verify_bearer_token(authorization_header: str | None)` is a
new function, not a refactor of the existing `get_current_user`. It
duplicates `get_current_user`'s JWT-verification body (scheme check, JWKS
lookup, ES256 decode, `sub`/`email` claim check, user-row upsert) because
`get_current_user` is a FastAPI dependency that receives its credentials via
`Depends(HTTPBearer())`, which has no meaning outside a FastAPI route — MCP
tool handlers aren't FastAPI routes and have no dependency-injection
machinery to invoke. `verify_bearer_token` takes the raw header string
directly so it works from either call site. This was a deliberate
duplication, not an oversight: `git diff` confirms `get_current_user`'s body
is byte-for-byte unchanged by this feature, so there is zero regression risk
to any existing REST endpoint from this addition.

Once a JWT is rejected (missing, malformed, expired, bad signature), the
MCP Python SDK itself catches the raised `HTTPException` inside its own
`call_tool` exception handling and converts it into a tool-level
`isError: true` response rather than crashing the transport or leaking a raw
500 — confirmed by reading the SDK source directly (not assumed), per the
same "verify, don't guess" standard applied to the auth mechanism itself.

Rate limiting follows the same "can't use FastAPI machinery" logic:
`enforce_mcp_rate_limit` (`app/rate_limit.py`) calls the underlying
`limits`-package limiter (`limiter.limiter.hit(...)`) directly, rather than
through `@limiter.limit(...)` or the `enforce_rate_limit` FastAPI
dependency used by REST routes — both of those rely on Starlette's
route-matching/dependency-injection machinery to locate the right limit and
attach response state, neither of which exists for an MCP tool call. The
underlying rate-limit item and IP-resolution logic (`get_client_ip`,
respecting `X-Forwarded-For` with `trusted_proxy_hops`) are the exact same
ones REST routes use — MCP and REST share one rate-limit budget per client
IP, not two independent ones.

## `content` / `transcript` / `source`: why each exists

- **`content` is required and meant to stay short.** It's validated
  (`UpdateCreate`, `app/schemas.py`) as 1–4000 characters, non-blank after
  stripping. This directly addresses a stated risk: if every update stored
  and re-returned a full transcript, repeatedly re-injecting that history as
  conversational context would make context windows "huge, noisy, and fill
  up" over a long coaching relationship. Keeping `content` short-by-
  construction is the load-bearing half of the fix.
- **`transcript` is optional and never returned by `list_updates`.** It's
  validated up to 20000 characters when present, but the `list_updates`
  SQL (`SELECT content, source, created_at FROM updates ...`) never names
  the `transcript` column at all — it isn't filtered out of a response
  after being fetched, it's never fetched into application memory in the
  first place. This is the other load-bearing half: if a future change
  makes `list_updates` include `transcript` "for completeness," the
  original context-bloat problem returns immediately. Any change to
  `list_updates`' `SELECT` clause should be treated as touching this
  contract, not as a harmless addition.
- **`source` exists now, for a future feature that doesn't exist yet.**
  The column, its default (`coaching_update`), and its `CHECK` constraint
  (`coaching_update` or `checkin`) are all added in this feature's
  migration — but no tool in this feature ever sets or accepts `checkin`.
  `record_update`'s INSERT never supplies `source` at all (the column's
  `DEFAULT` always applies), and there is no parameter on either tool that
  could produce a `checkin` row. This is intentional schema-readiness, not
  scope creep: a later check-ins feature (a user recording something on
  their own, without an AI↔user exchange) is explicit future product
  direction per `strategy.md`, and adding the column now avoids a second
  migration to retrofit it onto existing rows later. `list_updates`
  deliberately does not filter by `source` — a check-in is still relevant
  coaching context, so once check-ins exist, they show up in the same
  context-reinjection stream as coaching updates, indistinguishable except
  by the `source` field itself.

## Two unresolved risks, carried forward explicitly (not silently)

Both are recorded in
`knowledge/implementations/LFC-003-updates/test-results.md`'s "Feature
Summary" section as **PASS WITH CAVEATS**, not silently passed over:

1. **RLS policies have never been exercised against a live database.** No
   Docker daemon or local Postgres was available in the implementation
   environment for any of this feature's three stories. `updates_select_own`
   and `updates_insert_own` — including the `EXISTS` subquery against
   `goals` that the insert policy relies on — were verified only via
   Alembic's `--sql` dry-run output and application-level mocked-cursor
   tests, never against a real `auth.uid()` session. Before this feature is
   trusted in production: seed two users' goals and updates (including a
   `checkin`-source row inserted directly, since nothing in this feature can
   produce one) against a real Supabase/Postgres instance, and confirm
   `list_updates` for user A's goal never returns user B's rows, and that
   `record_update` is rejected for a `goal_id` not owned by the caller or
   already soft-deleted.
2. **MCP's `TransportSecurityMiddleware.allowed_hosts` defaults to `[]` with
   DNS-rebinding protection enabled.** Confirmed by reading
   `mcp/server/transport_security.py` directly: with an empty allow-list, the
   middleware rejects any request whose `Host` header isn't in that list
   with a `421`. In a real deployment behind a reverse proxy with any
   hostname other than `localhost`/`127.0.0.1`, every `/` (MCP) request —
   both tools — would be rejected outright. This is not a defect introduced
   by this feature's code; it's the SDK's secure-by-default posture, and no
   acceptance criterion in this feature required production deployment
   configuration. It must be configured (an explicit `allowed_hosts` list
   matching the deployed hostname) before this app is deployed behind a real
   reverse proxy — tracked here so it isn't rediscovered the hard way, the
   same way the HS256-vs-ES256 assumption was previously discovered the hard
   way in `JWT-VERIFICATION-INCIDENT.md`.

## Extending this safely

A future check-ins feature, per `strategy.md`, is expected to write into
this same `updates` table rather than getting its own migration:

1. **Writing a check-in**: a new tool (e.g. `record_checkin`) would insert
   into `updates` with `source = 'checkin'` explicitly, through the same
   `get_rls_connection(current_user.id)` pattern `record_update` already
   uses. The `source` CHECK constraint already permits this value — no
   migration is needed to add it, only a new tool/handler that sets it.
   `record_update` itself should not be the thing that gains a `source`
   parameter; keep the "agreed coaching outcome" tool and the "user records
   their own check-in" tool as separate handlers with separate MCP
   descriptions, since the two have different authorship semantics (this
   feature deliberately has no field distinguishing who originated a
   coaching update, but a check-in is unambiguously user-originated).
2. **Reading check-ins back**: `list_updates` already returns `checkin`
   rows alongside `coaching_update` rows with no filtering, by design — a
   future feature does not need to modify `list_updates` to surface
   check-ins as coaching context. If a future feature needs a check-ins-
   only view (e.g. a progress dashboard), add a new query/tool with an
   explicit `source = 'checkin'` filter rather than adding a filter
   parameter to `list_updates` that would change its existing contract.
3. **`transcript` stays off the read path.** Any new tool reading from
   `updates` for re-injection as LLM context should follow `list_updates`'
   precedent and never select `transcript` — the context-bloat risk this
   feature designed around applies equally to check-ins.
4. **RLS**: a new write path into `updates` needs no new RLS policy —
   `updates_insert_own` already covers any `INSERT` regardless of which
   tool issues it, as long as it goes through `get_rls_connection`. Do not
   add a second, looser insert policy for check-ins; reuse the existing one.
5. **Foreign-key and ownership pattern**: any further table referencing
   `updates.id` or `goals.id` should follow the same pattern `updates`
   itself follows from `goals` — see
   `knowledge/documentation/LFC-002-goals/technical-doc.md`'s "Extending
   this safely" section for the general template.
