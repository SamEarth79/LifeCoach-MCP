# Coding Style Rules

These rules apply to every agent (`frontend`, `backend`, `infrastructure`)
that writes application code. They encode senior-engineer, industry-standard
practice — not framework-specific style.

## 1. Match the existing codebase first

Before writing anything, read the surrounding code. If the repo already has
conventions — naming, file layout, import ordering, error handling patterns,
state management approach — follow them, even if you'd personally choose
differently. Consistency within a codebase beats any individual preference.

Only introduce a new pattern when no convention exists yet (e.g. the first
file of its kind), and in that case choose the idiomatic default for the
language/framework in use.

## 2. No premature abstraction

- Do not build a helper, factory, config layer, or interface for something
  used once. Three concrete, similar lines are better than an abstraction
  built for hypothetical future cases.
- Do not add feature flags, plugin systems, or extensibility hooks unless the
  story explicitly requires them.
- Duplication across two call sites is fine. Extract only once a third real
  call site appears.

## 3. Naming

- Names must say what a thing is or does; if a name needs a comment to
  explain it, rename it instead.
- Booleans read as predicates (`isActive`, `hasPermission`), not as opaque
  flags (`flag`, `status`).
- Avoid abbreviations except universally understood ones (`id`, `url`,
  `req`/`res` in handler signatures by convention).
- Match the casing convention already used in the file/module
  (`camelCase` for JS/TS variables and functions, `PascalCase` for
  classes/components/types, `snake_case` for Python and SQL, `SCREAMING_CASE`
  for constants/env vars).

## 4. Functions and files

- A function does one thing at one level of abstraction. If you need "and"
  to describe what it does, split it.
- Prefer early returns over nested conditionals.
- Keep functions short enough to read without scrolling; if you can't name a
  natural split point, that's a signal the function is doing too much.
- One responsibility per file. If a file is growing into multiple unrelated
  concerns, split it along those concerns, not arbitrarily by line count.

## 5. Comments

- Default to no comments. Well-named code should not need narration.
- Write a comment only when it captures a non-obvious WHY: a hidden
  constraint, a workaround for a specific external bug, an invariant that
  isn't visible from the code itself.
- Never write a comment that restates what the code already says, references
  a story code, ticket number, or "fix for X" — that context belongs in the
  commit message, not the source.
- No commented-out code. Delete it; git history preserves it.

## 6. Error handling

- Handle errors at the boundary where they're meaningful (API handler, I/O
  call, external service call) — not speculatively at every internal
  function call.
- Never swallow an error silently. Either handle it meaningfully, or let it
  propagate.
- Do not catch exceptions you have no plan for. An empty `catch` block is a
  bug.
- Fail loudly in development, fail safely in production — don't leak internal
  error detail (stack traces, query text) to end users or API responses.

## 7. Types and validation

- Prefer static typing wherever the language/tooling supports it (TypeScript
  over plain JS, type hints in Python). Don't use `any`/untyped escapes
  except at genuine external boundaries (third-party data, dynamic JSON).
- Validate data at the boundary where it enters the system (API input, form
  submission, file parse). Once validated, trust it internally — don't
  re-validate the same data repeatedly through the call stack.

## 8. Dependencies

- Don't add a new third-party package for something the standard library or
  an already-installed dependency can do.
- If a story genuinely requires a new dependency, prefer actively maintained,
  widely-adopted packages over obscure ones, and call out the addition
  explicitly in the implementation summary.

## 9. Git hygiene (code-level)

- Code should be committed in a state that builds and passes existing tests
  — never commit known-broken intermediate states (see `test.md` / `commit.md`
  for when commits actually happen).
- Commit-worthy code has no leftover debug statements (`console.log`,
  `print`, debugger breakpoints) and no dead code.

## 10. Formatting

- Defer to the repo's existing formatter/linter config (Prettier, ESLint,
  Black, gofmt, etc.) if one exists — run it, don't hand-format.
- If no formatter is configured, use the language's standard idiomatic
  formatting (e.g. `gofmt` defaults for Go, PEP 8 for Python).
