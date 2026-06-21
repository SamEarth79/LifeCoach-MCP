# LFC-STORY-002: set_goal_progress tool

## Description

As the coaching AI acting on behalf of a signed-in user, I want to record
a progress estimate for one of the user's goals after a conversation, so
that the home and goal-detail views have something real to display instead
of nothing.

## Acceptance criteria

1. A `set_goal_progress` tool accepts `goal_id`, `percentage` (integer,
   0–100), and an optional short `rationale` string, verifies the caller's
   JWT using the same logic as every existing MCP tool, and updates the
   caller's own goal's `progress_percent`.
2. Rejecting an out-of-range `percentage` (e.g. negative, or above 100)
   happens at the schema/validation boundary, before any database call.
3. Calling this tool with a `goal_id` that doesn't exist, isn't owned by
   the caller, or is soft-deleted fails (no row is updated) — enforced by
   the existing `goals_update_own` RLS policy, not a duplicated app-level
   check.
4. Rate limiting is enforced before JWT verification, and JWT verification
   happens before any database call — same fixed ordering as
   `record_update`/`list_updates`.
5. The tool's MCP-exposed description explicitly tells the calling AI this
   is for *its own* periodic self-assessment after a conversation, not
   something the rendered UI calls — preventing the AI from treating it as
   a user-facing action.
6. A successful call returns the updated `goal_id` and `percentage` as a
   plain tool result — not a UI resource, since this call isn't
   UI-initiated.

## Requirements implemented

- Requirement 2, 9

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
