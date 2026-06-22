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
and the missing-`authorization_id` failure state. LFC-STORY-005-002 (this
story) fills in the login form: a session check, an email/password form
rendered when there's no active session, and `signInWithPassword` wired to
submit. The consent screen itself is still a loading-state stub, left for
LFC-STORY-005-003 to replace.
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
    const errorEl = document.getElementById("oauth-login-error");
    errorEl.textContent = "Invalid email or password.";
    errorEl.hidden = false;
    return;
  }}

  renderLoginOrConsent(client, authorizationId);
}}

async function renderLoginOrConsent(client, authorizationId) {{
  // Login form lands in LFC-STORY-005-002; the consent screen itself is
  // built in LFC-STORY-005-003. Once a session exists, this only shows a
  // generic loading state until that story fills in the real
  // getAuthorizationDetails call.
  const {{ data }} = await client.auth.getSession();

  if (!data.session) {{
    lifecoachRenderLoginForm(client, authorizationId);
    return;
  }}

  lifecoachRenderLoadingState();
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

    Implements, across LFC-STORY-005-001 and LFC-STORY-005-002:
    - The page shell and the pinned-version `supabase-js` CDN script tag.
    - The missing-`authorization_id` failure state.
    - A session check: if no active Supabase session exists, an
      email/password login form is rendered and wired to
      `signInWithPassword`, with a generic invalid-credentials error on
      failure and no page reload required to retry. If a session exists
      (or is just established by a successful login), the page shows a
      generic loading state, a stub the consent screen (LFC-STORY-005-003)
      replaces without needing this shell to change.
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
