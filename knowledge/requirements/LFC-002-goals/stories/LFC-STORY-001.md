# LFC-STORY-001: Goals table migration with RLS

## Description

As a backend system, I want a versioned `goals` table with RLS policies
enforcing per-user, non-deleted ownership, so that every subsequent goals
endpoint can rely on the database itself to isolate and protect goal data.

## Acceptance criteria

1. A new Alembic migration creates a `goals` table with columns `id` (uuid,
   PK, default `gen_random_uuid()`), `user_id` (uuid, NOT NULL, FK →
   `auth.users.id` ON DELETE CASCADE), `title` (text, NOT NULL),
   `description` (text, nullable), `created_at` (timestamptz, NOT NULL,
   default `now()`), `updated_at` (timestamptz, NOT NULL, default `now()`),
   `deleted_at` (timestamptz, nullable).
2. RLS is enabled on `goals`, with policies: `goals_select_own` (`SELECT`
   `USING (auth.uid() = user_id AND deleted_at IS NULL)`),
   `goals_insert_own` (`INSERT` `WITH CHECK (auth.uid() = user_id)`),
   `goals_update_own` (`UPDATE` `USING (auth.uid() = user_id AND deleted_at
   IS NULL)`). No `DELETE` policy exists.
3. An index on `(user_id, deleted_at)` exists to support the list query.
4. `downgrade()` cleanly drops the policies, the index, and the table, with
   nothing left over.

## Requirements implemented

- Requirement 1, 2, 3

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
