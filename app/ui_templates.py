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
