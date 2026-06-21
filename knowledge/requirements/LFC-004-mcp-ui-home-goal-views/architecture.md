# Architecture: MCP-UI home and goal-detail views

## Approach

Add MCP-UI resources rendered server-side as HTML and returned from MCP
tool calls (`EmbeddedResource` with a `ui://` URI, `text/html` mimetype —
the convention `strategy.md` already committed to, confirmed mechanically
feasible with the already-installed `mcp` SDK). Two screens: a home view
(greeting + goal cards with a self-reported progress indicator + a "just
talk" entry + a "create goal" entry) and a goal-detail view (full
description, progress, recent updates, a delete action with a confirm
step). Navigation between screens happens by the UI invoking further MCP
tool calls that return a new UI resource (clicking a goal card calls
`get_goal_detail_view`, which re-renders); free-text conversational actions
(continuing a conversation, creating a goal) inject a chat message instead
of calling a tool, since goal creation and conversation stay conversational
per `strategy.md`.

Progress has no server-side source of truth to compute from — there's no
LLM in this backend. It is self-reported by the calling coaching AI through
a new `set_goal_progress` tool, the same pattern `record_update` already
establishes for committing an AI/user-agreed outcome.

## Components touched

- **Frontend**: new HTML/CSS templates for the home and goal-detail MCP-UI
  resources, generated server-side in Python (string templates or a
  minimal templating helper) and returned as `EmbeddedResource` content
  from the relevant tools. No separate JS framework/build step — matches
  `strategy.md`'s "light UI needs, raw-spec, no TS helper SDK" decision.
- **Backend**: `app/mcp_server.py` — four new tools: `get_home_view`,
  `get_goal_detail_view`, `set_goal_progress`, `delete_goal` (MCP version,
  mirroring the existing REST soft-delete). New Alembic migration adding
  `goals.progress_percent`. `app/schemas.py` — new narrow input models for
  `set_goal_progress`.
- **Infrastructure**: none.

## Data flow

**Home view:**
1. MCP host calls `get_home_view` (when/whether a host calls this
   automatically "on greeting" vs. requiring an explicit first tool call is
   host-side behavior outside this backend's control — flagged under Key
   decisions).
2. `enforce_mcp_rate_limit(request)`, then `verify_bearer_token(...)` —
   same fixed ordering as `record_update`/`list_updates`.
3. Query `users` for `display_name`/`email` (greeting), and `goals` for the
   caller's goals including the new `progress_percent` column — RLS-only
   filtering (`goals_select_own`), no app-level `deleted_at` clause, same
   as the existing `list_goals`.
