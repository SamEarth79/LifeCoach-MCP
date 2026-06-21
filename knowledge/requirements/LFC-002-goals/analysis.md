# Analysis: Goals

## Summary

Authenticated users can create, list, edit, and soft-delete freeform goals
(title + description, no category/template schema), each goal owned by
exactly one user and isolated via Supabase Row Level Security, following the
same auth/RLS/migration pattern established in `LFC-001-auth-infra-baseline`.

## Relevant existing code

- `app/auth.py` — `get_current_user` FastAPI dependency verifies the
  Supabase JWT (ES256 via JWKS) and returns a `CurrentUser(id, email)`. Every
  new goals endpoint depends on this the same way `/users/me` does; never
  trust a client-supplied user id.
- `app/db.py` — `get_rls_connection(user_id)` opens a connection as the
  `authenticated` Postgres role and sets `request.jwt.claim.sub`, so
  `auth.uid()` resolves correctly inside RLS policies. All goals queries
  should go through this, not `get_connection()` directly (which connects as
  `postgres`, which has `BYPASSRLS`).
- `app/main.py` — existing endpoints (`/health`, `/users/me`) show the
  established conventions: `@limiter.limit(per_ip_rate_limit)` decorator
  pattern, async handlers, raising `HTTPException` with explicit status
  codes, returning plain dicts (no Pydantic response models defined yet —
  this feature can introduce request/response models since goals need
  richer input validation than `/users/me`, which takes no body).
- `migrations/versions/16b5eb4c9d06_create_users_table.py` — the only
  existing migration. Shows the established pattern for a new table: create
  table, `ENABLE ROW LEVEL SECURITY`, then `CREATE POLICY` per operation
  (select/update/insert own-row only, via `auth.uid() = <owner column>`).
  The new `goals` migration should follow this shape exactly, add a
  `user_id` FK to `auth.users.id` (not `users.id`) for consistency with how
  `users.id` itself is FK'd, and add a `DELETE`-equivalent... actually no
  hard delete is planned (see below), so only SELECT/UPDATE/INSERT policies
  are needed, scoped by `user_id = auth.uid()`.
- `app/config.py` — `Settings` (pydantic-settings, env-var driven) already
  holds `rate_limit_requests`/`rate_limit_window_seconds` read by `main.py`
  at import time. No new settings are anticipated for this feature.
- `knowledge/strategy.md` — explicitly specifies: freeform goals (title +
  description, no fixed category/template schema), soft deletes (not hard
  deletes) for goals, per-user RLS isolation, JWT verified on every request,
  rate limiting on endpoints even given the small trusted user base.

## Constraints and risks

- Soft delete means a `deleted_at` (nullable timestamp) column, not a row
  removal. Every SELECT path (list, and any future suggestion/check-in
  queries that join to goals) must filter `deleted_at IS NULL` — easy to
  forget on a new query and accidentally resurrect "deleted" goals in a
  listing.
- RLS policies alone won't enforce the soft-delete filter (a policy can't
  conditionally hide rows by `deleted_at` without being written to do so
  explicitly) — needs either a partial-row policy clause or app-level
  filtering. Decide explicitly in `draft.md` rather than assuming RLS alone
  handles it.
- The JWT-verification incident in `JWT-VERIFICATION-INCIDENT.md` is a
  process risk, not a new one for this feature: this feature has no new
  external-system wire-format dependency (no new third-party contract), so
  that specific risk class doesn't recur here. No live-external-system gap
  is introduced by this feature beyond what `LFC-001` already covers.
- `app/main.py` currently has no Pydantic request/response models; this
  feature is the first to need body validation (goal create/edit payloads).
  `draft.md` should specify where these models live (e.g. inline in
  `main.py` per current file size, or a new `app/schemas.py` if it would
  otherwise grow too large — per `coding-style.md`'s "one responsibility per
  file" once main.py starts mixing routing with multiple model definitions).

## Open questions

- None blocking — scope was already clarified in `gather.md` (create, list,
  edit title/description, soft-delete; no categories/templates; no
  notifications).
