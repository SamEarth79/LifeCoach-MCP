# LFC-STORY-007-003: LLM-suggested todos at goal creation

> Filled in by `draft.md` during `/design`. One file per story, inside the
> feature's `stories/` directory.

## Description

As a user creating a new goal, I want the LLM to suggest a starting set of
subgoal-style todos at the moment I create the goal, so that I immediately
have concrete next steps instead of a blank goal.

## Acceptance criteria

1. `create_goal` accepts an optional `todos: list[str]` argument.
2. When `todos` is provided and non-empty, each string is persisted as a
   todo for the newly created goal in the same call, with `sort_order`
   assigned by list position (0-indexed) and `done` defaulting to false;
   blank/whitespace-only strings in the list are rejected the same way
   blank `text` is rejected in `create_todo`.
3. When `todos` is omitted or empty, goal creation behaves exactly as it
   does today (no behavior change for callers that don't pass it).
4. The MCP server's system instructions (`_COACH_INSTRUCTIONS`) and/or
   `create_goal`'s tool description are updated to instruct the LLM to
   suggest 3-5 concrete subgoal-style todos whenever it creates a goal,
   populating the new `todos` argument.
5. The system instructions also direct the LLM to use
   `create_todo`/`update_todo`/`toggle_todo`/`delete_todo`/`reorder_todos`
   (from LFC-STORY-007-002) whenever the user conversationally asks to
   add, change, complete, remove, or reorder todos for an existing goal.
6. A feature test confirms calling `create_goal` with a `todos` list
   results in that many todo rows persisted for the new goal, correctly
   ordered.

## Requirements implemented

- Requirement 2, 3, 10

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
