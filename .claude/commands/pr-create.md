# /pr-create

## Position in the framework

A standalone, **manually triggered** git command. It is not part of
`/implement` or `/implement-batch` — those commands only commit; they never
push or open a PR. This command is the only place a PR gets created.

- **Previous step**: none formal — the precondition is that one or more
  story commits already exist on `feature/<feature-folder>` (made via
  `commands/commit.md`).
- **This step**: generate technical documentation for the feature, push the
  branch, and open a PR, with a description generated from
  `knowledge/implementations/<feature-folder>/implementation-summary.md`.
- **Next step**: none automatic. `commands/pr-review.md` is a separate
  manual command the user runs when ready. Merging is always a human
  decision made outside this framework.

## Trigger

`/pr-create <feature-folder>`

e.g. `/pr-create LFC-001-user-auth`

## What this command does

1. Confirm `feature/<feature-folder>` exists and has commits ahead of the
   default branch. If there's nothing to PR, tell the user and stop.
2. Read `knowledge/implementations/<feature-folder>/implementation-summary.md`
   in full — this is the source for the PR description, not a re-derivation
   from the diff.
3. Read `knowledge/requirements/<feature-folder>/requirements.md` for the
   feature-level context (what this PR is for, at a glance).
4. Build the PR:
   - **Title**: `<feature-folder>: <short feature description>` (derived
     from the requirements doc), kept under ~70 characters.
   - **Body**: a summary section (what was built, pulled from
     implementation-summary.md, organized per story), and a test plan
     section (pulled from test-results.md — pass/fail status per story).
5. Show the proposed title and body to the user before doing anything.
   Get explicit confirmation — this is a visible, shared-state action.
6. On confirmation, generate documentation before opening the PR:
   - Invoke the `docs-writer` agent (`agents/docs-writer.md`) with
     `architecture.md`, `implementation-summary.md`, `test-results.md`, and
     the actual diff on `feature/<feature-folder>`.
   - It writes `knowledge/documentation/<feature-folder>/technical-doc.md`,
     appends an entry to `knowledge/documentation/CHANGELOG.md`, and
     updates `api-reference.md` / `architecture-overview.md` if applicable
     (creating any of these files if they don't exist yet).
   - Show the user a short summary of which doc files were created or
     updated — no separate confirmation needed here, since it's a side
     effect of the PR creation already confirmed in step 5.
   - Commit these documentation changes onto `feature/<feature-folder>` in
     a dedicated commit: `docs: <feature-folder>`.
7. Push `feature/<feature-folder>` to the remote (`git push -u origin
   feature/<feature-folder>`).
8. Create the PR via `gh pr create` with the confirmed title/body, targeting
   the repo's default branch.
9. Report the PR URL back to the user, and mention what documentation was
   generated.

## Rules

- Never auto-create a PR as a side effect of `/implement` or
  `/implement-batch` — this command must be invoked explicitly.
- Never merge. This command's job ends at opening the PR.
- If `implementation-summary.md` doesn't exist or is empty (e.g. user ran
  this before implementing anything), stop and tell the user rather than
  generating a placeholder description.
