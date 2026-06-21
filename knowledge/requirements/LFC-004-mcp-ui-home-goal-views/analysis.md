# Analysis: MCP-UI home and goal-detail views

## Summary

Adds an MCP-UI-rendered home screen (greeting + goal cards with a
self-reported AI progress indicator + "just talk" entry + "create goal"
entry) and a goal-detail screen (full description, progress, recent
updates, edit/delete), so the experience doesn't feel purely chat-driven.

## Relevant existing code

- `app/mcp_server.py` — the only existing MCP tool surface (`record_update`,
  `list_updates`). Both follow a fixed pattern this feature must match:
  `enforce_mcp_rate_limit(request)` first (cheap, keyed by IP, before any
  auth), then `verify_bearer_token(authorization_header)` from
  `ctx.request_context.request`, then a query through
  `get_rls_connection(current_user.id)`. New tools (`get_home_view`,
  `get_goal_detail_view`, `set_goal_progress`) must follow this exact
  ordering — it was a real PR review finding on LFC-003 (rate limit was
  briefly ordered after auth, then corrected).
- `app/main.py` — REST CRUD for goals (`create_goal`, `list_goals`,
  `update_goal`, `delete_goal`) and the MCP app mount
  (`app.mount("/mcp", mcp_asgi_app)`, with `streamable_http_path="/"` set on
  the `FastMCP` instance so the external contract stays `/mcp` while the
  mount itself is a scoped prefix, not a catch-all `/`). `list_goals`
  contains no explicit `deleted_at IS NULL` filter — it relies entirely on
  the `goals_select_own` RLS policy (`USING (auth.uid() = user_id AND
  deleted_at IS NULL)`) to exclude soft-deleted rows. Any new query against
  `goals` for this feature should follow the same RLS-only pattern, not
  duplicate the filter in SQL.
- `migrations/versions/2ae062d3817c_create_goals_table.py` — current
  `goals` schema: `id`, `user_id`, `title`, `description`, `created_at`,
  `updated_at`, `deleted_at` (soft delete). **No progress/completion column
  exists.** A new migration is required to add one.
- `migrations/versions/8e5660ff9d7f_create_updates_table.py` — `updates`
  table (`content`, `transcript`, `source`, `created_at`, FK to `goal_id`).
  `list_updates`' existing query (`SELECT content, source, created_at ...
  ORDER BY created_at DESC`) is directly reusable for the "recent updates"
  list on the goal-detail view — no new query pattern needed there.
- `app/schemas.py` — `GoalCreate`/`GoalUpdate`/`GoalResponse`,
  `UpdateCreate`/`UpdateResponse`/`UpdateListItem`. A new
  `set_goal_progress` tool will need its own narrow input schema (goal_id,
  percentage 0–100, optional rationale string), following the existing
  `UpdateCreate`-style validator pattern (reject out-of-range/blank values
  at the boundary).
- `app/rate_limit.py` — `enforce_mcp_rate_limit(request, user_id=None)`,
  keyed by IP via `get_client_ip`, shared between REST and MCP. Reusable
  as-is for new tools; no changes needed.
- `app/auth.py` — `verify_bearer_token`, `get_current_user` (now delegates
  to it). Reusable as-is.
- **No LLM/AI SDK dependency exists anywhere in `pyproject.toml`.** This
  backend is purely a tool server; the "coaching AI" is the external MCP
  client (e.g. Claude Desktop) calling these tools, not something this
  FastAPI process runs itself. This directly affects the progress-bar
  design: a percentage cannot be computed server-side. It must be
  self-reported by the calling AI through a new tool call
  (`set_goal_progress`), the same pattern `record_update` already
  establishes for committing AI/user-agreed outcomes.
- `mcp` package (`mcp>=1.28`, already installed) — confirmed via direct
  inspection (`mcp.types.EmbeddedResource`, `TextResourceContents`) that the
  installed SDK supports returning embedded resources from a tool call,
  which is the underlying mechanism the MCP-UI convention builds on (an
  `EmbeddedResource` with a `ui://` URI and an HTML/text mimetype,
  rendered by a capable host). This confirms `strategy.md`'s "raw MCP-UI
  spec from Python, not the TS helper SDK" decision is mechanically
  feasible with no new dependency for the rendering mechanism itself.
- `tests/feature/test_mcp_record_update.py`, `test_mcp_list_updates.py` —
  established test convention for new tools: a real wire-protocol test
  (`initialize` → `notifications/initialized` → `tools/call` via
  `httpx.ASGITransport`) against an isolated `FastMCP` test instance built
  from the real tool function, not a mock. New UI tools should follow the
  same pattern.

## Constraints and risks

- **Unverified: whether a UI click can directly trigger a tool call.**
  The installed Python `mcp` SDK only confirms the *content delivery*
  mechanism (embedded HTML resources); whether the MCP-UI convention's
  host-side `postMessage` protocol supports a UI element invoking a tool
  call directly (as opposed to only injecting a chat message) is a
  host/client-side behavior not verifiable by inspecting this repo's
  Python dependencies. Flagging this explicitly as an assumption to
  confirm against the live MCP-UI spec/a real host during implementation,
  not something to silently bake into the architecture as settled fact —
  same discipline as `JWT-VERIFICATION-INCIDENT.md`'s precedent. If
  direct tool-invocation from a UI click turns out unsupported, the
  fallback is the UI injecting a chat message (e.g. "Let's talk about
  <goal title>"), which is unambiguously supported by every MCP-UI host.
- **Two pre-existing, unresolved caveats from LFC-003 become more visible
  here**, since this is the first feature to read back per-user data
  through MCP specifically for display (not just tool-call request/response
  text): (1) RLS policies have never been verified against a live
  Postgres/Supabase instance in any feature so far, only at the app/query
  level; (2) MCP's `TransportSecurityMiddleware.allowed_hosts` defaults to
  `[]`, which would 421-reject all `/mcp` traffic (including these new UI
  resources) behind a real reverse proxy until configured. Neither is
  caused by this feature, but both should be resolved before this feature
  is exercised against a real deployed host.
- **`strategy.md` conflict, surfaced to the user and accepted as a change**:
  `strategy.md`'s "MCP-UI usage" section currently states MCP-UI is used
  "only for read-only displays" and "all input... stays conversational
  text." This feature introduces genuinely interactive UI (clickable goal
  cards that trigger a tool call, an inline create-goal action, a
  confirm-delete UI). This analysis does not silently override that
  recorded strategy — it should be updated via `/strategize` separately,
  or explicitly noted as superseded in this feature's own docs, since
  `/design` does not write to `strategy.md` itself.
- **No existing "general/goal-less conversation" concept in the schema.**
  Confirmed by inspecting `migrations/versions/8e5660ff9d7f_create_updates_table.py`:
  `updates.goal_id` is `NOT NULL`. Per the user's decision, the "just want
  to talk" entry point is purely transient/in-session and not persisted,
  so no schema change is needed for it — it only needs to inject a neutral
  conversational opener, not call any new tool.

## Open questions

(None outstanding — both items raised during analysis were resolved with
the user before this file was finalized: the progress-source approach, and
the strategy.md conflict being explicitly surfaced rather than silently
overridden.)
