# Implementation Summary: LFC-005-oauth-consent-login

## LFC-STORY-005-001: Serve the OAuth consent page at the registered authorization path

**What was implemented:** `app/oauth_consent.py` (new module), exposing
`render_oauth_consent_page(supabase_url, supabase_anon_key) -> str`, and a
new unauthenticated route `GET /oauth/consent` in `app/main.py`
(`get_oauth_consent_page`) that calls it with
`get_settings().supabase_url`/`.supabase_anon_key`. The returned page is a
complete static HTML document: a pinned-exact-version
`@supabase/supabase-js@2.108.2` CDN `<script>` tag, `SUPABASE_URL`/
`SUPABASE_ANON_KEY` injected as escaped JS string-literal constants via a
new `_escape_js_string` helper (escaping backslashes, double quotes, and
`</script>` tag-closing sequences — a JS-string/`<script>`-body injection
context, distinct from the HTML-attribute escaping `app/ui_templates.py`
already uses for MCP-UI `onclick` handlers), and an embedded
`lifecoachInit()` script that reads `authorization_id` from
`window.location.search` and renders a clear, non-technical failure state
immediately (without ever initializing the Supabase client) when it's
missing. `renderLoginOrConsent` is left as a named stub showing a generic
loading state — the real login form and consent screen are out of scope for
this story and land in LFC-STORY-005-002/003. The route has deliberately no
`Depends(...)` of any kind (no rate limit, no bearer-token auth), per
`architecture.md`'s documented rationale: the page must be reachable by an
unauthenticated browser since it needs to present a login form for visitors
with no active Supabase session.

**What was tested and why:** Read `app/oauth_consent.py` and the new route
in `app/main.py` in full before writing any test, rather than trusting the
story description. Per `rules/testing.md`, this story introduces new
non-trivial rendering/escaping logic and a new HTTP route, so both unit and
feature layers were required. E2E (Playwright) was explicitly **not**
written, per `requirements.md`'s own "Out of scope" instruction: a
self-consistency E2E test against a fake/mocked Supabase backend would only
prove internal consistency, not the real external contract, since no live
Supabase deployment with "Site URL"/"Authorization Path" configured exists
yet. The user will verify the live flow manually once a real deployment
exists.

- **Unit tests** (`tests/unit/test_oauth_consent.py`, new file, 14 tests):
  the pinned exact-version CDN script tag and a dedicated regression test
  asserting the version string is neither `@latest` nor a semver range; the
  injected `SUPABASE_URL`/`SUPABASE_ANON_KEY` JS constants; the full HTML
  document shape; the missing-`authorization_id` JS logic (reads
  `window.location.search`, calls `lifecoachRenderFailureState` with the
  exact non-technical message, and never reaches `createClient` on that
  path — verified by isolating that branch's source text and asserting on
  it directly); and a security-focused suite for `_escape_js_string` that
  constructs actual hostile payloads (a lone backslash, a lone double-quote,
  a `</script><script>alert(1)</script>` breakout, a combined
  quote-plus-`</script>` breakout, and full end-to-end hostile
  `supabase_url`/`supabase_anon_key` values run through
  `render_oauth_consent_page` itself) and asserts the unescaped/exploitable
  form never survives in the output — not just that the escaping function
  exists.
- **Feature tests** (`tests/feature/test_oauth_consent.py`, new file, 6
  tests), using `fastapi.testclient.TestClient` against the real
  `app.main.app` with `get_settings` monkeypatched (mirroring
  `test_health.py`'s pattern): `200` + `text/html` content type; the pinned
  script and injected config values present in the actual served response
  body; reachability with no `Authorization` header and no
  `WWW-Authenticate` response header; reachability *with* a garbage
  `Authorization` header present (proving the route ignores it either way,
  not just that it doesn't require it); a structural check on the live
  FastAPI route object's `dependant.dependencies` confirming neither
  `get_current_user` nor `enforce_rate_limit` is registered, verifying
  `architecture.md`'s "no auth dependency" claim directly rather than only
  inferring it from passing requests; and the missing-`authorization_id`
  failure-state JS logic re-confirmed against the actual HTTP response body.
- The no-auth-dependency design decision (architecture.md's most
  security-sensitive call in this story) was independently re-verified by
  reading the route's function signature and by inspecting the live route
  object at runtime, rather than trusting the architecture doc's claim at
  face value.

**Test results:** 20 new tests (14 unit + 6 feature), 223/223 full suite
passing across two consecutive runs with no flakiness (up from the 203
baseline carried over from LFC-004-mcp-ui-home-goal-views). See
`test-results.md` for the full breakdown per acceptance criterion, including
the hostile-input escaping verification detail and the explicit
out-of-scope-E2E caveat per `requirements.md`.
