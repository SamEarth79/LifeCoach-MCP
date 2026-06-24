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
  background: #fff8f4;
  color: #1f1b17;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.page {
  max-width: 440px;
  margin: 0 auto;
  padding: 48px 20px 40px;
}
.brand-header {
  text-align: center;
  margin-bottom: 32px;
}
.brand-header h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #416352;
}
.brand-header p {
  margin: 8px 0 0;
  font-size: 14px;
  color: #6b6259;
}
.auth-card {
  background: #fbf2eb;
  border: 1px solid rgba(193, 200, 194, 0.3);
  border-radius: 16px;
  padding: 32px;
  box-shadow: 0 8px 32px rgba(74, 69, 64, 0.04);
}
.loading-state {
  padding: 32px 0 8px;
  text-align: center;
  font-size: 13px;
  color: #9a9082;
}
.failure-state {
  padding: 4px 0;
}
.failure-message {
  background: #f6ece6;
  border-radius: 12px;
  padding: 16px 18px;
  font-size: 13px;
  color: #8a5a3c;
}
.login-form {
  padding: 0;
}
.input-group {
  margin: 0 0 20px;
}
.input-group label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #6b6259;
  margin: 0 0 8px 2px;
}
.input-wrapper {
  position: relative;
}
.input-wrapper .input-icon {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  color: #a39a8f;
  display: flex;
}
.input-wrapper input {
  width: 100%;
  height: 50px;
  padding: 0 16px 0 46px;
  border: 1px solid #ddd3c6;
  border-radius: 10px;
  background: #ffffff;
  font-size: 14px;
  font-family: inherit;
  color: #1f1b17;
}
.input-wrapper input:focus {
  outline: none;
  border-color: #416352;
  box-shadow: 0 0 0 2px rgba(65, 99, 82, 0.12);
}
.password-toggle {
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  padding: 4px;
  color: #a39a8f;
  cursor: pointer;
  display: flex;
}
.auth-button {
  width: 100%;
  margin-top: 8px;
  height: 52px;
  border: none;
  border-radius: 9999px;
  background: #416352;
  color: #ffffff;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.auth-button:hover {
  background: #355445;
}
.login-error {
  margin-top: 16px;
  background: #f6ece6;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
  color: #8a5a3c;
}
.consent-screen {
  padding: 4px 0;
  text-align: center;
}
.consent-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto 16px;
  border-radius: 9999px;
  background: #e8ded1;
  color: #416352;
  display: flex;
  align-items: center;
  justify-content: center;
}
.consent-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0 0 6px;
  color: #1f1b17;
}
.consent-subtitle {
  font-size: 13px;
  color: #6b6259;
  margin: 0 0 18px;
}
.consent-client-name {
  font-weight: 600;
  color: #1f1b17;
}
.scope-list {
  list-style: none;
  margin: 0 0 24px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
}
.scope-item {
  background: #ffffff;
  border: 1px solid #ece3d8;
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 13px;
  color: #1f1b17;
  display: flex;
  align-items: center;
  gap: 8px;
}
.scope-check {
  color: #416352;
  display: flex;
  flex-shrink: 0;
}
.consent-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.consent-approve {
  width: 100%;
  padding: 14px;
  border: none;
  border-radius: 9999px;
  background: #416352;
  color: #ffffff;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
}
.consent-approve:hover {
  background: #355445;
}
.consent-deny {
  width: 100%;
  padding: 14px;
  border: 1px solid #ddd3c6;
  border-radius: 9999px;
  background: transparent;
  color: #1f1b17;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
}
.consent-action-error {
  margin-top: 16px;
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

const LIFECOACH_MAIL_ICON =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>';
const LIFECOACH_LOCK_ICON =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>';
const LIFECOACH_EYE_ICON =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>';
const LIFECOACH_ARROW_ICON =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>';
const LIFECOACH_SHIELD_ICON =
  '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>';
const LIFECOACH_CHECK_ICON =
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';

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
      return (
        '<li class="scope-item"><span class="scope-check">' +
        LIFECOACH_CHECK_ICON +
        "</span>" +
        lifecoachEscapeHtml(scope) +
        "</li>"
      );
    }})
    .join("");

  document.getElementById("oauth-consent-root").innerHTML =
    '<div class="consent-screen">' +
    '<div class="consent-icon">' +
    LIFECOACH_SHIELD_ICON +
    "</div>" +
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
    '<div class="input-group">' +
    '<label for="oauth-login-email">Email Address</label>' +
    '<div class="input-wrapper">' +
    '<span class="input-icon">' +
    LIFECOACH_MAIL_ICON +
    '</span>' +
    '<input type="email" id="oauth-login-email" autocomplete="email" placeholder="name@example.com" required>' +
    '</div>' +
    '</div>' +
    '<div class="input-group">' +
    '<label for="oauth-login-password">Password</label>' +
    '<div class="input-wrapper">' +
    '<span class="input-icon">' +
    LIFECOACH_LOCK_ICON +
    '</span>' +
    '<input type="password" id="oauth-login-password" autocomplete="current-password" placeholder="••••••••" required>' +
    '<button type="button" class="password-toggle" id="oauth-login-password-toggle" aria-label="Show password">' +
    LIFECOACH_EYE_ICON +
    '</button>' +
    '</div>' +
    '</div>' +
    '<button type="submit" class="auth-button">Sign In ' +
    LIFECOACH_ARROW_ICON +
    '</button>' +
    '<p class="login-error" id="oauth-login-error" hidden></p>' +
    '</form>';

  document
    .getElementById("oauth-login-form")
    .addEventListener("submit", function (event) {{
      event.preventDefault();
      lifecoachHandleLoginSubmit(client, authorizationId);
    }});

  document
    .getElementById("oauth-login-password-toggle")
    .addEventListener("click", function () {{
      const passwordInput = document.getElementById("oauth-login-password");
      const isHidden = passwordInput.type === "password";
      passwordInput.type = isHidden ? "text" : "password";
      document
        .getElementById("oauth-login-password-toggle")
        .setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
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

    if (!("authorization_id" in details)) {{
      // The user already approved this OAuth client in a prior session.
      // getAuthorizationDetails returns an OAuthRedirect (redirect_url
      // only) instead of OAuthAuthorizationDetails (client, scope, etc.)
      // in this case - there is no consent screen to show, just redirect.
      if (!details.redirect_url) {{
        console.error(
          "lifecoach oauth consent: already-approved response missing redirect_url",
          details,
          {{ authorizationId: authorizationId }}
        );
        lifecoachRenderFailureState(
          "This link is invalid or has expired. Please try connecting again from the app."
        );
        return;
      }}
      window.location.href = details.redirect_url;
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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{_STYLE}</style>
<script src="{_SUPABASE_JS_CDN_URL}"></script>
</head>
<body>
<div class="page">
<header class="brand-header">
<h1>Coach</h1>
<p>A digital space to ground your day.</p>
</header>
<section class="auth-card">
<div id="oauth-consent-root"></div>
</section>
</div>
<script>{script}</script>
</body>
</html>"""


def _escape_js_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("</script>", "<\\/script>")
