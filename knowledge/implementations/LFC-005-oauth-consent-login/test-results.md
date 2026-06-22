# Test Results: LFC-005-oauth-consent-login

## LFC-STORY-005-001

**Verdict: PASS WITH CAVEATS** — per `requirements.md`'s explicit "Out of
scope" note, automated E2E (Playwright) against a real Supabase deployment
is out of scope for this feature (no live deployment exists yet); covered
instead by unit and feature tests only, with the live external-contract
verification left for the user to do manually once a real deployment exists.

### Implementation verified against the code (read in full before writing any test)

Read `app/oauth_consent.py` and the new `GET /oauth/consent` route in
`app/main.py` directly rather than trusting the story description at face
value. Confirmed:

- `render_oauth_consent_page(supabase_url, supabase_anon_key)` returns a
  complete `<!DOCTYPE html>` document containing a `<script
  src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.108.2/dist/umd/supabase.js">`
  tag — an exact version (`2.108.2`), not `@latest` and not a semver range
  (`^`/`~` prefix).
- `SUPABASE_URL`/`SUPABASE_ANON_KEY` are injected as JS `const` string
  literals inside the page's `<script>` body via `_escape_js_string`, not
  raw f-string interpolation.
- The embedded JS (`lifecoachInit`) reads `authorization_id` via
  `new URLSearchParams(window.location.search).get("authorization_id")`. If
  falsy, it calls `lifecoachRenderFailureState(...)` with the literal message
  "This link is invalid or has expired. Please try connecting again from the
  app." and `return`s immediately — `supabase.createClient(...)` is only
  reached after that early return, so the Supabase client is never
  initialized on the missing-`authorization_id` path.
- `app/main.py`'s `GET /oauth/consent` route (`get_oauth_consent_page`) has
  **no** `Depends(...)` parameters at all — confirmed by reading the route
  signature directly: `async def get_oauth_consent_page() -> str`, unlike
  every other route in the file, which takes
  `_rate_limit: None = Depends(enforce_rate_limit)` and/or
  `current_user: CurrentUser = Depends(get_current_user)`. This matches
  `architecture.md`'s documented, deliberate exception.
- `_escape_js_string` (`app/oauth_consent.py`) escapes, in order: `\` ->
  `\\`, `"` -> `\"`, then `</script>` -> `<\/script>`. Constructed hostile
  inputs (`</script><script>alert(1)</script>`, a combined
  `"; </script><script>alert(document.cookie)</script>//` payload, and a
  hostile `SUPABASE_URL`/`SUPABASE_ANON_KEY` value containing a backslash,
  an unescaped quote, and a literal `</script>` sequence) were actually run
  through both `_escape_js_string` directly and the full
  `render_oauth_consent_page` pipeline — in every case the raw `</script>`
  sequence and the unescaped quote/backslash do not survive in the rendered
  output, confirmed by assertion, not by reading the function and assuming
  it works.

### Layers required

- Unit: required — `render_oauth_consent_page`/`_escape_js_string` are new,
  non-trivial rendering and escaping logic (the failure-state JS-generation
  path and the security-sensitive string-escaping helper). Added
  `tests/unit/test_oauth_consent.py`, mirroring the existing
  `tests/unit/test_ui_templates.py` one-module-per-renderer convention.
- Feature: required — a new HTTP route (`GET /oauth/consent`) exists; its
  acceptance criteria (200 + HTML content, reachable without auth, embedded
  failure-state JS) are exercised through the real route via
  `fastapi.testclient.TestClient`, the same pattern as
  `tests/feature/test_health.py`. Added `tests/feature/test_oauth_consent.py`.
- E2E (Playwright): **not added**, per `requirements.md`'s explicit
  "Out of scope" instruction — this story only builds the page shell and
  failure state, with no login form or consent screen yet (those land in
  LFC-STORY-005-002/003), and a self-consistency E2E against a fake/mocked
  Supabase backend would only prove internal self-consistency, not the real
  external contract. The user will manually verify the live flow once a
  real Supabase deployment with "Site URL"/"Authorization Path" configured
  exists.

### Unit tests — 14 new, all passing

`tests/unit/test_oauth_consent.py`:

1. `test_render_oauth_consent_page_includes_pinned_exact_version_supabase_js_script_tag`
   — AC1: exact `<script src=...supabase-js@2.108.2/...>` tag present,
   `@latest` absent.
2. `test_pinned_supabase_js_cdn_url_is_an_exact_version_not_a_range` —
   security requirement: parses the version out of the CDN URL and asserts
   it starts with a digit and is not prefixed with `^`/`~`, and is not the
   literal string `"latest"`.
3. `test_render_oauth_consent_page_injects_supabase_url_and_anon_key_as_js_constants`
   — AC1: both `const SUPABASE_URL = "..."` and
   `const SUPABASE_ANON_KEY = "..."` lines present verbatim with the
   supplied values.
4. `test_render_oauth_consent_page_returns_200_compatible_full_html_document`
   — AC1: starts with `<!DOCTYPE html>`, has the expected `<title>`.
