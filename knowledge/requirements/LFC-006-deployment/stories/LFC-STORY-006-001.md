# LFC-STORY-006-001: Containerize and configure the app for Render's free tier

## Description

As the developer, I want a Dockerfile and Render Blueprint that build and
run this app correctly, so that I can deploy it to Render's free tier
without manually configuring build/start commands in the dashboard.

## Acceptance criteria

1. `Dockerfile` builds the image using `uv sync --frozen` against the
   committed `uv.lock`, and starts `uvicorn app.main:app` bound to
   `0.0.0.0:$PORT`.
2. `docker build` succeeds locally; `docker run` with the three required
   env vars set returns a healthy `GET /health` response.
3. `render.yaml` declares the web service (Dockerfile-based), `GET /health`
   as the health check path, and `SUPABASE_URL`/`SUPABASE_ANON_KEY`/
   `DATABASE_URL` as `sync: false` (dashboard-set, never committed) env
   vars.
4. `.dockerignore` excludes `.venv/`, `.env`, `.git/`, `__pycache__/`,
   `.pytest_cache/`.
5. No real secret value appears anywhere in any committed file.

## Requirements implemented

- Requirement 1, 2, 3, 4, 5

## Agents likely needed

- [ ] frontend
- [ ] backend
- [x] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
