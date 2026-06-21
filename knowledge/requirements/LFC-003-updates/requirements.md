# Requirements: Updates

## Functional requirements

1. An `updates` table exists in Postgres, with one row per update, storing
   `id`, `user_id`, `goal_id`, `content` (a short, required summary of
   what the AI and user agreed on), `transcript` (optional full
   conversation text), `source` (required, one of `coaching_update` or
   `checkin`, defaulting to `coaching_update`), and `created_at`, created
   via a versioned Alembic migration. `source` exists so a future
   check-ins feature can write into this same table without a further
   migration — this feature's own tools only ever write
   `coaching_update` rows.
2. Row Level Security is enabled on the `updates` table, restricting
   select access to rows owned by the requester's verified user id, and
   restricting insert to rows where the inserted `user_id` matches the
   requester's verified user id AND the referenced `goal_id` is an active
   (non-soft-deleted) goal owned by that same user.
3. There is no update or delete capability for updates in this feature —
   updates are append-only once recorded.
4. An MCP tool server is mounted on the existing FastAPI app (same
   process), exposing tools callable by an MCP client.
5. A `record_update` MCP tool lets an authenticated caller store a new
   update linked to one of their own active goals, with a required
   `content` summary and an optional `transcript`; the stored `user_id`
   always comes from the verified JWT subject, never client-supplied.
   Either the AI or the user may have originated the underlying
   suggestion — what's stored is the agreed outcome, with no field
   distinguishing who proposed it.
6. A `list_updates` MCP tool lets an authenticated caller retrieve their
   own past updates for a given goal, returning `content`, `source`, and
   `created_at` for each — never `transcript`, so repeated re-injection
   as conversational context stays cheap regardless of history length.
   Results are not filtered by `source` — a future check-in is relevant
   coaching context too, so all of a goal's updates are returned
   regardless of which source recorded them.
7. MCP tool calls require a valid Supabase JWT, verified using the same
   logic as the existing REST endpoints; calls with a missing, malformed,
   or expired JWT are rejected before any tool logic runs or any database
   call is made.
8. MCP tool calls are rate-limited consistent with the existing REST
   endpoints' rate-limiting approach.

## Non-functional requirements

- **Security**: No client-supplied user id is ever trusted for
  authorization on an update — only the verified JWT claim, consistent
  with every prior feature in this repo. `goal_id` ownership/active-status
  is enforced at the RLS layer (`WITH CHECK`), not only by application
  logic.
- **Maintainability**: The `updates` migration follows the same
  table/RLS/policy structure already established by `users` (LFC-001) and
  `goals` (LFC-002), including the explicit `WITH CHECK` clause lesson
  learned from LFC-002's PR review.
- **Third-party integration**: The MCP Python SDK's actual authentication
  support is confirmed against its current documentation during
  implementation, not assumed from a "standard-sounding" guess — per the
  precedent in `JWT-VERIFICATION-INCIDENT.md`.
- **Context efficiency**: `content` is bounded to a reasonable length at
  the application boundary (it's meant to stay a short summary, not a
  transcript); `transcript`, when provided, is still validated for a sane
  maximum size to avoid unbounded storage growth, even though it's not
  returned by `list_updates`.

## Out of scope

- Editing or deleting a recorded update — append-only for v1.
- Free-text search or retrieval over transcripts; no vector DB (per
  `strategy.md`, only reconsider if a real need emerges).
- MCP-UI or any visual progress display of updates — that's a later,
  separate feature.
- Building the actual check-in write path (e.g. a `record_checkin` tool)
  — explicitly deferred to a future feature. This feature only adds the
  `source` column to the schema so that future feature doesn't need its
  own migration; `record_update`/`list_updates` never write or expose a
  way to write `source = 'checkin'`.
- Any change to how the existing REST `/goals` or `/users/me` endpoints
  work — this feature only adds new surface, the MCP tool layer.
