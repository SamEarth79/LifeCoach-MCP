# LFC-STORY-007-002: Todo CRUD and reorder MCP tools

> Filled in by `draft.md` during `/design`. One file per story, inside the
> feature's `stories/` directory.

## Description

As a user, I want to add, edit, complete, remove, list, and reorder todos
for any of my goals through conversation, so that the LLM can manage my
subgoal steps on my behalf.

## Acceptance criteria

1. `create_todo(goal_id, text)` validates non-blank `text`, inserts a todo
   owned by the requesting user with `sort_order` set to one past the
   current max `sort_order` for that goal (0 if none exist), and returns
   the created todo.
2. `update_todo(todo_id, text)` validates non-blank `text`, updates the
   todo if owned by the requesting user, and returns the updated todo; it
   has no effect and returns a clear not-found result if the todo doesn't
   exist or isn't owned by the user.
3. `toggle_todo(todo_id)` flips `done` (true→false, false→true) for a
   todo owned by the requesting user and returns the updated todo.
4. `delete_todo(todo_id)` permanently removes a todo owned by the
   requesting user and returns confirmation; it has no effect on todos not
   owned by the user.
5. `list_todos(goal_id)` returns all todos for a goal owned by the
   requesting user, ordered by `sort_order` ascending.
6. `reorder_todos(goal_id, todo_ids)` accepts an ordered list of todo ids
   belonging to that goal and rewrites their `sort_order` to match the
   given order, in a single transaction; a subsequent `list_todos` call
   reflects the new order.
7. Every tool rejects (without leaking which case it is) a `goal_id`/
   `todo_id` belonging to another user, relying on the RLS policies from
   LFC-STORY-007-001.
8. New Pydantic schemas (`TodoCreate`, `TodoUpdate`, `TodoResponse`,
   `TodoReorder`) validate input shape and non-blank text, following the
   existing validator pattern in `app/schemas.py` (e.g.
   `reject_blank_title`/`reject_blank_content`).

## Requirements implemented

- Requirement 4, 5, 6, 7, 8, 9, 14

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
