# test.md

## Position in the framework

Step 3 of 4 in the `/implement` workflow, invoked by `commands/implement.md`
(and, per-story, by `commands/implement-batch.md`).

- **Previous step**: `commands/execute.md`. Its output is the combined
  change report (all files touched, across all specialist agents that ran),
  held in conversation context.
- **This step**: the `qa` agent writes and runs the three test layers
  defined in `rules/testing.md`, then records results.
- **Next step**: `commands/commit.md`, but only if this step passes. On
  failure, this step is the end of the line for this `/implement` run —
  control returns to the user for a decision.

## What this command does

1. Spawn/invoke the `qa` agent (`agents/qa.md`) with: the story file (for
   acceptance criteria), the combined change report from `execute.md`, and
   `rules/testing.md`.
2. The `qa` agent determines required layers (unit, feature, E2E) per the
   scoping rules in `rules/testing.md`, writes the tests, and runs them
   plus the existing suite.
3. Append results to:
   - `knowledge/implementations/<feature-folder>/test-results.md` — pass/
     fail counts per layer, failure detail if any, under a heading for this
     story code.
   - `knowledge/implementations/<feature-folder>/implementation-summary.md`
     — a plain-text note (no code) of what was tested and why, under a
     heading for this story code.
4. Show the results directly in the conversation — do not just write the
   files silently and assume the user will go read them.
5. **If all required layers pass**: proceed to `commit.md`.
6. **If any layer fails**: stop. Tell the user exactly which layer, which
   test, and the error. Ask: fix (route back to the relevant specialist
   agent via `execute.md`), skip this story, or abort the `/implement` run.
   Do not auto-retry.

## Output

- `knowledge/implementations/<feature-folder>/test-results.md` (appended)
- `knowledge/implementations/<feature-folder>/implementation-summary.md`
  (appended)
- Pass/fail verdict, which gates whether `commit.md` runs at all.
