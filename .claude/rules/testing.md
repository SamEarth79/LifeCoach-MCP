# Testing Rules

These rules govern the `qa` agent during `test.md`, and apply to any other
agent writing tests alongside implementation code. They define the three
test layers used throughout this framework and what "passing" means before
`commit.md` is allowed to run.

## The three layers

### 1. Unit tests

- Scope: a single function, method, or component in isolation. All
  collaborators (network, database, filesystem, other modules) are mocked or
  stubbed.
- Required for: new business logic, utility functions, data
  transformations, validation logic, and non-trivial component behavior
  (conditional rendering, state transitions).
- Not required for: trivial pass-through code (e.g. a one-line wrapper with
  no logic), pure config/type declarations.
- Use the project's existing test runner/framework (Jest, Vitest, pytest,
  Go's `testing` package, etc.) — don't introduce a second one.

### 2. Feature tests

- Scope: a single story's behavior end-to-end within its own
  layer — e.g. an API route tested through its real HTTP handler with a real
  (test) database, or a UI component tested through real user interaction
  (clicks, form fills) without a full browser.
- These verify the story's acceptance criteria as stated in its
  `stories/<STORY-CODE>.md` file — each acceptance criterion should map to at
  least one feature test assertion.
- Use a real test database/test environment, not the production database.
  Seed and tear down test data per test run; tests must not depend on
  leftover state from a previous run.

### 3. End-to-end (E2E) tests — Playwright

- Scope: the full user-facing flow through a real browser against a running
  instance of the app, covering the story's primary user journey
  (golden path) plus at least one meaningful edge case (e.g. invalid input,
  empty state, unauthorized access).
- Required for any story that changes user-facing behavior (UI flows, pages,
  forms). Not required for purely internal/infra stories with no user-facing
  surface (e.g. a backend migration with no new UI).
- Playwright tests live in the project's existing E2E directory if one
  exists; otherwise create `e2e/` at the repo root.
- E2E tests must be deterministic: no arbitrary `sleep`/fixed waits — use
  Playwright's built-in waiting/assertions (`expect(...).toBeVisible()`,
  `waitForResponse`, etc.).

## General testing principles

- Tests assert behavior, not implementation detail. Don't assert on internal
  state that isn't part of the contract; assert on observable input/output.
- Test names describe the scenario and expected outcome (e.g.
  `"rejects login with an expired token"`), not `"test1"` or the function
  name alone.
- No flaky tolerances: don't add retries or increased timeouts to paper over
  a nondeterministic test — find and fix the source of nondeterminism.
- Tests must be runnable independently and in any order; no test may depend
  on another test having run first.
- Mirror the existing test file layout/naming convention of the repo if one
  exists (e.g. `*.test.ts` colocated with source, or a parallel `tests/`
  tree). If the repo is new, colocate unit tests with source
  (`foo.ts` / `foo.test.ts`) and keep feature/E2E tests in their own
  directories.

## Definition of done for `test.md`

A story is only marked passing when:

1. All required layers (per the scoping rules above) have tests written.
2. All written tests, plus the existing test suite, pass.
3. Results (pass/fail counts per layer, and failure detail if any) are
   recorded in `knowledge/implementations/<feature>/test-results.md`.

If any layer fails, `test.md` stops and surfaces the failure — it does not
mark the story done, and `commit.md` does not run.
