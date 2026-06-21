import html
from dataclasses import dataclass


@dataclass
class HomeGoalCard:
    """One goal card on the home view.

    `progress_percent` is `None` when the goal has no self-reported
    progress estimate yet — render an explicit "no estimate yet" state,
    never a misleading 0%. `last_updated_at` is `None` when the goal has
    zero recorded updates — render no "updated X ago" line at all rather
    than fabricating one.
    """

    id: str
    title: str
    progress_percent: int | None
    last_updated_at: str | None


@dataclass
class GoalDetailUpdate:
    """One recent update shown on the goal-detail view.

    `content` only — never `transcript`, consistent with `list_updates`.
    """

    content: str
    created_at: str


@dataclass
class GoalDetailViewData:
    """Data contract for `render_goal_detail_view`.

    `id` and `title` identify the goal the detail view is for; `title` is
    also used to build the "continue this conversation" chat-message
    injection, so it must be the raw (un-escaped) title — escape at render
    time, not here.

    `description` is `None` when the goal has no description set — render
    no description block at all rather than an empty one.

    `progress_percent` follows the same contract as `HomeGoalCard`: `None`
    means "no estimate yet," distinct from `0`.

    `recent_updates` is the goal's most recent updates (already limited and
    ordered newest-first by the caller), one `GoalDetailUpdate` per update.
    An empty list is a normal, valid state (zero updates yet) and must
    render an explicit "no updates yet" treatment, not a blank section.

    `error` is `None` on a normal render. When set (e.g. the goal doesn't
    exist, isn't owned by the caller, or is soft-deleted), it carries a
    short, user-safe description of that handled failure, and the renderer
    must produce a failure-state UI instead of attempting to render
    title/description/progress/updates — never both at once.
    """

    id: str | None
    title: str | None
    description: str | None
    progress_percent: int | None
    recent_updates: list[GoalDetailUpdate]
    error: str | None = None


@dataclass
class HomeViewData:
    """Data contract for `render_home_view`.

    `greeting_name` is the caller's display name, falling back to their
    email when no display name is set — resolve that fallback before
    constructing this object, not inside the renderer.

    `goals` is the caller's active (non-soft-deleted) goals, already
    RLS-scoped and ordered, one `HomeGoalCard` per goal. An empty list is
    a normal, valid state (zero active goals) and must render the
    empty-state variant from requirements.md Requirement 7 — greeting
    plus the "create a new goal" and "just want to talk" entries, no goal
    cards, no placeholder/broken-looking content.

    `error` is `None` on a normal render. When set, it carries a short,
    user-safe description of a handled failure (e.g. the caller's user
    row could not be found) and the renderer must produce a failure-state
    UI instead of attempting to render greeting/goals — never both at
    once.
    """

    greeting_name: str | None
    goals: list[HomeGoalCard]
    error: str | None = None


def render_home_view(data: HomeViewData) -> str:
    """Render the home view as a complete standalone HTML document.

    Consumes a `HomeViewData` and must produce:
    - A greeting using `data.greeting_name` (or a generic greeting if
      `error` is set).
    - One card per entry in `data.goals`, each showing `title` and a
      progress bar/percentage, or a dashed "no estimate yet" treatment
      when `progress_percent` is `None`, plus an "updated X ago" line
      derived from `last_updated_at` when not `None`.
    - A distinct "create a new goal" entry and a distinct "just want to
      talk?" entry, visually separate from goal cards. Both inject a
      plain chat message when clicked — they must not call any tool.
    - Each goal card, when clicked, invokes the `get_goal_detail_view`
      tool for that goal id directly (pending confirmation that the
      MCP-UI host's postMessage mechanism supports direct tool invocation
      from a UI click; fall back to chat-message injection if not).
    - An empty-state variant when `data.goals` is empty: greeting plus
      the two entries above, no goal cards, no placeholder content.
    - A failure-state variant when `data.error` is set: a clear,
      non-technical message and the same "create a new goal" / "just
      want to talk" entries, no goal cards.
    - No persistent bottom tab bar, no "Total Days"/"Current Streak" stat
      cards — explicitly out of scope per architecture.md.

    TODO(frontend): replace this placeholder body with the real HTML/CSS.
    """
    if data.error:
        body = _render_failure_state(data.error)
    elif not data.goals:
        body = _render_empty_state(data.greeting_name)
    else:
        body = _render_goals_state(data.greeting_name, data.goals)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{_STYLE}</style>
