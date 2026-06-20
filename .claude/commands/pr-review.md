# /pr-review

## Position in the framework

A standalone, **manually triggered** git command. It is independent of every
other command in this framework — by design, it does not share context with
them.

- **Previous step**: none formal — the precondition is that a PR already
  exists (created via `commands/pr-create.md` or otherwise).
- **This step**: spawn the `reviewer` agent with **no conversation
  history** — only the PR diff and `rules/` — and have it post a review.
- **Next step**: none automatic. The merge decision belongs to the user,
  made outside this framework, informed by the review this command
  produces.

## Trigger

`/pr-review <pr-number>`

e.g. `/pr-review 42`

## What this command does

1. Fetch the PR diff and description via `gh pr diff <pr-number>` and
   `gh pr view <pr-number>`.
2. Spawn the `reviewer` agent (`agents/reviewer.md`) as a **fresh agent
   with no prior conversation context**. Pass it only:
   - The PR diff
   - The PR description
   - `rules/coding-style.md`, `rules/security.md`, `rules/testing.md`
   Do not pass it `knowledge/`, the chat history that led to this PR, or any
   other context from this session — the independence is the point.
3. The `reviewer` agent reviews and produces:
   - Inline comments on specific lines for concrete, actionable issues.
   - One summary verdict: approve / request changes / comment.
4. Post the inline comments and summary verdict to the PR via `gh pr
   review` / `gh api`.
5. Show the user the same review output directly in this conversation —
   don't make them go read GitHub to see what was found.
6. Stop. Do not merge, do not push fixes, do not re-invoke specialist agents
   to address findings — if the user wants fixes made, that's a new
   `/implement` story or a manual edit, not something this command does
   automatically.

## Rules

- The `reviewer` agent must never be given this session's conversation
  history. If the harness/tool used to spawn it would otherwise carry
  context forward, explicitly strip it — the value of this command is an
  independent second opinion, not a continuation of the same reasoning that
  produced the code.
- Never auto-merge, regardless of verdict.
