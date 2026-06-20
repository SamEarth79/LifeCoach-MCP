# /design

## Position in the framework

This is the **entry point and orchestrator** for the design phase. It does
not do any work itself — it runs these steps in order, each defined in its
own command file:

1. `commands/gather.md`
2. `commands/analyze.md`
3. `commands/draft.md`
4. `commands/review.md`

There is no finalize step. Whatever is on disk in
`knowledge/requirements/<feature-folder>/` when the user stops giving
feedback during step 4 is what `/implement` will later read as final.

## Trigger

`/design` or `/design <feature description>`

## What this command does

### 1. Resolve the product prefix and config

- Check whether `knowledge/config.json` exists at the product repo root.
- If it does not exist: ask the user for the product name, derive a prefix
  (e.g. "LifeCoach" → `LFC`), and create `knowledge/config.json`:
  ```json
  {
    "prefix": "<PREFIX>",
    "nextFeatureNumber": 1,
    "nextStoryNumber": {}
  }
  ```
- If it exists, read it. This is the single source of truth for the prefix
  and counters used by every later step.

### 2. Resolve the feature folder

- If the user did not name the feature, ask for a short feature name now.
- Slugify it (lowercase, hyphenated).
- Take `nextFeatureNumber` from config, format as 3 digits, build the folder
  name: `<PREFIX>-<NNN>-<slug>` (e.g. `LFC-001-user-auth`).
- Create `knowledge/requirements/<feature-folder>/stories/`.
- Increment `nextFeatureNumber` in `knowledge/config.json` and add
  `"<feature-folder>": 1` to `nextStoryNumber`.
- This `<feature-folder>` value is what every subsequent step (and later,
  `/implement`) refers to. Pass it explicitly into each step below.

### 3. Run the steps in order

Run each step as described in its own file, passing along `<feature-folder>`
and the running context (what the user has said so far):

1. **`gather.md`** — produces a working understanding of the feature (no
   file output).
2. **`analyze.md`** — reads `<feature-folder>` context from step 1, writes
   `knowledge/requirements/<feature-folder>/analysis.md`.
3. **`draft.md`** — reads `analysis.md` from step 2, writes
   `architecture.md`, `requirements.md`, and `stories/<PREFIX>-STORY-NNN.md`
   files into `knowledge/requirements/<feature-folder>/`.
4. **`review.md`** — reads all files written in step 3, loops on user
   feedback, patches files in place. Ends when the user stops giving
   feedback.

### 4. End state

When `review.md` ends, tell the user where everything landed:
`knowledge/requirements/<feature-folder>/` — and that they can run
`/implement <feature-folder> <story-code>` or
`/implement-batch <feature-folder>` whenever they're ready. Do not ask them
to "confirm" or "finalize" — the design phase is simply over when they stop
talking.
