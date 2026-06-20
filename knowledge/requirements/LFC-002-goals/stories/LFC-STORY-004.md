# LFC-STORY-004: Edit goal endpoint

## Description

As an authenticated user, I want to edit a goal's title and/or description,
so that I can correct or refine it after creating it.

## Acceptance criteria

1. `PATCH /goals/{goal_id}` with a valid JWT and a body containing `title`
   and/or `description` updates only the provided field(s) on a goal owned
   by the requester, bumps `updated_at`, and returns `200` with the updated
   goal.
2. Editing a goal that doesn't exist, isn't owned by the requester, or is
   already soft-deleted returns `404` — the app-level check never trusts a
   client-supplied id alone, in addition to RLS already hiding the row.
3. A request with an explicitly empty `title` (e.g. `""`) is rejected with
   `422`; `description` may be set to `null`/empty.
4. A missing, malformed, or expired JWT is rejected with `401` before
   reaching handler logic.
5. `PATCH /goals/{goal_id}` is subject to the existing rate limiter.

## Requirements implemented

- Requirement 6, 8, 9

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
