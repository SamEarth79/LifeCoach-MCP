# commit.md

## Position in the framework

Step 4 of 4 in the `/implement` workflow, invoked by `commands/implement.md`
(and, per-story, by `commands/implement-batch.md`). This is the last step —
there is no separate finalize or report step.

- **Previous step**: `commands/test.md`. This step only runs if `test.md`
  reported all required layers passing. Its output is the test results
  already shown to the user and recorded in
  `knowledge/implementations/<feature-folder>/test-results.md`.
- **This step**: propose a commit message, show it alongside the test
  results, get explicit user confirmation, then commit.
- **Next step**: none within `/implement`. Control returns to
  `implement.md`'s (or `implement-batch.md`'s) closing/looping logic.

## What this command does

1. Assemble the proposed commit message from the combined specialist
   agent reports (from `execute.md`) and the story title:
   `<STORY-CODE>: <short summary>` — e.g.
   `LFC-STORY-001: add login form`.
2. Show the user:
   - The proposed commit message.
   - A short recap of the test results (already shown in `test.md`, but
     restate the pass summary here so the confirmation is self-contained).
   - The list of files that will be included in the commit.
3. Ask for explicit confirmation before doing anything. Do not commit
   silently or proceed on an assumed "yes."
4. If confirmed:
   - Stage exactly the files changed for this story (not an unrelated
     `git add -A`).
   - Commit onto `feature/<feature-folder>` with the confirmed message.
   - Confirm the commit succeeded and show the commit hash.
5. If the user wants changes to the message, update and re-confirm before
   committing.
6. If the user declines to commit at all, stop here — do not commit, and
   tell them the changes remain uncommitted on the working tree.

## Output

- A git commit on `feature/<feature-folder>`, only after explicit user
  confirmation.
- No PR is created and nothing is pushed — that is `commands/pr-create.md`,
  triggered manually, separately.
