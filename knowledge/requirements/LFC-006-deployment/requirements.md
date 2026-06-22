# Requirements: LFC-006-deployment

## Functional requirements

1. A `Dockerfile` exists that builds and runs the FastAPI app via `uv`,
   binding to `0.0.0.0:$PORT` (not a hardcoded port).
2. A `render.yaml` Blueprint exists declaring the web service, the
   Dockerfile build, and the three required environment variables
   (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL`) as
   dashboard-set secrets, never committed with real values.
3. `GET /health` is configured as Render's health check path.
4. A `.dockerignore` excludes local-only/sensitive files
   (`.venv/`, `.env`, `.git/`, `__pycache__/`, `.pytest_cache/`) from the
   build context.
5. The Docker image builds successfully and runs `GET /health` correctly
   locally (`docker build` + `docker run`, verified before relying on
   Render's own build).

## Non-functional requirements

- **Security**: no real secret values committed anywhere in
  `Dockerfile`/`render.yaml`/`.dockerignore`. `.env` must never be copied
  into the image.
- **Reproducibility**: dependency install uses the committed `uv.lock`
  (`uv sync --frozen`), not an unpinned resolve.

## Out of scope

- Actually creating the Render account / connecting the GitHub repo /
  setting the real environment variable values in Render's dashboard —
  manual steps outside this codebase, walked through separately once
  this story's files exist.
- Configuring Supabase's OAuth "Site URL"/"Authorization Path" — depends
  on the deployed URL existing first; tracked as a follow-up.
- A custom domain, CDN, or any scaling/multi-region configuration —
  unnecessary for a free-tier, small-trusted-user-base deployment per
  `strategy.md`.
- Engineering around free-tier cold starts (e.g. a keep-alive cron) — see
  architecture.md's explicit rationale for accepting this tradeoff as-is.