5. `test_render_oauth_consent_page_embedded_js_reads_authorization_id_from_query_string`
   — AC3: confirms `window.location.search` and
   `params.get("authorization_id")` both appear in the embedded JS source.
6. `test_render_oauth_consent_page_embedded_js_renders_failure_state_when_authorization_id_missing`
   — AC3: isolates the `if (!authorizationId)` branch's source text and
   asserts it calls `lifecoachRenderFailureState(...)` with the
   "invalid or has expired" message.
7. `test_render_oauth_consent_page_does_not_initialize_supabase_client_on_missing_authorization_id_path`
   — AC3: confirms `createClient` does not appear anywhere inside the
   `if (!authorizationId)` branch's source text — the Supabase client is
   never constructed on this path.
8. `test_render_oauth_consent_page_failure_message_is_clear_and_non_technical`
   — AC3/requirements.md's non-functional "consistency" requirement: the
   exact non-technical message is present; no `Traceback`/`Exception`
   substrings anywhere in the page.
9. `test_escape_js_string_escapes_backslashes` — escaping: `a\b` ->
   `a\\b`.
10. `test_escape_js_string_escapes_double_quotes` — escaping: `a"b` ->
    `a\"b`.
11. `test_escape_js_string_escapes_closing_script_tag_sequence` — escaping:
    a literal `</script><script>alert(1)</script>` payload has every
    `</script>` occurrence replaced with `<\/script>`.
12. `test_escape_js_string_neutralizes_combined_quote_and_script_breakout_payload`
    — escaping: a combined quote-plus-`</script>` breakout string is fully
    neutralized (no raw `</script>` survives, the quote is escaped).
13. `test_render_oauth_consent_page_neutralizes_hostile_supabase_url_breakout_attempt`
    — end-to-end through `render_oauth_consent_page` with a hostile
    `supabase_url` containing an unescaped quote and a `</script><script>`
    breakout attempt: the raw breakout sequence never appears in the
    rendered page.
14. `test_render_oauth_consent_page_neutralizes_hostile_anon_key_with_backslash_and_quote`
    — end-to-end through `render_oauth_consent_page` with a hostile
    `supabase_anon_key` containing a backslash followed by a quote and a
    `; alert(1); //` JS-injection attempt: asserts the exact expected
    escaped line is present, and that the unescaped/exploitable form
    (`abc"; alert(1); //`, which would terminate the JS string literal and
    let `alert(1)` execute as a statement) never appears anywhere in the
    output.

### Feature tests — 6 new, all passing

`tests/feature/test_oauth_consent.py`, using `fastapi.testclient.TestClient`
against the real `app.main.app`, with `app.main.get_settings` monkeypatched
to return a `Settings` instance with known test values (mirroring
`test_health.py`'s monkeypatch-the-dependency style, since this route reads
config directly via `get_settings()` rather than through FastAPI's
dependency-injection mechanism):

1. `test_get_oauth_consent_returns_200_with_html_content_type` — AC1: `200`
   status, `text/html` content-type.
2. `test_get_oauth_consent_includes_pinned_supabase_js_script_and_injected_config`
   — AC1: pinned version string present in the response body, `@latest`
   absent, both injected config constants present with the exact test
   values supplied via the monkeypatched settings.
