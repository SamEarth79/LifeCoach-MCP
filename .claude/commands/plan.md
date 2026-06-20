# plan.md

## Position in the framework

Step 1 of 4 in the `/implement` workflow, invoked by `commands/implement.md`
(and, per-story, by `commands/implement-batch.md`).

- **Previous step**: none within `/implement` — input is the story file
  `knowledge/requirements/<feature-folder>/stories/<story-code>.md` plus
  `architecture.md`/`requirements.md`, loaded by `implement.md` before this
  step runs.
- **This step**: the `orchestrator` agent decides which specialist agents
  are needed and in what order. Produces no file — output is a plan
  presented in conversation and carried forward into `execute.md`.
- **Next step**: `commands/execute.md`, which runs the plan produced here.

## What this command does

1. Spawn or invoke the `orchestrator` agent (`agents/orchestrator.md`) with
   the story file and relevant architecture context.
2. The orchestrator reads the story's "Agents likely needed" checklist and
   confirms or adjusts it — that checklist is a starting guess from
   `draft.md`, not binding.
3. The orchestrator decides execution order based on dependencies:
   - `infrastructure` before `backend`/`frontend` if new infra (service,
     queue, env var) is a prerequisite.
   - `backend` before `frontend` if frontend consumes a new/changed API.
   - Agents with no dependency on each other may be noted as independent,
     but default to sequential execution unless there's a clear reason to
     parallelize (parallelism across agents within a story is not yet
     formalized in this framework — keep it sequential unless trivially
     safe).
4. Present the plan to the user: which agents, in which order, and why.

## Output

- A confirmed plan (agent list + order), held in conversation context, not
  written to disk.
- This plan is the direct input to `execute.md` — it must not start
  spawning specialist agents without a plan from this step.
