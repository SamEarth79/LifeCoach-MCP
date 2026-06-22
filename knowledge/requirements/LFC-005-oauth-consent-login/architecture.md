# Architecture: LFC-005-oauth-consent-login

> Filled in by `draft.md` during `/design`, informed by `analysis.md`.
> Describes the technical approach before any code is written.

## Approach

Add a single new unauthenticated route, `GET /oauth/consent`, that returns a
static HTML document with embedded JavaScript. The page implements the
entire login + consent flow client-side via the `@supabase/supabase-js` SDK
(loaded from a pinned-version CDN script tag), per the verified contract in
`analysis.md`: read `authorization_id` from the query string, show a login
form if there's no active Supabase session, then call
`getAuthorizationDetails`/`approveAuthorization`/`denyAuthorization` and
redirect to the `redirect_url` each returns. The only server-side dynamic
content is injecting the existing `SUPABASE_URL` and `SUPABASE_ANON_KEY`
config values (both already public-safe, already used elsewhere in this
app) into the page so the SDK can initialize — everything else (login,
session check, consent rendering, approve/deny) happens entirely in the
browser, not in FastAPI.

## Components touched

- **Frontend**: a new HTML/JS template module (`app/oauth_consent.py`,
  mirroring the existing `app/ui_templates.py` convention of keeping
  render functions/string templates in their own module) covering: the
  login form, the consent screen, and the failure state for a
  missing/invalid/expired `authorization_id`.
- **Backend**: one new route in `app/main.py` — `GET /oauth/consent` —
  returning the rendered page via `HTMLResponse`. No new dependency on
  `app/auth.py`'s bearer-token verification; this route is intentionally
  public, per the verified contract (the page must be reachable
  unauthenticated to show the login form in the first place).
- **Infrastructure**: none required for `/implement` to build. Production
  use requires the Supabase project dashboard's "Site URL" and
  "Authorization Path" settings to be manually pointed at this route — a
  one-time manual configuration step outside this codebase, not something
  `/implement` produces.

## Data flow

1. Supabase's OAuth 2.1 Server redirects the browser to
   `GET /oauth/consent?authorization_id=<id>`.
2. FastAPI returns the static HTML+JS page (no DB access, no auth
   dependency at this layer), with `SUPABASE_URL`/`SUPABASE_ANON_KEY`
   already injected as JS constants.
3. Page JS reads `authorization_id` from `window.location.search`. If
   absent, render the failure state immediately and stop.
4. Page JS initializes `supabase-js` and checks for an active session.
   - No session: render the login form. On submit, call
     `signInWithPassword(email, password)`. Failure shows a generic
     "invalid email or password" error and allows retry. Success proceeds
     to step 5.
   - Session present: proceed directly to step 5.
5. Call `getAuthorizationDetails(authorization_id)`. On success, render the
   consent screen with the escaped `client.name` and a human-readable
   rendering of the space-separated `scope` string. On failure (invalid/
   expired `authorization_id`), render the failure state.
6. User clicks Approve or Deny → call `approveAuthorization(authorization_id)`
   or `denyAuthorization(authorization_id)` → both return a `redirect_url`
   → `window.location.href = redirect_url`, handing control back to the
   OAuth client (e.g. Claude Desktop).

## Data model changes

None. Login uses Supabase's own `auth.users` table and session management;
no new tables, no changes to `users`/`goals`/`updates`.

## Key decisions

- **Decision**: render the page as a static `HTMLResponse` with JS-constant
  injection (server-side f-string interpolation of `SUPABASE_URL`/
  `SUPABASE_ANON_KEY` only), not a Jinja2 template.
  **Rationale**: every other dynamic value (client name, scopes, session
  state) is resolved client-side via SDK calls after the page loads — there
  is no server-side templating need beyond two config constants, so adding
  a templating dependency would be premature per `rules/coding-style.md`.
- **Decision**: load `@supabase/supabase-js` via a pinned-version CDN
  `<script>` tag rather than introducing a JS bundler/build step.
  **Rationale**: this is the only client-side-JS-driven page in the repo;
  a build pipeline for one page is premature abstraction. The version must
  be pinned exactly (not `@latest`) for supply-chain stability, per
  `rules/security.md`'s dependency-pinning rule.
- **Decision**: `GET /oauth/consent` has no FastAPI-level auth dependency,
  unlike every other route in `app/main.py`.
  **Rationale**: dictated by Supabase's actual, verified contract — the
  page must be reachable by an unauthenticated browser so it can present
  the login form. This is a deliberate exception, not an oversight; it
  should be called out explicitly during `qa`'s review so it isn't
  mistaken for a missed auth check.
- **Decision**: `client.name` and the `scope` string must be HTML-escaped
  before being rendered into the consent screen, never inserted as raw
  HTML/`innerHTML`.
  **Rationale**: both values are self-reported metadata controlled by the
  connecting OAuth client, not data this app's users entered — they cross
  a trust boundary and must be treated as untrusted input per
  `rules/security.md`'s XSS rule, the same way goal titles are escaped
  before rendering in the MCP-UI templates.