3. `test_get_oauth_consent_is_reachable_with_no_authorization_header` — AC2:
   no `Authorization` header sent, `200` returned, no `WWW-Authenticate`
   header in the response (same negative-assertion style as
   `test_health.py`'s equivalent test).
4. `test_get_oauth_consent_with_authorization_header_present_still_succeeds`
   — AC2 (symmetric case): a request that *does* send an (invalid/garbage)
   `Authorization` header still succeeds with `200`, confirming the route
   truly ignores the header rather than conditionally rejecting it.
5. `test_get_oauth_consent_route_has_no_auth_or_rate_limit_dependency` — AC2,
   verified structurally rather than just behaviorally: inspects the actual
   registered FastAPI route's `dependant.dependencies` list and asserts
   neither `get_current_user` nor `enforce_rate_limit` appears by name —
   confirms the absence directly from the route object, not just from the
   passing behavior of the requests above.
6. `test_get_oauth_consent_embedded_js_renders_failure_state_for_missing_authorization_id`
   — AC3, exercised through the real HTTP response body rather than just the
   renderer directly: confirms `params.get("authorization_id")`, the
   `if (!authorizationId)` branch, `lifecoachRenderFailureState`, the
   non-technical message, and the absence of `createClient` within that
   branch are all present in the actual served HTML.

### Security review

- **JS-string-context escaping**: confirmed (not merely read) that
  `_escape_js_string` neutralizes the three relevant injection primitives —
  backslash, double-quote, and a `</script>` tag-closing sequence — both in
  isolation and via constructed combined hostile payloads run through the
  full `render_oauth_consent_page` pipeline. This is the same escaping
  discipline already established for the MCP-UI `onclick`-attribute escaping
  in `app/ui_templates.py`, applied here to a `<script>`-body JS-string
  context instead of an HTML-attribute context — a different injection
  surface, correctly handled with the appropriate escaping for that context
  (not just reusing `html.escape`, which would be insufficient for a
  `<script>` body).
- **Version pin**: confirmed the CDN URL pins an exact `supabase-js` version
  (`2.108.2`) rather than `@latest` or a semver range, both by direct string
  inspection and a dedicated regression test that would fail if the pin were
  ever loosened to a range or `@latest`.
- **No-auth-dependency claim**: confirmed by reading the actual route
  function signature (zero `Depends(...)` parameters) and by inspecting the
  live FastAPI route object's resolved dependency list at runtime — not
  inferred only from the route returning `200` without a header.

### Full suite regression check

Ran `uv run pytest` from the repo root twice in a row to rule out flakiness:

- Run 1: **223 passed**, 0 failed, 36 warnings (same pre-existing
  deprecation warnings as before, unrelated to this story).
- Run 2: **223 passed**, 0 failed, 36 warnings — identical result, no
  flakiness.

223 = 203 (prior baseline carried over from LFC-004-mcp-ui-home-goal-views)
+ 14 new unit tests + 6 new feature tests = 223. The full suite run confirms
this exactly: **223 passed, 0 failed**, across two consecutive runs.

### Totals: 20 new automated tests (14 unit + 6 feature), 223/223 full suite
passing across two consecutive runs, 0 failed, no flakiness. All 3
acceptance criteria are covered by at least one test each, including a
genuine hostile-input behavioral test for the JS-string-escaping helper
(constructed `</script>`/quote/backslash breakout payloads, run through both
the helper directly and the full page-rendering pipeline, confirmed
neutralized on the actual rendered output — not assumed safe from reading
the code). The no-auth-dependency design decision was independently
re-verified by inspecting the live route object's dependency list, not just
trusted from `architecture.md`'s claim. Per `requirements.md`'s explicit
scope note, no E2E test was written or attempted for this story — the live
external contract against a real Supabase "Site URL"/"Authorization Path"
deployment remains genuinely unverified and is the responsibility of the
user's manual verification once a real deployment exists; this is recorded
as the story's `PASS WITH CAVEATS` caveat, not silently passed.

## LFC-STORY-005-002

**Verdict: PASS WITH CAVEATS** — same out-of-scope-E2E rationale as story
001 (no live Supabase deployment exists yet to test the real
`signInWithPassword` wire contract against); covered instead by unit tests
only, against the actual JS source structure embedded in
`render_oauth_consent_page`'s output.

### Implementation verified against the code (read in full before writing any test)

Read the full current `app/oauth_consent.py`, confirming:

- `lifecoachRenderLoginForm(client, authorizationId)` renders a form with an
  `id="oauth-login-email"` (`type="email"`) field, an
  `id="oauth-login-password"` (`type="password"`) field, a submit button, and
  a hidden `id="oauth-login-error"` paragraph for the error message — no
  signup/account-creation link or text anywhere in the form markup.
- The form's `submit` listener calls `event.preventDefault()` then
  `lifecoachHandleLoginSubmit(client, authorizationId)` — no native form
  submission/page reload on submit.
- `lifecoachHandleLoginSubmit` reads `email`/`password` from the two input
  elements' `.value`, calls
  `client.auth.signInWithPassword({ email, password })`, and on `error`
  sets `errorEl.textContent = "Invalid email or password."` and
  `errorEl.hidden = false`, then `return`s — no `window.location` assignment,
  no DOM removal/`innerHTML` rewrite, and no use of the `email`/`password`
  variables anywhere in that branch (only the fixed generic literal string,
  which itself happens to contain the substring "email" as English prose,
  not as the variable).
- On success (no `error`), it calls
  `renderLoginOrConsent(client, authorizationId)` — re-running the session
  check rather than navigating away.
- `renderLoginOrConsent` now calls `client.auth.getSession()` first; if
  `!data.session` it calls `lifecoachRenderLoginForm(...)` and returns;
  otherwise it falls through to `lifecoachRenderLoadingState()` (the
  consent-screen stub, unchanged from story 001, still a placeholder for
  LFC-STORY-005-003).
- Grepped the entire file (`grep -in "sign up|signup|create account|register"
  app/oauth_consent.py`) — zero matches. No signup link or account-creation
  text exists anywhere in the file.

### Layers required

- Unit: required — `lifecoachRenderLoginForm`, `lifecoachHandleLoginSubmit`,
  and the updated `renderLoginOrConsent` are new/changed non-trivial
  conditional-rendering and state-transition logic. Added 10 new tests to
  the existing `tests/unit/test_oauth_consent.py` (no second file created
  for the same module, per the existing one-module-per-renderer
  convention).
- Feature: **not required** — this story adds no new HTTP route and no new
  server-side behavior; the existing `GET /oauth/consent` feature tests from
  story 001 already cover the route itself, and the returned HTML body
  growing with more embedded JS doesn't change the route's
  request/response contract. Per `rules/testing.md`'s scoping rule, feature
  tests are for a story's behavior end-to-end within its own layer — this
  story's behavior (login form interaction, `signInWithPassword` call
  wiring) lives entirely in untestable-from-Python client-side JS, the same
  rationale story 001 used for skipping E2E on its own JS logic, just one
  layer down: there is no real HTTP layer to additionally exercise here
  beyond what's already covered.
