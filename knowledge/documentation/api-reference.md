# API Reference

Base path: none configured yet (routes are mounted at the app root).

## Authentication

Authenticated endpoints require a Supabase-issued JWT, sent as a bearer
token:

```
Authorization: Bearer <supabase-jwt>
```

Tokens are verified locally against Supabase's public JWKS endpoint
(ES256). A missing, malformed, expired, or otherwise invalid token is
rejected with `401` before any handler logic runs, with a
`WWW-Authenticate: Bearer` header on the response.

---

## `GET /health`

Liveness check for the hosting platform's deploy/restart checks.

- **Auth required**: no.
- **Rate limited**: no.

### Response — `200 OK` (database reachable)

```json
{
  "status": "healthy",
  "database": "reachable"
}
```

### Response — `503 Service Unavailable` (database unreachable)

```json
{
  "status": "unhealthy",
  "database": "unreachable"
}
```

No other error cases — this endpoint never raises an unhandled exception;
any database error is caught and reported as `503`.

---

## `GET /users/me`

Returns the authenticated user's own profile row.

- **Auth required**: yes (`Authorization: Bearer <jwt>`).
- **Rate limited**: yes, per client IP. Default 30 requests / 60 seconds,
  configurable via `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS`.

### Request

No request body or parameters. The user is identified entirely from the
verified JWT — there is no way to request another user's profile.

### Response — `200 OK`

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "email": "user@example.com",
  "display_name": null,
  "created_at": "2026-06-20T11:31:19.600000+00:00",
  "updated_at": "2026-06-20T11:31:19.600000+00:00"
}
```

`display_name` is nullable. Timestamps are ISO 8601 with timezone.

### Error cases

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing, malformed, expired, or invalid-signature JWT; rejected before any handler/database logic runs. |
| `403 Forbidden` | The user row fetched does not match the verified id from the JWT (defense-in-depth check; should not occur under correct RLS configuration). |
| `404 Not Found` | No `users` row exists yet for the verified id (should be rare in practice, since a row is upserted on first authenticated request via `get_current_user`). |
| `429 Too Many Requests` | Per-IP rate limit exceeded. |

---

## `POST /goals`

Creates a goal owned by the authenticated requester.

- **Auth required**: yes (`Authorization: Bearer <jwt>`).
- **Rate limited**: yes, per client IP, same configured threshold as
  `GET /users/me`.

### Request

```json
{
  "title": "Run a 10K",
  "description": "Optional details about the goal"
}
```

- `title` — required, non-empty after stripping whitespace. A missing,
  empty, or whitespace-only `title` is rejected.
- `description` — optional, nullable.
- Any other field in the body (e.g. a client-supplied `user_id`) is ignored;
  the goal's owner is always the verified JWT subject, never a value from
  the request body.

### Response — `201 Created`

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "title": "Run a 10K",
  "description": "Optional details about the goal",
  "created_at": "2026-06-20T11:31:19.600000+00:00",
  "updated_at": "2026-06-20T11:31:19.600000+00:00"
}
```

### Error cases

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing, malformed, expired, or invalid-signature JWT; rejected before any handler/database logic runs. |
| `422 Unprocessable Entity` | Missing, empty, or whitespace-only `title`. No database write occurs. |
| `429 Too Many Requests` | Per-IP rate limit exceeded. |

---

## `GET /goals`

Lists the authenticated requester's own active (non-soft-deleted) goals,
most recently created first.

- **Auth required**: yes (`Authorization: Bearer <jwt>`).
- **Rate limited**: yes, per client IP, same configured threshold as
  `GET /users/me`.

### Request

No request body or parameters. No pagination, sorting, or filtering options
exist yet — the response is always the requester's full set of active
goals, ordered by `created_at` descending.

### Response — `200 OK`

```json
[
  {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "title": "Run a 10K",
    "description": null,
    "created_at": "2026-06-20T11:31:19.600000+00:00",
    "updated_at": "2026-06-20T11:31:19.600000+00:00"
  }
]
```

An empty array (`[]`) is returned, not an error, when the requester has no
active goals. Soft-deleted goals and other users' goals never appear in this
list.

