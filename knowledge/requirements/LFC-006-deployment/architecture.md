# Architecture: LFC-006-deployment

> Filled in by `draft.md` during `/design`, informed by a lightweight
> analysis pass (this is infra-only, well-understood from prior
> conversation — no separate `analysis.md`/gather round was needed; the
> codebase already has everything required: a `uv`-managed `pyproject.toml`,
> no existing Dockerfile/`render.yaml`/`Procfile`).

## Approach

Deploy the existing FastAPI app (already runnable locally via
`uv run uvicorn app.main:app`) to Render's free web-service tier, per the
verified-current (not assumed) free-tier comparison: Render still offers a
genuine no-credit-card free tier (750 instance-hours/month, auto HTTPS,
git-based deploy); Fly.io and Railway no longer do. Render auto-detects a
Dockerfile if present, so containerize the app explicitly rather than
relying on a buildpack, for reproducibility and consistency with `uv`'s
lockfile-based dependency resolution.

## Components touched

- **Frontend**: none.
- **Backend**: none — no application code changes, only deployment
  packaging.
- **Infrastructure**:
  - New `Dockerfile` — multi-stage, `uv`-based, runs
    `uvicorn app.main:app` bound to `0.0.0.0:$PORT` (Render injects `PORT`
    at runtime; must not hardcode `8001`).
  - New `render.yaml` (Render's Blueprint spec) — defines the web service,
    its build/start commands (or Dockerfile path), the existing `/health`
    endpoint as the health check path, and declares (but does not set
    values for) the required environment variables
    (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL`) as
    `sync: false` secrets the user sets manually in Render's dashboard —
    never committed.
  - `.dockerignore` — exclude `.venv/`, `.env`, `__pycache__/`,
    `.pytest_cache/`, `.git/` from the build context.

## Data flow

1. User pushes to `main` (or connects the repo once; Render auto-deploys
   on push thereafter).
2. Render builds the Docker image from `Dockerfile`, injects the
   dashboard-configured env vars, and starts the container.
3. Render's health check polls `GET /health` (already implemented,
   returns `503` if the database is unreachable) before marking the
   deploy live.
4. The resulting public HTTPS URL is what gets configured as Supabase's
   OAuth "Site URL" (separate manual step, outside this story's scope —
   tracked as a follow-up once the URL exists).

## Data model changes

None.

## Key decisions

- **Decision**: Render over Fly.io/Railway.
  **Rationale**: verified via live web search (not assumed from training
  data) that Render is the only one of the three still offering a real,
  no-credit-card free tier as of now; Fly.io and Railway both moved to
  trial-credit-only models.
- **Decision**: Dockerfile-based deploy, not Render's auto-detected
  Python buildpack.
  **Rationale**: this project uses `uv` with a committed `uv.lock`; a
  Dockerfile gives explicit, reproducible control over the exact install
  step (`uv sync --frozen`) rather than relying on Render's buildpack
  guessing the right Python tooling.
- **Decision**: free-tier cold starts (~30-60s after 15 min idle) are
  accepted as-is for now, not engineered around (e.g. no keep-alive
  pinger).
  **Rationale**: per `strategy.md`, this is explicitly a small
  trusted-user-base product, not a polished public launch — a cold start
  on an infrequent personal/beta tool is an acceptable tradeoff for zero
  cost, and engineering around it (a cron keep-alive ping) would be
  premature optimization for a problem that hasn't actually been felt yet.
