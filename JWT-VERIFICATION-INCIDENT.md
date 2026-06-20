# Incident: JWT verification built against the wrong signing algorithm

## What happened

`LFC-STORY-003` ("Supabase Auth sign-in and JWT verification dependency") was
implemented, tested, and committed under the assumption that Supabase signs
JWTs with a static, shared **HS256 secret** (`SUPABASE_JWT_SECRET`). All
unit/feature tests passed. The story was marked done.

When a real Supabase project was later created and a real user actually
signed in, the issued JWT's header was:

```json
{ "alg": "ES256", "kid": "590fd1de-...", "typ": "JWT" }
```

Not HS256. This project uses Supabase's current default — **asymmetric
ES256 keys verified via a public JWKS endpoint**
(`https://<project>.supabase.co/auth/v1/.well-known/jwks.json`) — not the
legacy shared-secret scheme the code was built for. Every real token was
being rejected with a 401, even though the implementation "passed" all its
tests.

## Root cause

1. **The assumption was never checked against Supabase's actual current
   behavior.** `architecture.md` stated "Supabase issues JWTs signed with a
   project-specific JWT secret (HS256 by default)" during `/design`. This
   was written without a docs lookup or a live Supabase project to test
   against — it was carried through `analyze.md` → `draft.md` as an
   unverified assertion.

2. **The backend agent flagged the ambiguity itself, then picked the wrong
   default anyway.** Its own implementation plan said: *"Supabase issues
   JWTs signed with a project-specific JWT secret (HS256) by default, OR
   using asymmetric JWKS depending on project config"* — it correctly
   identified two possibilities, but resolved the ambiguity by guessing
   instead of verifying against documentation or a real project.

3. **Testing only validated internal self-consistency, not the actual
   external contract.** The `qa` agent's tests for this story signed test
   tokens with the *same* assumed algorithm/secret the implementation
   used, then verified them with that implementation. This is circular: a
   wrong assumption about Supabase's real behavior can satisfy 100% of
   such tests while failing 100% of real traffic. There was no live
   Supabase project available at implementation time to test against, and
   no test was written to flag "this assumption is unverified against the
   real external system" the way the dry-run gap in `LFC-STORY-002`
   (Alembic migration never run against a live DB) *was* explicitly
   flagged in `test-results.md`.

4. **No live external system existed until after all four stories in this
   feature were already committed.** A real Supabase project was only
   created mid-conversation, well after implementation — at which point
   this and one other real bug (an RLS gap, fixed separately) surfaced
   immediately on first contact with the actual service.

## How it was found and fixed

A real Supabase project was created, a real user signed up and signed in
via the Auth REST API, and the resulting JWT was decoded (without
verification) to inspect its header — revealing `alg: ES256` and a `kid`.
The matching public key was confirmed live at the standard JWKS endpoint.

Fix: `app/auth.py` now fetches and caches Supabase's public signing key by
`kid` from the JWKS endpoint and verifies ES256 signatures against it.
`SUPABASE_JWT_SECRET` was removed entirely — it's not needed for this
verification scheme. Verified end-to-end against the real project with a
real signed-in user before committing.

## Recommendation for the agent framework

- When a story's correctness depends on an **external system's actual wire
  format/protocol** (auth token format, webhook signing scheme, API
  response shape, etc.) rather than purely on our own code's logic, the
  implementing agent should treat any uncertainty about that external
  behavior as a flagged, open risk — not something to resolve by picking
  the "more standard-sounding" option and moving on.
- `rules/testing.md` should distinguish between tests that verify
  *internal self-consistency* (sign with assumption X, verify with
  assumption X) and tests that verify *the actual external contract*.
  Self-consistency tests passing should never be reported as confirming
  behavior against a real third-party system — that requires either a
  live sandbox/test instance of the external service, or an explicit,
  visible caveat in `test-results.md` (the same pattern already used for
  the un-runnable-migration gap in `LFC-STORY-002`, which *was* disclosed
  honestly — this JWT assumption should have received the same treatment
  but wasn't recognized as needing it).
- Consider requiring agents to check current platform documentation (via
  web search or a docs-lookup tool) before hardcoding a "default" behavior
  for any third-party identity/auth provider, since these specifically are
  security-critical and prone to silent platform-level changes (e.g.
  Supabase's shift from shared-secret to per-project asymmetric signing
  keys as its default).
