# Technical Deep Dive: OAuth consent login page (LFC-005)

## What this feature is, and why it exists

A single new unauthenticated route, `GET /oauth/consent`, that Supabase's
OAuth 2.1 Server redirects a browser to when an external OAuth client (e.g.
Claude Desktop, connecting to this app's MCP server) needs a user to log in
and approve or deny access. Before this feature, the backend had no
browser-facing page at all — every other route in `app/main.py` is either a
JSON REST endpoint or an MCP tool call. This is the first (and so far only)
route that returns a standalone, directly browser-navigable HTML document
and the first page in the repo where the actual login/consent logic runs
client-side in the browser rather than in Python on the server.

The whole flow: Supabase redirects here with `?authorization_id=<id>` → show
a login form if there's no active Supabase session → once authenticated,
fetch the authorization's details (requesting client's name + scopes) →
render a consent screen → Approve/Deny reports the decision back to
Supabase, which returns a `redirect_url` → the browser is sent back to the
OAuth client.

## Components touched

- `app/oauth_consent.py` (new module) — `render_oauth_consent_page(supabase_url, supabase_anon_key) -> str`,
  mirroring `app/ui_templates.py`'s existing convention of keeping
  render functions/string templates in their own module, separate from
  route wiring.
- `app/main.py` — one new route, `GET /oauth/consent` (`get_oauth_consent_page`),
  calling the renderer with `get_settings().supabase_url`/`.supabase_anon_key`
  and returning the result via `HTMLResponse`.
- No data model changes. No new infrastructure beyond a manual,
  outside-this-codebase step (pointing Supabase's dashboard "Site URL"/
  "Authorization Path" settings at this route).

## Why this page is static HTML + client-side JS, not server-rendered

Every other piece of dynamic content on this page — whether there's an
active session, the requesting client's name, the requested scopes, the
approve/deny result — is only knowable by calling Supabase's
`@supabase/supabase-js` SDK from the browser. The server has no part to play
in any of that; FastAPI's only job is to serve the page shell. Given that,
`render_oauth_consent_page` returns a plain f-string-assembled
`<!DOCTYPE html>` document (the same string-template style
`app/ui_templates.py` already uses) rather than introducing a templating
engine (Jinja2) or a JS build pipeline for what is, and will likely remain,
a single page. The only server-side dynamic content is interpolating the
already-public `SUPABASE_URL`/`SUPABASE_ANON_KEY` config values (already
used elsewhere in this app, not secrets) into the page as JS constants so
the SDK can initialize.

`@supabase/supabase-js` is loaded from jsDelivr at a pinned **exact**
version (`2.108.2`, not `@latest`, not a semver range) via a `<script>` tag —
the simplest way to get the SDK into a single page without adding a bundler,
and pinned per `rules/security.md`'s supply-chain stability requirement (an
unpinned CDN script is a classic supply-chain attack surface: the vendor
could ship a different file at the same URL at any time).

## The route is deliberately unauthenticated

`GET /oauth/consent` has zero `Depends(...)` parameters — `async def
get_oauth_consent_page() -> str`, unlike every other route in `app/main.py`,
which carries `Depends(enforce_rate_limit)` and/or `Depends(get_current_user)`.
This is not a missed auth check; it's required by the flow itself. Supabase
redirects a browser here *before* it knows whether the visitor is logged in
— the page has to be reachable with no session and no bearer token in order
to show the login form in the first place. Server-side auth has nothing to
check yet at this layer; the actual authentication happens entirely
client-side via `signInWithPassword`, and the only thing protected behind
it is the page's own internal state transitions (login form → consent
screen), not the HTTP response itself.

## Two distinct escaping helpers, for two distinct injection contexts

This feature introduces two separate escaping functions in
`app/oauth_consent.py`, and the distinction between them is the single most
security-relevant design decision in this feature:

- **`_escape_js_string(value)`** (server-side, Python) — escapes `\` ->
  `\\`, `"` -> `\"`, then `</script>` -> `<\/script>`. Used once, at render
  time, for the two values FastAPI injects into the page:
  `SUPABASE_URL`/`SUPABASE_ANON_KEY`. These are interpolated into a
  `<script>` body as JS string-literal constants (`const SUPABASE_URL =
  "{value}";`), so the relevant injection primitives are: breaking out of
  the quoted string literal (backslash, double-quote) and breaking out of
  the `<script>` element itself (a literal `</script>` sequence closing the
  tag early, letting an attacker-controlled config value smuggle in a second
  `<script>` payload). `html.escape` (HTML-entity escaping) would not help
  here at all — neither risk is an HTML-markup-injection risk; both are
  JS-string/script-body-injection risks, which is precisely why this is a
  different function from the one below, not a reuse of `app/ui_templates.py`'s
  `html.escape` discipline.

