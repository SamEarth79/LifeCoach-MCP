# Requirements: LFC-005-oauth-consent-login

> Filled in by `draft.md` during `/design`. Plain numbered requirements —
> no per-requirement code; stories reference these by number.

## Functional requirements

1. The system serves an HTML page at `GET /oauth/consent`, reachable
   without authentication, that Supabase's OAuth 2.1 Server can redirect a
   browser to with an `authorization_id` query parameter.
2. If the visitor has no active Supabase session, the page presents an
   email + password login form.
3. Submitting valid credentials authenticates the visitor via Supabase's
   client-side SDK (`signInWithPassword`); submitting invalid credentials
   shows a single generic "invalid email or password" error — never
   revealing which field was wrong or whether the email is registered —
   and lets the user retry without reloading the page.
4. Once authenticated, the page retrieves authorization details
   (`client.name`, `scope`, `redirect_uri`) for the given
   `authorization_id` and renders a consent screen showing the requesting
   client's name and the requested scopes in human-readable form.
5. The user can approve or deny the request. Either action reports the
   decision to Supabase (`approveAuthorization`/`denyAuthorization`) and
   redirects the browser to the returned `redirect_url`, handing control
   back to the OAuth client.
6. If `authorization_id` is missing, malformed, or Supabase reports it
   invalid/expired, the page shows a clear, non-technical failure state
   instead of a broken login or consent form.
7. There is no signup or account-creation path on this page — only
   existing users can log in.

## Non-functional requirements

- **Security**: `client.name` and `scope` (OAuth-client-controlled, not
  user-entered) must be HTML-escaped before rendering, never inserted as
  raw HTML. No password is logged at any point. The `@supabase/supabase-js`
  script is loaded from a pinned exact version, not `@latest`.
- **No new secrets**: uses the existing `SUPABASE_URL`/`SUPABASE_ANON_KEY`
  config already present in `app/config.py`.
- **Consistency**: failure/error states must be clear and non-technical,
  matching the tone of the failure states already established in
  `app/ui_templates.py`'s home/goal-detail views (no raw exception text,
  no stack traces).

## Out of scope

- Signup / account creation.
- Forgot password / password reset flow.
- Any OAuth client registration UI — Dynamic Client Registration is
  handled entirely by Supabase, not this app.
- Visual design polish beyond a clean, functional minimum — this is v1
  functional infrastructure, not a design-led screen.
- Configuring the Supabase dashboard's "Site URL"/"Authorization Path"
  settings to point at this route — that's a manual, one-time deployment
  step outside this codebase's scope.
- Automated end-to-end (Playwright) testing of the full live flow against
  a real Supabase project's "Site URL"/"Authorization Path" config — this
  requires a real public deployment, which doesn't exist yet. `test.md`
  should cover this story with unit tests (escaping, error-state logic)
  and feature tests (route reachability, page content, embedded JS
  structure) only, and mark the feature `PASS WITH CAVEATS` per
  `rules/testing.md` rather than attempting a self-consistency E2E test
  that can't verify the real external contract. The user will manually
  verify the live flow end-to-end once a real deployment exists.
