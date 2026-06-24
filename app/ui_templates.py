from dataclasses import dataclass


@dataclass
class HomeGoalCard:
    id: str
    title: str
    progress_percent: int | None
    last_updated_at: str | None


@dataclass
class GoalDetailUpdate:
    content: str
    created_at: str


@dataclass
class GoalDetailViewData:
    id: str | None
    title: str | None
    description: str | None
    progress_percent: int | None
    recent_updates: list[GoalDetailUpdate]
    error: str | None = None


@dataclass
class HomeViewData:
    greeting_name: str | None
    goals: list[HomeGoalCard]
    error: str | None = None


def home_view_data_to_dict(data: HomeViewData) -> dict:
    if data.error:
        return {"greetingName": None, "goals": [], "error": data.error}
    return {
        "greetingName": data.greeting_name,
        "goals": [
            {
                "id": g.id,
                "title": g.title,
                "progressPercent": g.progress_percent,
                "lastUpdatedAt": g.last_updated_at,
            }
            for g in data.goals
        ],
        "error": None,
    }


def goal_detail_data_to_dict(data: GoalDetailViewData) -> dict:
    if data.error:
        return {"error": data.error}
    return {
        "id": data.id,
        "title": data.title,
        "description": data.description,
        "progressPercent": data.progress_percent,
        "recentUpdates": [
            {"content": u.content, "createdAt": u.created_at}
            for u in data.recent_updates
        ],
        "error": None,
    }


def render_home_view() -> str:
    return _HOME_TEMPLATE


def render_goal_detail_view() -> str:
    return _DETAIL_TEMPLATE


_STYLE = """
:root {
  color-scheme: light;
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  background: #fff8f4;
  color: #1f1b17;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.page {
  max-width: 480px;
  margin: 0 auto;
  padding: 28px 20px 40px;
}
.greeting {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin: 0 0 4px;
  color: #1f1b17;
}
.subgreeting {
  font-size: 13px;
  color: #6b6259;
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
  border-radius: 16px;
  padding: 16px 18px;
  box-shadow: 0 1px 3px rgba(74, 69, 64, 0.04);
  cursor: pointer;
  border: 1px solid #ece3d8;
  text-align: left;
  width: 100%;
  font-family: inherit;
  transition: box-shadow 0.15s ease;
}
.card:hover {
  box-shadow: 0 4px 16px rgba(65, 99, 82, 0.08);
}
.card-title {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: #1f1b17;
}
.card-updated {
  display: block;
  font-size: 11px;
  color: #a39a8f;
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
  stroke: #e8ded1;
  stroke-width: 4;
}
.progress-ring-fill {
  fill: none;
  stroke: #416352;
  stroke-width: 4;
  stroke-linecap: round;
}
.progress-ring-fill.no-estimate {
  stroke: #c1c8c2;
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
  color: #6b6259;
}
.entry-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}
.entry-card {
  border: 1.5px dashed #c1c8c2;
  border-radius: 9999px;
  padding: 14px 18px;
  background: transparent;
  font-size: 14px;
  font-weight: 600;
  color: #416352;
  cursor: pointer;
  text-align: center;
  width: 100%;
  font-family: inherit;
}
.entry-card:hover {
  background: #fbf2eb;
}
.talk-entry {
  border: none;
  border-radius: 9999px;
  padding: 14px 18px;
  background: #416352;
  font-size: 14px;
  font-weight: 600;
  color: #ffffff;
  cursor: pointer;
  text-align: center;
  width: 100%;
  font-family: inherit;
}
.talk-entry:hover {
  background: #355445;
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

_DETAIL_STYLE = """
.detail-title {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin: 0 0 4px;
  color: #1f1b17;
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
  color: #6b6259;
  margin: 0 0 24px;
  white-space: pre-wrap;
}
.section-label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #a39a8f;
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
  border: 1px solid #ece3d8;
  border-radius: 12px;
  padding: 12px 16px;
}
.update-content {
  font-size: 13px;
  color: #1f1b17;
  margin: 0 0 4px;
  white-space: pre-wrap;
}
.update-date {
  font-size: 11px;
  color: #a39a8f;
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
  border-radius: 9999px;
  padding: 14px 18px;
  background: #416352;
  font-size: 14px;
  font-weight: 600;
  color: #ffffff;
  cursor: pointer;
  text-align: center;
  width: 100%;
  font-family: inherit;
}
.continue-entry:hover {
  background: #355445;
}
.delete-entry {
  border: 1.5px dashed #ddc6bc;
  border-radius: 9999px;
  padding: 14px 18px;
  background: transparent;
  font-size: 14px;
  font-weight: 600;
  color: #9a5a45;
  cursor: pointer;
  text-align: center;
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
  border-radius: 14px;
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
  border-radius: 9999px;
  padding: 8px 16px;
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
  color: #6b6259;
}
.hidden {
  display: none;
}
"""

_BRIDGE_JS = """
(function() {
  var PENDING = {};
  var MSG_ID = 0;
  var READY = false;
  var BUFFERED = null;

  function handleResult(params) {
    if (READY && typeof onToolResult === 'function') {
      onToolResult(params);
    } else {
      BUFFERED = params;
    }
  }

  function sendRequest(method, params) {
    var id = ++MSG_ID;
    return new Promise(function(resolve, reject) {
      PENDING[id] = function(result, err) {
        if (err) reject(err);
        else resolve(result);
      };
      window.parent.postMessage({
        jsonrpc: "2.0", id: id, method: method, params: params || {}
      }, "*");
    });
  }

  window.addEventListener("message", function(event) {
    var msg = event.data;
    if (!msg || msg.jsonrpc !== "2.0") return;

    if (msg.id === "__init__") {
      READY = true;
      window.parent.postMessage({
        jsonrpc: "2.0",
        method: "ui/notifications/initialized"
      }, "*");
      if (BUFFERED) {
        if (typeof onToolResult === 'function') onToolResult(BUFFERED);
        BUFFERED = null;
      }
      return;
    }

    if (msg.method === "ui/notifications/tool-result") {
      handleResult(msg.params);
      return;
    }

    if (msg.id && PENDING[msg.id]) {
      PENDING[msg.id](msg.result, msg.error);
      delete PENDING[msg.id];
    }
  });

  window.parent.postMessage({
    jsonrpc: "2.0",
    id: "__init__",
    method: "ui/initialize",
    params: {
      protocolVersion: "2026-01-26",
      appInfo: { name: "LifeCoach", version: "1.0.0" },
      appCapabilities: {}
    }
  }, "*");

  window.callTool = function(name, args) {
    return sendRequest("tools/call", { name: name, arguments: args || {} });
  };

  window.sendMessage = function(text) {
    return sendRequest("ui/message", {
      role: "user",
      content: [{ type: "text", text: text }]
    });
  };
})();
"""

_RENDER_JS = """
function progressRing(percent) {
  var r = 18;
  var circ = 2 * 3.14159265 * r;
  if (percent == null) {
    return '<div class="progress-ring"><svg width="44" height="44" viewBox="0 0 44 44">' +
      '<circle class="progress-ring-track" cx="22" cy="22" r="' + r + '"></circle>' +
      '<circle class="progress-ring-fill no-estimate" cx="22" cy="22" r="' + r + '" stroke-dashoffset="0"></circle>' +
      '</svg><span class="progress-ring-label">&mdash;</span></div>';
  }
  var offset = circ * (1 - percent / 100);
  return '<div class="progress-ring"><svg width="44" height="44" viewBox="0 0 44 44">' +
    '<circle class="progress-ring-track" cx="22" cy="22" r="' + r + '"></circle>' +
    '<circle class="progress-ring-fill" cx="22" cy="22" r="' + r + '" stroke-dasharray="' +
    circ.toFixed(2) + '" stroke-dashoffset="' + offset.toFixed(2) + '"></circle>' +
    '</svg><span class="progress-ring-label">' + percent + '%</span></div>';
}