</head>
<body>
<div class="page">
{body}
</div>
<script>{_SCRIPT}</script>
</body>
</html>"""


_STYLE = """
:root {
  color-scheme: light;
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  background: #f7f3ee;
  color: #3a352f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
.page {
  max-width: 480px;
  margin: 0 auto;
  padding: 28px 20px 40px;
}
.greeting {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 4px;
  color: #2e2a25;
}
.subgreeting {
  font-size: 13px;
  color: #8a8073;
  margin: 0 0 24px;
}
.goal-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}
.card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #ffffff;
  border-radius: 18px;
  padding: 16px 18px;
  box-shadow: 0 1px 3px rgba(60, 50, 40, 0.06);
  cursor: pointer;
  border: 1px solid #efe9e1;
  text-align: left;
  width: 100%;
  font-family: inherit;
}
.card:hover {
  box-shadow: 0 2px 6px rgba(60, 50, 40, 0.1);
}
.card-title {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: #3a352f;
}
.card-updated {
  display: block;
  font-size: 11px;
  color: #a59a8c;
  margin-top: 2px;
  font-weight: 400;
}
.progress-ring {
  flex-shrink: 0;
  position: relative;
  width: 44px;
  height: 44px;
}
.progress-ring svg {
  transform: rotate(-90deg);
}
.progress-ring-track {
  fill: none;
  stroke: #efe9e1;
  stroke-width: 4;
}
.progress-ring-fill {
  fill: none;
  stroke: #c98a5e;
  stroke-width: 4;
  stroke-linecap: round;
}
.progress-ring-fill.no-estimate {
  stroke: #cfc6b8;
  stroke-dasharray: 2 4;
}
.progress-ring-label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  color: #6b6258;
}
.entry-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}
.entry-card {
  border: 1.5px dashed #cbbfae;
  border-radius: 16px;
  padding: 14px 18px;
  background: transparent;
  font-size: 14px;
  font-weight: 500;
  color: #7a6f5f;
  cursor: pointer;
  text-align: left;
  width: 100%;
  font-family: inherit;
}
.entry-card:hover {
  background: #fbf8f3;
}
.talk-entry {
  border: none;
  border-radius: 16px;
  padding: 14px 18px;
  background: #ece4d8;
  font-size: 14px;
  font-weight: 500;
  color: #5c5346;
  cursor: pointer;
  text-align: left;
  width: 100%;
  font-family: inherit;
}
.talk-entry:hover {
  background: #e4dac9;
}
.empty-state {
  padding: 32px 0 8px;
  text-align: center;
}
.empty-state p {
  font-size: 13px;
  color: #9a9082;
  margin: 0 0 20px;
}
.failure-state {
  padding: 20px 0 8px;
}
.failure-message {
  background: #f6ece6;
  border-radius: 14px;
  padding: 16px 18px;
  font-size: 13px;
  color: #8a5a3c;
  margin-bottom: 20px;
}
"""

_SCRIPT = """
function lifecoachSendTool(toolName, params) {
  // UNVERIFIED against a live MCP-UI host: this assumes the host's
  // postMessage convention supports a UI-initiated tool-call intent
  // shaped like { type: "tool", payload: { toolName, params } }, per
  // the mcp-ui community reference implementations encountered during
  // design. If a live host does not honor this shape, the documented
  // fallback is chat-message injection (see lifecoachSendPrompt) and
  // this call site should be switched to that instead.
  window.parent.postMessage({ type: "tool", payload: { toolName, params } }, "*");
}

