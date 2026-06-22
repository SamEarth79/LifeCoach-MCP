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

## LFC-STORY-005-002: Login form authenticates existing users via the Supabase client SDK

**What was implemented:** `app/oauth_consent.py` extended with
`lifecoachRenderLoginForm(client, authorizationId)` (renders an
email/password form with a hidden error placeholder, no signup/
account-creation link) and `lifecoachHandleLoginSubmit(client,
authorizationId)` (calls `client.auth.signInWithPassword({ email, password
})`; on error, sets a single fixed generic `"Invalid email or password."`
message with no field- or account-existence-specific variant; on success,
re-invokes `renderLoginOrConsent` rather than navigating away). The existing
`renderLoginOrConsent` (previously a stub) now calls
`client.auth.getSession()` first and only renders the login form when there
is no active session, otherwise falling through to the existing
loading-state stub left for LFC-STORY-005-003 to replace with the real
consent screen.

**What was tested and why:** Read the full current `app/oauth_consent.py`
before writing any test. Per `rules/testing.md`, this is new non-trivial
conditional-rendering/state-transition logic, so unit tests were required.
Feature tests were judged **not required**: this story adds no new HTTP
route or server-side behavior — the existing `GET /oauth/consent` feature
tests from story 001 already cover the route's request/response contract,
and this story's actual behavior (form interaction, SDK call wiring) lives
entirely in client-side JS with no additional HTTP-layer surface to
exercise. E2E (Playwright) was **not** written, for the same reason as
story 001: no live Supabase deployment exists yet to test the real
`signInWithPassword` wire contract against, and a test against a mocked
backend would only prove self-consistency with the same assumption already
baked into the implementation — flagged explicitly as an unverified
external-contract assumption in `test-results.md` rather than silently
passed.

- **Unit tests** (`tests/unit/test_oauth_consent.py`, 10 new tests added to
  the existing file): the no-session path renders the login form
  (email + password fields only, no signup link); the form's submit handler
  calls `preventDefault()` then `lifecoachHandleLoginSubmit`;
  `signInWithPassword` is called with `{ email, password }` read from the
  two input elements; success calls `renderLoginOrConsent` again rather
  than redirecting; failure shows exactly one generic error string anywhere
  in the page, with explicit negative assertions ruling out
  field-specific/account-existence-revealing variants
  (`"email not found"`, `"no such user"`, `"wrong password"`, etc.); the
  failure path never reassigns `window.location` or tears down the form
  (`.remove(`/`.innerHTML`), only updates the error text — so the user can
  retry without a reload; the `email`/`password` variables are never
  logged (`console.*`) or echoed anywhere outside the `signInWithPassword`
  call itself; a whole-file grep plus a dedicated regression test confirm
  no "sign up"/"signup"/"create account"/"register" text exists anywhere on
  the page; and a symmetric case confirms an active session skips the
  login form and falls through to the loading state.
- The single-generic-error-message requirement (this repo's established
  no-account-enumeration discipline) was verified by asserting both the
  presence of the correct generic string and the explicit absence of any
  more specific alternative — not just that *a* message appears.

**Test results:** 10 new unit tests, 233/233 full suite passing across two
consecutive runs with no flakiness (up from the 223 baseline after
LFC-STORY-005-001). No feature or E2E tests were added — see
`test-results.md` for the full per-acceptance-criterion breakdown, the
security-review detail on the no-enumeration error handling, and the
explicitly flagged unverified `signInWithPassword` wire-contract assumption
(`PASS WITH CAVEATS`).

## LFC-STORY-005-003: Consent screen renders scopes and reports the approve/deny decision back to Supabase

**What was implemented:** `app/oauth_consent.py` extended with
`lifecoachEscapeHtml(value)` (HTML-entity escaping for `&`, `<`, `>`, `"`,
`'` — distinct from the existing `_escape_js_string`, which escapes for a
JS-string-literal context, not HTML), `lifecoachRenderConsentScreen(client,
authorizationId, details)` (renders `details.client.name` and each
space-split scope from `details.scope`, each individually run through
`lifecoachEscapeHtml` before being concatenated into the consent screen's
`innerHTML`, plus Approve/Deny buttons wired to
`lifecoachHandleConsentDecision`), and `lifecoachHandleConsentDecision(client,
authorizationId, decision)` (calls `approveAuthorization`/
`denyAuthorization`, navigates via `window.location.href =
data.redirect_url` on success, and shows a retryable
`"Something went wrong. Please try again."` message — clearing any prior
error at the start of each attempt, never removing or disabling the buttons
— on a falsy/incomplete response or a thrown exception). The existing
`renderLoginOrConsent`'s session-present branch now calls
`client.auth.oauth.getAuthorizationDetails(authorizationId)` inside a
`try`/`catch`, routing to `lifecoachRenderConsentScreen` on success or to
the same shared `lifecoachRenderFailureState` helper already used for the
missing-`authorization_id` case (both the error-response branch and the
catch block) on failure — replacing the loading-state stub this story's
fetch call now uses for its real intended transitional purpose.

