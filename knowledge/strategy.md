# Strategy

## 2026-06-19

**Product & audience**
- Personal life-coach MCP server. Audience at launch is the user plus a few
  friends/family — a small trusted group, not a public signup product.
  Reasoning: keeps auth/multi-tenancy concerns light while still being a
  real "prod" release for real users, not just a solo tool.
- v1 scope is: sign in, create freeform goals, conversational coaching with
  stored suggestions, freeform check-ins, and progress views via MCP-UI.
- Explicitly out of scope for v1: goal templates/categories,
  notifications/reminders, multi-device sync beyond what auth already
  gives, analytics, admin dashboard, monitoring/alerting stack (e.g.
  Sentry), CI/CD beyond basic deploy-on-push, automated backups beyond
  Supabase's defaults.

**Architecture**
- Remote-hosted MCP server (not a locally-run/npx server) so MCP-UI and
  sign-in work the way a real product needs them to.
- Backend/MCP server is Python + FastAPI. Considered Django (user's
  background) but chose FastAPI for this project specifically.
- MCP-UI is implemented directly against the raw MCP-UI spec from Python,
  not the TS helper SDK. Reasoning: MCP-UI tooling is more mature in
  TypeScript, but this project's UI needs are light (read-only progress
  views and simple selections, not rich interactive dashboards), so the
  manual-spec approach is low-risk and keeps the stack in Python.
- Hosting on a simple PaaS (Railway/Render/Fly.io-class) — low ops
  overhead, fits a small user base, easy git-based deploys.

**Data & auth**
- Supabase Auth for sign-in; Supabase Postgres for storage.
- "Memory" is not a special MCP protocol feature — it's plain relational
  tables (goals, suggestions, check-ins, transcripts) that MCP tools query
  and re-inject as context on each call. No vector DB needed for v1; only
  reconsider if free-text retrieval over large transcript volumes becomes
  a real need.
- Goals are freeform: title + description, no fixed category/template
  schema.
- Suggestions are stored both as structured, goal-linked records (for
  querying/display) and as full conversation transcripts (for fidelity).
- Check-ins are fully freeform conversational entries — no structured
  status picker (e.g. no on-track/behind selector).
- DB migrations managed with Alembic from day one, since the schema will
  change repeatedly during early use.
- Goals and check-ins use soft deletes, not hard deletes — losing months of
  someone's progress log to an accidental delete is a real failure mode for
  a life-coach app.

**MCP-UI usage**
- Primarily read-only displays: goal list, progress views, suggestion
  history. Most input (new goals, check-ins, suggestions) stays
  conversational text, not structured UI input — keeps the UI layer simple
  given the light UI requirements.
- Exception (added 2026-06-25, goal todos feature): the goal detail view's
  todo list has interactive checkboxes that call a `toggle_todo` tool
  directly from the UI. Scoped narrowly to toggling todo completion only —
  creating, editing, reordering, or deleting todos still happens
  conversationally through the LLM. Reasoning: marking a step done is a
  single, low-risk, unambiguous action well-suited to a tap; it doesn't
  carry the ambiguity of freeform input that the read-only-by-default rule
  was meant to avoid.

**Security & technical baseline (folded into v1, not deferred)**
- Per-user data isolation enforced via Supabase Row Level Security (RLS)
  policies on every table, in addition to app-level authorization checks in
  FastAPI — defense in depth, since this stores personal goal data.
- FastAPI validates Supabase-issued JWTs (signature + expiry) on every
  request; never trusts a client-supplied user ID directly.
- Rate limiting on auth and MCP endpoints, even given the small trusted
  user base.
- Secrets (Supabase keys, any LLM API keys) via environment variables on
  the PaaS only; never committed. Only `.env.example` with placeholders
  goes in the repo.
- Basic server-side logging of failed auth attempts and unhandled errors,
  without logging PII or secrets — enough to debug "it lost my data"
  reports without building a full observability stack.
- A health check endpoint, since the chosen PaaS platforms use it for
  deploy/restart logic and skipping it causes flaky deploys.