- E2E (Playwright): **not added**, same rationale as story 001 — no live
  Supabase deployment exists to test the real `signInWithPassword` wire
  contract against; a Playwright test against a mocked/fake Supabase
  backend would only prove internal self-consistency with the same
  assumption the implementation already makes about Supabase's response
  shape, not the real external contract. Flagged as the explicit unverified
  assumption below, per `rules/testing.md`'s "External-contract assumptions"
  section.

### Unit tests — 10 new, all passing

Added to `tests/unit/test_oauth_consent.py`:

1. `test_render_oauth_consent_page_renders_login_form_when_no_active_session`
   — AC1: isolates `renderLoginOrConsent`'s source and confirms the
   `if (!data.session)` branch calls
   `lifecoachRenderLoginForm(client, authorizationId)`.
2. `test_login_form_html_contains_email_and_password_fields_only` — AC1: the
   rendered form markup contains exactly an email field, a password field,
   and an error placeholder — no other input fields.
3. `test_login_form_submit_handler_is_wired_to_lifecoach_handle_login_submit`
   — AC2 setup: confirms the submit listener calls `preventDefault()` then
   `lifecoachHandleLoginSubmit(client, authorizationId)`.
4. `test_handle_login_submit_calls_sign_in_with_password_with_email_and_password_argument_shape`
   — AC2: confirms `client.auth.signInWithPassword({ email, password })` is
   called with values read from the email/password input elements'
   `.value`.
5. `test_handle_login_submit_calls_render_login_or_consent_on_success` — AC2:
   confirms the success path (no `error`) calls
   `renderLoginOrConsent(client, authorizationId)`, transitioning onward by
   re-running the session check rather than any other mechanism.
6. `test_handle_login_submit_shows_single_generic_error_message_on_invalid_credentials`
   — AC3 + security rule: the literal string `"Invalid email or password."`
   appears in the error branch and appears exactly once anywhere in the
   whole rendered page; confirms no field-specific or
   account-existence-revealing strings (`"email not found"`,
   `"no such user"`, `"wrong password"`, `"user not found"`,
   `"does not exist"`) appear anywhere in the handler.
7. `test_handle_login_submit_error_path_only_sets_error_text_and_does_not_navigate_or_remove_form`
   — AC3: confirms the error branch contains no `window.location`
   assignment and no `.remove(`/`.innerHTML` DOM-teardown call — only
   `errorEl.textContent`/`errorEl.hidden` are set, so the form survives a
   failed login and the user can retry without a reload.
8. `test_handle_login_submit_never_logs_or_echoes_submitted_credentials` —
   security (this repo's no-email-enumeration discipline, extended to
   credential confidentiality): confirms no `console.log`/`console.error`/
   `console.warn` calls exist in the handler, and that the `email`/
   `password` variables never appear in the error branch (only the fixed
   generic literal string, which is excluded from the check before
   asserting).
9. `test_no_signup_or_account_creation_text_anywhere_in_rendered_page` — AC4:
   confirms none of "sign up", "signup", "create account",
   "create an account", "register" (case-insensitive) appear anywhere in
   the full rendered page.
10. `test_render_login_or_consent_shows_loading_state_when_session_already_active`
    — regression/symmetric case for AC1-AC2: confirms an active session
    skips the login form entirely and falls through to
    `lifecoachRenderLoadingState()`.

### Security review

- **Single generic error message, no enumeration**: confirmed the error
  branch contains exactly one fixed literal string
  (`"Invalid email or password."`) regardless of failure reason — there is
  no conditional branching on `error.message`/`error.status`/any other
  property of the SDK's error object that would produce a different message
  for "wrong password" vs. "no such user". The code unconditionally sets
  the same string whenever `error` is truthy, so no code path exists that
  could leak which emails are registered.
- **No credential logging/echoing**: confirmed the `email`/`password`
  variables are read once (from the input elements), passed directly into
  `signInWithPassword`, and never referenced again anywhere else in the
  function — not in the error branch, not via `console.*`, not interpolated
  into any rendered text.
- **No premature page teardown on failure**: confirmed the error path is a
  pure DOM-text-content update (`textContent`/`hidden`) with no
  `window.location` reassignment and no removal/replacement of the form's
  DOM subtree, so a failed login attempt leaves the form intact and
  resubmittable without a page reload, satisfying AC3's "lets the user retry
  without a page reload" requirement directly, not just by absence of an
  explicit redirect.

### Unverified external-contract assumption (flagged per `rules/testing.md`)

