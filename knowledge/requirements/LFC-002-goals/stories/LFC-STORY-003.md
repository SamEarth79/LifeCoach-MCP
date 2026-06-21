# LFC-STORY-003: List goals endpoint

## Description

As an authenticated user, I want to list my own active goals, so that I can
see what I'm currently working on.

## Acceptance criteria

1. `GET /goals` with a valid JWT returns `200` with a JSON array of the
   requester's own active (non-soft-deleted) goals, each with `id`, `title`,
   `description`, `created_at`, `updated_at`.
2. A user with no goals gets `200` with an empty array, not an error.
3. Soft-deleted goals never appear in the response.
4. Goals owned by a different user never appear in the response, even if
   they exist in the table.
5. A missing, malformed, or expired JWT is rejected with `401` before
   reaching handler logic.
6. `GET /goals` is subject to the existing rate limiter.

## Requirements implemented

- Requirement 5, 8, 9

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
