# Changelog

All notable changes to this project are documented in this file, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.

## Unreleased

### Added

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