function lifecoachSendPrompt(prompt) {
  // UNVERIFIED against a live MCP-UI host: this assumes the host's
  // postMessage convention supports injecting a chat message shaped
  // like { type: "prompt", payload: { prompt } }, per the mcp-ui
  // community reference implementations encountered during design.
  window.parent.postMessage({ type: "prompt", payload: { prompt } }, "*");
}
"""


def _progress_ring(progress_percent: int | None) -> str:
    radius = 18
    circumference = 2 * 3.14159265 * radius
    if progress_percent is None:
        return f"""<div class="progress-ring">
  <svg width="44" height="44" viewBox="0 0 44 44">
    <circle class="progress-ring-track" cx="22" cy="22" r="{radius}"></circle>
    <circle class="progress-ring-fill no-estimate" cx="22" cy="22" r="{radius}"
      stroke-dashoffset="0"></circle>
  </svg>
  <span class="progress-ring-label">&mdash;</span>
</div>"""

    offset = circumference * (1 - progress_percent / 100)
    return f"""<div class="progress-ring">
  <svg width="44" height="44" viewBox="0 0 44 44">
    <circle class="progress-ring-track" cx="22" cy="22" r="{radius}"></circle>
    <circle class="progress-ring-fill" cx="22" cy="22" r="{radius}"
      stroke-dasharray="{circumference:.2f}" stroke-dashoffset="{offset:.2f}"></circle>
  </svg>
  <span class="progress-ring-label">{progress_percent}%</span>
</div>"""


def _updated_line(last_updated_at: str | None) -> str:
    if last_updated_at is None:
        return ""
    date_only = last_updated_at.split("T", 1)[0]
    return f'<span class="card-updated">Updated {html.escape(date_only)}</span>'


def _goal_card(card: HomeGoalCard) -> str:
    safe_title = html.escape(card.title)
    safe_id = html.escape(card.id)
    return f"""<button class="card" type="button"
  onclick="lifecoachSendTool('get_goal_detail_view', {{ goal_id: '{safe_id}' }})">
  {_progress_ring(card.progress_percent)}
  <span class="card-title">{safe_title}{_updated_line(card.last_updated_at)}</span>
</button>"""


_CREATE_GOAL_ENTRY = """<button class="entry-card" type="button"
  onclick="lifecoachSendPrompt('I want to create a new goal.')">
  + Create a new goal
</button>"""

_TALK_ENTRY = """<button class="talk-entry" type="button"
  onclick="lifecoachSendPrompt('I just want to talk.')">
  Just want to talk?
</button>"""


def _render_goals_state(greeting_name: str | None, goals: list[HomeGoalCard]) -> str:
    safe_greeting = html.escape(greeting_name) if greeting_name else "there"
    cards = "\n".join(_goal_card(card) for card in goals)
    return f"""<p class="greeting">Hi {safe_greeting},</p>
<p class="subgreeting">Here's where your goals stand today.</p>
<div class="goal-list">
{cards}
</div>
<div class="entry-list">
{_CREATE_GOAL_ENTRY}
{_TALK_ENTRY}
</div>"""


def _render_empty_state(greeting_name: str | None) -> str:
    safe_greeting = html.escape(greeting_name) if greeting_name else "there"
    return f"""<p class="greeting">Hi {safe_greeting},</p>
<div class="empty-state">
  <p>You don't have any goals yet.</p>
</div>
<div class="entry-list">
{_CREATE_GOAL_ENTRY}
{_TALK_ENTRY}
</div>"""


def _render_failure_state(error: str) -> str:
    safe_error = html.escape(error)
    return f"""<p class="greeting">Hi there,</p>
<div class="failure-state">
  <p class="failure-message">{safe_error}</p>
