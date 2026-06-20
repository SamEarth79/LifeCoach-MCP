# Analysis: Auth & Infra Baseline

## Summary

Establish the foundational auth and infrastructure layer — Supabase Auth
sign-in (email/password + Google OAuth), FastAPI JWT validation, a
users/profile table with an RLS policy pattern, Alembic migrations, and a
health check endpoint — so that every later feature has a real signed-in
user and a database/migration setup to build on.

## Relevant existing code

This is a greenfield product repo. No application code exists yet — only
the agent framework (`.claude/`) and `knowledge/strategy.md`. There is
nothing to extend or stay consistent with; this feature establishes the
first conventions (FastAPI project layout, Alembic setup, auth pattern)
that all later features will follow.

## Constraints and risks

- `knowledge/strategy.md` mandates: Python + FastAPI backend, Supabase Auth
  + Postgres, RLS enforced per-table in addition to app-level authorization
  checks, FastAPI validates Supabase-issued JWTs (signature + expiry) on
  every request and never trusts a client-supplied user ID, secrets via
  environment variables only (`.env.example` with placeholders committed),
  rate limiting on auth endpoints, server-side logging of failed auth
  attempts and unhandled errors without logging PII/secrets, and a health
  check endpoint required by the chosen PaaS for deploy/restart logic.
- Strategy explicitly defers a monitoring/alerting stack (e.g. Sentry) and
  CI/CD beyond basic deploy-on-push — this feature should not introduce
  either.
- Since this is the first feature, decisions made here (FastAPI app
  structure, dependency-injection pattern for the authenticated user,
  Alembic migration conventions, RLS policy naming pattern) become the
  baseline every subsequent feature must match. Getting the JWT-validation
  dependency and RLS pattern right here avoids rework later.
- No goals/suggestions/check-ins tables are in scope for this feature
  (confirmed with user) — only the users/profile table and the RLS
  scaffolding pattern it demonstrates.
- Google OAuth requires provider configuration in the Supabase project
  (client ID/secret) — this is an external setup step, not something
  expressible purely in code, and should be called out in the
  implementation summary as a manual prerequisite.

## Open questions

- None outstanding — sign-in methods (email/password + Google OAuth) and
  data scope (users/profile table only, no other tables yet) were
  confirmed with the user during `gather.md`.
