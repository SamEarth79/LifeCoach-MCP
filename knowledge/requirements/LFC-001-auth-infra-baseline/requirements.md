# Requirements: Auth & Infra Baseline

## Functional requirements

1. Users can sign up and sign in via Supabase Auth using email/password.
2. Users can sign in via Supabase Auth using Google OAuth.
3. The FastAPI backend exposes a dependency that verifies a Supabase-issued
   JWT (signature + expiry) on incoming requests and exposes the verified
   user id to request handlers.
4. Requests with a missing, malformed, or expired JWT are rejected with a
   401 response before reaching any handler logic.
5. A `users` table exists in Postgres, with one row per Supabase Auth user,
   storing `id`, `email`, `display_name`, `created_at`, `updated_at`.
6. Row Level Security is enabled on the `users` table, restricting
   select/update access to the row matching the requester's verified user
   id.
7. A `GET /users/me` endpoint returns the authenticated user's own profile
   row, with an app-level ownership check in addition to RLS.
8. A `GET /health` endpoint returns a liveness response without requiring
   authentication, for use by the PaaS host's deploy/restart checks.
9. Database schema is managed via Alembic migrations from the first
   migration onward; the `users` table is created via a versioned
   migration, not manual SQL.
10. Authentication-adjacent endpoints (sign-in-related backend routes, if
    any exist beyond what Supabase handles directly) are rate-limited.

## Non-functional requirements

- **Security**: Secrets (Supabase URL, anon/service keys, DB connection
  string, JWT signing material) are read from environment variables only;
  a committed `.env.example` contains placeholder values, and `.env` is
  gitignored. No client-supplied user id is ever trusted for
  authorization — only the verified JWT claim. Failed-auth and unhandled
  server errors are logged without including PII, secrets, or full request
  payloads.
- **Reliability**: `/health` must respond successfully whenever the app
  process and DB connection are healthy, since the PaaS uses it to decide
  whether to keep the instance running.
- **Maintainability**: All schema changes from this point forward go
  through Alembic migrations, establishing the pattern every later feature
  must follow.

## Out of scope

- Goals, suggestions, check-ins tables or any related logic — separate
  features.
- Notifications, reminders, multi-device sync beyond what Supabase Auth
  provides natively, analytics, admin dashboard, monitoring/alerting stack
  (e.g. Sentry), and automated backups beyond Supabase defaults — all
  explicitly deferred per `knowledge/strategy.md`.
- MCP-UI or any MCP protocol surface — this feature is plain REST
  (FastAPI) auth/infra, not MCP tooling.
- Password reset / account management UI flows beyond what Supabase Auth's
  hosted/SDK flow provides out of the box.
- CI/CD pipeline setup beyond basic deploy-on-push (already excluded by
  strategy.md).