</div>
<div class="entry-list">
{_CREATE_GOAL_ENTRY}
{_TALK_ENTRY}
</div>"""


def render_goal_detail_view(data: GoalDetailViewData) -> str:
    """Render the goal-detail view as a complete standalone HTML document.

    Consumes a `GoalDetailViewData` and must produce:
    - A failure-state variant when `data.error` is set: a clear,
      non-technical message (e.g. "This goal isn't available.") and no
      title/description/progress/updates/actions — mirror the structure
      of `_render_failure_state` above, adapted for this view (no
      "create a new goal"/"just want to talk" entries here; those are
      home-view-specific).
    - Otherwise, the full `data.title` and `data.description` (HTML-escape
      both — this is free-text user input, never trust it as safe markup;
      omit the description block entirely when `data.description` is
      `None`, rather than rendering an empty one).
    - A progress indicator reusing the existing `_progress_ring(...)`
      helper from this module rather than re-implementing the ring/"no
      estimate yet" treatment a second time — this is the second real call
      site for that helper, which is exactly the case that justifies
      reusing it instead of duplicating its logic.
    - A short recent-updates list from `data.recent_updates`, each item
      showing `content` and `created_at` (date only, same truncation style
      as `_updated_line` above) — never anything beyond those two fields.
      When `data.recent_updates` is empty, render an explicit "no updates
      yet" message instead of an empty list.
    - A "continue this conversation" action that calls
      `lifecoachSendPrompt(...)` (not `lifecoachSendTool`) with a prompt
      that references the goal by `data.title`, e.g. something like
      "Let's continue talking about {title}." — this must inject a chat
      message, not invoke any tool.
    - A delete action gated behind an explicit confirm step (e.g. a
      two-stage button: first click reveals an inline "Are you sure?"
      confirmation, second click on the confirm button actually proceeds).
      Only the confirmed action calls
      `lifecoachSendTool('delete_goal', { goal_id: data.id })`. Note:
      `delete_goal` does not exist yet as of this story — it ships as a
      sibling story in this same feature — but the click handler should
      still be wired to call it now, since by the time this view ships
      end-to-end the tool will exist.

    TODO(frontend): replace this placeholder body with the real HTML/CSS.
    """
    if data.error:
        body = _render_detail_failure_state(data.error)
    else:
        body = _render_detail_content(data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{_DETAIL_STYLE}{_STYLE}</style>
</head>
<body>
<div class="page">
{body}
</div>
<script>{_DETAIL_SCRIPT}{_SCRIPT}</script>
</body>
</html>"""


_DETAIL_STYLE = """
.detail-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 4px;
  color: #2e2a25;
}
.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
.detail-description {
  font-size: 14px;
  line-height: 1.5;
  color: #5c5346;
  margin: 0 0 24px;
  white-space: pre-wrap;
}
.section-label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #a59a8c;
  margin: 0 0 10px;
}
.update-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 24px;
}
.update-item {
  background: #ffffff;
  border: 1px solid #efe9e1;
  border-radius: 14px;
  padding: 12px 16px;
}
.update-content {
  font-size: 13px;
  color: #3a352f;
  margin: 0 0 4px;
  white-space: pre-wrap;
}
.update-date {
  font-size: 11px;
  color: #a59a8c;
}
.no-updates {
  font-size: 13px;
  color: #9a9082;
  margin: 0 0 24px;
}
.action-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.continue-entry {
  border: none;
  border-radius: 16px;
  padding: 14px 18px;
  background: #ece4d8;
  font-size: 14px;
  font-weight: 500;
  color: #5c5346;
  cursor: pointer;
  text-align: left;
  width: 100%;
  font-family: inherit;
}
.continue-entry:hover {
  background: #e4dac9;
}
.delete-entry {
  border: 1.5px dashed #cbbfae;
  border-radius: 16px;
  padding: 14px 18px;
  background: transparent;
  font-size: 14px;
  font-weight: 500;
  color: #9a5a45;
  cursor: pointer;
  text-align: left;
  width: 100%;
  font-family: inherit;
}
.delete-entry:hover {
  background: #fbf2ee;
}
.delete-confirm {
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 16px;
  padding: 14px 18px;
  background: #f6ece6;
}
.delete-confirm-text {
  flex: 1;
  font-size: 13px;
  color: #8a5a3c;
}
.delete-confirm-btn {
  border: none;
  border-radius: 10px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}
.delete-confirm-btn.confirm {
  background: #b2543a;
  color: #fff;
}
.delete-confirm-btn.cancel {
  background: #eee2da;
  color: #6b6258;
}
.hidden {
  display: none;
}
"""

