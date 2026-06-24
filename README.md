# LifeCoach

A personal life-coach, built as a remote [MCP](https://modelcontextprotocol.io) server that runs inside Claude. Talk to Claude like you would a coach — set goals, log progress, check in — and it remembers everything across conversations, backed by a real database instead of chat history.

Live at: `https://lifecoach-api.onrender.com`

## What it does

- **Goals**: create goals conversationally, just by telling Claude what you want to work on.
- **Coaching updates**: Claude logs a concise summary whenever you and it settle on something concrete — not a transcript dump, an actual note.
- **Progress tracking**: Claude keeps a 0–100 progress estimate per goal, shown as a progress ring.
- **Home & goal-detail views**: a real UI rendered inside the Claude chat (not just text) — a card per goal with progress, and a detail screen with recent updates and a delete action.
- **`/coach`**: an explicit prompt that opens a coaching session already grounded in your current goals, instead of starting from a blank slate.

Everything is scoped to your own account — goals, updates, and progress are private per user, enforced at the database level (Postgres Row-Level Security via Supabase), not just in application code.

## How to use it

1. Get access (see [Access](#access) below) — you'll need a Supabase login.
2. In Claude Desktop: **Settings → Connectors → Add custom connector**, and point it at `https://lifecoach-api.onrender.com/mcp`.
3. Claude will walk you through OAuth login the first time you connect.
4. Start a new chat and either:
   - Just talk: *"I want to get back into running, training for a 5k"* — Claude will create the goal and start coaching.
   - Type `/coach` (the connector's coach prompt) to open a session grounded in your current goals.
   - Ask to see your goals — Claude will show the home view inside the chat.

## Access

This isn't a public signup product — it's a small, invite-only group. To get access, email **samarthmm.work@gmail.com** and I'll set up your account.

## Architecture

- **API**: FastAPI (`app/main.py`) — REST endpoints for goals/users, plus the OAuth consent/login page (`app/oauth_consent.py`) Supabase's OAuth 2.1 server redirects to.
- **MCP server**: built on the official `mcp` SDK's `FastMCP` (`app/mcp_server.py`), mounted into the same FastAPI app at `/mcp`. Tools and a prompt are listed below.
- **UI**: home/goal-detail screens (`app/ui_templates.py`) are MCP Apps ([SEP-1865](https://modelcontextprotocol.io/seps/1865-mcp-apps-interactive-user-interfaces-for-mcp)) — static HTML+JS resources rendered inside a sandboxed iframe in Claude, talking back to the server over a JSON-RPC/postMessage bridge.
- **Auth**: Supabase Auth (Postgres + OAuth 2.1 Server). MCP tool calls are authenticated via a Supabase-issued JWT bearer token, verified against Supabase's JWKS.
- **Database**: Postgres (Supabase), accessed via `psycopg`, migrated with Alembic. Row-Level Security policies enforce per-user data isolation at the database layer.
- **Deployment**: Dockerized, deployed on Render's free tier (see `render.yaml`, `Dockerfile`).

### MCP tools

| Tool | Purpose |
|---|---|
| `create_goal` | Create a new goal (title + optional description) |
| `record_update` | Log a concise coaching update for a goal |
| `list_updates` | Retrieve past updates for a goal |
| `set_goal_progress` | Record Claude's 0–100 progress self-assessment for a goal |
| `get_home_view` | Render the home screen UI (greeting + goal cards) |
| `get_goal_detail_view` | Render the goal-detail screen UI |
| `delete_goal` | Soft-delete a goal |

### MCP prompt

| Prompt | Purpose |
|---|---|
| `coach` | Explicit, user-invoked entry point that opens a coaching session pre-loaded with your real home-view data |

## Local development

Requires [`uv`](https://docs.astral.sh/uv/) and a Supabase project.

```bash
uv sync
cp .env.example .env   # fill in SUPABASE_URL, SUPABASE_ANON_KEY, DATABASE_URL
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8001
```

Run the test suite:

```bash
uv run pytest
```

## Tech stack

Python, FastAPI, the official MCP Python SDK, Supabase (Postgres + Auth), Docker, Render.