### Error cases

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing, malformed, expired, or invalid-signature JWT; rejected before any handler/database logic runs. |
| `429 Too Many Requests` | Per-IP rate limit exceeded. |

---

## `PATCH /goals/{goal_id}`

Partially updates a goal's `title` and/or `description`. Fields omitted
from the request body are left unchanged; only fields actually present in
the body are updated.

- **Auth required**: yes (`Authorization: Bearer <jwt>`).
- **Rate limited**: yes, per client IP, same configured threshold as
  `GET /users/me`.

### Request

```json
{
  "title": "Run a half marathon",
  "description": null
}
```

- `title` — optional; if present, must be non-empty after stripping
  whitespace.
- `description` — optional, nullable; sending `null` explicitly clears the
  description, while omitting the field entirely leaves the current value
  untouched.
- An empty body (`{}`) is a no-op: the goal is returned unchanged with its
  existing `updated_at`, and no database write occurs.

### Response — `200 OK`

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "title": "Run a half marathon",
  "description": null,
  "created_at": "2026-06-20T11:31:19.600000+00:00",
  "updated_at": "2026-06-20T12:05:42.100000+00:00"
}
```

### Error cases

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing, malformed, expired, or invalid-signature JWT; rejected before any handler/database logic runs. |
| `404 Not Found` | The goal doesn't exist, isn't owned by the requester, or is already soft-deleted. |
| `422 Unprocessable Entity` | `title` is present but empty or whitespace-only. No database write occurs. |
| `429 Too Many Requests` | Per-IP rate limit exceeded. |

---

## `DELETE /goals/{goal_id}`

Soft-deletes a goal: sets `deleted_at` to the current time. Never issues a
SQL `DELETE` against the `goals` table — the row is never removed.

- **Auth required**: yes (`Authorization: Bearer <jwt>`).
- **Rate limited**: yes, per client IP, same configured threshold as
  `GET /users/me`.

### Request

No request body. The goal to delete is identified by `{goal_id}` in the
path.

### Response — `204 No Content`

Empty body on success. The goal subsequently disappears from `GET /goals`
and a later `PATCH` against the same `goal_id` returns `404`.

### Error cases

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing, malformed, expired, or invalid-signature JWT; rejected before any handler/database logic runs. |
| `404 Not Found` | The goal doesn't exist, isn't owned by the requester, or is already soft-deleted. |
| `429 Too Many Requests` | Per-IP rate limit exceeded. |

---

## `GET /oauth/consent`

Serves the OAuth consent login page that Supabase's OAuth 2.1 Server
redirects a browser to when an external OAuth client (e.g. an MCP client
such as Claude Desktop) requests access. Returns a complete, standalone
HTML document; the entire login + consent flow (session check, login form,
consent screen, approve/deny) runs client-side via the
`@supabase/supabase-js` SDK after the page loads — this route's only job is
to serve the page shell with `SUPABASE_URL`/`SUPABASE_ANON_KEY` injected as
JS constants so the SDK can initialize.

- **Auth required**: **no** — unlike every other endpoint in this
  reference. This is deliberate, not an oversight: Supabase redirects a
  browser here before it's known whether the visitor has an active
  session, so the page must be reachable with no bearer token and no
  cookie in order to present the login form in the first place. The actual
  authentication happens entirely client-side, after the page loads, via
  `signInWithPassword`.
- **Rate limited**: no.

### Request

```
GET /oauth/consent?authorization_id=<id>
```

`authorization_id` is read client-side from the query string, not parsed
server-side. If it's missing, the page renders a non-technical failure
state in the browser rather than a broken form — the server still returns
`200` either way, since the failure state is part of the served page, not
an HTTP error.

### Response — `200 OK`

`Content-Type: text/html`. A complete `<!DOCTYPE html>` document containing
the pinned-exact-version `@supabase/supabase-js` CDN script tag, the
injected config constants, and the embedded JS that drives the rest of the
flow (login form, consent screen rendering, and the approve/deny calls to
Supabase's `getAuthorizationDetails`/`approveAuthorization`/
`denyAuthorization`).

### Error cases

None at the HTTP level — this route never returns a non-`200` status; every
failure mode (missing `authorization_id`, invalid/expired
`authorization_id`, failed login, a failed approve/deny call) is rendered
as a state within the same `200` HTML page, not as an HTTP error response.

**Unverified external contract**: the actual response shapes of
`signInWithPassword`, `getAuthorizationDetails`, `approveAuthorization`, and
`denyAuthorization` (all assumed as `{ data, error }`) have not been
confirmed against a live Supabase project — see this feature's technical
doc (`knowledge/documentation/LFC-005-oauth-consent-login/technical-doc.md`)
for the full caveat.

---

## MCP tools

Mounted on the same FastAPI app (same process, root path), via the MCP
Python SDK's streamable-HTTP transport. These are not REST endpoints — they
are tools called by an MCP client (e.g. an LLM-based coaching client) over
the MCP wire protocol (`initialize` → `notifications/initialized` →
`tools/call`).

### Authentication

Every MCP tool call requires the same Supabase-issued JWT REST endpoints
require, sent the same way:

```
Authorization: Bearer <supabase-jwt>
```

Verified via `app/auth.py`'s `verify_bearer_token`, which applies the exact
same JWKS/ES256 verification logic as the REST `get_current_user`
dependency. A missing, malformed, expired, or invalid-signature token is
rejected before any tool logic runs and before any database call is made.
The MCP SDK catches the resulting error and returns it as a tool-level
`isError: true` result rather than a raw exception.

### Rate limiting

Every MCP tool call is rate-limited per client IP, using the same threshold
and `X-Forwarded-For`-aware IP resolution as REST endpoints (default 30
requests / 60 seconds, configurable via `RATE_LIMIT_REQUESTS` /
`RATE_LIMIT_WINDOW_SECONDS`). MCP and REST traffic from the same client IP
share one rate-limit budget, not two independent ones.

---

### Tool: `record_update`

Stores a new update against one of the caller's own active goals. Intended
to be called by the MCP client only once the AI and the user have settled
on something concrete — not after every conversational turn.

- **Auth required**: yes (`Authorization` bearer JWT, verified before any
  tool logic runs).
- **Rate limited**: yes, same per-IP threshold as REST endpoints.

#### Input schema

| Field | Type | Required | Constraints |
|---|---|---|---|
| `goal_id` | `string` (UUID) | yes | Must be a valid UUID; must reference an active (non-soft-deleted) goal owned by the caller. |
| `content` | `string` | yes | 1–4000 characters, non-blank after stripping. A short summary of the agreed outcome, not a raw transcript. |
| `transcript` | `string` | no | Up to 20000 characters. Full conversation text, only when the caller chooses to attach one. |

The stored `user_id` always comes from the verified JWT subject — there is
no `user_id` or `source` parameter on this tool; a client cannot influence
either.

#### Output

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "goal_id": "a1b2c3d4-58cc-4372-a567-0e02b2c3d479",
  "content": "Agreed to run 3x/week starting Monday.",
  "source": "coaching_update",
  "created_at": "2026-06-21T09:00:00.000000+00:00"
}
```

