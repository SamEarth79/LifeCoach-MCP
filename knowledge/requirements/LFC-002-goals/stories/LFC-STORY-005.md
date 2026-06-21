# LFC-STORY-005: Soft-delete goal endpoint

## Description

As an authenticated user, I want to delete a goal without permanently losing
its data, so that I don't lose months of progress history to an accidental
delete.

## Acceptance criteria

1. `DELETE /goals/{goal_id}` with a valid JWT sets `deleted_at` on a goal
   owned by the requester and returns `204` with no body.
2. No SQL `DELETE` statement is ever issued against the `goals` table by
   this endpoint — only an `UPDATE` setting `deleted_at`.
3. Deleting a goal that doesn't exist, isn't owned by the requester, or is
   already soft-deleted returns `404`.
4. After soft-deletion, the goal no longer appears in `GET /goals` and a
   `PATCH` on it returns `404`.
5. A missing, malformed, or expired JWT is rejected with `401` before
   reaching handler logic.
6. `DELETE /goals/{goal_id}` is subject to the existing rate limiter.

## Requirements implemented

- Requirement 7, 8, 9

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