`signInWithPassword({ email, password })`'s actual success/error response
shape (a `{ data, error }` object, with `error` falsy on success) is
asserted against here as a fixed assumption baked into both the
implementation and these tests — it has not been verified against a live
Supabase Auth instance in this session. This is the same category of
unverified external-contract risk story 001 flagged for the overall
OAuth flow; it is not a new risk introduced by this story, but is
re-flagged explicitly here since this story is the first to actually call
an Auth SDK method. The user should confirm this shape against a real
Supabase project (or the current `@supabase/supabase-js@2.108.2` docs)
before relying on this flow in production.

### Full suite regression check

Ran `uv run pytest` from the repo root twice in a row:

- Run 1: **233 passed**, 0 failed, 36 warnings (same pre-existing
  deprecation warnings as before, unrelated to this story).
- Run 2: **233 passed**, 0 failed, 36 warnings — identical result, no
  flakiness.

233 = 223 (prior baseline after LFC-STORY-005-001) + 10 new unit tests = 233.

### Totals: 10 new unit tests, 233/233 full suite passing across two
consecutive runs, 0 failed, no flakiness. All 4 acceptance criteria are
covered by at least one test each. The single-generic-error-message /
no-enumeration security requirement was independently verified by asserting
the absence of any field-specific or account-existence-revealing error
strings, not just the presence of the correct generic one. No signup/
account-creation text exists anywhere in the file, confirmed both by direct
grep and by an automated regression test. Per the same out-of-scope
rationale as story 001, no E2E test was written; the real
`signInWithPassword` wire-contract shape remains an explicitly flagged,
unverified assumption pending a live Supabase instance — recorded as this
story's `PASS WITH CAVEATS` caveat, not silently passed.

## LFC-STORY-005-003

**Verdict: PASS WITH CAVEATS** — same out-of-scope-E2E rationale as stories
001/002 (no live Supabase deployment exists yet to verify the real
`getAuthorizationDetails`/`approveAuthorization`/`denyAuthorization` wire
contracts against); covered instead by unit tests only, against the actual
JS source structure embedded in `render_oauth_consent_page`'s output.

### Implementation verified against the code (read in full before writing any test)

Read the full current `app/oauth_consent.py` end to end, confirming:

- `lifecoachEscapeHtml(value)` is a distinct function from `_escape_js_string`
  — it performs HTML-entity escaping (`&`->`&amp;`, `<`->`&lt;`, `>`->`&gt;`,
  `"`->`&quot;`, `'`->`&#39;`), the correct escaping discipline for a value
  being concatenated into an `innerHTML`-bound string, as opposed to
  `_escape_js_string`'s JS-string-literal escaping (backslash/quote/
  `</script>`), which is the wrong context for this sink.
- `lifecoachRenderConsentScreen(client, authorizationId, details)` computes
  `safeClientName = lifecoachEscapeHtml(details.client.name)` and, inside the
  `scopes.map(...)` callback, computes
  `lifecoachEscapeHtml(scope)` for every individual space-split scope token,
  before concatenating either into the `innerHTML` string. The raw
  `details.client.name` value and raw scope strings are never concatenated
  directly — only the escaped `safeClientName`/`scopeItems` variables are.
  Confirmed this by isolating the literal `innerHTML =` assignment's source
  text and asserting `details.client.name` does not appear in it at all.
- `lifecoachHandleConsentDecision(client, authorizationId, decision)` calls
  `client.auth.oauth.approveAuthorization(authorizationId)` when
  `decision === "approve"` and `client.auth.oauth.denyAuthorization(authorizationId)`
  otherwise; on success (`data.redirect_url` present, no `error`) it sets
  `window.location.href = data.redirect_url`; on a falsy/incomplete response
  (`error`, missing `data`, or missing `data.redirect_url`) or a thrown
  exception (caught via `try`/`catch`), it sets the same generic
  `"Something went wrong. Please try again."` message on the
  `#oauth-consent-action-error` element and unhides it, without navigating,
  removing the buttons, disabling them, or rewriting `innerHTML` — so a
  retry is always possible without a reload. It also unhides-then-rehides
  (`errorEl.hidden = true`) at the very start of each invocation, so a retry
  after a prior failure doesn't get stuck showing the stale error
  indefinitely.
- `renderLoginOrConsent`'s session-present branch (after
  `lifecoachRenderLoadingState()`) calls
  `client.auth.oauth.getAuthorizationDetails(authorizationId)` inside a
  `try`/`catch`. On `error || !details`, and in the `catch` block, **both**
  call the exact same `lifecoachRenderFailureState("This link is invalid or
  has expired. Please try connecting again from the app.")` invocation used
  by `lifecoachInit`'s missing-`authorization_id` branch — confirmed there is
  only one `function lifecoachRenderFailureState(` definition in the whole
  file and the exact failure-message literal appears exactly 3 times (one
  per call site: missing-id, details-fetch-error, details-fetch-throw), so
  this is genuine reuse of the single shared helper, not a new parallel
  implementation that could drift from it.