- **`lifecoachEscapeHtml(value)`** (client-side, JS) — standard HTML-entity
  escaping: `&` -> `&amp;`, `<` -> `&lt;`, `>` -> `&gt;`, `"` -> `&quot;`,
  `'` -> `&#39;`. Used on `details.client.name` and on each individual
  space-split scope token from `details.scope`, both returned by
  `getAuthorizationDetails` and both concatenated into the consent screen's
  `innerHTML` string. These two values are self-reported metadata supplied
  by the *connecting OAuth client* (e.g. whatever name/scopes a malicious or
  buggy third-party app registers with Supabase), not data this app's own
  users entered — they cross a trust boundary the moment they're fetched,
  and the sink they're written into is `innerHTML`, an HTML-markup context.
  `_escape_js_string` would be the wrong tool here: it doesn't touch `<`/`>`/
  `&` at all, so an `<img src=x onerror=alert(1)>` payload as a hostile
  client name would pass through it completely unescaped and execute as
  real markup once assigned to `innerHTML`.

Both `client.name` and every scope are escaped individually before
concatenation (escaping the already-joined string would still leave each
token raw before the join), and the raw, unescaped expressions never appear
in the `innerHTML =` assignment itself — only the pre-escaped
`safeClientName`/`scopeItems` variables are referenced there, confirmed
directly against the source rather than inferred from the function being
called somewhere in the file.

## Login error handling: one generic message, no account enumeration

`signInWithPassword` failures all produce the exact same fixed string,
`"Invalid email or password."`, regardless of whether the email doesn't
exist, the password is wrong, or any other reason the SDK reports an error.
There is no branching on `error.message`/`error.status` that would let a
different message leak which emails are registered. The form survives a
failed attempt (only `textContent`/`hidden` are touched, never
`window.location` or `innerHTML` teardown), so retrying needs no page
reload. The `email`/`password` values are read once from the two inputs,
passed straight into `signInWithPassword`, and never logged or referenced
anywhere else.

## Approve/Deny failure handling

`lifecoachHandleConsentDecision` calls `approveAuthorization` or
`denyAuthorization` depending on which button was clicked, and treats a
falsy/incomplete response (`error`, missing `data`, or missing
`data.redirect_url`) the same as a thrown exception: both show a generic
`"Something went wrong. Please try again."` message on a dedicated error
element, without navigating, removing, or disabling the Approve/Deny
buttons — so the user can always retry. The error element is explicitly
hidden again at the start of every new attempt, so a second click after a
prior failure doesn't get stuck showing a stale message.

## Failure state, reused across all three entry points

A single `lifecoachRenderFailureState(message)` helper renders the same
non-technical message — `"This link is invalid or has expired. Please try
connecting again from the app."` — and is the only place that string
literal exists in the file. It's invoked from three places: the missing
`authorization_id` query parameter (checked before the Supabase client is
even constructed, so a request with no `authorization_id` never calls
`createClient`), a `getAuthorizationDetails` error response, and a thrown
exception from that same call. There is no second, parallel
failure-rendering implementation — verified by confirming there is exactly
one function definition and exactly three call sites using the identical
message.

## Unverified external contract — the caveat carried through all three stories

All three stories (`LFC-STORY-005-001/002/003`) are recorded as `PASS WITH
CAVEATS`. The caveat is the same one in every case: there is no live
Supabase deployment to test against yet, so the actual wire-format/response
shapes this implementation assumes for `signInWithPassword`,
`getAuthorizationDetails`, `approveAuthorization`, and `denyAuthorization`
(all shaped as `{ data, error }`, with `data.session`/`data.redirect_url`/
`details.client.name`/`details.scope` accessed as plain object properties)
have not been confirmed against a real Supabase Auth/OAuth 2.1 Server
instance. The unit test suite proves the implementation behaves correctly
*given* those assumed shapes — it is a self-consistency test, not a
verification of the real external contract, per `rules/testing.md`'s
explicit warning about exactly this category of risk. No E2E (Playwright)
test was attempted for the same reason: a Playwright test against a
mocked/fake Supabase backend would prove nothing beyond what the unit tests
already prove. **Before relying on this flow in production, the user must
manually verify the full live flow — login, consent rendering, and both
approve and deny redirecting correctly — against a real Supabase project
with "Site URL"/"Authorization Path" actually configured to point at this
route.**

## Extending this safely

- If a second client-side-JS-driven page is ever needed, this is the
  precedent: a dedicated module mirroring `app/ui_templates.py`'s
  string-template structure, an unauthenticated route only if the flow
  genuinely requires reachability before any session exists, and the CDN
  script (if any) pinned to an exact version.
- Any new value injected by the server into a `<script>` body must go
  through `_escape_js_string` (or an equivalent JS-string-literal escape),
  never `html.escape`/`lifecoachEscapeHtml`.
- Any value fetched client-side from an external, non-user-controlled
  source (here, the OAuth client's registered name/scopes) and written into
  `innerHTML` must go through `lifecoachEscapeHtml`, never raw string
  concatenation, even if the value "looks like" it would always be safe.
- Do not conflate the two escaping functions — they protect against
  different injection primitives in different sinks, and using the wrong
  one for a given sink (e.g. `_escape_js_string` on a value headed for
  `innerHTML`) leaves the real risk for that sink completely unaddressed.
