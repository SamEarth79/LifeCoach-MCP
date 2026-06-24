"""Renders the OAuth consent page Supabase's OAuth 2.1 Server redirects to.

Unlike `app/ui_templates.py` (MCP-UI resources rendered inside a sandboxed
iframe via a postMessage bridge), this page is a normal, directly
browser-navigable HTML document with no parent-frame messaging — it talks
to Supabase Auth directly via the `@supabase/supabase-js` SDK. The two
modules deliberately don't share helpers because their execution contexts
and trust models are different (sandboxed MCP-UI iframe vs. plain browser
page), but the string-template structure (module-level style/script
constants, an f-string-assembled `<!DOCTYPE html>` document, `html.escape`
discipline) follows the same convention as `app/ui_templates.py`.

LFC-STORY-005-001 built the page shell: CDN script load, config injection,
and the missing-`authorization_id` failure state. LFC-STORY-005-002 filled
in the login form: a session check, an email/password form rendered when
there's no active session, and `signInWithPassword` wired to submit.
LFC-STORY-005-003 (this story) replaces the post-login loading-state stub
with the real consent screen: `getAuthorizationDetails`, the
approve/deny actions, and the redirect each returns.
"""

_SUPABASE_JS_CDN_URL = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.108.2/dist/umd/supabase.js"

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
  max-width: 420px;
  margin: 0 auto;
  padding: 28px 20px 40px;
}
.loading-state {
  padding: 32px 0 8px;
  text-align: center;
  font-size: 13px;
  color: #9a9082;
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
}
.login-form {
  padding: 20px 0 8px;
}
.login-form label {
  display: block;
  font-size: 13px;
  margin: 14px 0 6px;
}
.login-form input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd3c6;
  border-radius: 10px;
  font-size: 14px;
}
.login-form button {
  width: 100%;
  margin-top: 20px;
  padding: 12px;
  border: none;
  border-radius: 10px;
  background: #3a352f;
  color: #f7f3ee;
  font-size: 14px;
  cursor: pointer;
}
.login-error {
  margin-top: 14px;
  background: #f6ece6;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
  color: #8a5a3c;
}
.consent-screen {
  padding: 20px 0 8px;
}
.consent-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 6px;
  color: #2e2a25;
}
.consent-subtitle {
  font-size: 13px;
  color: #8a8073;
  margin: 0 0 18px;
}
.consent-client-name {
  font-weight: 600;
  color: #3a352f;
}
.scope-list {
  list-style: none;
  margin: 0 0 24px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.scope-item {
  background: #ffffff;
  border: 1px solid #efe9e1;
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 13px;
  color: #3a352f;
}
.consent-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.consent-approve {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 10px;
  background: #3a352f;
  color: #f7f3ee;
  font-size: 14px;
  cursor: pointer;
}
.consent-deny {
  width: 100%;
  padding: 12px;
  border: 1px solid #ddd3c6;
  border-radius: 10px;
  background: transparent;
  color: #3a352f;
  font-size: 14px;
  cursor: pointer;
}
.consent-action-error {
  margin-top: 14px;
  background: #f6ece6;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
  color: #8a5a3c;
}
"""

_SCRIPT_TEMPLATE = """
const SUPABASE_URL = "{supabase_url}";
const SUPABASE_ANON_KEY = "{supabase_anon_key}";

function lifecoachRenderFailureState(message) {{
  document.getElementById("oauth-consent-root").innerHTML =
    '<div class="failure-state"><p class="failure-message"></p></div>';
  document.querySelector(".failure-message").textContent = message;
}}

function lifecoachRenderLoadingState() {{
  document.getElementById("oauth-consent-root").innerHTML =
    '<div class="loading-state">Loading...</div>';
}}

function lifecoachEscapeHtml(value) {{
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}}

function lifecoachRenderConsentScreen(client, authorizationId, details) {{
  const safeClientName = lifecoachEscapeHtml(details.client.name);
  const scopes = details.scope.split(" ").filter(function (scope) {{
    return scope.length > 0;
  }});
  const scopeItems = scopes
    .map(function (scope) {{
      return '<li class="scope-item">' + lifecoachEscapeHtml(scope) + "</li>";
    }})
    .join("");

  document.getElementById("oauth-consent-root").innerHTML =
    '<div class="consent-screen">' +
    '<p class="consent-title">Connect your account</p>' +
    '<p class="consent-subtitle"><span class="consent-client-name">' +
    safeClientName +
    "</span> wants to access:</p>" +
    '<ul class="scope-list">' +
    scopeItems +
    "</ul>" +
    '<div class="consent-actions">' +
    '<button class="consent-approve" type="button" id="oauth-consent-approve">Approve</button>' +
    '<button class="consent-deny" type="button" id="oauth-consent-deny">Deny</button>' +
    '</div>' +
    '<p class="consent-action-error" id="oauth-consent-action-error" hidden></p>' +
    "</div>";

  document
    .getElementById("oauth-consent-approve")
    .addEventListener("click", function () {{
      lifecoachHandleConsentDecision(client, authorizationId, "approve");
    }});
  document
    .getElementById("oauth-consent-deny")
    .addEventListener("click", function () {{
      lifecoachHandleConsentDecision(client, authorizationId, "deny");
    }});
}}

async function lifecoachHandleConsentDecision(client, authorizationId, decision) {{
  const errorEl = document.getElementById("oauth-consent-action-error");
  errorEl.hidden = true;

  try {{
    const {{ data, error }} =
      decision === "approve"
        ? await client.auth.oauth.approveAuthorization(authorizationId)
        : await client.auth.oauth.denyAuthorization(authorizationId);

    if (error || !data || !data.redirect_url) {{
      console.error("lifecoach oauth consent: " + decision + "Authorization failed", error, data);
      errorEl.textContent = "Something went wrong. Please try again.";
      errorEl.hidden = false;
      return;
    }}

    window.location.href = data.redirect_url;
  }} catch (caughtError) {{
    console.error("lifecoach oauth consent: " + decision + "Authorization threw", caughtError);
    errorEl.textContent = "Something went wrong. Please try again.";
    errorEl.hidden = false;
  }}
}}

function lifecoachRenderLoginForm(client, authorizationId) {{
  document.getElementById("oauth-consent-root").innerHTML =
    '<form class="login-form" id="oauth-login-form">' +
    '<label for="oauth-login-email">Email</label>' +
    '<input type="email" id="oauth-login-email" autocomplete="email" required>' +
    '<label for="oauth-login-password">Password</label>' +
    '<input type="password" id="oauth-login-password" autocomplete="current-password" required>' +
    '<button type="submit">Log in</button>' +
    '<p class="login-error" id="oauth-login-error" hidden></p>' +
    '</form>';

  document
    .getElementById("oauth-login-form")
    .addEventListener("submit", function (event) {{
      event.preventDefault();
      lifecoachHandleLoginSubmit(client, authorizationId);
    }});
}}

async function lifecoachHandleLoginSubmit(client, authorizationId) {{
  const email = document.getElementById("oauth-login-email").value;
  const password = document.getElementById("oauth-login-password").value;

  const {{ error }} = await client.auth.signInWithPassword({{ email, password }});

  if (error) {{
    console.error("lifecoach oauth consent: signInWithPassword failed", error);
    const errorEl = document.getElementById("oauth-login-error");
    errorEl.textContent = "Invalid email or password.";
    errorEl.hidden = false;
    return;
  }}

  renderLoginOrConsent(client, authorizationId);
}}

async function renderLoginOrConsent(client, authorizationId) {{
  const {{ data }} = await client.auth.getSession();

  if (!data.session) {{
    lifecoachRenderLoginForm(client, authorizationId);
    return;
  }}

  lifecoachRenderLoadingState();

  try {{
    const {{ data: details, error }} = await client.auth.oauth.getAuthorizationDetails(
      authorizationId
    );

    if (error || !details) {{
      console.error("lifecoach oauth consent: getAuthorizationDetails failed", error, {{
        authorizationId: authorizationId,
      }});
      lifecoachRenderFailureState(
        "This link is invalid or has expired. Please try connecting again from the app."
      );
      return;
    }}

    lifecoachRenderConsentScreen(client, authorizationId, details);
  }} catch (caughtError) {{
    console.error("lifecoach oauth consent: getAuthorizationDetails threw", caughtError, {{
      authorizationId: authorizationId,
    }});
    lifecoachRenderFailureState(
      "This link is invalid or has expired. Please try connecting again from the app."
    );
  }}
}}

function lifecoachInit() {{
  const params = new URLSearchParams(window.location.search);
  const authorizationId = params.get("authorization_id");

  if (!authorizationId) {{
    lifecoachRenderFailureState(
      "This link is invalid or has expired. Please try connecting again from the app."
    );
    return;
  }}

  const client = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  renderLoginOrConsent(client, authorizationId);
}}

lifecoachInit();
"""


def render_oauth_consent_page(supabase_url: str, supabase_anon_key: str) -> str:
    """Render the OAuth consent page as a complete standalone HTML document.

    The entire login + consent flow runs client-side via `supabase-js`
    after this page loads; the only server-side dynamic content is
    injecting `supabase_url`/`supabase_anon_key` as JS constants so the SDK
    can initialize. Both values are already public-safe config (the same
    anon key already used elsewhere in this app), not secrets, but are
    still injected via an escaped JS string literal rather than interpolated
    as raw HTML.

    Implements, across LFC-STORY-005-001 through LFC-STORY-005-003:
    - The page shell and the pinned-version `supabase-js` CDN script tag.
    - The missing-`authorization_id` failure state.
    - A session check: if no active Supabase session exists, an
      email/password login form is rendered and wired to
      `signInWithPassword`, with a generic invalid-credentials error on
      failure and no page reload required to retry.
    - Once a session exists (or is just established by a successful
      login), `getAuthorizationDetails` is fetched and rendered as a
      consent screen (client name + requested scopes, both HTML-escaped),
      with Approve/Deny wired to `approveAuthorization`/
      `denyAuthorization` and a redirect to the returned `redirect_url`.
      An invalid/expired `authorization_id` routes to the same shared
      failure-state rendering used for the missing-parameter case.
    """
    script = _SCRIPT_TEMPLATE.format(
        supabase_url=_escape_js_string(supabase_url),
        supabase_anon_key=_escape_js_string(supabase_anon_key),
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect your account</title>
<style>{_STYLE}</style>
<script src="{_SUPABASE_JS_CDN_URL}"></script>
</head>
<body>
<div class="page">
<div id="oauth-consent-root"></div>
</div>
<script>{script}</script>
</body>
</html>"""


def _escape_js_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("</script>", "<\\/script>")