- On a successful fetch, `lifecoachRenderConsentScreen(client, authorizationId,
  details)` is called, which wires the rendered Approve/Deny buttons'
  `click` listeners to `lifecoachHandleConsentDecision(client, authorizationId,
  "approve")` / `"deny"` respectively.

### Layers required

- Unit: required — `lifecoachEscapeHtml`, `lifecoachRenderConsentScreen`,
  `lifecoachHandleConsentDecision`, and the updated `renderLoginOrConsent` are
  new/changed non-trivial rendering, escaping, and state-transition logic.
  Added 22 new tests to the existing `tests/unit/test_oauth_consent.py` (no
  second file created, per the established one-module-per-renderer
  convention).
- Feature: **not required** — same rationale as story 002: no new HTTP route
  or server-side behavior; the existing `GET /oauth/consent` feature tests
  from story 001 already cover the route's request/response contract, and
  this story's behavior lives entirely in client-side JS with no additional
  HTTP-layer surface to exercise.
- E2E (Playwright): **not added**, per `requirements.md`'s explicit
  out-of-scope note — no live Supabase deployment exists to verify the real
  `getAuthorizationDetails`/`approveAuthorization`/`denyAuthorization` wire
  contracts against. A Playwright test against a mocked backend would only
  prove self-consistency with the same response-shape assumption already
  baked into the implementation, not the real external contract. Flagged
  explicitly below per `rules/testing.md`'s "External-contract assumptions"
  section.

### Unit tests — 22 new, all passing

Added to `tests/unit/test_oauth_consent.py`:

1. `test_render_login_or_consent_calls_get_authorization_details_when_session_active`
   — AC1: confirms `client.auth.oauth.getAuthorizationDetails(authorizationId)`
   is called in the active-session branch.
2. `test_render_login_or_consent_routes_to_consent_screen_on_successful_details_fetch`
   — AC1: confirms `lifecoachRenderConsentScreen(client, authorizationId, details)`
   is called on success.
3. `test_render_login_or_consent_routes_to_failure_state_when_details_fetch_errors`
   — AC5: confirms the `error || !details` branch calls
   `lifecoachRenderFailureState` with the non-technical message.
4. `test_render_login_or_consent_routes_to_failure_state_when_get_authorization_details_throws`
   — AC5: confirms the `catch` block also routes to
   `lifecoachRenderFailureState`, so a thrown exception doesn't crash the
   page.
5. `test_failure_state_helper_used_for_authorization_details_error_is_the_same_function_as_missing_id_case`
   — AC5, the "verify reuse not drift" check: confirms there's exactly one
   `lifecoachRenderFailureState` function definition and the exact failure
   message literal appears exactly 3 times (missing-id,
   details-fetch-error, details-fetch-throw) — all sharing the single
   helper, not a new parallel implementation.
6. `test_render_consent_screen_renders_client_name_and_scopes` — AC1:
   confirms `details.client.name`, `details.scope.split(" ")`, and the
   `scope-item`/`scope-list` markup are present.
7. `test_render_consent_screen_escapes_client_name_with_html_escape_helper_not_js_string_escape`
   — **AC2, security-critical**: confirms `lifecoachEscapeHtml(details.client.name)`
   is the exact expression used — not `_escape_js_string`.
8. `test_render_consent_screen_escapes_every_scope_with_html_escape_helper` —
   **AC2, security-critical**: confirms `lifecoachEscapeHtml(scope)` is
   called inside the per-scope `.map()` callback, so every individual scope
   token is escaped, not just the joined string.
9. `test_consent_screen_client_name_and_scopes_never_inserted_into_innerhtml_unescaped`
   — **AC2, security-critical**: isolates the literal `innerHTML =`
   assignment text and confirms the raw `details.client.name` expression
   does not appear in it at all — only the pre-escaped `safeClientName`/
   `scopeItems` variables are concatenated.
10. `test_lifecoach_escape_html_function_escapes_all_five_html_metacharacters`
    — structural check that `lifecoachEscapeHtml`'s regex replacements cover
    all five HTML metacharacters (`&`, `<`, `>`, `"`, `'`) with the correct
    entity for each.
11. `test_lifecoach_escape_html_neutralizes_img_onerror_xss_payload_in_client_name_position`
    — **AC2, security-critical, hostile-payload test**: a constructed
    `<img src=x onerror=alert(1)>` payload, run through a Python
    re-implementation of the exact JS replacement chain, is fully
    neutralized (no raw `<`/`>` survive).
12. `test_lifecoach_escape_html_neutralizes_attribute_breakout_payload_in_scope_position`
    — **AC2, security-critical, hostile-payload test**: a
    `read"><script>alert(document.cookie)</script>` payload (a realistic
    hostile scope value) is fully neutralized — no raw `"`, `<`, `>` survive.
