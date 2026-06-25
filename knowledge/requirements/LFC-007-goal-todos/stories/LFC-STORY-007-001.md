# LFC-STORY-007-001: Todos table and RLS policies

> Filled in by `draft.md` during `/design`. One file per story, inside the
> feature's `stories/` directory.

## Description

As the system, I need a `todos` table linked to `goals` with per-user
isolation enforced at the database level, so that every later todo feature
(CRUD tools, suggestions, UI) has a correct, secure place to persist data.

## Acceptance criteria

1. A new Alembic migration creates a `todos` table with columns `id`
   (UUID PK, `gen_random_uuid()`), `user_id` (FK `auth.users.id`, `ON
   DELETE CASCADE`), `goal_id` (FK `goals.id`, `ON DELETE CASCADE`),
   `text` (not null), `done` (boolean, not null, default `false`),
   `sort_order` (integer, not null), `created_at`/`updated_at`
   (timestamptz, `now()` server defaults).
2. An index `ix_todos_goal_id_sort_order` exists on `(goal_id,
   sort_order)`.
3. RLS is enabled on `todos`, with `SELECT`, `INSERT`, `UPDATE`, and
   `DELETE` policies that all require `auth.uid() = user_id AND EXISTS
   (SELECT 1 FROM goals g WHERE g.id = goal_id AND g.user_id = auth.uid()
   AND g.deleted_at IS NULL)`.
4. Deleting a goal cascades to delete its todos (verified by a feature
   test that creates a goal with todos, deletes the goal, and confirms the
   todos are gone).
5. A feature test confirms a second user cannot read, update, or delete
   another user's todos even when given the correct todo id (RLS
   enforcement, not just app-level checks).
6. The migration runs cleanly against the existing migration chain
   (`alembic upgrade head` succeeds from the current head revision).

## Requirements implemented

- Requirement 1, 14, 15

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
