# LFC-STORY-002: Alembic setup and users table with RLS

## Description

As the developer, I want Alembic migrations wired up and a first migration
creating the `users` table with a Row Level Security policy, so that all
future schema changes follow a versioned migration pattern and per-user
data isolation is established from the first table onward.

## Acceptance criteria

1. Alembic is initialized in the repo and configured to read the DB
   connection string from the app's environment settings (not a separate
   hardcoded config).
2. Running `alembic upgrade head` against a fresh database creates a
   `users` table with columns `id` (uuid, PK), `email` (text, not null),
   `display_name` (text, nullable), `created_at`, `updated_at` (both
   timestamptz, default now()).
3. The same migration enables Row Level Security on `users` and adds a
   policy restricting select/update to rows where `auth.uid() = id`.
4. Running `alembic downgrade base` cleanly drops the table and policy
   with no leftover objects.

## Requirements implemented

- Requirement 5 (users table), Requirement 6 (RLS on users table),
  Requirement 9 (Alembic-managed schema)

## Agents likely needed

- [ ] frontend
- [x] backend
- [x] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
