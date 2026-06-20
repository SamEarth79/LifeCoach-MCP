# Implementation Summary: LFC-002-goals

## LFC-STORY-001

Tested the `create_goals_table` migration (`2ae062d3817c`) against all four
acceptance criteria, following the same dry-run approach established for
LFC-001-auth-infra-baseline's LFC-STORY-002 (the users-table migration),
since this is the same shape of work: a hand-written Alembic DDL migration
with RLS, and no live Postgres/Supabase instance was available in this
environment either.

What was tested and why:

- AC1 (table columns: `id`, `user_id` FK with cascade, `title`,
  `description`, `created_at`, `updated_at`, `deleted_at`) and AC2 (RLS
  enabled with `goals_select_own`/`goals_insert_own`/`goals_update_own`, no
  DELETE policy) and AC3 (index on `(user_id, deleted_at)`): no live
  database was available (no Docker daemon running, no local `psql`), and
  the migration's `auth.users` FK reference is Supabase-managed and
  wouldn't exist in a plain Postgres without a stub schema anyway. Instead
  of skipping these ACs, ran `alembic upgrade head --sql` — Alembic's
  offline mode, which generates the exact SQL it would execute without
  touching a database — and inspected the output directly. The generated
  `CREATE TABLE`, `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`, `CREATE
  INDEX`, and three `CREATE POLICY` statements match the story's spec
  exactly, including verifying no DELETE policy is generated anywhere in
  the output.
- AC4 (clean downgrade): ran `alembic downgrade 2ae062d3817c:base --sql`
  and confirmed the generated SQL drops the three policies, then the
  index, then the table, in that order, with nothing left over, before
  continuing on to unwind the prior users-table migration — confirming the
  migration chain itself is intact and fully reversible.
- Unit tests: no new ones were needed. This migration introduces no new
  logic in `migrations/env.py` (the DB-URL-sourcing wiring it depends on is
  unchanged and already covered by the existing
  `tests/unit/test_migrations_env.py`), and a hand-written DDL migration
  file has no other unit-testable surface.
- E2E (Playwright) was explicitly skipped: this is a backend/infra-only
  story (a database migration), with no UI, no page, and no browser flow
  to test. Per `rules/testing.md`, E2E is only required for stories that
  change user-facing behavior — the same carve-out applied to
  LFC-STORY-002.

Important caveat: none of AC1–AC4 were verified against a real, running
database. The `--sql` dry-run proves the migration is internally
consistent and generates correct-looking DDL, but cannot catch issues that
only manifest at execution time against a real `auth.users` table and a
real Postgres RLS engine (e.g. FK resolution against actual rows,
`auth.uid()` behavior under a real session, the index actually being used
by the query planner, behavior under the `authenticated` role specifically
since LFC-001 enforces RLS via that role rather than bypassing it). This is
a genuine gap, not a fabricated pass — it should be re-verified against a
real Supabase/Postgres instance before being trusted in production.

Result: 0 new automated tests needed (no new unit-testable logic; coverage
gap is none — existing tests remain valid). Full suite: 37/37 passing, 0
regressions from adding this migration file. All four acceptance criteria
verified via dry-run SQL generation, not live execution. Verdict: PASS WITH
CAVEATS (see test-results.md for the full environment-limitation writeup).

## LFC-STORY-002

Tested the `POST /goals` endpoint (`app/main.py`) and its request/response
schemas (`app/schemas.py`) against all five acceptance criteria, by reading
the actual implementation first rather than testing against the story's
prose alone, then writing feature tests that mock at the same seams the
existing `/users/me` tests use: `dependency_overrides[get_current_user]`
for identity, and `monkeypatch.setattr(main, "get_rls_connection", ...)`
with a fake async connection/cursor for the database.

What was tested and why:

- AC1 (201 with full shape, description optional): two tests in the new
  `tests/feature/test_create_goal.py` confirm the exact `GoalResponse`
  JSON shape with and without a `description` in the request body.
- AC2 (missing/empty title -> 422, no DB write): two tests cover both a
  missing `title` key and a whitespace-only `title` (`"   "`), each
  asserting the fake cursor's `execute` was never called — proving
  Pydantic's `field_validator` rejects the request before the handler body
  runs, not just before some surface-level check.
- AC3 (user_id always from the verified JWT, never client-supplied): one
  test captures the actual `user_id` passed to `get_rls_connection` and
  the first bound parameter of the `INSERT INTO goals` statement and
  asserts both equal the verified identity. A second test sends a request
  body that includes a `user_id` field for a *different* user and confirms
  it has zero effect on the insert — the inserted `user_id` is still the
  verified identity, and the client-supplied value never appears in the
  executed parameters anywhere. This also confirms `GoalCreate` correctly
  has no `user_id` field and that Pydantic v2's default config (no
  `extra="allow"`) silently drops unrecognized input fields — checked
  against the actually-installed `pydantic==2.13.4` rather than assumed
  from memory.
- AC4 (missing/malformed/expired JWT -> 401 before handler logic): one
  feature-level test sends a request to `POST /goals` with no
  `Authorization` header at all and no `dependency_overrides` for
  `get_current_user`, confirming `401` — proving `get_current_user` is
  actually wired into *this* route's dependency chain (not just present
  elsewhere in the app, e.g. only on `/users/me`). Malformed/expired-token
  handling itself is already covered by `tests/unit/test_auth.py`'s
  existing `get_current_user` unit tests and wasn't re-verified at the
  unit level here, per the story's intent to confirm route wiring rather
  than re-test `get_current_user`'s internals.
