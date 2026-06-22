# LFC-STORY-005-001: Serve the OAuth consent page at the registered authorization path

> Filled in by `draft.md` during `/design`. One file per story, inside the
> feature's `stories/` directory.

## Description

As an OAuth client (e.g. Claude Desktop) initiating an authorization flow,
I want Supabase's redirect to `{Site URL}{Authorization Path}?authorization_id=...`
to reach a real, reachable page on LifeCoach, so that the OAuth flow can
continue instead of dead-ending.

## Acceptance criteria

1. `GET /oauth/consent` returns `200` with an HTML document containing a
   pinned-exact-version `@supabase/supabase-js` `<script>` tag and the
   server-injected `SUPABASE_URL`/`SUPABASE_ANON_KEY` JS constants.
2. The route is reachable without any `Authorization` header (no
   `get_current_user`/`verify_bearer_token` dependency).
3. When `authorization_id` is missing from the query string, the page's
   embedded JS renders a clear, non-technical failure state instead of a
   login form or consent screen.

## Requirements implemented

- Requirement 1, Requirement 6 (the missing-`authorization_id` case)

## Agents likely needed

- [x] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
