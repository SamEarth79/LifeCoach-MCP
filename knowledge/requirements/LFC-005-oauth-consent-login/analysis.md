# Analysis: LFC-005-oauth-consent-login

> Filled in by `analyze.md` during `/design`. Summarizes what already exists
> in the codebase that is relevant to this feature, before any architecture
> or requirements are drafted.

## Summary

A login + consent page that Supabase Auth's OAuth 2.1 Server redirects a
browser to during an OAuth authorization flow, so MCP clients (e.g. Claude
Desktop's native "Add custom connector" UI) can authenticate against
LifeCoach via standards-compliant OAuth instead of the current manual
workaround (hand-minting a bearer token via `mcp-remote`).

## Relevant existing code

- `app/main.py` — the only FastAPI app instance in the repo. All existing
  routes (`/health`, `/users/me`, `/goals*`) are JSON API endpoints, not
  HTML pages. There is currently zero HTML-page-serving infrastructure
  (no Jinja2/templates setup, no static file mount, no cookie/session
  middleware). This feature is the first HTML page this backend will ever
  serve.
- `app/auth.py` — `verify_bearer_token`/`get_current_user` validate
  already-issued Supabase JWTs via JWKS (`ES256`, audience
  `"authenticated"`). This is purely a per-request bearer-token verifier;
  there is no session/cookie-based login anywhere in the codebase, and (per
  the verified contract below) this feature does not need one — the
  login/consent UI authenticates and reports decisions entirely through the
  client-side `supabase-js` SDK, not through this backend's existing JWT
  verification path.
- `app/config.py` — `Settings` holds `supabase_url`, `supabase_anon_key`,
  `database_url`. The anon key is exactly what the client-side
  `supabase-js` SDK on the new page will need (it's a public-safe key,
  already used by this app); no new secret is required for the core flow.
- `app/ui_templates.py` — exists, but is purpose-built for the unrelated
  MCP-UI client-rendering architecture (`ui://` resources rendered inside
  an MCP host's iframe via a JSON-RPC-over-postMessage bridge). It is not
  reusable here: this feature needs a normal, directly browser-navigable
  HTML page served over plain HTTP, not an MCP resource.
- No existing signup flow anywhere — consistent with this feature's scope
  (login only, for already-existing users; account creation stays manual
  via the Supabase dashboard for now, per `knowledge/strategy.md`).

## Constraints and risks

- **Verified contract (via Supabase's official docs, fetched live during
  this analysis — not guessed):** Supabase's OAuth 2.1 Server redirects the
  browser to `{Site URL}{Authorization Path}?authorization_id={id}` (the
  "Authorization Path" is a setting configured in the Supabase project
  dashboard). The page must:
  1. Read `authorization_id` from the query string.
  2. If the visitor has no active Supabase session, show a login form
     (email + password) and authenticate via the `supabase-js` SDK's
     `signInWithPassword`.
  3. Once authenticated, call `supabase.auth.oauth.getAuthorizationDetails(authorization_id)`
     to retrieve `client.name`, `scope` (a space-separated string, e.g.
     `"openid email profile"`), and `redirect_uri`, and render a consent
     screen showing the client name and requested scopes.
  4. On the user's decision, call `supabase.auth.oauth.approveAuthorization(authorization_id)`
     or `.denyAuthorization(authorization_id)`. Both return a `redirect_url`
     the page must navigate the browser to, handing control back to the
     OAuth client (Claude Desktop).
  - This means the actual login + approval logic runs **client-side, in the
    browser, via `supabase-js`** — not as new FastAPI POST endpoints. This
    backend's role is narrower than originally assumed: serve one HTML page
    (with embedded JS) at whatever path is registered as the "Authorization
    Path," rather than implementing OAuth approval logic in Python.
- **New dependency:** this is the first page in the repo needing a
  client-side JS SDK (`@supabase/supabase-js`, loaded via CDN script tag is
  the simplest fit for a single server-rendered page — avoids introducing a
  frontend build pipeline for one page). Per `rules/coding-style.md`'s
  dependency rule, this should be called out explicitly as a new addition
  in the implementation summary when built.
- **Deployment dependency:** the Supabase dashboard's "Site URL" +
  "Authorization Path" settings require a real, stable, public URL — this
  cannot be meaningfully end-to-end tested purely against `localhost`. This
  ties directly into the still-open "no real deployment yet" item from the
  broader beta-readiness punch list; full E2E verification of this feature
  is blocked on having a real deployed hostname, and should be flagged
  `PASS WITH CAVEATS` in `test-results.md` if implemented before deployment
  exists.
- **No existing HTML-serving precedent in this repo** means conventions
  (templating approach, escaping discipline, where the file lives) need to
  be established fresh in `draft.md`'s architecture — there's nothing to
  match for consistency, so the idiomatic FastAPI default (return
  `HTMLResponse`, or `Jinja2Templates` if the page has any conditional
  server-rendered content) should be chosen there.

## Open questions

- None blocking — the previously-unverified contract is now confirmed
  directly from Supabase's documentation (see Constraints above). The one
  remaining open item (full E2E testing requires a real deployed URL) is a
  testing/deployment-sequencing question, not a design ambiguity, and is
  already captured as a flagged risk above for `test.md` to handle when the
  time comes.