13. `test_lifecoach_escape_html_neutralizes_single_quote_breakout_payload` —
    **AC2, security-critical**: a single-quote attribute-breakout payload is
    also neutralized, exercising the `'` -> `&#39;` rule distinctly from the
    double-quote case.
14. `test_lifecoach_escape_html_is_distinct_from_escape_js_string` — confirms
    the two escaping functions produce different output for the same hostile
    input, and that `_escape_js_string`'s output does NOT HTML-escape angle
    brackets — proving `_escape_js_string` would be the wrong choice for this
    `innerHTML` sink, the exact mistake AC2 guards against.
15. `test_consent_screen_renders_approve_and_deny_buttons_wired_to_handler` —
    AC3/AC4: confirms both buttons exist and their `click` listeners call
    `lifecoachHandleConsentDecision(client, authorizationId, "approve"/"deny")`
    respectively.
16. `test_handle_consent_decision_calls_approve_authorization_on_approve` —
    AC3: confirms the `"approve"` branch calls
    `client.auth.oauth.approveAuthorization(authorizationId)`.
17. `test_handle_consent_decision_calls_deny_authorization_on_deny` — AC4:
    confirms the `"deny"` branch calls
    `client.auth.oauth.denyAuthorization(authorizationId)`.
18. `test_handle_consent_decision_navigates_to_redirect_url_on_success` —
    AC3/AC4: confirms `window.location.href = data.redirect_url;` is the
    shared success-path navigation for both decisions.
19. `test_handle_consent_decision_shows_retryable_error_on_missing_redirect_url`
    — edge case named in the story: confirms the `error || !data ||
    !data.redirect_url` branch sets a retryable error message and explicitly
    does NOT navigate, remove the buttons (`.remove(`), disable them
    (`.disabled`), or rewrite `innerHTML`.
20. `test_handle_consent_decision_shows_retryable_error_when_sdk_call_throws`
    — edge case: confirms a thrown exception is caught and shows the same
    retryable error, not an unhandled rejection or a dead screen.
21. `test_handle_consent_decision_clears_previous_error_state_at_start_of_each_attempt`
    — retry behavior: confirms `errorEl.hidden = true` runs before the
    `try` block on every invocation, so a second attempt after a failure
    doesn't get stuck displaying the stale error indefinitely.
22. `test_consent_action_error_element_starts_hidden_in_rendered_markup` —
    confirms the error placeholder element is rendered with the `hidden`
    attribute by default.

### Security review

- **HTML-escaping discipline for an `innerHTML` sink (AC2, the
  security-critical criterion)**: independently verified, not just trusted
  from the implementation report, that `client.name` and every individual
  scope token are run through `lifecoachEscapeHtml` — a genuinely distinct
  function from `_escape_js_string` with different escaping rules (HTML
  entities vs. JS-string-literal escaping) — before being concatenated into
  the `innerHTML`-bound string. Constructed two realistic hostile payloads
  (`<img src=x onerror=alert(1)>` for a hostile client name,
  `read"><script>alert(document.cookie)</script>` for a hostile scope value)
  and confirmed, via a faithful Python re-implementation of the exact JS
  replacement chain, that both are fully neutralized — no raw `<`, `>`, or
  `"` survives. Also confirmed structurally that the raw, unescaped
  `details.client.name` expression never appears inside the `innerHTML =`
  assignment itself — only the pre-escaped `safeClientName` variable does —
  ruling out a scenario where escaping is computed but never actually used
  at the sink.
- **Approve/deny decision reporting and redirect handling (AC3/AC4)**:
  confirmed `approveAuthorization`/`denyAuthorization` are called with the
  correct `authorizationId` for the correct button, and that the
  `redirect_url` navigation is the single shared success path for both
  decisions (no separate, possibly-divergent redirect logic per decision).
- **Failure-state reuse, not drift (AC5)**: confirmed by direct string
  inspection that there is exactly one `lifecoachRenderFailureState`
  function definition in the entire file, and the exact non-technical
  failure message literal is used at all three call sites (missing
  `authorization_id`, `getAuthorizationDetails` error response, and a
  thrown exception from `getAuthorizationDetails`) — ruling out a scenario
  where the agent's report claims reuse but actually wrote a second,
  parallel failure-rendering implementation that could silently drift from
  the first over time.
- **No dead-end error states on approve/deny failure**: confirmed the
  approve/deny failure path (`error`/missing `data`/missing `redirect_url`,
  or a thrown exception) only ever sets `errorEl.textContent`/
  `errorEl.hidden = false` — it never removes, disables, or hides the
  Approve/Deny buttons themselves, and clears the previous error state at
  the start of each new attempt, so the user can always click Approve or
  Deny again to retry without reloading the page.

### Unverified external-contract assumption (flagged per `rules/testing.md`)

