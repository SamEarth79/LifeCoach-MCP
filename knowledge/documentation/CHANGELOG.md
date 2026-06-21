# Changelog

All notable changes to this project are documented in this file, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.

## Unreleased

### Added

- Goals (LFC-002): freeform goals for the authenticated user — create, list,
  edit, and soft-delete. `goals` table with Row Level Security restricting
  access to each user's own, non-deleted goals; deleting a goal sets a
  `deleted_at` timestamp rather than removing the row, and there is no
  database path that can hard-delete a goal.
- `POST /goals` — create a goal with a required `title` and optional
  `description`, always owned by the authenticated requester.
- `GET /goals` — list the requester's own active (non-deleted) goals.
- `PATCH /goals/{goal_id}` — partially update a goal's `title` and/or
  `description`; omitted fields are left unchanged.
- `DELETE /goals/{goal_id}` — soft-delete a goal.
- Per-IP rate limiting extended to all four `/goals` endpoints, using the
  same configurable threshold already applied to `GET /users/me`.
- Auth & infra baseline (LFC-001): FastAPI backend with Supabase Auth
  (email/password and Google OAuth) as the identity provider. Requests
  authenticate via a Supabase-issued JWT, verified against Supabase's
  public JWKS endpoint (ES256).
- `users` table in Postgres, one row per Supabase Auth user, with Row
  Level Security restricting access to each user's own row. Schema is
  managed from this point forward via versioned Alembic migrations.
- `GET /users/me` — returns the authenticated user's own profile, the
  first real authenticated endpoint in the app.
- `GET /health` — unauthenticated liveness endpoint reporting app and
  database reachability, for the hosting platform's deploy/restart checks.
- Per-IP rate limiting on `GET /users/me`, configurable via
  `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` (defaults: 30
  requests / 60 seconds).
