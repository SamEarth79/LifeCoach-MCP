# /strategize

## Position in the framework

A standalone command, sitting above the feature-level `/design` workflow.
Used both on a brand-new project (to establish initial direction) and on an
ongoing basis (to revisit or course-correct direction as the project
evolves). It is not part of the `/design` or `/implement` step sequences,
but its output (`knowledge/strategy.md`) is read by `/design`'s
`analyze.md` step for every feature planned afterward.

## Trigger

`/strategize`

## What this command does

1. Check whether `knowledge/strategy.md` exists.
   - If not, this is a new-project conversation: invoke the `strategist`
     agent (`agents/strategist.md`) to discuss business, UX, and technical
     direction from scratch.
   - If it exists, read it in full first, then invoke the `strategist`
     agent with that history loaded — this is a steering/course-correction
     conversation, not a fresh start.
2. Have the conversation. Let the user drive the topic (a specific decision
   they're stuck on, or an open-ended "let's talk about direction").
3. When the conversation reaches a natural stopping point (the user
   indicates they're done, or a clear decision has been reached and
   confirmed), summarize the decisions made — not a transcript.
4. Append the summary to `knowledge/strategy.md` under a dated heading
   (`## YYYY-MM-DD`), creating the file with a top-level heading if it
   doesn't exist yet. Each entry should capture: the decision, the
   reasoning/tradeoff considered, and what it means going forward.
5. Tell the user where it was recorded and that future `/design` runs will
   read it automatically.

## Output

- `knowledge/strategy.md` — created or appended to, at the `knowledge/`
  root (not inside any feature folder, since this is project-wide, not
  feature-specific).

## Rules

- Never write application code or feature-level docs from this command —
  that's `/design`/`/implement`'s job, informed by what's recorded here.
- Don't record open-ended discussion that didn't reach a decision — only
  record actual decisions and the reasoning behind them.
