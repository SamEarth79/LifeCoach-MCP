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
