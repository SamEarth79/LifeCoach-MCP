# Requirements: Goals

## Functional requirements

1. A `goals` table exists in Postgres, with one row per goal, storing `id`,
   `user_id`, `title`, `description`, `created_at`, `updated_at`, and
   `deleted_at`, created via a versioned Alembic migration.
2. Row Level Security is enabled on the `goals` table, restricting
   select/update access to rows owned by the requester's verified user id,
   and restricting insert to rows where the inserted `user_id` matches the
   requester's verified user id.
3. A soft-deleted goal (`deleted_at` non-null) is excluded from select and
   update access at the RLS policy level, not only by application-level
   filtering.
4. Authenticated users can create a goal via `POST /goals` with a required
   `title` (non-empty string) and an optional `description`. The created
   goal is owned by the requester's verified user id, never a
   client-supplied id.
5. Authenticated users can list their own active (non-soft-deleted) goals
   via `GET /goals`, returning only goals they own.
6. Authenticated users can edit a goal's `title` and/or `description` via
   `PATCH /goals/{goal_id}`, with an app-level ownership check in addition
   to RLS; editing a goal that doesn't exist, isn't owned by the requester,
   or is already soft-deleted returns a 404.
7. Authenticated users can soft-delete a goal via `DELETE /goals/{goal_id}`,
   which sets `deleted_at` rather than removing the row, with the same
   ownership/existence checks as edit.
8. All `/goals` endpoints require a valid Supabase JWT (reusing the
   existing `get_current_user` dependency); requests with a missing,
   malformed, or expired JWT are rejected with 401 before reaching handler
   logic.
9. All `/goals` endpoints are rate-limited using the existing
   `limiter`/`per_ip_rate_limit` mechanism already configured in
   `app/main.py`.

## Non-functional requirements

- **Security**: No client-supplied user id is ever trusted for
  authorization on a goal — only the verified JWT claim, consistent with
  `LFC-001`. Input validation (title required/non-empty, reasonable max
  length) happens at the request boundary via Pydantic models in
  `app/schemas.py`, not re-validated deeper in the call stack.
- **Reliability**: Soft delete must be irreversible-by-accident-proof at the
  schema level — there is no code path in this feature that issues a hard
  `DELETE` against `goals`.
- **Maintainability**: The `goals` migration follows the same
  table/RLS/policy structure already established by the `users` table
  migration in `LFC-001`.

## Out of scope

- Goal categories, templates, tags, or any fixed taxonomy — goals remain
  freeform (per `strategy.md`).
- Restoring/undeleting a soft-deleted goal, or any UI/endpoint to view
  soft-deleted goals — not requested for v1.
- Suggestions, check-ins, or progress views that reference goals — separate
  future features.
- MCP-UI or any MCP protocol surface for goals — this feature is plain REST
  (FastAPI), matching `LFC-001`'s scope boundary.
- Pagination/sorting/filtering on `GET /goals` beyond returning all of the
  requester's active goals — not needed at this user scale per
  `strategy.md`.
