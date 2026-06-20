# LFC-STORY-001: FastAPI app skeleton, env config, and health check

## Description

As the developer, I want a runnable FastAPI app with environment-based
configuration and a health check endpoint, so that there's a deployable
baseline before any auth or data logic is added.

## Acceptance criteria

1. A FastAPI app starts locally and exposes `GET /health`, returning a 200
   response with a simple liveness payload, with no authentication
   required.
2. App configuration (Supabase URL, Supabase keys, DB connection string)
   is read from environment variables via a settings module — no secret
   values are hardcoded anywhere in source.
3. A `.env.example` file is committed with placeholder values for every
   required environment variable; `.env` is listed in `.gitignore`.
4. `GET /health` returns a non-200/error response if the configured DB
   connection cannot be established (so the PaaS can detect a broken
   deploy).

## Requirements implemented

- Requirement 8 (health check endpoint)
- Non-functional: Security (secrets via env vars, `.env.example`),
  Reliability (`/health` reflects real app health)

## Agents likely needed

- [ ] frontend
- [x] backend
- [x] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
