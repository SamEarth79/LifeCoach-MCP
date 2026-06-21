# Analysis: Updates

## Summary

A goal-linked record of what an AI coach and a user agreed on during a
conversation — a "suggestion" in the original framing, rebranded to
"update" because it's bidirectional: either party can originate it, and
what gets stored is whatever the two settled on, not raw AI output. A
later user check-in is also conceptually an update — the table includes a
`source` column (`coaching_update` / `checkin`) so a future check-ins
feature can write into this same table without its own migration, but
this feature only ever writes `coaching_update` rows; the check-in write
path itself is still a separate future feature's job. Stored as a short,
required summary (for cheap, repeated re-injection as context) plus an
optional full transcript (for fidelity, when the caller chooses to attach
one) — never the reverse, to avoid the structured summary silently growing
into the same noisy bulk the summary was meant to avoid. `list_updates`
returns both sources once check-ins exist, since a check-in is relevant
coaching context too. Exposed via two MCP tools (`record_update`,
`list_updates`) mounted on the existing FastAPI app.

## Relevant existing code

- `app/main.py` — the existing FastAPI app (`/health`, `/users/me`, the
  `/goals` CRUD set). First feature to add anything beyond plain REST
  routes — the MCP tool surface needs to be mounted alongside the existing
  routes, not replace them.
- `app/auth.py` — `get_current_user` FastAPI dependency, verifies the
  Supabase JWT (ES256 via JWKS) and returns `CurrentUser(id, email)`. MCP
  tool calls need the same identity verification before touching any data;
  this dependency (or the same verification logic factored out for
  non-HTTP-route use) is the natural reuse point.
- `app/db.py` — `get_rls_connection(user_id)`, opens a Postgres connection
  as the `authenticated` role with `request.jwt.claim.sub` set, so RLS
  policies see the right `auth.uid()`. Every new query for this feature
  should go through this, exactly as `goals` does.
- `app/schemas.py` — Pydantic models (`GoalCreate`, `GoalUpdate`,
  `GoalResponse`). Will need new models for update create/list payloads,
  following the same pattern.
- `migrations/versions/2ae062d3817c_create_goals_table.py` — the `goals`
  table and its RLS policy shape. Notably, its `UPDATE` policy originally
  shipped *without* an explicit `WITH CHECK`, which let Postgres reuse the
  `USING` clause as the post-update check too — silently breaking the
  soft-delete `UPDATE` (it would have failed its own policy's `deleted_at
  IS NULL` check). This was caught and fixed in PR review, not by the
  original mocked-cursor tests. This feature's table is append-only (no
  `UPDATE` policy needed at all), so that specific failure mode doesn't
  recur here, but the lesson — RLS `WITH CHECK` clauses must be reasoned
  about explicitly, not left to default to `USING` — applies directly to
  this feature's `INSERT` policy's `WITH CHECK` subquery.
- `pyproject.toml` — no MCP SDK dependency exists yet. This feature is the
  first to need one (PyPI package `mcp`, `mcp.server.fastmcp.FastMCP`,
  ASGI-mountable). New dependency to add and call out explicitly per
  `coding-style.md`'s dependency rule.
- `knowledge/strategy.md` — originally specified "suggestions" stored both
  structured and as full transcripts, and check-ins as a separate,
  freeform feature. This feature's rebrand (updates, summary-first,
  optional transcript) and the decision to give check-ins a forward-
  compatible `source` column on this same table (rather than their own
  table) refine that direction without contradicting its substance —
  flagged here per `analyze.md`'s rule to surface anything that revises
  recorded strategy, in case `strategy.md` itself should be updated via
  `/strategize` later to reflect the "updates" terminology and the
  shared-table decision.

## Constraints and risks

- **MCP auth integration is the main open technical risk** (unchanged from
  the original analysis): `get_current_user` is a FastAPI route
  dependency; an MCP tool handler doesn't receive a `Request` the same
  way. The JWT verification logic (`_decode_token`) is reusable, but the
  integration point — how the MCP SDK surfaces the incoming Authorization
  credential to a tool handler — must be confirmed against the actual
  installed MCP Python SDK's current documentation during implementation,
  not assumed, per `agents/backend.md`'s external-integration rule and
  `JWT-VERIFICATION-INCIDENT.md`'s precedent.
- **Context-bloat risk is now an explicit design constraint, not just a
  storage detail.** The user's stated goal: updates must stay cheap to
  re-inject as context across a long-running coaching relationship,
  without losing the ability to recover full fidelity when it actually
  matters. The resolved approach (required short `content` summary +
  optional `transcript`) only works if `list_updates` never returns
  `transcript` by default — if a future change makes `list_updates`
  include it "for completeness," the original noise problem comes back.
  This constraint should be enforced explicitly in the tool's contract,
  not left as an implicit convention. Including all `source` values in
  `list_updates`' output (rather than filtering to `coaching_update`
  only) widens what counts as "context" once check-ins exist, but doesn't
  reopen the noise problem itself — each row is still summary-sized
  regardless of source, since `transcript` is excluded either way.
- An update is doubly-scoped: by owning user AND by an existing,
  non-soft-deleted goal of that user's — same shape as the original
  suggestions design. RLS `WITH CHECK` must verify both. The `source`
  column does not change this scoping — it's an attribute of an already-
  scoped row, not an additional ownership dimension.
- **The `source` column is schema-only in this feature** — `record_update`
  hardcodes `coaching_update` and accepts no `source` parameter, so there
  is no path in this feature's code that can produce a `checkin` row.
  Anyone testing `list_updates`' "returns both sources" behavior has to
  insert a `checkin` row directly (e.g. via the test's mocked cursor or a
  manual `INSERT`), not through any tool this feature exposes — this is
  expected, not a gap, but worth being explicit about so `qa` doesn't
  mistake the absence of a real check-in-producing path for a missed
  requirement.
- No size limit is specified for `content`/`transcript` in strategy.md or
  this conversation. `draft.md` should set a reasonable bound on `content`
  given it's meant to stay short (e.g. enforce a max length at the
  application boundary, consistent with `security.md`'s
  validate-at-the-boundary rule); `transcript`, being optional and
  fidelity-oriented, can be left less tightly bounded but still validated
  for sane size limits to avoid unbounded storage growth.
- This is the first feature introducing a third-party SDK dependency
  beyond FastAPI/Supabase-adjacent tooling (`mcp`). Pin it consistent with
  the existing `uv` lockfile practice.

## Open questions

- None blocking for `draft.md`. The MCP-auth integration risk remains
  explicitly deferred to implementation-time verification (not resolved by
  guessing), consistent with how it was already flagged before this
  rebrand.
