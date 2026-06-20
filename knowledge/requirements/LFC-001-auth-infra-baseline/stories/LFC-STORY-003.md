# LFC-STORY-003: Supabase Auth sign-in and JWT verification dependency

## Description

As a user, I want to sign in with email/password or Google via Supabase
Auth and have the backend trust only my verified identity, so that my data
stays private to me and the backend never relies on a client-supplied user
id.

## Acceptance criteria

1. Supabase Auth is configured for email/password sign-in and Google
   OAuth (Google provider setup in the Supabase project is documented as a
   manual prerequisite in the implementation summary, since it can't be
   expressed in code).
2. A FastAPI dependency (e.g. `get_current_user`) verifies the signature
   and expiry of a Supabase-issued JWT passed as a `Bearer` token and
   returns the verified user id; requests without a valid token receive a
   401 before reaching handler logic.
3. `GET /users/me` returns the authenticated user's row from the `users`
   table, using the verified user id from the dependency — never a
   client-supplied id from the request.
4. A new Supabase Auth user automatically gets a corresponding row in the
   `users` table (e.g. via a sign-up hook or first-request upsert) so
   `/users/me` has data to return after sign-up.
5. Failed authentication attempts are logged server-side without including
   the token value, password, or other PII.

## Requirements implemented

- Requirement 1, 2, 3, 4, 7 (sign-in methods, JWT dependency, rejecting bad
  tokens, `/users/me` endpoint)

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
