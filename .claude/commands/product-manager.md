# /product-manager

## Position in the framework

A standalone command, sitting between `/strategize` and `/design`. It does
not plan a feature in detail (that's `/design`'s job) and it does not
record direction (that's `/strategize`'s job) — it answers a narrower
question: *given the current strategy and what's already built, what
should be designed next?*

## Trigger

`/product-manager next-task`

## What this command does

1. Check whether `knowledge/strategy.md` exists.
   - If not, tell the user there's no recorded direction yet and suggest
     running `/strategize` first. Do not guess at a next feature without it.
2. Read `knowledge/strategy.md` in full, and list the feature folders under
   `knowledge/requirements/` (already designed) and
   `knowledge/implementations/` (already built), along with
   `knowledge/config.json` if present for prefix/counter context.
3. Invoke the `product-manager` agent (`agents/product-manager.md`) with
   all of the above loaded, to produce a single recommended next feature
   with its reasoning.
4. Present the recommendation to the user. If the agent flagged a close
   tie between two candidates, present both with the tradeoff and let the
   user pick.
5. If the user accepts the suggestion, tell them they can run
   `/design <suggested feature description>` to proceed — do not invoke
   `/design` automatically; this command only recommends.

## Output

- No files written. This command is purely advisory — a recommendation
  surfaced in conversation, handed off to `/design` only if and when the
  user chooses to act on it.

## Rules

- Never write to `knowledge/requirements/`, `knowledge/strategy.md`, or any
  other framework file — that's `/design`'s and `/strategize`'s job.
- Never auto-trigger `/design` — the user decides whether to act on the
  recommendation.
- If `knowledge/strategy.md` is missing or too sparse to ground a
  recommendation, say so plainly rather than inventing a direction.
