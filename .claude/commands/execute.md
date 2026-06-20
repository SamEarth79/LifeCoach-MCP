# execute.md

## Position in the framework

Step 2 of 4 in the `/implement` workflow, invoked by `commands/implement.md`
(and, per-story, by `commands/implement-batch.md`).

- **Previous step**: `commands/plan.md`. Its output is the confirmed plan
  (which specialist agents, in what order) held in conversation context.
- **This step**: run each planned specialist agent in sequence against the
  actual product repo, collecting their change reports.
- **Next step**: `commands/test.md`, which receives the combined change
  reports from this step to determine what needs testing.

## What this command does

1. For each specialist agent in the plan, in order:
   - Spawn/invoke the agent (`agents/frontend.md`, `agents/backend.md`, or
     `agents/infrastructure.md`) with: the story file, the relevant slice
     of `architecture.md`, and the output/report of any prior agent in this
     sequence it depends on (e.g. the API contract a `backend` agent just
     produced).
   - The agent reads `rules/coding-style.md` and `rules/security.md` before
     writing anything, per its own definition.
   - The agent implements its part directly in the product repo (not in
     `knowledge/`), on the already-checked-out `feature/<feature-folder>`
     branch.
   - Collect its report: files changed, summary, any deviation from
     architecture, any new dependency, anything incomplete and why.
   - **Before moving to the next agent in the sequence**, the orchestrator
     verifies this agent's output against the contract it was handed (per
     `agents/orchestrator.md`'s execute responsibilities) — e.g. does the
     frontend agent's API usage actually match the backend agent's
     documented request/response shape? This is a quick consistency check,
     not a full review.
   - If the check fails, do not proceed to the next agent. Send the
     mismatch back to whichever agent drifted from the contract, with the
     specific discrepancy, and re-verify before continuing.
2. If an agent reports it's blocked on something the next agent in sequence
   was supposed to produce, stop and surface this to the user — don't let
   agents guess at each other's contracts.
3. Once all planned agents have reported and passed their handoff checks,
   assemble a combined change report (all files touched across all agents,
   in order).

## Output

- Actual code changes committed to the working tree (not yet git-committed
  — that only happens in `commit.md` after tests pass).
- A combined change report, held in conversation context, passed directly
  into `test.md`.