_DETAIL_SCRIPT = """
function lifecoachContinueGoal(goalId) {
  var el = document.getElementById("goal-title-" + goalId);
  var title = el ? el.textContent : "this goal";
  lifecoachSendPrompt("Let's continue talking about " + title + ".");
}

function lifecoachShowDeleteConfirm(goalId) {
  document.getElementById("delete-entry-" + goalId).classList.add("hidden");
  document.getElementById("delete-confirm-" + goalId).classList.remove("hidden");
}

function lifecoachCancelDeleteConfirm(goalId) {
  document.getElementById("delete-confirm-" + goalId).classList.add("hidden");
  document.getElementById("delete-entry-" + goalId).classList.remove("hidden");
}

function lifecoachConfirmDelete(goalId) {
  lifecoachSendTool("delete_goal", { goal_id: goalId });
}
"""


def _detail_updated_line(created_at: str) -> str:
    date_only = created_at.split("T", 1)[0]
    return html.escape(date_only)


def _detail_update_item(update: GoalDetailUpdate) -> str:
    safe_content = html.escape(update.content)
    safe_date = _detail_updated_line(update.created_at)
    return f"""<div class="update-item">
  <p class="update-content">{safe_content}</p>
  <span class="update-date">{safe_date}</span>
</div>"""


def _render_recent_updates(updates: list[GoalDetailUpdate]) -> str:
    if not updates:
        return '<p class="no-updates">No updates yet.</p>'
    items = "\n".join(_detail_update_item(update) for update in updates)
    return f'<div class="update-list">\n{items}\n</div>'


def _render_detail_content(data: GoalDetailViewData) -> str:
    safe_id = html.escape(data.id or "")
    safe_title = html.escape(data.title or "")
    description_block = ""
    if data.description:
        description_block = f'<p class="detail-description">{html.escape(data.description)}</p>'

    return f"""<div class="detail-header">
  {_progress_ring(data.progress_percent)}
  <p class="detail-title" id="goal-title-{safe_id}">{safe_title}</p>
</div>
{description_block}
<p class="section-label">Recent updates</p>
{_render_recent_updates(data.recent_updates)}
<div class="action-list">
  <button class="continue-entry" type="button"
    onclick="lifecoachContinueGoal('{safe_id}')">
    Continue this conversation
  </button>
  <button class="delete-entry" type="button" id="delete-entry-{safe_id}"
    onclick="lifecoachShowDeleteConfirm('{safe_id}')">
    Delete goal
  </button>
  <div class="delete-confirm hidden" id="delete-confirm-{safe_id}">
    <span class="delete-confirm-text">Are you sure?</span>
    <button class="delete-confirm-btn confirm" type="button"
      onclick="lifecoachConfirmDelete('{safe_id}')">Confirm</button>
    <button class="delete-confirm-btn cancel" type="button"
      onclick="lifecoachCancelDeleteConfirm('{safe_id}')">Cancel</button>
  </div>
</div>"""


def _render_detail_failure_state(error: str) -> str:
    safe_error = html.escape(error)
    return f'<div class="failure-state"><p class="failure-message">{safe_error}</p></div>'
