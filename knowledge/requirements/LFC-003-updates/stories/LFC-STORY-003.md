# LFC-STORY-003: list_updates tool

## Description

As an MCP client acting on behalf of a signed-in user, I want to retrieve
past updates for one of my goals, so that I can use them as context in an
ongoing coaching conversation without re-reading entire past
conversations.

## Acceptance criteria

1. A `list_updates` tool accepts a `goal_id`, verifies the caller's
   Supabase JWT using the same verification logic as the existing REST
   endpoints and `record_update`, and returns the caller's own updates
   for that goal, each with exactly `content`, `source`, and `created_at`
   — never `transcript`, even if one was stored, so repeated context
   re-injection stays cheap regardless of how many updates have
   accumulated.
2. Results are not filtered by `source` — a row with `source = 'checkin'`
   (written by a future feature, not this one) is returned alongside
   `coaching_update` rows for the same goal, since both are relevant
   coaching context. This feature has no way to produce a `checkin` row
   itself, so this criterion is testable only by inserting one directly
   via the test's mocked cursor, not by exercising any tool in this
   feature.
3. A goal with no updates yet returns an empty result, not an error.
4. Updates belonging to a different user are never returned, even if they
   exist in the table for the same `goal_id`.
5. A missing, malformed, or expired JWT is rejected before any tool logic
   runs or any database call is made.
6. `list_updates` calls are rate-limited, consistent with the existing
   REST endpoints and `record_update`.

## Requirements implemented

- Requirement 6, 7, 8

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
