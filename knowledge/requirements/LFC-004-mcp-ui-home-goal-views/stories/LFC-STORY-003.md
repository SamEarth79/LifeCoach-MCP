# LFC-STORY-003: get_home_view tool

## Description

As a signed-in user opening the app, I want a home screen showing a
greeting and my current goals as cards (with a progress indicator), plus
distinct entries to start a new goal or just talk, so the experience
doesn't feel purely chat-driven.

## Acceptance criteria

1. A `get_home_view` tool verifies the caller's JWT using the same logic
   as every existing MCP tool, queries the caller's display name/email and
   active (non-soft-deleted) goals — RLS-only filtering, no app-level
   `deleted_at` clause, same pattern as the existing `list_goals` — and
   returns an MCP-UI `EmbeddedResource` (`ui://` URI, `text/html`
   mimetype).
2. The rendered HTML includes: a greeting using the caller's display
   name/email, one card per active goal showing its title and a progress
   bar/percentage, or an explicit "no estimate yet" treatment when
   `progress_percent IS NULL` (never a misleading 0%).
3. The rendered HTML includes a "create a new goal" entry and a "just want
   to talk?" entry, both visually distinct from goal cards.
4. A caller with zero active goals gets a distinct empty-state rendering:
   greeting plus the two entries from criterion 3, no goal cards, no
   placeholder/broken-looking content.
5. Each goal card, when clicked, invokes the `get_goal_detail_view` tool
   for that goal directly (a structured UI action) — **flag this as
   unverified against the live MCP-UI host postMessage mechanism**; if
   direct tool-invocation from a UI click is confirmed unsupported during
   implementation, fall back to injecting a chat message instead, and
   record that finding explicitly in this story's test/implementation
   notes rather than silently shipping a non-functional click target.
6. The "create a new goal" and "just want to talk?" entries inject a plain
   chat message into the conversation when clicked — they do not call any
   tool.
7. Rate limiting is enforced before JWT verification, and JWT verification
   happens before any database call.
8. If the underlying query fails in a handled way, the tool returns a UI
   resource describing the failure rather than letting an unhandled
   exception surface with no renderable content.

## Requirements implemented

- Requirement 4, 6, 7, 8, 9

## Agents likely needed

- [x] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
