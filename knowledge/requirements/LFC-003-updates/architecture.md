# Architecture: Updates

## Approach

Add an `updates` table (goal-linked, RLS-isolated, append-only — no
edit/delete in scope) and mount an MCP tool server onto the existing
FastAPI app via the official Python MCP SDK (`mcp`, providing
`mcp.server.fastmcp.FastMCP`), exposing two tools: `record_update` (write
a short, required summary of whatever the AI and user agreed on, plus an
optional full transcript when fidelity matters) and `list_updates` (read a
goal's past updates back, for an LLM client to re-inject as context).
Either party — the AI or the user — can originate the content that
becomes an update; what's stored is the agreed outcome, not raw model
output, so there is no "origin" field distinguishing who proposed it.
MCP tool calls reuse the same Supabase JWT verification already built for
the REST endpoints, and all queries go through the same
`get_rls_connection(user_id)` pattern as `goals`, so Postgres RLS — not
application logic — remains the primary per-user isolation mechanism.

## Components touched

- **Frontend**: none — no MCP-UI in this feature (progress views are a
  later feature per `strategy.md`); the conversational interface is the
  MCP client itself, outside this repo.
- **Backend**:
  - New `app/mcp_server.py` — builds the `FastMCP` instance, defines the
    two tools, and exposes the ASGI app to mount.
  - `app/main.py` — mounts the MCP ASGI app (e.g.
    `app.mount("/mcp", mcp_asgi_app)`) alongside the existing REST routes;
    no existing route changes.
  - `app/schemas.py` — new `UpdateCreate`/`UpdateResponse` models.
  - New dependency: `mcp` (Python MCP SDK), added to `pyproject.toml`.
- **Infrastructure**: one new Alembic migration for the `updates` table +
  RLS policies.

## Data flow

1. The MCP client (e.g. Claude, acting on behalf of a signed-in user)
   calls the `record_update` or `list_updates` tool, passing the user's
   Supabase JWT the same way it would authenticate an HTTP request to
   this server (exact transport-level mechanism — header vs. other MCP
   auth convention — is confirmed against the installed MCP SDK's actual
   support during implementation, per the risk flagged in `analysis.md`;
   not assumed here).
2. The tool handler verifies the JWT using the same verification logic as
   `get_current_user` (reused, not reimplemented), resolving the verified
   `user_id`.
3. For `record_update`: there is no mechanism in this backend that
   detects "the conversation has produced an agreement" — this server
   never sees the live conversation, only whatever the MCP client (the
   LLM) sends when it actually calls the tool. The only lever available
   to influence *when* and *what* is the tool's own MCP-exposed
   description, which is what the calling LLM reads to decide how to use
   it. That description must explicitly instruct the LLM to call this
   tool only once it and the user have settled on something concrete —
   not after every message — and to write a concise summary into
   `content`, not paste the raw conversation. This is a load-bearing part
   of the tool's contract, not just documentation; see the corresponding
   acceptance criterion in `LFC-STORY-002`. The handler validates
   `goal_id`, `content` (the short,
   required summary of the agreed update), and an optional `transcript`
   via `UpdateCreate`, then inserts through `get_rls_connection(user_id)`.
   RLS's `updates_insert_own` policy enforces both that `user_id` matches
   `auth.uid()` AND that `goal_id` refers to an active (non-soft-deleted)
   goal owned by the same user.
4. For `list_updates`: the handler queries `updates` for the given
   `goal_id` through the same RLS-scoped connection; `updates_select_own`
   restricts results to the requester's own rows. No filter on `source`
   is applied — a future check-in is relevant coaching context too, so
   `list_updates` returns all of a goal's updates regardless of source,
   including `content`, `source`, and `created_at` for each, so the
   caller can distinguish a coaching update from a check-in if it needs
   to. The query and the tool's output **never include `transcript`** —
   so repeated context re-injection across a long coaching relationship
   stays cheap regardless of how many updates accumulate.
5. Results are returned to the MCP client as tool output, for it to use as
   context in the ongoing coaching conversation.

## Data model changes

New `updates` table:

| Column        | Type          | Constraints                                      |
|---------------|---------------|---------------------------------------------------|
| `id`          | `uuid`        | PK, default `gen_random_uuid()`                   |
| `user_id`     | `uuid`        | NOT NULL, FK → `auth.users.id` ON DELETE CASCADE  |
| `goal_id`     | `uuid`        | NOT NULL, FK → `goals.id` ON DELETE CASCADE       |
| `content`     | `text`        | NOT NULL (short, required summary of the agreed update) |
| `transcript`  | `text`        | nullable (full conversation, only when the caller chooses to attach one) |
| `source`      | `text`        | NOT NULL, default `'coaching_update'`, `CHECK (source IN ('coaching_update', 'checkin'))` |
| `created_at`  | `timestamptz` | NOT NULL, default `now()`                         |

`source` distinguishes an AI↔user coaching update from a future user
check-in — added now so the table is ready for a later check-ins feature
to write into, without that feature needing its own table/migration. This
feature only ever writes `coaching_update` rows; no tool in this feature
sets or accepts `checkin` as a value (see "Key decisions" below).

No `updated_at`/`deleted_at` — updates are append-only in this feature's
scope (no edit/delete requirement).

RLS enabled, policies:
- `updates_select_own`: `SELECT` `USING (auth.uid() = user_id)`
- `updates_insert_own`: `INSERT` `WITH CHECK (auth.uid() = user_id AND
  EXISTS (SELECT 1 FROM goals g WHERE g.id = goal_id AND g.user_id =
  auth.uid() AND g.deleted_at IS NULL))`

No `UPDATE`/`DELETE` policies — matches the append-only scope; same
"structurally impossible to violate" posture used for `goals`'
soft-delete-only design.

Index: `(goal_id, created_at)` to support `list_updates`' query pattern.

## Key decisions

- **Decision**: Rebrand "suggestions" to "updates," modeling a single
  agreed outcome rather than AI-only output, with no field distinguishing
  who originated it.
  **Rationale**: explicit framing from `gather.md`'s feedback round — the
  conversation is bidirectional, and what matters for future context is
  what was settled on, not which party said it first. Adding an
  origin/source field was considered and explicitly rejected for this
  feature's scope (see the check-ins-unification decision below) — no
  premature schema flexibility for a need that hasn't been scoped yet.
- **Decision**: `content` is required and meant to stay short (a summary);
  `transcript` is optional, used only when the caller chooses to attach
  full fidelity. `list_updates` never returns `transcript`.
  **Rationale**: directly addresses the stated risk that repeatedly
  re-injecting full conversations as context would make updates "huge,
  noisy, and fill up the context window." Keeping the required field
  short-by-construction and excluding the optional fidelity field from
  the read path that feeds back into context is the only way this
  actually holds going forward — if a future change makes `list_updates`
  include `transcript` "for completeness," the original problem returns.
  This is now a load-bearing contract, not just a convenience default.
- **Decision**: Check-ins will write into this same `updates` table later
  (via a `source = 'checkin'` row), not a separate table — so the
  `source` column is added now, schema-only, in this feature.
  **Rationale**: explicit product direction — a check-in is conceptually
  an update, just one a user records on their own rather than through a
  negotiated AI↔user exchange. Adding the column now avoids a later
  migration to retrofit it onto existing rows. The actual write path (a
  `record_checkin` tool or equivalent) is explicitly **not** built in this
  feature — that's still a separate future feature's job, scoped and
  designed when check-ins themselves are designed; this feature's tools
  (`record_update`, `list_updates`) only ever read/write
  `source = 'coaching_update'` rows.
- **Decision**: Enforce the goal-ownership-and-not-deleted check for a new
  update's `goal_id` via the RLS `WITH CHECK` subquery, not only an
  app-level check.
  **Rationale**: consistent with this project's established defense-in-
  depth posture (RLS as the real enforcement, app-level checks secondary)
  — and directly informed by the LFC-002 PR review finding that an
  `UPDATE` policy without an explicit `WITH CHECK` can silently fail in a
  way unit tests with mocked cursors can't catch; being explicit and
  RLS-first here is the safer default given that history.
- **Decision (flagged risk, not yet resolved)**: The exact mechanism by
  which an MCP tool handler receives and verifies the caller's JWT is not
  assumed here — it must be confirmed against the actual installed MCP
  Python SDK's documented authentication support before being implemented,
  per `agents/backend.md`'s external-integration rule and the precedent
  set by `JWT-VERIFICATION-INCIDENT.md` (guessing at a third-party
  integration's "standard-sounding" default previously caused a real,
  shipped bug in this same repo).
