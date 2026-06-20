# /implement-batch

## Position in the framework

This is the **entry point and orchestrator** for implementing every story in
a feature folder. It does not duplicate the logic of `/implement` — it runs
the exact same four steps (`plan.md` → `execute.md` → `test.md` →
`commit.md`) once per story, in sequence.

## Trigger

`/implement-batch <feature-folder>`

e.g. `/implement-batch LFC-001-user-auth`

If the argument is missing, ask the user which feature folder before
proceeding.

## What this command does

### 1. Load the story list

- Read `knowledge/requirements/<feature-folder>/stories/` — list all story
  files, sorted by story number.
- If empty, stop and tell the user there's nothing to implement.

### 2. Ensure the feature branch exists

- Same as `implement.md`: `feature/<feature-folder>`, created from default
  branch if it doesn't exist, checked out for the duration of this run.

### 3. Run `/implement` logic per story, sequentially

For each story in order:

1. Run the same four steps as `commands/implement.md` step 3
   (`plan.md` → `execute.md` → `test.md` → `commit.md`) for this story.
2. `test.md` and `commit.md` append to the same shared
   `knowledge/implementations/<feature-folder>/test-results.md` and
   `implementation-summary.md` — these files grow across the whole batch,
   not reset per story.
3. **If a story's `test.md` fails**: stop the batch entirely at this story.
   Surface the failure to the user (story code, layer, test, error) and
   ask: fix, skip this story and continue with the rest, or abort the
   batch. Do not silently continue to the next story on failure.
4. **If a story's `commit.md` is declined** by the user (they don't want to
   commit yet): stop the batch and ask whether to continue to the next
   story leaving this one uncommitted, or abort.
5. Only proceed to the next story once the current one is committed (or the
   user explicitly chose to skip/continue past it).

### 4. End state

After all stories are processed (or the batch is stopped early), report a
summary: which stories passed and were committed, which were skipped, which
failed and why. Point to
`knowledge/implementations/<feature-folder>/implementation-summary.md` and
`test-results.md` for full detail. Mention `/pr-create <feature-folder>` is
available once ready.
