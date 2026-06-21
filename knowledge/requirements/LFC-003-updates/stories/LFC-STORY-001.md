# LFC-STORY-001: Updates table migration with RLS

## Description

As a backend system, I want a versioned `updates` table with RLS policies
enforcing per-user ownership and active-goal linkage, so that every
subsequent MCP tool can rely on the database to isolate and protect
update data.

## Acceptance criteria

1. A new Alembic migration creates an `updates` table with columns `id`
   (uuid, PK, default `gen_random_uuid()`), `user_id` (uuid, NOT NULL, FK
   → `auth.users.id` ON DELETE CASCADE), `goal_id` (uuid, NOT NULL, FK →
   `goals.id` ON DELETE CASCADE), `content` (text, NOT NULL), `transcript`
   (text, nullable), `source` (text, NOT NULL, default
   `'coaching_update'`, `CHECK (source IN ('coaching_update', 'checkin'))`),
   `created_at` (timestamptz, NOT NULL, default `now()`). `source` is
   added now for a future check-ins feature to use — no tool in this
   feature writes or accepts `checkin` as a value.
2. RLS is enabled on `updates`, with policies: `updates_select_own`
   (`SELECT` `USING (auth.uid() = user_id)`) and `updates_insert_own`
   (`INSERT` `WITH CHECK (auth.uid() = user_id AND EXISTS (SELECT 1 FROM
   goals g WHERE g.id = goal_id AND g.user_id = auth.uid() AND
   g.deleted_at IS NULL))`). No `UPDATE`/`DELETE` policies exist.
3. An index on `(goal_id, created_at)` exists to support the
   `list_updates` query pattern.
4. `downgrade()` cleanly drops the policies, the index, and the table,
   with nothing left over.

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