`source` is always `"coaching_update"` for any update created by this
tool — there is no way to produce a `"checkin"` row through `record_update`.

#### Error cases

| Condition | Behavior |
|---|---|
| Missing, malformed, expired, or invalid-signature JWT | Rejected before any tool logic or database call; returned as an MCP `isError: true` result. |
| Per-IP rate limit exceeded | Rejected before any database call. |
| `goal_id` is not a valid UUID, or `content` is missing/blank/too long, or `transcript` exceeds the size limit | Validation error raised before any database call. |
| `goal_id` does not exist, is not owned by the caller, or is soft-deleted | The RLS `WITH CHECK` on `updates_insert_own` causes the `INSERT` to return no row; the tool raises an error rather than silently succeeding. |

---

### Tool: `list_updates`

Retrieves the caller's own past updates for a given goal, for the MCP
client to re-inject as context in an ongoing coaching conversation.

- **Auth required**: yes (`Authorization` bearer JWT, verified before any
  tool logic runs).
- **Rate limited**: yes, same per-IP threshold as REST endpoints.

#### Input schema

| Field | Type | Required | Constraints |
|---|---|---|---|
| `goal_id` | `string` (UUID) | yes | Must be a valid UUID. |

No pagination, sorting, or filtering options. Results are not filtered by
`source` — a future check-in is relevant coaching context too, so all of a
goal's updates are returned regardless of which source recorded them.

