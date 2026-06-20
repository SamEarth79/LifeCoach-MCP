# Architecture: Goals

## Approach

Add a `goals` table and a `/goals` REST resource on top of the existing
auth/RLS baseline from `LFC-001`. Every endpoint depends on
`get_current_user` for identity and uses `get_rls_connection(user_id)` for
all queries, so Postgres RLS — not application logic — is the primary
enforcement layer for "a user can only see/edit their own goals," with an
app-level ownership check as defense in depth, mirroring the existing
`/users/me` pattern. Soft delete is implemented as a nullable `deleted_at`
timestamp, enforced directly in the RLS policies (`deleted_at IS NULL` in
the `SELECT`/`UPDATE` `USING` clauses) so a deleted goal is invisible and
uneditable at the database layer, not just filtered out by query code that
could be forgotten on a future endpoint.

## Components touched

- **Frontend**: none — this feature is plain REST, no MCP-UI or client
  surface yet (per `strategy.md`, MCP-UI is for progress views, a later
  feature).
- **Backend**: new `app/schemas.py` for the request/response Pydantic
  models (`GoalCreate`, `GoalUpdate`, `GoalResponse`) — first feature in
  this repo needing body validation, so a dedicated module keeps
  `app/main.py` focused on routing per `coding-style.md`'s one-responsibility
  rule. New route handlers added to `app/main.py`: `POST /goals`,
  `GET /goals`, `PATCH /goals/{goal_id}`, `DELETE /goals/{goal_id}`
  (soft-delete).
- **Infrastructure**: one new Alembic migration creating the `goals` table,
  RLS policies, and an index on `(user_id, deleted_at)` to keep the list
  query efficient as goal counts grow.

## Data flow

1. Client sends a request to a `/goals` endpoint with a Supabase-issued
   Bearer JWT.
2. `get_current_user` (existing, unchanged) verifies the JWT via JWKS and
   resolves the verified `user_id`.
3. The route handler validates the request body (for create/edit) against
   the Pydantic schema in `app/schemas.py`.
4. The handler opens `get_rls_connection(user_id)`, which sets the
   `authenticated` role and `request.jwt.claim.sub`, then issues a
   parameterized query scoped to that connection.
5. Postgres RLS policies on `goals` restrict every query to rows where
   `user_id = auth.uid()` (and, for select/update, `deleted_at IS NULL`).
6. The handler maps the row(s) to `GoalResponse` and returns JSON; create
   returns `201`, list returns `200` with an array, edit returns `200` with
   the updated row, soft-delete returns `204`.
7. Every `/goals` endpoint is rate-limited the same way `/users/me` is,
   via the existing `limiter`/`per_ip_rate_limit` already wired in
   `app/main.py`.

## Data model changes

New `goals` table:

| Column        | Type          | Constraints                                    |
|---------------|---------------|-------------------------------------------------|
| `id`          | `uuid`        | PK, default `gen_random_uuid()`                |
| `user_id`     | `uuid`        | NOT NULL, FK → `auth.users.id` ON DELETE CASCADE |
| `title`       | `text`        | NOT NULL                                       |
| `description` | `text`        | nullable                                       |
| `created_at`  | `timestamptz` | NOT NULL, default `now()`                      |
| `updated_at`  | `timestamptz` | NOT NULL, default `now()`                      |
| `deleted_at`  | `timestamptz` | nullable — NULL means active, non-NULL means soft-deleted |

RLS enabled, policies:
- `goals_select_own`: `SELECT` `USING (auth.uid() = user_id AND deleted_at IS NULL)`
- `goals_insert_own`: `INSERT` `WITH CHECK (auth.uid() = user_id)`
- `goals_update_own`: `UPDATE` `USING (auth.uid() = user_id AND deleted_at IS NULL)`

No `DELETE` policy is created — there is no hard-delete path, by design.

Index: `(user_id, deleted_at)` to support the list query's filter pattern.

## Key decisions

- **Decision**: Enforce the soft-delete visibility rule (`deleted_at IS
  NULL`) inside the RLS `USING` clauses themselves, rather than relying on
  every query to remember to add `WHERE deleted_at IS NULL`.
  **Rationale**: `analysis.md` flagged this as an easy-to-forget filter on
  future endpoints (e.g. a later suggestions/check-ins feature joining to
  `goals`). Pushing it into RLS makes "can't see/edit a deleted goal" true
  by construction at the database layer, consistent with this project's
  defense-in-depth RLS posture from `LFC-001`.
- **Decision**: Soft-delete is implemented via the existing `UPDATE` policy
  (the endpoint issues `UPDATE goals SET deleted_at = now() WHERE id = ...`)
  rather than a separate `DELETE` policy/SQL `DELETE`.
  **Rationale**: Strategy explicitly calls for soft deletes, not hard
  deletes; never issuing a real `DELETE` statement against the table makes
  it structurally impossible for this feature's code to hard-delete a row,
  rather than relying on code review to catch a future `DELETE` query.
- **Decision**: New `app/schemas.py` module for Pydantic request/response
  models, instead of defining them inline in `app/main.py`.
  **Rationale**: `app/main.py` currently has zero body-validated endpoints;
  this feature introduces three (create, edit, plus the list/get response
  shape). Per `coding-style.md`, once a file would mix multiple unrelated
  concerns (routing + multiple data-shape definitions), split along the
  concern rather than letting `main.py` grow indefinitely.
