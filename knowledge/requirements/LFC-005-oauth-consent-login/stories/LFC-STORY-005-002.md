# LFC-STORY-005-002: Login form authenticates existing users via the Supabase client SDK

> Filled in by `draft.md` during `/design`. One file per story, inside the
> feature's `stories/` directory.

## Description

As an existing LifeCoach user opening the OAuth consent page without an
active session, I want to log in with my email and password, so that I can
proceed to approve or deny the connecting app's access request.

## Acceptance criteria

1. When the page loads with no active Supabase session, it renders an
   email + password form instead of a consent screen.
2. Submitting valid credentials calls `signInWithPassword`, establishes a
   session, and transitions the page toward the consent screen for the
   current `authorization_id` (consent rendering itself is
   LFC-STORY-005-003 — this story's done-state is "session established,
   ready to fetch authorization details").
3. Submitting invalid credentials shows a single generic "invalid email or
   password" error — never indicating which field was wrong or whether the
   email is registered — and lets the user retry without a page reload.
4. No signup link or account-creation path appears anywhere on the page.

## Requirements implemented

- Requirement 2, Requirement 3, Requirement 7

## Agents likely needed

- [x] frontend
- [ ] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