#### Output

```json
[
  {
    "content": "Agreed to run 3x/week starting Monday.",
    "source": "coaching_update",
    "created_at": "2026-06-21T09:00:00.000000+00:00"
  }
]
```

Ordered most-recently-created first. An empty array (`[]`) is returned, not
an error, when the goal has no updates yet. `transcript` is never included
in the output — the underlying query never selects the column, so it never
reaches application memory, regardless of how the response is later
serialized. `id` and `goal_id` are also not included.

#### Error cases

| Condition | Behavior |
|---|---|
| Missing, malformed, expired, or invalid-signature JWT | Rejected before any tool logic or database call; returned as an MCP `isError: true` result. |
| Per-IP rate limit exceeded | Rejected before any database call. |
| `goal_id` is not a valid UUID | Validation error raised before any database call. |
| `goal_id` does not exist, isn't owned by the caller, or has no updates | Returns `[]` — not an error. Cross-user/cross-goal isolation is enforced entirely by the `updates_select_own` RLS policy, not by an application-level filter. |

---

### Tool: `get_home_view`

Returns the home screen UI for the signed-in user as a rendered HTML
resource: a greeting, a card per active goal with its progress, and
distinct "create a new goal" / "just want to talk?" entries. Not a source
of goal data for an MCP client's own reasoning — use `list_updates`/other
tools for that.

- **Auth required**: yes (`Authorization` bearer JWT, verified before any
  tool logic runs).
- **Rate limited**: yes, same per-IP threshold as REST endpoints.

#### Input schema

No parameters. The user is identified entirely from the verified JWT.

#### Output

An MCP `EmbeddedResource`:

```json
{
  "type": "resource",
  "resource": {
    "uri": "ui://home-view",
    "mimeType": "text/html",
    "text": "<!DOCTYPE html>..."
  }
}
```

The rendered HTML shows one card per active goal (title + a circular
progress indicator, showing a real percentage or a dashed "no estimate
yet" treatment when `progress_percent` is `NULL`, plus an "Updated <date>"
line when the goal has at least one recorded update), a "create a new
goal" entry and a "just want to talk?" entry (both inject a chat message
via `postMessage` rather than calling a tool), or an empty-state variant
when the caller has zero active goals. Clicking a goal card invokes
`get_goal_detail_view` directly via `postMessage` — **unverified against a
live MCP-UI host**, see this feature's technical doc for the open risk.

#### Error cases

| Condition | Behavior |
|---|---|
| Missing, malformed, expired, or invalid-signature JWT | Rejected before any tool logic or database call; returned as an MCP `isError: true` result. |
| Per-IP rate limit exceeded | Rejected before any database call. |
| The caller's `users` row is missing, or any unhandled error occurs while loading the screen | Handled internally — returns a failure-state `EmbeddedResource` describing the problem in user-safe language, rather than raising. Never an `isError: true` result for this case. |

---

### Tool: `get_goal_detail_view`

Returns the goal-detail screen UI for one of the caller's own goals as a
rendered HTML resource: full title/description, progress, a short list of
recent updates, a "continue this conversation" action, and a delete action
behind an explicit confirm step.

- **Auth required**: yes (`Authorization` bearer JWT, verified before any
  tool logic runs).
- **Rate limited**: yes, same per-IP threshold as REST endpoints.

#### Input schema

| Field | Type | Required | Constraints |
|---|---|---|---|
| `goal_id` | `string` (UUID) | yes | Must be a valid UUID. |

#### Output

Same `EmbeddedResource` shape as `get_home_view`, with `uri:
"ui://goal-detail-view"`. The rendered HTML shows the goal's full
title/description, its progress indicator, up to 5 most recent updates
(`content` + date only, never `transcript` — same discipline as
`list_updates`, with an explicit "No updates yet." message when there are
none), a "continue this conversation" action (injects a chat message
referencing the goal by title, never a tool call), and a two-stage
delete-confirm action whose confirmed step calls `delete_goal` directly via
`postMessage` — **unverified against a live MCP-UI host**, see this
feature's technical doc.

#### Error cases

