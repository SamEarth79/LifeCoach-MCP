# LFC-STORY-004: get_goal_detail_view tool

## Description

As a signed-in user who tapped a goal card, I want a detail screen showing
the goal's full information, its progress, and its recent history, so that
I have real context before continuing to talk about it or deciding to
delete it.

## Acceptance criteria

1. A `get_goal_detail_view` tool accepts `goal_id`, verifies the caller's
   JWT using the same logic as every existing MCP tool, queries the
   caller's own goal (RLS-scoped) plus its most recent updates (same query
   shape as the existing `list_updates`, limited to a small recent count),
   and returns an MCP-UI `EmbeddedResource`.
2. The rendered HTML includes the goal's full title and description, its
   progress indicator (or "no estimate yet" when `progress_percent IS
   NULL`), and a short list of recent updates showing `content` and
   `created_at` only — never `transcript`, consistent with `list_updates`.
3. The rendered HTML includes a "continue this conversation" action that
   injects a chat message into the conversation (e.g. referencing the
   goal by title) — it does not call any tool.
4. The rendered HTML includes a delete action gated behind an explicit
   confirm step (e.g. a two-stage button or inline confirmation), which
   only then invokes the `delete_goal` tool.
5. Calling this tool with a `goal_id` that doesn't exist, isn't owned by
   the caller, or is soft-deleted returns a UI resource describing that
   the goal isn't available, rather than an unhandled error.
6. Rate limiting is enforced before JWT verification, and JWT verification
   happens before any database call.

## Requirements implemented

- Requirement 5, 6, 8, 9

## Agents likely needed

- [x] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
