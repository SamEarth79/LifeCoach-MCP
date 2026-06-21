# Changelog

All notable changes to this project are documented in this file, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.

## Unreleased

### Added

- Updates (LFC-003): a goal-linked record of what an AI coach and a user
  agreed on during a coaching conversation, exposed via two MCP
  (Model Context Protocol) tools rather than REST — the first feature with
  no REST surface. `updates` table with Row Level Security restricting
  access to the requester's own rows and enforcing that any new update's
  goal is owned by the requester and not soft-deleted. Updates are
  append-only — no edit/delete capability.
- `record_update` MCP tool — stores a new update against one of the
  caller's own active goals: a required short `content` summary and an
  optional full `transcript`.
- `list_updates` MCP tool — retrieves a goal's past updates (`content`,
  `source`, `created_at`); never returns `transcript`, so re-injecting
  update history as conversational context stays cheap regardless of how
  many updates accumulate.
- MCP tool calls require the same Supabase JWT verification and per-IP rate
  limiting already enforced on REST endpoints, mounted onto the existing
  FastAPI app in the same process.
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
