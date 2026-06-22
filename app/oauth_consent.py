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

This story (LFC-STORY-005-001) only builds the page shell: CDN script load,
config injection, and the missing-`authorization_id` failure state. The
login form and consent screen are filled in by `_render_login_form` and
`_render_consent_screen` in later stories — both are left as named stubs
below so this file doesn't need restructuring when they land.
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

function renderLoginOrConsent(client, authorizationId) {{
  // Stub for LFC-STORY-005-002 (login form) and LFC-STORY-005-003
  // (consent screen). For now this only shows a generic loading state;
  // the real session check / getAuthorizationDetails call lands later.
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

    This story only implements:
    - The page shell and the pinned-version `supabase-js` CDN script tag.
    - The missing-`authorization_id` failure state.
    - A `renderLoginOrConsent` stub showing a generic loading state when
      `authorization_id` is present — the real login form
      (LFC-STORY-005-002) and consent screen (LFC-STORY-005-003) replace
      that stub's body in later stories without needing this shell to
      change.
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