function updatedLine(lastUpdatedAt) {
  if (!lastUpdatedAt) return "";
  var dateOnly = lastUpdatedAt.split("T")[0];
  return '<span class="card-updated">Updated ' + escapeHtml(dateOnly) + '</span>';
}

function escapeHtml(s) {
  if (typeof s !== 'string') return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}

function renderHomeView(data) {
  if (data.error) return renderHomeError(data.error);
  var safeName = escapeHtml(data.greetingName) || "there";
  var body = '<p class="greeting">Hi ' + safeName + ',</p>';
  if (!data.goals || data.goals.length === 0) {
    body += '<div class="empty-state"><p>You don\\'t have any goals yet.</p></div>';
  } else {
    body += '<p class="subgreeting">Here\\'s where your goals stand today.</p>';
    body += '<div class="goal-list">';
    for (var i = 0; i < data.goals.length; i++) {
      var g = data.goals[i];
      body += goalCard(g);
    }
    body += '</div>';
  }
  body += '<div class="entry-list">' +
    '<button class="entry-card" type="button" onclick="window.sendMessage(\\'I want to create a new goal.\\')">+ Create a new goal</button>' +
    '<button class="talk-entry" type="button" onclick="window.sendMessage(\\'I just want to talk.\\')">Just want to talk?</button>' +
    '</div>';
  return body;
}

