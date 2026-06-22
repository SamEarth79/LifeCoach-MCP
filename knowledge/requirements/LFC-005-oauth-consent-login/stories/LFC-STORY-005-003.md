# LFC-STORY-005-003: Consent screen renders scopes and reports the approve/deny decision back to Supabase

> Filled in by `draft.md` during `/design`. One file per story, inside the
> feature's `stories/` directory.

## Description

As a logged-in LifeCoach user, I want to see which app is requesting access
and what it can access, and choose to approve or deny it, so that I control
which third-party apps can act on my behalf.

## Acceptance criteria

1. Once authenticated, the page calls
   `getAuthorizationDetails(authorization_id)` and renders the requesting
   client's name and a human-readable list of the requested scopes.
2. `client.name` and each scope value are HTML-escaped before rendering —
   never inserted as raw HTML/`innerHTML` — since they are OAuth-client-
   controlled metadata, not trusted input.
3. Clicking Approve calls `approveAuthorization(authorization_id)` and
   navigates the browser to the returned `redirect_url`.
4. Clicking Deny calls `denyAuthorization(authorization_id)` and navigates
   the browser to the returned `redirect_url`.
5. If `getAuthorizationDetails` rejects (invalid/expired
   `authorization_id`), the page shows a clear, non-technical failure state
   instead of a broken consent screen.

## Requirements implemented

- Requirement 4, Requirement 5, Requirement 6 (the invalid/expired case)

## Agents likely needed

- [x] frontend
- [ ] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
