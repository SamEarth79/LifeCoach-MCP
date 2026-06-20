# draft.md

## Position in the framework

Step 3 of 4 in the `/design` workflow, invoked by `commands/design.md`.

- **Previous step**: `commands/analyze.md`. Its output is
  `knowledge/requirements/<feature-folder>/analysis.md`. Read it before
  doing anything in this step.
- **This step**: generate `architecture.md`, `requirements.md`, and one
  file per story in `stories/`, all inside
  `knowledge/requirements/<feature-folder>/`.
- **Next step**: `commands/review.md`, which presents everything written
  here to the user and loops on feedback.

## What this command does

1. Read `analysis.md` from the previous step in full.
2. Write `knowledge/requirements/<feature-folder>/architecture.md` using
   `templates/architecture.md` — approach, components touched, data flow,
   data model changes, key decisions. Base this on what `analysis.md`
   found, not on assumptions about the codebase.
3. Write `knowledge/requirements/<feature-folder>/requirements.md` using
   `templates/requirements.md` — plain numbered functional requirements
   (no per-requirement codes), non-functional requirements, out-of-scope
   section.
4. Break the requirements into stories:
   - For each story, read `nextStoryNumber["<feature-folder>"]` from
     `knowledge/config.json`, format as 3 digits, build the story code
     `<PREFIX>-STORY-NNN`.
   - Write `knowledge/requirements/<feature-folder>/stories/<STORY-CODE>.md`
     using `templates/story.md` — description, acceptance criteria,
     which requirement numbers it implements, and an initial guess at which
     agents (frontend/backend/infrastructure) it will need.
   - Increment `nextStoryNumber["<feature-folder>"]` in
     `knowledge/config.json` after each story is created.
5. Stories should be small enough that one story is independently
   implementable and testable — split a requirement into multiple stories
   if it bundles distinct pieces of work (e.g. "backend endpoint" and
   "frontend form" can be one story if tightly coupled, or two if either
   could ship/test independently).

## Output

- `knowledge/requirements/<feature-folder>/architecture.md`
- `knowledge/requirements/<feature-folder>/requirements.md`
- `knowledge/requirements/<feature-folder>/stories/<STORY-CODE>.md` (one or
  more)
- `knowledge/config.json` updated with incremented story counter

These are the required inputs for `review.md` — do not let `review.md` run
without all of the above existing.
