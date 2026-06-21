# Requirements: MCP-UI home and goal-detail views

## Functional requirements

1. A `goals.progress_percent` column exists (integer, nullable, `CHECK
   (progress_percent IS NULL OR (progress_percent BETWEEN 0 AND 100))`),
   added via a versioned Alembic migration, defaulting to `NULL` ("no
   estimate yet") for both existing and newly created goals.
2. A `set_goal_progress` MCP tool lets the calling coaching AI record a
   progress estimate (0–100) and an optional short rationale for one of
   the caller's own active goals, verified via the same JWT/rate-limit
   pattern as every existing MCP tool. This tool is for the AI to call
   after a conversation, not something the rendered UI calls directly.
3. A `delete_goal` MCP tool lets the caller soft-delete one of their own
   goals (mirroring the existing REST `DELETE /goals/{id}` behavior
   exactly — same RLS-scoped soft delete, no hard delete), callable
   directly from the goal-detail view's delete confirmation UI. On
   success, it returns a refreshed home-view UI resource rather than a
   plain acknowledgement, so the host can re-render the goal list in one
   round trip.
4. A `get_home_view` MCP tool returns an MCP-UI `EmbeddedResource`
   rendering: a greeting using the caller's display name/email, one card
   per active (non-soft-deleted) goal showing its title and a progress
   bar/percentage (or a neutral "no estimate yet" state when
   `progress_percent` is `NULL`), a distinct "create a new goal" entry, and
   a distinct "just want to talk?" entry that is visually separate from
   goal cards.
5. A `get_goal_detail_view` MCP tool, given a `goal_id`, returns an
   `EmbeddedResource` rendering: the goal's full title and description,
   its progress indicator, a short list of its most recent updates
   (content + date, never the full transcript — consistent with the
   existing `list_updates` tool), a "continue this conversation" action,
   and a delete action behind an explicit confirm step.
6. Clicking a goal card on the home view invokes `get_goal_detail_view` for
   that goal directly (a structured UI action, not a typed chat message).
   Clicking "create a new goal," "just want to talk," or "continue this
   conversation" instead injects a plain chat message into the
   conversation, since goal creation and conversation stay conversational
   per existing project direction — these are UI shortcuts into the
   chat, not new tool calls.
7. A user with zero active goals sees a distinct empty-state rendering of
   the home view (greeting plus the "create a new goal" and "just want to
   talk" entries, no goal cards, no placeholder/broken-looking content).
8. If a tool backing either view encounters a handled failure (e.g. a
   `goal_id` that doesn't resolve to one of the caller's own active
   goals), it returns a UI resource describing the failure state rather
   than letting an unhandled exception surface with no renderable content.
9. Every new MCP tool added by this feature follows the same
   rate-limit-before-auth ordering and `get_rls_connection`-scoped query
   pattern already established by `record_update`/`list_updates`; no
   client-supplied user id is ever trusted for authorization.

## Non-functional requirements

- **Security**: identical to every prior MCP tool in this repo — JWT
  verification before any tool logic or DB call, RLS as the actual
  per-user isolation mechanism (not just an app-level filter), rate
  limiting on every new tool.
- **Consistency with `strategy.md`**: this feature introduces UI
  interactivity (clickable cards triggering tool calls, a UI-driven delete
  action) that goes beyond `strategy.md`'s current "MCP-UI is read-only
  only" statement. This requirements doc does not silently override that
  recorded decision — `strategy.md` should be updated via `/strategize`
  to reflect this change, separately from this design.
- **External-contract honesty**: whether a UI element can invoke an MCP
  tool call directly via the host's `postMessage` mechanism (vs. only
  injecting a chat message) is not verified against the live MCP-UI spec
  as of this design (web research was unavailable in this session). This
  must be explicitly confirmed during implementation before the
  card-click-to-tool-call behavior is relied upon; if unsupported, the
  documented fallback is chat-message injection for navigation, same as
  the other UI actions in this feature.

## Out of scope

- Any change to how goals are created or edited — both stay purely
  conversational text, as already established. This feature only adds a
  way to delete a goal directly from the UI and to view/navigate them.
- A true "loading" UI state during tool-call latency — that's rendered by
  the MCP host itself, not controllable from this backend.
- Computing progress from anything other than the calling AI's own
  self-reported estimate (e.g. no update-count/frequency heuristic, no
  separate background job).
- Check-ins (a separate, already-identified future feature; the `source`
  column on `updates` anticipates it but nothing in this feature reads or
  writes `source = 'checkin'`).
- Persisting the "just want to talk" goal-less conversation in any form —
  it is purely transient/in-session, no schema change for it.
- Verifying RLS policies or MCP `allowed_hosts`/reverse-proxy behavior
  against a live deployment — both are pre-existing, unresolved caveats
  carried forward from LFC-003-updates, not introduced or resolved here.
