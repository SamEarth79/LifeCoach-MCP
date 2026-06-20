# analyze.md

## Position in the framework

Step 2 of 4 in the `/design` workflow, invoked by `commands/design.md`.

- **Previous step**: `commands/gather.md`. Its output is the restated
  feature understanding (what it does, who it's for, scope boundaries,
  known constraints), carried forward in conversation context — not a file.
- **This step**: scan the existing codebase for anything relevant to the
  feature, and write the findings to
  `knowledge/requirements/<feature-folder>/analysis.md`.
- **Next step**: `commands/draft.md`, which reads `analysis.md` to inform
  `architecture.md`, `requirements.md`, and the stories.

## What this command does

1. Read the feature understanding handed off from `gather.md`.
2. Read `knowledge/strategy.md` if it exists — this is the project's
   accumulated business/UX/technical direction from `/strategize`. Ensure
   the feature being analyzed doesn't conflict with recorded direction; if
   it does, surface the conflict to the user before proceeding rather than
   silently analyzing around it.
3. Search the product repo for relevant existing code: similar features,
   models/schema that overlap, existing patterns this feature should match
   (auth, routing, state management, API conventions), and anything that
   could conflict with the new feature.
4. Identify constraints and risks surfaced by what's actually in the repo
   (e.g. "auth is already cookie-session based, not JWT" or "no existing
   payment integration to extend").
5. If something genuinely blocking or ambiguous is discovered that
   `gather.md` didn't surface, ask the user now rather than guessing.
6. Write the findings into
   `knowledge/requirements/<feature-folder>/analysis.md` using
   `templates/analysis.md` as the structure.

## Output

- File written: `knowledge/requirements/<feature-folder>/analysis.md`
- This file is the required input for `draft.md` — do not let `draft.md`
  run without it existing.