- AC5 (same rate limiter as /users/me): extended
  `tests/feature/test_rate_limit.py` with three tests following its
  existing `low_limit_app` fixture pattern (low limit via env var +
  `importlib.reload`). One gotcha surfaced during this: the fixture's
  `_FakeConnection` didn't have a `commit()` method, because `/users/me`
  is read-only — `POST /goals` calls `conn.commit()` after the insert, so
  the fixture needed a no-op async `commit()` added. A second gotcha: an
  initial test assumed `/users/me` and `/goals` share one global counter
  (so a request to one would consume the other's quota); this failed,
  revealing that slowapi tracks rate-limit buckets per decorated route,
  not globally. The test was corrected to assert what AC5 actually
  requires — both routes enforce the *same configured threshold* via the
  same `enforce_rate_limit` dependency and `per_ip_rate_limit` string, not
  a single shared counter.

Result: 10 new automated tests (7 in `tests/feature/test_create_goal.py`,
3 added to `tests/feature/test_rate_limit.py`). Full suite: 47/47 passing
(37 pre-existing + 10 new), 0 regressions. All five acceptance criteria
verified directly against the real implementation. No unverified
external-contract assumptions baked into this story — JWT verification's
external contract (Supabase's actual signing scheme) was already verified
in LFC-001-auth-infra-baseline and isn't re-litigated here. Verdict: PASS.

## LFC-STORY-003

Tested the `GET /goals` endpoint (`app/main.py`), which lists the
requester's goals via a plain, unfiltered `SELECT ... ORDER BY created_at
DESC` that relies entirely on the `goals_select_own` RLS policy (`auth.uid()
= user_id AND deleted_at IS NULL`, created in LFC-STORY-001's migration) for
per-user scoping and soft-delete exclusion — no app-level `WHERE` clause.

What was tested and why:

- AC1 (200 with full shape) and AC2 (200 with empty array when no goals):
  two tests in the new `tests/feature/test_list_goals.py` confirm the exact
  `GoalResponse` array shape for one row, and an empty array when the
  (mocked) cursor's `fetchall()` returns nothing.
- AC3 (soft-deleted goals excluded) and AC4 (other users' goals excluded):
  these are enforced entirely by the `goals_select_own` RLS policy at the
  Postgres layer, not by application code, and this environment has no
  live Postgres/Supabase instance (same constraint as LFC-STORY-001's
  migration testing). A feature test with a mocked cursor cannot exercise
  real RLS evaluation — the mock returns whatever rows the test hands it
  regardless of `auth.uid()` or `deleted_at`. Writing a test that fed the
  mock a "deleted" or "other user's" row and asserted it didn't appear
  would only prove the test's own setup is self-consistent, not that RLS
  actually filters anything — exactly the kind of misleading test
  `rules/testing.md`'s "External-contract assumptions" section warns
  against, applied here to an internal trust boundary (RLS) rather than an
  external one. Instead, what's verifiable and was tested: that the
  endpoint issues no client-side filter that could mask or conflict with
  RLS, and correctly passes the verified user id into the RLS-scoped
  connection (`test_list_goals_issues_no_client_side_filter_that_would_conflict_with_rls`).
  AC3 and AC4 are therefore unverified against a live database — flagged
  explicitly in test-results.md, not silently assumed to pass.
- AC5 (missing/malformed/expired JWT -> 401): one test sends a request
  with no `Authorization` header and no `dependency_overrides` for
  `get_current_user`, confirming `401` and that `get_current_user` is
  wired into this specific route.
- AC6 (rate-limited like other endpoints, and stable `ORDER BY
  created_at DESC` ordering): split into two parts. The application-side
  ordering contract was tested directly — the endpoint passes through
  whatever order the (mocked) cursor's `fetchall()` returns without
  re-sorting, and the literal SQL string contains `ORDER BY created_at
  DESC` — but whether Postgres actually executes that ordering correctly
  against live data is, like AC3/AC4, unverified here. The rate-limiting
  half was tested by extending `tests/feature/test_rate_limit.py` with
  three tests following the existing `low_limit_app` fixture pattern; the
  fixture's shared `_FakeCursor`/`_FakeConnection` needed a new `fetchall()`
  method added since it previously only supported `fetchone()` (both prior
  routes using the fixture, `/users/me` and `POST /goals`, are single-row).

Result: 8 new automated tests (5 in `tests/feature/test_list_goals.py`, 3
added to `tests/feature/test_rate_limit.py`). Full suite: 55/55 passing (47
pre-existing + 8 new), 0 regressions. AC1, AC2, AC5, and the application-side
half of AC6 verified directly against the real implementation. AC3, AC4,
and the live-execution half of AC6 (the `ORDER BY` actually sorting
correctly in Postgres) are unverified against a real database in this
environment — explicit caveat in test-results.md, consistent with the
precedent set by LFC-STORY-001's migration testing. No code defects found.
Verdict: PASS WITH CAVEATS.
