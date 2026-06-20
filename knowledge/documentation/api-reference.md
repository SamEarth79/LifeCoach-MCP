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
