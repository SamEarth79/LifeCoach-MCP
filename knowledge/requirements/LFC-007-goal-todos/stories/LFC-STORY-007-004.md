# LFC-STORY-007-004: Todo checklist in goal detail view with interactive toggle

> Filled in by `draft.md` during `/design`. One file per story, inside the
> feature's `stories/` directory.

## Description

As a user viewing a goal's detail screen, I want to see its todos as a
checklist and tap a checkbox to mark one done or not done, so that I can
track subgoal progress at a glance without leaving the conversation.

## Acceptance criteria

1. `get_goal_detail_view` fetches the goal's todos (ordered by
   `sort_order`) alongside its existing data and includes them in the
   returned view payload.
2. `GoalDetailViewData` (in `app/ui_templates.py`) gains a `todos` field
   (list of a new `GoalDetailTodo` dataclass with `id`, `text`, `done`,
   `sortOrder`), and `goal_detail_data_to_dict` maps it to camelCase JS
   keys.
3. `renderGoalDetailView` renders the todo list as a checklist (text +
   checkbox reflecting `done`), in `sort_order`, below/alongside the
   existing recent-updates section.
4. Clicking a todo's checkbox calls `toggle_todo` via the existing
   MCP-UI `window.callTool` bridge with that todo's id, and the rendered
   checkbox state updates to reflect the new `done` value once the tool
   call resolves.
5. No other todo control (add/edit/reorder/delete) appears in the UI —
   those remain conversational/tool-only, per requirement 13.
6. The view continues to report its content size to the host correctly
   (per the existing iframe-sizing behavior) after the todo list is added,
   even when a goal has many todos.
7. A goal with zero todos renders the detail view without errors and
   without an empty/broken checklist section.

## Requirements implemented

- Requirement 11, 12, 13

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