**What was tested and why:** Read the full current `app/oauth_consent.py`
end to end before writing any test, including re-verifying (not just
trusting) the claim that the failure-state path reuses the existing shared
helper rather than introducing a second, parallel implementation. Per
`rules/testing.md`, this is new non-trivial rendering, escaping, and
state-transition logic, so unit tests were required. Feature tests were
judged **not required**, same rationale as story 002: no new HTTP route or
server-side behavior. E2E (Playwright) was **not** written, for the same
reason as stories 001/002: no live Supabase deployment exists yet to verify
the real `getAuthorizationDetails`/`approveAuthorization`/
`denyAuthorization` wire contracts against — flagged explicitly as
unverified external-contract assumptions in `test-results.md`.

- **Unit tests** (`tests/unit/test_oauth_consent.py`, 22 new tests added to
  the existing file): `getAuthorizationDetails` is called on the
  active-session path and routes to the consent screen on success or the
  shared failure-state helper on error/thrown-exception (with a dedicated
  test confirming genuine reuse — one helper function definition, one
  message literal used at all three call sites — rather than a new
  parallel implementation); the consent screen renders `client.name` and
  every scope; **the security-critical escaping requirement** is verified
  three ways — confirming `lifecoachEscapeHtml` (not `_escape_js_string`) is
  the exact function called on both `details.client.name` and each
  individual scope token inside the `.map()` callback, confirming the raw
  unescaped `details.client.name` expression never appears inside the
  literal `innerHTML =` assignment text (only the pre-escaped variable
  does), and running two constructed hostile payloads (an `<img
  src=x onerror=alert(1)>` XSS payload as a hostile client name, a
  `read"><script>alert(document.cookie)</script>` attribute-breakout
  payload as a hostile scope) through a faithful Python re-implementation
  of `lifecoachEscapeHtml`'s exact replacement chain, confirming both are
  fully neutralized; Approve/Deny buttons are wired to
  `lifecoachHandleConsentDecision` with the correct decision string, which
  calls the correct SDK method per decision and navigates via
  `window.location.href` on success; the approve/deny failure path (missing
  `redirect_url`, `error`, or a thrown exception) shows a retryable error
  message without navigating, removing, or disabling the buttons, and
  clears any prior error at the start of each new attempt.
- The AC2 security requirement (HTML-escaping before any `innerHTML`
  insertion) was independently verified, not just trusted from reading the
  code: confirmed `lifecoachEscapeHtml` is structurally distinct from
  `_escape_js_string` (different escaping rules for a different injection
  context), confirmed it is actually invoked at both insertion points, and
  confirmed via hostile-payload simulation that it neutralizes a realistic
  `<script>`/`<img onerror>`-style XSS attempt the same way any HTML-escaping
  helper must.
- One stale documentation note (not a test/behavior issue) was found and
  flagged rather than silently fixed: `render_oauth_consent_page`'s
  docstring still describes the consent screen as a stub this story
  replaces, in present tense, which is now inaccurate documentation since
  this story has already replaced it.

**Test results:** 22 new unit tests, 255/255 full suite passing across two
consecutive runs with no flakiness (up from the 233 baseline after
LFC-STORY-005-002). No feature or E2E tests were added — see
`test-results.md` for the full per-acceptance-criterion breakdown, the
hostile-payload escaping verification, the failure-state-reuse verification,
and the explicitly flagged unverified `getAuthorizationDetails`/
`approveAuthorization`/`denyAuthorization` wire-contract assumptions
(`PASS WITH CAVEATS`).

## Overall feature summary: LFC-005-oauth-consent-login

All three stories are implemented, tested, and verdict `PASS WITH CAVEATS`.
The feature builds a complete OAuth 2.1 consent flow at `GET
/oauth/consent`: the missing-`authorization_id` failure state (001), the
login form for unauthenticated visitors (002), and the
authorization-details fetch, HTML-escaped consent screen, and
approve/deny-with-redirect flow (003), all sharing one failure-state helper
and one consistent escaping discipline appropriate to each injection context
(`_escape_js_string` for server-injected JS string literals,
`lifecoachEscapeHtml` for OAuth-client-controlled values rendered into
`innerHTML`). The single caveat carried through every story: no automated
E2E test exists against a real, live Supabase deployment, since none exists
yet — all of Supabase's actual wire-format/response-shape assumptions
(`signInWithPassword`, `getAuthorizationDetails`,
`approveAuthorization`/`denyAuthorization`) remain explicitly flagged,
unverified external-contract risks pending the user's manual verification
against a real deployment.