`getAuthorizationDetails`'s response shape (`{ data: { client: { name },
scope }, error }`), and `approveAuthorization`/`denyAuthorization`'s response
shape (`{ data: { redirect_url }, error }`), are asserted against here as
fixed assumptions baked into both the implementation and these tests — none
of the three have been verified against a live Supabase Auth/OAuth 2.1
Server instance in this session. This is the same category of unverified
external-contract risk flagged in stories 001 and 002, now extended to the
three new SDK methods this story is the first to call. The user should
confirm these shapes against a real Supabase project (or the current
`@supabase/supabase-js@2.108.2` OAuth docs) before relying on this flow in
production.

### Final holistic check across all three stories (LFC-005-oauth-consent-login complete)

Read the entire current `app/oauth_consent.py` end to end (not just the
story-003 diff) to confirm the full three-story flow is internally
consistent:

- `lifecoachInit` -> missing-`authorization_id` failure state, or
  `renderLoginOrConsent` -> (no session) `lifecoachRenderLoginForm` ->
  `lifecoachHandleLoginSubmit` -> on success, re-invokes
  `renderLoginOrConsent` -> (session present) `lifecoachRenderLoadingState`
  (a genuine brief transitional state while the fetch is in flight, not an
  orphaned placeholder — the original story-001 loading-state stub is now
  exercised for its real intended purpose) -> `getAuthorizationDetails` ->
  either `lifecoachRenderConsentScreen` or the shared
  `lifecoachRenderFailureState`. No leftover/orphaned code from the
  original story-001 stub was found: `lifecoachRenderLoadingState` is still
  defined once and used exactly once, in its original intended spot.
- `lifecoachRenderFailureState` is the single failure-state implementation
  used by all three stories' failure paths (missing ID, login errors use a
  separate dedicated `login-error` element by design since AC3 requires
  in-form retry rather than a full failure-state replacement, and the two
  `getAuthorizationDetails` failure paths from this story) — confirmed no
  second/parallel failure-rendering function exists anywhere in the file.
- One stale piece of *documentation* (not behavior) was noticed and is
  flagged here rather than silently fixed, per the qa agent's role: the
  module-level docstring on `render_oauth_consent_page` (lines ~342-351)
  still describes the consent screen as "a stub the consent screen
  (LFC-STORY-005-003) replaces" as of stories 001/002 — this is now stale
  since story 003 has replaced that stub with the real consent screen. This
  is a documentation-accuracy nit, not a functional or test issue, and is
  surfaced for the orchestrator/frontend agent to update rather than
  corrected here.

### Full suite regression check

Ran `uv run pytest` from the repo root twice in a row:

- Run 1: **255 passed**, 0 failed, 36 warnings (same pre-existing
  deprecation warnings as before, unrelated to this story).
- Run 2: **255 passed**, 0 failed, 36 warnings — identical result, no
  flakiness.

255 = 233 (prior baseline after LFC-STORY-005-002) + 22 new unit tests = 255.

### Totals: 22 new unit tests, 255/255 full suite passing across two
consecutive runs, 0 failed, no flakiness. All 5 acceptance criteria are
covered by at least one test each, with AC2 (the security-critical
HTML-escaping requirement) independently verified via constructed hostile
XSS/attribute-breakout payloads run through a faithful re-implementation of
the exact JS escaping logic, and structurally confirmed that the raw,
unescaped `client.name`/scope values never reach the `innerHTML` sink — only
the pre-escaped variables do. AC5's failure-state reuse claim was verified
to be genuine (one shared helper function, one message literal used at all
three call sites), not a new parallel implementation. Per
`requirements.md`'s explicit scope note, no E2E test was written; the real
`getAuthorizationDetails`/`approveAuthorization`/`denyAuthorization` wire
contracts remain explicitly flagged, unverified assumptions pending a live
Supabase instance — recorded as this story's `PASS WITH CAVEATS` caveat, not
silently passed.

## Overall feature summary: LFC-005-oauth-consent-login

All three stories (LFC-STORY-005-001, -002, -003) are complete and tested.
Combined: 46 unit tests (14 + 10 + 22) plus 6 feature tests from story 001 =
52 new automated tests for this feature, contributing to a final full-suite
total of **255 passing, 0 failed**, confirmed stable across two consecutive
runs at the end of each story. Every acceptance criterion across all three
stories' story files is covered by at least one test assertion.

**Feature-level verdict: PASS WITH CAVEATS.** The single caveat, carried
identically through every story in this feature: per `requirements.md`'s
explicit "Out of scope" note, no automated end-to-end (Playwright) test was
written against a real, live Supabase deployment, because no such
deployment exists yet — there is no real "Site URL"/"Authorization Path"
configured to redirect a browser to this page in practice. All three
stories' unverified external-contract assumptions about Supabase's actual
wire formats (`signInWithPassword`, `getAuthorizationDetails`,
`approveAuthorization`/`denyAuthorization` response shapes) remain
explicitly flagged, unverified risks rather than settled facts — the
self-consistency unit tests in this suite prove the implementation behaves
correctly *given* those assumed shapes, not that the assumed shapes match
Supabase's real behavior. The user must manually verify the complete live
flow (login -> consent -> approve/deny -> redirect back to the OAuth client)
against a real Supabase project before relying on this feature in
production.