function goalCard(g) {
  var safeTitle = escapeHtml(g.title);
  var safeId = escapeHtml(g.id);
  return '<button class="card" type="button" onclick="window.callTool(\\'get_goal_detail_view\\', {goal_id: \\'' + safeId + '\\'}).then(function(r){var d=r.structuredContent||JSON.parse(r.content[0].text);var el=document.getElementById(\\'root\\');if(el)el.innerHTML=renderGoalDetailView(d);})">' +
    progressRing(g.progressPercent) +
    '<span class="card-title">' + safeTitle + updatedLine(g.lastUpdatedAt) + '</span></button>';
}

function renderHomeError(error) {
  return '<p class="greeting">Hi there,</p>' +
    '<div class="failure-state"><p class="failure-message">' + escapeHtml(error) + '</p></div>' +
    '<div class="entry-list">' +
    '<button class="entry-card" type="button" onclick="window.sendMessage(\\'I want to create a new goal.\\')">+ Create a new goal</button>' +
    '<button class="talk-entry" type="button" onclick="window.sendMessage(\\'I just want to talk.\\')">Just want to talk?</button>' +
    '</div>';
}

function renderGoalDetailView(data) {
  if (data.error) return renderGoalDetailError(data.error);
  var safeId = escapeHtml(data.id);
  var safeTitle = escapeHtml(data.title);
  var html = '<div class="detail-header">' +
    progressRing(data.progressPercent) +
    '<p class="detail-title" id="goal-title-' + safeId + '">' + safeTitle + '</p></div>';
  if (data.description) {
    html += '<p class="detail-description">' + escapeHtml(data.description) + '</p>';
  }
  html += '<p class="section-label">Recent updates</p>';
  if (data.recentUpdates && data.recentUpdates.length > 0) {
    html += '<div class="update-list">';
    for (var i = 0; i < data.recentUpdates.length; i++) {
      var u = data.recentUpdates[i];
      var safeContent = escapeHtml(u.content);
      var dateOnly = (u.createdAt || "").split("T")[0];
      html += '<div class="update-item"><p class="update-content">' + safeContent + '</p>' +
        '<span class="update-date">' + escapeHtml(dateOnly) + '</span></div>';
    }
    html += '</div>';
  } else {
    html += '<p class="no-updates">No updates yet.</p>';
  }
  html += '<div class="action-list">' +
    '<button class="continue-entry" type="button" onclick="continueGoal(\\'' + safeId + '\\')">Continue this conversation</button>' +
    '<button class="delete-entry" type="button" id="delete-entry-' + safeId + '" onclick="showDeleteConfirm(\\'' + safeId + '\\')">Delete goal</button>' +
    '<div class="delete-confirm hidden" id="delete-confirm-' + safeId + '">' +
    '<span class="delete-confirm-text">Are you sure?</span>' +
    '<button class="delete-confirm-btn confirm" type="button" onclick="confirmDelete(\\'' + safeId + '\\')">Confirm</button>' +
    '<button class="delete-confirm-btn cancel" type="button" onclick="cancelDeleteConfirm(\\'' + safeId + '\\')">Cancel</button></div></div>';
  return html;
}

function renderGoalDetailError(error) {
  return '<div class="failure-state"><p class="failure-message">' + escapeHtml(error) + '</p></div>';
}

function continueGoal(goalId) {
  var el = document.getElementById("goal-title-" + goalId);
  var title = el ? el.textContent : "this goal";
  window.sendMessage("Let's continue talking about " + title + ".");
}

function showDeleteConfirm(goalId) {
  document.getElementById("delete-entry-" + goalId).classList.add("hidden");
  document.getElementById("delete-confirm-" + goalId).classList.remove("hidden");
}

function cancelDeleteConfirm(goalId) {
  document.getElementById("delete-confirm-" + goalId).classList.add("hidden");
  document.getElementById("delete-entry-" + goalId).classList.remove("hidden");
}

function confirmDelete(goalId) {
  window.callTool("delete_goal", { goal_id: goalId }).then(function(r) {
    var d = r.structuredContent || JSON.parse(r.content[0].text);
    var el = document.getElementById("root");
    if (el) el.innerHTML = renderHomeView(d);
  });
}
"""

_HOME_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>""" + _STYLE + """</style>
</head>
<body>
<div class="page" id="root"></div>
<script>""" + _BRIDGE_JS + _RENDER_JS + """
(function() {
  window.onToolResult = function(params) {
    var data = params.structuredContent || JSON.parse(params.content[0].text);
    document.getElementById("root").innerHTML = renderHomeView(data);
  };
})();
</script>
</body>
</html>"""

_DETAIL_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>""" + _STYLE + _DETAIL_STYLE + """</style>
</head>
<body>
<div class="page" id="root"></div>
<script>""" + _BRIDGE_JS + _RENDER_JS + """
(function() {
  window.onToolResult = function(params) {
    var data = params.structuredContent || JSON.parse(params.content[0].text);
    document.getElementById("root").innerHTML = renderGoalDetailView(data);
  };
})();
</script>
</body>
</html>"""
