# LFC-STORY-002: Create goal endpoint

## Description

As an authenticated user, I want to create a freeform goal with a title and
optional description, so that I can start tracking something I want to work
on.

## Acceptance criteria

1. `POST /goals` with a valid JWT and a body `{"title": "...", "description":
   "..."}` (description optional) creates a goal owned by the requester's
   verified user id and returns `201` with the created goal's full shape
   (`id`, `title`, `description`, `created_at`, `updated_at`).
2. A request with a missing or empty `title` is rejected with `422` before
   any database write.
3. The created goal's `user_id` always equals the verified JWT subject,
   never a client-supplied value — there is no `user_id` field accepted in
   the request body.
4. A missing, malformed, or expired JWT is rejected with `401` before
   reaching handler logic.
5. `POST /goals` is subject to the existing rate limiter, the same as
   `/users/me`.

## Requirements implemented

- Requirement 4, 8, 9

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
