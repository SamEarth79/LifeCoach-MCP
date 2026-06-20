# update-agent-framework

## Purpose

Use this skill when adding a new file (command, agent, template, rule, or
skill) to this framework repo, or modifying the structure of an existing
one. It keeps the framework internally consistent — new files referenced
correctly, the index in `CLAUDE.md` kept current, and the change deployed
to whichever target project repos are using this framework.

## When to use

- Adding a new command file under `commands/`.
- Adding a new agent under `agents/`.
- Adding a new template under `templates/`.
- Adding a new rule under `rules/`.
- Adding a new skill under `skills/` (including a future skill replacing
  this one).
- Renaming or removing any of the above.

Do not use this for changes to application code in a target product repo —
this skill only touches the framework repo itself.

## What this skill does

1. **Place the file** in the correct directory, following the existing
   naming convention in that directory (lowercase, hyphenated, `.md`).
2. **Follow the established structure** for that file type:
   - Commands: state position in the workflow, previous step's output
     location, what this step does, next step's input — matching the
     pattern used by every existing file in `commands/`.
   - Agents: role, inputs, responsibilities/rules consulted, output format
     — matching the pattern used by every existing file in `agents/`.
   - Templates: placeholder-driven Markdown skeleton, with a note on which
     command fills it in.
   - Rules: numbered, industry-standard, senior-engineer-level guidance —
     matching the tone and specificity of `rules/coding-style.md`,
     `rules/security.md`, `rules/testing.md`.
3. **Update `CLAUDE.md`**:
   - Add the new command to the Commands table, or new agent to the Agents
     table, if applicable.
   - If a new top-level directory is introduced, add it to the directory
     map.
4. **Update any file that should now reference the new addition** — e.g. a
   new command that's a step in an existing orchestrator workflow
   (`design.md`/`implement.md`/`implement-batch.md`) must be added into
   that orchestrator's step sequence, not left orphaned.
5. **Redeploy**: run `scripts/deploy.sh <target-project-path>` for any
   target project repo currently using this framework, so the change is
   reflected there. If no target path is known/given, tell the user which
   command to run themselves rather than guessing a path.

## Rules

- Never add a file without updating `CLAUDE.md`'s index — an
  undocumented command/agent is effectively invisible to future sessions.
- Never duplicate an existing command/agent/rule's responsibility — check
  the existing directory first; extend an existing file if it already owns
  the relevant concern.
- Keep changes scoped to exactly what was asked — this skill is for
  structural additions/edits to the framework, not an opportunity to
  refactor unrelated files.