4. Render: a goal card per row (title, progress bar/percentage, "updated
   X" derived from `updates.created_at` if any), a "create new goal" card,
   a "just want to talk?" entry, or an empty-state variant if the caller
   has zero goals.
5. Return as an `EmbeddedResource`.

**Goal-detail view:**
1. UI emits a tool-call action (clicking a goal card) invoking
   `get_goal_detail_view(goal_id)`.
2. Same rate-limit → auth ordering.
3. Query the goal row (RLS-scoped) and its recent updates (same query
   shape as the existing `list_updates`, `LIMIT`-ed for "recent").
4. Render: full title/description, progress, a short recent-updates list,
   a "continue conversation" action (chat-message injection, not a tool
   call), and a delete action behind a confirm step.
5. Return as an `EmbeddedResource`.

**Progress update (AI-initiated, not from the UI):**
1. Coaching AI calls `set_goal_progress(goal_id, percentage, rationale)`
   after a conversation where it judges progress changed.
2. Same rate-limit → auth ordering, validate `percentage` is 0–100 at the
   schema boundary.
3. `UPDATE goals SET progress_percent = %s WHERE id = %s` through
   `get_rls_connection` — relies on the existing `goals_update_own` RLS
   policy's explicit `WITH CHECK (auth.uid() = user_id)` (the fix from
   LFC-002's PR review), no RLS change needed.
4. Returns the updated goal's id/percentage as a plain tool result (not a
   UI resource — this call isn't UI-initiated).

**Delete (UI-initiated):**
1. Detail view's confirm step (client-side, inside the rendered HTML) on
   confirmation invokes the `delete_goal` MCP tool directly.
2. Same rate-limit → auth ordering.
3. Same soft-delete SQL as the existing REST `delete_goal`
   (`UPDATE goals SET deleted_at = now() WHERE id = %s AND deleted_at IS
   NULL`), through `get_rls_connection`.
4. Returns a refreshed `get_home_view`-equivalent `EmbeddedResource`
   directly, rather than just a success flag — so the host re-renders the
   updated goal list in one round trip instead of requiring a second tool
   call.

## Data model changes

- `goals.progress_percent` (integer, nullable, no default — `NULL` means
  "no estimate yet," distinct from `0`). `CHECK (progress_percent IS NULL
  OR (progress_percent BETWEEN 0 AND 100))`. Added via a new Alembic
  migration; no RLS policy changes required, since the existing
  `goals_select_own`/`goals_update_own` policies already cover all columns
  on the row, not specific columns.

## Key decisions

- **Decision**: Progress is self-reported by the calling AI via a new
  `set_goal_progress` tool, not computed by this backend.
  **Rationale**: confirmed during analysis that no LLM/AI SDK exists
  anywhere in this codebase — this backend is a tool server only. The
  alternative (a simple non-AI recency/frequency heuristic) was considered
  and explicitly rejected by the user in favor of a real AI estimate.
- **Decision**: Card-click navigation calls an MCP tool directly (returns a
  new UI resource); "continue conversation" and "create goal" actions
  inject a chat message instead of calling a tool.
  **Rationale**: matches `strategy.md`'s decision that goal creation and
  conversation stay conversational text, while still satisfying the user's
  requirement that clicking a card is a structured action, not a typed
  message. **Unverified assumption, flagged explicitly**: whether the
  MCP-UI host-side `postMessage` convention actually supports a UI element
  invoking a tool call directly (vs. only injecting a chat message) could
  not be confirmed against the live MCP-UI spec in this sandbox (web
  research was unavailable during this design session). Must be confirmed
  against the actual MCP-UI spec/a real host during implementation, with a
  documented fallback to chat-message injection for navigation if direct
  tool-invocation turns out unsupported.
- **Decision**: Add a new MCP `delete_goal` tool (mirroring the existing
  REST soft-delete), rather than routing UI-initiated deletes through a
  conversational chat message.
  **Rationale**: the user explicitly scoped in a confirm-delete *UI*
  affordance, which requires a structured action the UI can call directly;
  there is currently no way for an MCP client to delete a goal at all
  (delete is REST-only today). No equivalent "edit" tool is added — edits
  stay purely conversational, consistent with goals being freeform text
  and the user's choice not to add edit affordances to the detail screen.
- **Decision**: `delete_goal` returns a refreshed home-view `EmbeddedResource`
  directly, instead of a plain success acknowledgement.
  **Rationale**: avoids requiring the host to make a second `get_home_view`
  call just to reflect the deletion; keeps the UI loop self-contained, this design's
  own home/detail tools are the only ones that return UI resources.
- **Decision**: No separate "loading" UI is built — loading state during
  tool-call latency is rendered by the MCP host itself, outside this
  backend's control. A failure-state HTML fallback IS built (an
  `EmbeddedResource` describing the error, returned by `get_home_view`/
  `get_goal_detail_view` on a handled failure, rather than letting an
  unhandled exception surface as a raw tool error with no UI at all).

## Visual reference, with explicit exclusions

A Google Stitch mockup (`stitch_serene_coaching_ui/`) was used to validate
the overall look and feel before implementation — calm/minimal styling,
circular progress indicator, dashed "no estimate yet" treatment, distinct
"just talk"/"create goal" entries, inline delete-confirm. Two elements in
that mockup are explicitly **not** part of this feature's scope and must
not be carried into the implementation:

- A persistent bottom tab bar (Reflect / Goals / Journey). This feature
  only builds the home and goal-detail screens; there is no multi-section
  app shell concept anywhere in `requirements.md`. Do not add tab
  navigation, even as inert placeholders.
- "Total Days" / "Current Streak" stat cards on the goal-detail screen. No
  streak/day-count data exists in the schema, and computing one is out of
  scope for this feature. The detail screen's data is limited to what
  `requirements.md` Requirement 5 specifies: title, description, progress,
  and recent updates.