| Condition | Behavior |
|---|---|
| Missing, malformed, expired, or invalid-signature JWT | Rejected before any tool logic or database call; returned as an MCP `isError: true` result. |
| Per-IP rate limit exceeded | Rejected before any database call. |
| `goal_id` is not a valid UUID | Validation error raised before any database call. |
| `goal_id` does not exist, isn't owned by the caller, or is soft-deleted | Handled internally — returns a failure-state `EmbeddedResource` ("This goal isn't available.") rather than raising. Never an `isError: true` result for this case. |
| Any unhandled error occurs while loading the screen | Same handled-failure behavior as above. |

---

### Tool: `set_goal_progress`

Lets the calling coaching AI record its own periodic self-assessment of
progress (0-100) on one of the caller's own goals, after a conversation
where it judges progress changed. This is for the AI's own internal
bookkeeping — the rendered UI never calls this tool directly, and it
should not be presented to the user as something they asked for or need to
confirm.

- **Auth required**: yes (`Authorization` bearer JWT, verified before any
  tool logic runs).
- **Rate limited**: yes, same per-IP threshold as REST endpoints.

#### Input schema

| Field | Type | Required | Constraints |
|---|---|---|---|
| `goal_id` | `string` (UUID) | yes | Must be a valid UUID; must reference a goal owned by the caller. |
| `percentage` | `integer` | yes | `0`-`100` inclusive. |
| `rationale` | `string` | no | Up to 500 characters, blank-to-`null`. Validated but not persisted — there is no `rationale` column on `goals`. |

#### Output

```json
{
  "goal_id": "a1b2c3d4-58cc-4372-a567-0e02b2c3d479",
  "percentage": 42
}
```

A plain dict, not a UI resource — this tool is never UI-initiated.

#### Error cases

| Condition | Behavior |
|---|---|
| Missing, malformed, expired, or invalid-signature JWT | Rejected before any tool logic or database call; returned as an MCP `isError: true` result. |
| Per-IP rate limit exceeded | Rejected before any database call. |
| `goal_id` is not a valid UUID, `percentage` is outside `0`-`100`, or `rationale` exceeds 500 characters | Validation error raised before any database call. |
| `goal_id` does not exist, is not owned by the caller, or is soft-deleted | The RLS `WITH CHECK` on `goals_update_own` causes the `UPDATE` to return no row; the tool raises an error rather than silently succeeding. |

---

### Tool: `delete_goal`

Soft-deletes one of the caller's own goals — identical SQL semantics to the
existing REST `DELETE /goals/{id}` (an `UPDATE ... SET deleted_at = now()`,
never a SQL `DELETE`). Intended to be called from the goal-detail view's
confirm-delete UI action after the user has explicitly confirmed, not
invoked proactively mid-conversation. On success, returns a refreshed home
screen resource reflecting the deletion, rather than a plain
acknowledgement.

- **Auth required**: yes (`Authorization` bearer JWT, verified before any
  tool logic runs).
- **Rate limited**: yes, same per-IP threshold as REST endpoints.

#### Input schema

| Field | Type | Required | Constraints |
|---|---|---|---|
| `goal_id` | `string` (UUID) | yes | Must be a valid UUID; must reference a goal owned by the caller. |

#### Output

Same `EmbeddedResource` shape as `get_home_view` (`uri: "ui://home-view"`)
— the home view, refreshed to exclude the deleted goal — produced via the
same `_fetch_home_view_data`/`_build_home_view_resource` helpers
`get_home_view` itself uses, not a parallel implementation.

#### Error cases

| Condition | Behavior |
|---|---|
| Missing, malformed, expired, or invalid-signature JWT | Rejected before any tool logic or database call; returned as an MCP `isError: true` result. |
| Per-IP rate limit exceeded | Rejected before any database call. |
| `goal_id` is not a valid UUID | Validation error raised before any database call. |
| `goal_id` does not exist, is not owned by the caller, or is already soft-deleted | The RLS-scoped `UPDATE` returns no row; the tool raises an error with no commit and no home-view refresh attempted. |
| The post-delete home-view refresh itself fails (e.g. an unhandled error reading the caller's updated goal list) | Handled internally — returns a failure-state `EmbeddedResource` rather than raising, even though the delete itself already succeeded and committed. |
