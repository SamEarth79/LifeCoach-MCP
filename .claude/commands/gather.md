# gather.md

## Position in the framework

Step 1 of 4 in the `/design` workflow, invoked by `commands/design.md`.

- **Previous step**: none — this is the first step. Input is whatever the
  user has said about the feature so far (from the `/design` invocation or
  the conversation immediately around it).
- **This step**: have a conversation with the user to reach a clear,
  unambiguous understanding of what the feature is, who it's for, and any
  hard constraints. Produces no file — the output is a clear understanding
  carried forward in context into step 2.
- **Next step**: `commands/analyze.md`, which uses this understanding plus
  the codebase to write `analysis.md`.

## What this command does

1. Take the user's description of the feature as given.
2. Assess whether it's actually clear enough to analyze and draft from.
   Ambiguous means: unclear who the user/actor is, unclear what "done"
   looks like, unclear scope boundaries, or a missing critical constraint
   (e.g. "add payments" with no indication of provider, currency, or
   one-time vs. recurring).
3. **If clear**: skip straight to handing off to `analyze.md` — do not ask
   questions just to seem thorough.
4. **If ambiguous**: ask targeted clarifying questions, one focused round at
   a time (don't interrogate with ten questions at once). Stop asking once
   scope, actor, and success criteria are unambiguous — not before, not
   after.

## What to carry forward to the next step

A short, explicit restatement of the feature, covering:
- What it does
- Who it's for
- Scope boundaries (what it explicitly does NOT include, if mentioned)
- Any hard constraints already known (tech choices, deadlines, integrations)

Hand this off directly into `analyze.md` — do not write it to a file; it's
intermediate context only, not part of `knowledge/`.
