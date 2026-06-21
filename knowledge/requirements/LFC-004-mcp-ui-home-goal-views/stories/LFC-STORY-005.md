# LFC-STORY-005: delete_goal MCP tool

## Description

As an MCP client acting on behalf of a signed-in user, I want to delete
one of the user's own goals directly through a tool call, so that the
goal-detail view's delete confirmation can act on the user's choice
without going through a conversational round trip.

## Acceptance criteria

1. A `delete_goal` tool accepts `goal_id`, verifies the caller's JWT using
   the same logic as every existing MCP tool, and soft-deletes
   (`deleted_at = now()`) the caller's own goal — identical semantics to
   the existing REST `DELETE /goals/{id}`, never a hard delete.
2. Calling this tool with a `goal_id` that doesn't exist, isn't owned by
   the caller, or is already soft-deleted fails cleanly (no row is
   updated, no row found to "re-delete").
3. Rate limiting is enforced before JWT verification, and JWT verification
   happens before any database call — same fixed ordering as every other
   MCP tool in this repo.
4. On success, the tool returns a refreshed home-view `EmbeddedResource`
   (the same rendering `get_home_view` would produce for the caller right
   now, reflecting the deletion) rather than a plain success
   acknowledgement, so the host can re-render the updated goal list
   without a second tool call.
5. This tool is documented (in its MCP-exposed description) as intended
   to be called from the UI's confirm-delete action, not as something the
   coaching AI should invoke proactively mid-conversation.

## Requirements implemented

- Requirement 3, 9

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
