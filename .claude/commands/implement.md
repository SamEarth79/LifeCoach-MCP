# /implement

## Position in the framework

This is the **entry point and orchestrator** for implementing a single
story. It does not do any work itself — it runs these steps in order, each
defined in its own command file:

1. `commands/plan.md`
2. `commands/execute.md`
3. `commands/test.md`
4. `commands/commit.md`

It reads finalized output from `/design` and writes implementation output.
It does not modify anything under `knowledge/requirements/`.

## Trigger

`/implement <feature-folder> <story-code>`

e.g. `/implement LFC-001-user-auth LFC-STORY-001`

If either argument is missing, ask the user for it before proceeding — do
not guess which feature or story is intended.

## What this command does

### 1. Load context

- Read `knowledge/requirements/<feature-folder>/stories/<story-code>.md` —
  this is the unit of work. If it doesn't exist, stop and tell the user.
- Read `knowledge/requirements/<feature-folder>/architecture.md` and
  `requirements.md` for surrounding context.
- Ensure `knowledge/implementations/<feature-folder>/` exists; create
  `implementation-summary.md` and `test-results.md` there if they don't
  exist yet (empty files with a top-level heading) — they grow across
  stories, they are not recreated per story.

### 2. Ensure the feature branch exists

- Branch name: `feature/<feature-folder>`.
- If it doesn't exist, create it from the current default branch. If it
  exists, check it out (or confirm it's already checked out).
- All work for this story happens on this branch.

### 3. Run the steps in order

1. **`plan.md`** — orchestrator agent reads the story, decides which
   specialist agents are needed and in what order, presents the plan to the
   user.
2. **`execute.md`** — runs the planned specialist agents in sequence,
   collects their change reports.
3. **`test.md`** — `qa` agent writes/runs the three test layers, writes
   results into `knowledge/implementations/<feature-folder>/test-results.md`
   and `implementation-summary.md`, shows results to the user.
   - **On failure**: stop here. Surface the failure to the user (which
     layer, which test, the error) and ask: fix, skip, or abort. Do not
     proceed to `commit.md`.
4. **`commit.md`** — only runs if `test.md` passed. Shows the proposed
   commit message and the test results, asks for explicit confirmation,
   commits onto `feature/<feature-folder>` only after the user confirms.

### 4. End state

Report to the user: story code, pass/fail, whether it was committed, and
where the summary/test-results files live. Mention that
`/pr-create <feature-folder>` is available once they're ready to open a PR.
