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
