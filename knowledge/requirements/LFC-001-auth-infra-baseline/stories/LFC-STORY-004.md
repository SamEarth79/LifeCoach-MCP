# LFC-STORY-004: Rate limiting on auth-adjacent endpoints

## Description

As the developer, I want auth-adjacent backend endpoints to be
rate-limited, so that the small trusted user base is still protected
against brute-force attempts on authentication.

## Acceptance criteria

1. Requests to auth-adjacent FastAPI endpoints (e.g. `/users/me`, and any
   other endpoint that participates in establishing or confirming
   identity) are rate-limited per client (e.g. per IP or per token).
2. Exceeding the rate limit returns a 429 response rather than an
   unhandled error or silent pass-through.
3. The rate limit configuration (thresholds/window) is set via environment
   variables or a settings module, not hardcoded magic numbers scattered
   in route code.

## Requirements implemented

- Requirement 10, Non-functional: Security (rate limiting)

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
