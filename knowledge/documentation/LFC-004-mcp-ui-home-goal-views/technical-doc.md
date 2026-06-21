# Technical Deep Dive: MCP-UI home and goal-detail views (LFC-004)

## What this feature is, and why it exists

Two interactive screens — a home view and a goal-detail view — rendered as
HTML and returned from MCP tool calls, viewable inside an MCP-UI-capable
host. Before this feature, the only way to interact with LifeCoach was
conversational text through `record_update`/`list_updates`
(LFC-003-updates); `strategy.md` records an explicit product goal that the
app should not feel purely chat-driven. This feature is the first concrete
step toward that: a user opens the app and sees a calm, structured "here's
where your goals stand" screen rather than an empty chat box, and can tap
into a goal for detail without typing anything.

Four new MCP tools, all in `app/mcp_server.py`:

- `get_home_view` — greeting, one card per active goal (progress + "updated
  X" if any updates exist), a "create a new goal" entry, a "just want to
  talk?" entry, or an empty-state/failure-state variant.
- `get_goal_detail_view(goal_id)` — full title/description, progress, up to
  5 recent updates, a "continue this conversation" action, and a two-stage
  delete-confirm action.
- `set_goal_progress(goal_id, percentage, rationale)` — lets the calling
  coaching AI record a 0–100 self-assessment after a conversation. Not
  called by the rendered UI.
- `delete_goal(goal_id)` — soft-deletes a goal and returns a refreshed home
  view in the same round trip.

Plus a new `goals.progress_percent` column
(`migrations/versions/66f94137137d_add_goals_progress_percent.py`) and the
rendering layer itself, `app/ui_templates.py`.

## The rendering mechanism: `EmbeddedResource` over `ui://`

MCP tools normally return plain JSON-like results. To render an actual
screen instead, `get_home_view`/`get_goal_detail_view`/`delete_goal` return
an `EmbeddedResource` (from `mcp.types`) wrapping a `TextResourceContents`
with a `ui://` URI and `mimeType="text/html"`:

```python
def _build_embedded_html_resource(uri: str, html_text: str) -> EmbeddedResource:
    return EmbeddedResource(
        type="resource",
        resource=TextResourceContents(uri=uri, mimeType="text/html", text=html_text),
    )
```

`_build_home_view_resource` calls this with `uri="ui://home-view"`;
`_build_goal_detail_view_resource` with `uri="ui://goal-detail-view"`. Both
HTML bodies are generated server-side in `app/ui_templates.py` via plain
Python string templates — no separate JS framework or build step, matching
`strategy.md`'s "light UI needs, raw-spec, no TS helper SDK" direction.
This mechanism (the `EmbeddedResource`/`TextResourceContents` shape actually
parsing and serializing through the installed `mcp` SDK, with
`uri.scheme == "ui"` and `mimeType == "text/html"`) was verified directly
against the installed package during LFC-STORY-003, not assumed from
documentation — see `test-results.md`'s LFC-STORY-003 section.

## Data contracts: `HomeViewData`/`GoalDetailViewData`

Both view-data dataclasses live in `app/ui_templates.py`, separate from the
tool functions in `app/mcp_server.py` — rendering logic and tool/DB logic
are different responsibilities, each tested independently.

- `HomeGoalCard` / `HomeViewData`: `progress_percent: int | None` —`None`
  means "no estimate yet," a distinct rendering state from a real `0`
  (dashed ring + em-dash label vs. an actual `0%`). `last_updated_at: str |
  None` controls whether an "Updated <date>" line renders at all.
  `HomeViewData.error` is mutually exclusive with `goals`/empty-state
  rendering — when set, the renderer produces a failure-state UI and
  nothing else, even if `goals` is simultaneously non-empty (defensive
  contract on the renderer, not reachable from `get_home_view` itself).
- `GoalDetailUpdate` / `GoalDetailViewData`: mirrors the same
  `None`-vs-`0` progress contract; `recent_updates` carries only `content`
  and `created_at` per item — never `transcript`, the same discipline
  `list_updates` already established. `GoalDetailViewData.error` follows
  the same precedence rule as `HomeViewData.error`.

### Why progress is self-reported, not computed

There is no LLM or AI SDK anywhere in this backend — it is a tool server
only, confirmed during design analysis. A goal's "progress" therefore has
no server-side source of truth to derive from updates or timestamps. The
alternative considered was a recency/frequency heuristic (e.g. "3 updates
in the last week = high progress"); this was explicitly rejected in favor
of a real judgment call, so `set_goal_progress` exists for the calling
coaching AI to record its own 0–100 estimate after a conversation, the same
pattern `record_update` already establishes for committing an AI/user-
agreed outcome. `rationale` is accepted and validated (`GoalProgressUpdate`
in `app/schemas.py`, max 500 chars) but never persisted — there is no
`rationale` column on `goals`; this is intentional, not a bug, since
LFC-STORY-001's migration only added `progress_percent`.

## Card-click-calls-tool vs. chat-message-injection: the design split

Two distinct interaction patterns exist in the rendered HTML, both driven
by inline JS in `app/ui_templates.py`'s `_SCRIPT`/`_DETAIL_SCRIPT`:

- `lifecoachSendTool(toolName, params)` — `window.parent.postMessage({type:
  "tool", payload: {toolName, params}}, "*")`. Used only for the goal
  card's `onclick` (`get_goal_detail_view`) and the delete-confirm button's
  `onclick` (`delete_goal`).
- `lifecoachSendPrompt(prompt)` — `window.parent.postMessage({type:
  "prompt", payload: {prompt}}, "*")`. Used for "create a new goal," "just
  want to talk," and "continue this conversation."

The split follows `strategy.md`/`requirements.md` directly: goal creation
and conversation stay conversational text — they are UI shortcuts *into*
the chat, not new tool calls — while navigation (home → detail) and the
explicit delete-confirm action are structured actions the UI invokes
directly. `delete_goal` is a new MCP tool specifically because there was
previously no way for an MCP client to delete a goal at all (delete was
REST-only); no equivalent "edit" tool was added, since edits stay purely
conversational, consistent with goals being freeform text.

## XSS escaping, and the JS-string-breakout risk class that was avoided

Every piece of user-controlled text (`greeting_name`, goal `title`,
`description`, update `content`, `error`) is passed through `html.escape`
(default `quote=True`) before interpolation into the HTML body. This was
verified with actual constructed `<script>alert(1)</script>` payloads, not
just read as a claim — see `test-results.md`'s LFC-STORY-003/004 sections.

A more specific risk was identified and explicitly recorded, not silently
assumed safe: the home view's goal card interpolates `card.id` into a
JS-string context inside an `onclick` attribute
(`onclick="lifecoachSendTool('get_goal_detail_view', { goal_id: '{safe_id}' })"`).
`html.escape`'s HTML-entity-encoding of a quote character prevents breaking
out of the *HTML attribute*, but does not fully neutralize a JS-string-
context breakout for an arbitrary untrusted string, because the browser
HTML-decodes the attribute value before the `onclick` body actually
executes as JS. This is not exploitable today — `card.id` is always a
server-generated UUID from `goals.id`, never user-controlled text — but is
flagged so a future change doesn't carelessly interpolate a different,
non-UUID value into the same template.

The goal-detail view's "continue this conversation" action faces exactly
this risk for real free text — the goal *title* — and avoids it
structurally rather than relying on escaping alone: the title is rendered
only as `html.escape`d DOM text content
(`<p class="detail-title" id="goal-title-{safe_id}">{safe_title}</p>`),
never inside any `onclick` string. `lifecoachContinueGoal(goalId)` reads
the title back at click time via
`document.getElementById("goal-title-" + goalId).textContent` — which
returns the browser-decoded plain string, not re-parsed markup — and passes
that as a `postMessage` payload field (`lifecoachSendPrompt(...)`), never
as a JS-string-literal insertion. Every `onclick` attribute in the
goal-detail document was confirmed, by extracting and inspecting them
programmatically against a hostile title containing a double-quote,
single-quote, and raw `<script>` tag, to contain only the trusted UUID and
never any fragment of the title (see `test-results.md`'s LFC-STORY-004
hostile-input re-verification section). This DOM-`textContent` technique —
read free text back from an escaped DOM node rather than ever interpolating
it into a JS string literal — is the pattern to follow for any future
screen that needs to reference free text from a click handler.

## `delete_goal` returns a refreshed home view, not a plain acknowledgement

On a successful soft-delete, `delete_goal` calls the same
`_fetch_home_view_data(user_id)` / `_build_home_view_resource(...)` helper
pair `get_home_view` itself uses (the former was extracted out of
`get_home_view`'s body specifically to give `delete_goal` a second real
call site, rather than duplicating the query) and returns that
`ui://home-view` resource directly. This avoids the host needing to make a
second `get_home_view` call just to reflect the deletion — the delete
action is a single round trip from the UI's perspective. On the
no-row-matched failure path (goal not found / not owned / already deleted),
no commit happens and `_fetch_home_view_data` is never even called — a
clean `ValueError` is raised instead, confirmed via
`AsyncMock(wraps=...)` in the unit tests, not inferred from query counts
alone.

## Known risks / unresolved

**1. TOP ITEM — unverified MCP-UI host `postMessage` tool-invocation
assumption.** No live MCP-UI host was available in any sandbox across all
five stories of this feature. Every interactive element this feature ships
— card-click navigation (`lifecoachSendTool('get_goal_detail_view', ...)`),
the delete-confirm action (`lifecoachSendTool('delete_goal', ...)`), and
every chat-injection entry — was implemented and tested only against the
assumption that a real MCP-UI host's `postMessage` convention supports a UI
element invoking a tool call directly, shaped like `{type: "tool", payload:
{toolName, params}}`. If a real host only supports chat-message injection
and not direct tool invocation, **every structured UI action in this
feature** must fall back to `lifecoachSendPrompt`-style injection instead.
This is not a routine caveat — it is a potential rework of this feature's
core interaction model, and must be confirmed against the actual MCP-UI
spec or a real host before this feature is considered production-ready.

**2. RLS policies unverified against a live database.** No Docker daemon
or local Postgres was available in any sandbox session across all five
stories. Every RLS-dependent behavior in this feature —
`goals_select_own`'s cross-user/soft-delete exclusion for
`get_home_view`/`get_goal_detail_view`, `goals_update_own`'s enforcement for
`set_goal_progress`/`delete_goal` — was verified only by inspecting
executed SQL text (confirming no app-level `user_id` filter exists) and by
mocking zero-row responses to simulate RLS rejection. Before production:
seed two users' goals, soft-delete one, and confirm
`get_home_view`/`get_goal_detail_view` never leak another user's or a
soft-deleted goal, and that `set_goal_progress`/`delete_goal` reject a
`goal_id` not owned by the caller.

**3. MCP `TransportSecurityMiddleware.allowed_hosts` deployment risk,
carried forward unresolved from LFC-003-updates.** Still defaults to `[]`
with DNS-rebinding protection on; behind a real reverse proxy this would
421-reject every `/` (MCP) request, including all four tools this feature
adds, unless `allowed_hosts` is explicitly configured for the deployed
hostname.

**4. `strategy.md`'s "MCP-UI is read-only" statement is now stale.** This
feature ships interactive cards (card-click navigation, pending
verification of item 1) and an interactive delete-confirm action
(`delete_goal`, a write operation invoked directly from rendered UI) — this
is no longer read-only by any reasonable definition. The implementation
correctly matches what this feature's `architecture.md`/`requirements.md`
specify; the gap is that the project's standing strategic record
(`strategy.md`) has not been updated via `/strategize` to reflect the
change. This is a documentation/process gap, not a code defect, but should
be closed before this feature (or a similar one) ships further interactive
surface.

## Extending this safely: adding a third UI screen/tool

A future screen following this same pattern should:

1. Define a new `XxxViewData` dataclass (and any nested item dataclasses)
   in `app/ui_templates.py`, following the existing `None`-vs-`0` progress
   contract and the `error`-takes-precedence-over-content contract already
   established by `HomeViewData`/`GoalDetailViewData`.
2. Write a `render_xxx_view(data) -> str` function alongside the existing
   renderers, escaping every piece of user-controlled text via
   `html.escape` before interpolation, and reusing `_progress_ring(...)` if
   the screen shows progress rather than re-implementing it.
3. If the screen needs to reference free text from a click handler (like
   "continue this conversation" does), use the DOM-`textContent`
   read-back pattern from `lifecoachContinueGoal` — never interpolate free
   text directly into an `onclick` JS-string literal, even with
   `html.escape` applied.
4. Add the corresponding MCP tool in `app/mcp_server.py`, following the
   established `enforce_mcp_rate_limit(request)` →
   `verify_bearer_token(...)` ordering, RLS-only query scoping (no
   app-level `user_id`/`deleted_at` clause), and a try/except wrapping the
   whole query block that returns a failure-state `EmbeddedResource`
   instead of letting an exception propagate raw.
5. Build the resource via `_build_embedded_html_resource(uri, html_text)`
   with a new `ui://<screen-name>` URI, rather than constructing
   `EmbeddedResource`/`TextResourceContents` independently — keep one
   shared construction path.
6. Decide card-click/structured-action vs. chat-injection per the same
   rule this feature used: if the action is "go look at something
   structured," call a tool directly; if it's "create/edit/talk," inject a
   chat message — and be aware this entire direct-tool-invocation channel
   is still pending verification against a real MCP-UI host (risk #1
   above).
