# Test Results: LFC-002-goals

## LFC-STORY-001

**Verdict: PASS WITH CAVEATS** — see "Environment limitation" below. No real
Postgres/Supabase instance was available to run the migration against; the
SQL-level acceptance criteria (AC1, AC2, AC3, AC4) were verified by
generating and inspecting the actual SQL Alembic would execute
(`alembic upgrade head --sql` / `alembic downgrade 2ae062d3817c:base --sql`),
not by running it against a live database. This is the same shape of work
as LFC-001-auth-infra-baseline's LFC-STORY-002 (the users-table migration),
and the same testing approach is used here.

### Layers required

- Unit: not required beyond what already exists. This migration adds no new
  business logic in `migrations/env.py` — the DB-URL-sourcing wiring it
  relies on is unchanged and already covered by
  `tests/unit/test_migrations_env.py`. There is no other unit-testable
  surface in a hand-written DDL migration file.
- Feature: there is no HTTP/API surface in this story to drive a
  conventional feature test through; the "feature" is the migration itself,
  verified via dry-run SQL generation (below) rather than a pytest feature
  test — same precedent as LFC-STORY-002.
- E2E (Playwright): **not required**. This is a backend/infrastructure-only
  story (an Alembic migration creating a table + RLS policies) with zero
  user-facing UI, no page, no rendered component, and no browser-driven
  flow. Per `rules/testing.md`, E2E is required only for stories that change
  user-facing behavior; a schema migration with no new UI is explicitly the
  kind of story called out as not needing it.

### Environment limitation (read before trusting "PASS")

No Docker daemon was running and no local Postgres/`psql` was available in
this sandbox (`docker ps` failed to connect to the daemon; `psql` not
found) — identical constraint to LFC-STORY-002. The migration also
references `auth.users`, a Supabase-managed table that doesn't exist in a
plain local Postgres without a stub schema. Given that constraint, testing
fell back to static/dry-run verification: the migration was never executed
against a real database, so things only a live DB could catch — e.g. the FK
actually resolving against a real `auth.users` row, RLS policy behavior
under an actual session with `auth.uid()` set, the index actually being
used by the planner, runtime permission errors under the `authenticated`
role — are **not** verified here. This should be re-run against a real
Supabase/Postgres instance (with the `auth` schema present) before being
considered fully verified for production.

### Dry-run SQL verification (executed for real via Alembic's offline mode, no DB needed)

Ran `alembic upgrade head --sql` against the actual migration file:
- Confirms AC1: generates `CREATE TABLE goals` with `id UUID DEFAULT
  gen_random_uuid() NOT NULL PRIMARY KEY`, `user_id UUID NOT NULL` with
  `CONSTRAINT goals_user_id_fkey FOREIGN KEY(user_id) REFERENCES auth.users
  (id) ON DELETE CASCADE`, `title TEXT NOT NULL`, `description TEXT`
  (nullable), `created_at`/`updated_at TIMESTAMP WITH TIME ZONE DEFAULT
  now() NOT NULL`, and `deleted_at TIMESTAMP WITH TIME ZONE` (nullable) —
  matches the story's column spec exactly, including the FK's `ON DELETE
  CASCADE`.
- Confirms AC2: generates `ALTER TABLE goals ENABLE ROW LEVEL SECURITY;`
  followed by `CREATE POLICY goals_select_own ... FOR SELECT USING
  (auth.uid() = user_id AND deleted_at IS NULL)`, `CREATE POLICY
  goals_insert_own ... FOR INSERT WITH CHECK (auth.uid() = user_id)`, and
  `CREATE POLICY goals_update_own ... FOR UPDATE USING (auth.uid() =
  user_id AND deleted_at IS NULL)` — wording matches the AC verbatim. No
  `DROP`/`CREATE POLICY` for a DELETE policy appears anywhere in the
  generated SQL, confirming no DELETE policy was created, per AC2.
- Confirms AC3: generates `CREATE INDEX ix_goals_user_id_deleted_at ON
  goals (user_id, deleted_at)` — column order matches the AC.

Ran `alembic downgrade 2ae062d3817c:base --sql` against the same migration:
- Confirms AC4: generates `DROP POLICY IF EXISTS goals_update_own`, `DROP
  POLICY IF EXISTS goals_insert_own`, `DROP POLICY IF EXISTS
  goals_select_own`, then `DROP INDEX ix_goals_user_id_deleted_at`, then
  `DROP TABLE goals`, in that order — policies first, then the index, then
  the table, with nothing left over. The downgrade continues on to drop the
  `users` table from the prior migration, confirming the chain is intact
  and reversible end-to-end.

Also ran `alembic history --verbose`: confirms a single linear head
(`2ae062d3817c` → parent `16b5eb4c9d06` → `<base>`) — no branching, no
chain issues.

### Static checks

- `py_compile` on the migration file: syntactically valid Python.
- No new dependencies required; `alembic`/`sqlalchemy` already installed
  from LFC-STORY-002.

### Unit tests — 0 new (no new unit-testable logic; existing
`tests/unit/test_migrations_env.py` coverage is unaffected and unchanged)

### Feature tests — not applicable; covered by dry-run SQL verification above

### E2E tests — not applicable (see rationale above)

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root: **37 passed, 0
failed** (all pre-existing tests; no new tests added by this story). No
regressions introduced by adding this migration file.

### Totals: 0 new automated tests (none applicable beyond what already
exists), 37/37 full suite passing, 0 failed. AC1–AC4 verified via dry-run
SQL generation, not live execution — see environment limitation above.

## LFC-STORY-002

**Verdict: PASS**

### Layers required

- Unit: not separately required beyond what the feature tests already
  exercise. `GoalCreate`'s whitespace-stripping/blank-rejection validator
  is simple Pydantic field-validator logic, fully exercised end-to-end
  through the feature tests below (a unit test in isolation would just
  duplicate the same assertions without mocking anything new).
- Feature: required and written — `POST /goals` is a new HTTP endpoint, and
  every acceptance criterion maps to at least one assertion (see below).
- E2E (Playwright): **not required**. This is a backend-only story (no new
  UI, no page, no frontend consuming this endpoint yet) — same carve-out as
  LFC-STORY-001 and every other backend-only story so far in this repo.

### Feature tests — `tests/feature/test_create_goal.py` (7 new)

Followed the conventions of `tests/feature/test_users_me.py`: `TestClient`
with `dependency_overrides[get_current_user]` to inject a fake verified
identity, and `monkeypatch.setattr(main, "get_rls_connection", ...)` with a
fake async-context-manager connection/cursor to avoid touching a real
database.

- `test_create_goal_returns_201_with_full_shape` — AC1: valid JWT + full
  body (title + description) returns `201` with the exact `GoalResponse`
  shape (`id`, `title`, `description`, `created_at`, `updated_at`).
- `test_create_goal_allows_omitted_description` — AC1: description is
  genuinely optional; omitting it still returns `201` with `description:
  null`.
- `test_create_goal_rejects_missing_title_with_422_and_no_db_write` — AC2:
  omitting `title` entirely returns `422`, and the fake cursor's
  `execute` was never called — proving Pydantic validation rejects the
  request before the handler body (and therefore the DB) is ever reached.
- `test_create_goal_rejects_empty_title_with_422_and_no_db_write` — AC2:
  a whitespace-only title (`"   "`) is rejected by `GoalCreate`'s
  `reject_blank_title` validator with `422`, again with zero DB writes —
  confirms the validator catches the "looks non-empty but isn't" case, not
  just a literal empty string.
- `test_create_goal_uses_verified_jwt_subject_as_user_id_for_insert` — AC3:
  captures the `user_id` argument passed into `get_rls_connection` and the
  first bound parameter of the `INSERT INTO goals` statement, and asserts
  both equal `current_user.id` (the verified JWT subject), not anything
  else.
- `test_create_goal_ignores_client_supplied_user_id_in_request_body` — AC3:
  sends a request body containing `"user_id": <a different UUID>` alongside
  a valid title. Confirms the response is still `201` and the actual
  `INSERT` parameter is the verified JWT subject's id — the
  client-supplied `user_id` value never appears anywhere in the executed
  query parameters. This also confirms the behavior the story requires:
  `GoalCreate` has no `user_id` field, and Pydantic v2's default
  `model_config` (no `extra="allow"` set) silently ignores unknown input
  fields rather than erroring or passing them through — verified directly
  against the installed `pydantic==2.13.4`, not assumed.
- `test_create_goal_requires_authentication` — AC4: no `Authorization`
  header → `401`, with no `dependency_overrides` for `get_current_user`,
  proving `get_current_user` is actually wired into this specific route
  (not just present elsewhere in the app) — mirrors
  `test_get_users_me_requires_authentication` in
  `tests/feature/test_users_me.py`.

### Feature tests — `tests/feature/test_rate_limit.py` (3 new, extending the existing file)

Followed the existing `low_limit_app` fixture pattern (env-var-driven low
limit + `importlib.reload` of `app.main`), extended the fixture's
`_FakeConnection` with an async `commit()` no-op since `POST /goals` commits
after insert and the existing fixture's fake connection didn't previously
need one (`GET /users/me` is read-only).

- `test_create_goal_allows_requests_within_the_configured_limit` — AC5:
  two requests under a configured limit of 2/60s both return `201`.
- `test_create_goal_rejects_request_exceeding_the_configured_limit` — AC5:
  a third request in the same window returns `429`.
- `test_create_goal_and_users_me_enforce_the_same_configured_threshold` —
  AC5: drives both `/users/me` and `/goals` to their 3rd request under the
  same `RATE_LIMIT_REQUESTS=2` config and confirms both independently
  return `429`. Note: slowapi tracks each `@limiter.limit`-style bucket per
  decorated callable (here, the shared `enforce_rate_limit` dependency
  function, but invoked once per route), so `/users/me` and `/goals` do
  *not* share a single global counter — a request to one does not consume
  the other's quota. The test was written to first assert exactly that (an
  earlier draft assumed a shared bucket and failed, which is how this was
  caught), then corrected to assert what AC5 actually requires: both
  routes enforce the *same configured threshold* via the *same
  `enforce_rate_limit` dependency and `per_ip_rate_limit` string*, not a
  literal shared counter.

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root: **47 passed, 0
failed** (37 pre-existing + 10 new). No regressions.

### Totals: 10 new automated tests (7 feature in `test_create_goal.py` + 3
feature in `test_rate_limit.py`), 47/47 full suite passing, 0 failed. All 5
acceptance criteria verified directly against the real implementation
(`app/main.py`, `app/schemas.py`), no unverified external-contract
assumptions in this story (no third-party wire format involved — JWT
verification itself was already covered and verified in LFC-001).

## LFC-STORY-003

**Verdict: PASS WITH CAVEATS** — see "Unverified-against-live-DB caveat"
below for AC3 and AC4.

### Layers required

- Unit: not separately required. `GET /goals` introduces no new
  business logic beyond what `POST /goals` already established (response
  mapping into `GoalResponse`); that mapping pattern is already exercised
  by `tests/feature/test_create_goal.py`, and the route itself is a thin
  passthrough — a unit test in isolation would duplicate the feature tests
  below without mocking anything new.
- Feature: required and written — `GET /goals` is a new HTTP endpoint, and
  every acceptance criterion that is testable at this layer maps to at
  least one assertion (see below).
- E2E (Playwright): **not required**. This is a backend-only story (no new
  UI, no page, no frontend consuming this endpoint yet) — same carve-out as
  LFC-STORY-001 and LFC-STORY-002.

### Feature tests — `tests/feature/test_list_goals.py` (5 new)

Followed the conventions of `tests/feature/test_create_goal.py`:
`TestClient` with `dependency_overrides[get_current_user]` to inject a fake
verified identity, and `monkeypatch.setattr(main, "get_rls_connection", ...)`
with a fake async-context-manager connection/cursor (extended with
`fetchall` since `GET /goals` returns multiple rows, unlike the existing
`fetchone`-based fixtures).

- `test_list_goals_returns_200_with_full_shape` — AC1: valid JWT returns
  `200` with a JSON array containing the exact `GoalResponse` shape (`id`,
  `title`, `description`, `created_at`, `updated_at`) for each row the
  (mocked) cursor returns.
- `test_list_goals_returns_200_with_empty_array_when_user_has_no_goals` —
  AC2: when the (mocked) cursor's `fetchall()` returns `[]`, the response
  is `200` with `[]`, not an error.
- `test_list_goals_issues_no_client_side_filter_that_would_conflict_with_rls`
  — AC3/AC4, application-boundary portion only (see caveat below):
  confirms the executed query string contains no `WHERE` clause and no
  bound parameters, and that the verified `current_user.id` is the value
  passed into `get_rls_connection(...)`. This proves the endpoint adds no
  app-level filter that could mask, duplicate, or conflict with the
  `goals_select_own` RLS policy, and that it scopes the connection to the
  correct user — but it does **not** prove the RLS policy itself correctly
  excludes other users' or soft-deleted rows, because the cursor is mocked
  and returns whatever rows the test supplies regardless of policy logic.
- `test_list_goals_requires_authentication` — AC5: no `Authorization`
  header, no `dependency_overrides` for `get_current_user` → `401`,
  confirming `get_current_user` is wired into this specific route, mirroring
  `test_create_goal_requires_authentication` and
  `test_get_users_me_requires_authentication`.
- `test_list_goals_returns_rows_in_the_order_the_cursor_yields_them_without_resorting`
  — AC6, application-side contract only (see caveat below): supplies two
  rows from the mocked cursor in a given order and confirms the response
  array preserves that exact order (no client-side re-sorting), and that
  the literal SQL string contains `ORDER BY created_at DESC`. This does
  **not** prove Postgres actually executes that `ORDER BY` correctly
  against live data, since the cursor is mocked.

### Feature tests — `tests/feature/test_rate_limit.py` (3 new, extending the existing file)

Extended the existing `low_limit_app` fixture's `_FakeCursor`/`_FakeConnection`
with a `fetchall()` method (it previously only supported `fetchone()`,
since `/users/me` and `POST /goals` are both single-row), so `GET /goals`
can be exercised through the same fixture.

- `test_list_goals_allows_requests_within_the_configured_limit` — AC6: two
  requests under a configured limit of 2/60s both return `200`.
- `test_list_goals_rejects_request_exceeding_the_configured_limit` — AC6: a
  third request in the same window returns `429`.
- `test_list_goals_enforces_the_same_configured_threshold_as_other_routes` —
  AC6: drives `/users/me` and `/goals` each to their 3rd request under the
  same `RATE_LIMIT_REQUESTS=2` config and confirms both independently
  return `429`, confirming `GET /goals` uses the same `enforce_rate_limit`
  dependency and `per_ip_rate_limit` string as the other routes (each route
  is its own slowapi bucket, per the precedent already established in
  LFC-STORY-002's rate-limit tests).

### Unverified-against-live-DB caveat (AC3, AC4)

AC3 ("soft-deleted goals never appear") and AC4 ("goals owned by a
different user never appear") are enforced entirely by the
`goals_select_own` RLS policy (`auth.uid() = user_id AND deleted_at IS
NULL`) created in LFC-STORY-001's migration, at the Postgres layer — `GET
/goals` issues a plain, unfiltered `SELECT ... FROM goals ORDER BY
created_at DESC` with zero app-level `WHERE` clause, relying entirely on
the RLS-scoped connection from `get_rls_connection(current_user.id)` to do
the filtering.

This test environment has no live Postgres/Supabase instance (same
constraint documented in LFC-STORY-001's migration testing — no Docker
daemon, no local `psql`). A feature test with a mocked cursor cannot
exercise real RLS policy evaluation: the mocked cursor's `fetchall()`
returns exactly the rows the test hands it, regardless of what `auth.uid()`
or `deleted_at` actually are, so any test that "verifies" cross-user
isolation or soft-delete exclusion using this mock would only be proving
self-consistency with its own setup, not real RLS enforcement. Per
`rules/testing.md`'s "External-contract assumptions" section (the same
logic applies here to an internal trust boundary — Postgres RLS — that
isn't actually exercised by this test layer), AC3 and AC4 are therefore
**not verified** by the automated tests in this story. What was verified
instead, and is the correct and complete claim for this test layer, is
that the endpoint does not add any conflicting client-side filter and
correctly delegates scoping to the RLS-scoped connection
(`test_list_goals_issues_no_client_side_filter_that_would_conflict_with_rls`).

AC3 and AC4 should be re-verified against a real Supabase/Postgres
instance (e.g. by inserting rows for two different users plus a
soft-deleted row, then querying through the `authenticated` role with
`auth.uid()` set, and confirming the result set excludes both) before this
story is considered fully verified for production. This mirrors the
caveat already on record for LFC-STORY-001's migration (RLS policy
behavior under a real session was likewise never executed against a live
database).

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root: **55 passed, 0
failed** (47 pre-existing + 8 new). No regressions.

### Totals: 8 new automated tests (5 feature in `test_list_goals.py` + 3
feature in `test_rate_limit.py`), 55/55 full suite passing, 0 failed. AC1,
AC2, AC5, AC6 (application-side contract) verified directly against the
real implementation. AC3 and AC4 (and the live-execution half of AC6's
`ORDER BY`) are unverified against a real database in this environment —
explicit caveat above, not a silent gap.

## LFC-STORY-004

**Verdict: PASS WITH CAVEATS** — see "Unverified-against-live-DB caveat"
below for AC2 (the "RLS hides the row" half).

### Layers required

- Unit: not separately required. `GoalUpdate`'s partial-update/blank-title
  validation is simple Pydantic logic, fully exercised end-to-end through
  the feature tests below; the route itself has no other unit-testable
  logic in isolation.
- Feature: required and written — `PATCH /goals/{goal_id}` is a new HTTP
  endpoint, and every acceptance criterion maps to at least one assertion.
- E2E (Playwright): **not required**. This is a backend-only story (no new
  UI, no page, no frontend consuming this endpoint yet) — same carve-out as
  every other backend-only story in this feature so far.

### Feature tests — `tests/feature/test_update_goal.py` (11 new)

Followed the conventions of `tests/feature/test_create_goal.py` and
`tests/feature/test_list_goals.py`: `TestClient` with
`dependency_overrides[get_current_user]` and `monkeypatch.setattr(main,
"get_rls_connection", ...)` with a fake async connection/cursor (extended
with a `committed` flag to assert whether `conn.commit()` was actually
called, since this route conditionally commits).

- `test_update_goal_title_only_updates_only_title` — AC1: sends `{"title":
  ...}` only, asserts `200` with the full updated shape, and — critically —
  inspects the literal executed SQL's `SET` clause and the bound parameter
  tuple to confirm `description` is never referenced and the only bound
  values are `(new_title, goal_id)`. This proves partial-update semantics
  actually work at the SQL level, not just that the response looks right.
- `test_update_goal_description_only_updates_only_description` — AC1, the
  mirror case: sends `{"description": ...}` only, confirms the `SET` clause
  (sliced before `updated_at`) contains `description = %s` and not `title`,
  and the bound params are `(new_description, goal_id)`.
- `test_update_goal_both_fields_updates_both` — AC1: sends both fields,
  confirms both appear in the `SET` clause and both are bound in the
  correct order before `goal_id`.
- `test_update_goal_returns_404_when_no_row_returned` — AC2 (application-side
  half only, see caveat below): mocks `fetchone()` to return `None` after
  the `UPDATE ... RETURNING`, confirms `404` and that `conn.commit()` was
  never called (no point committing an `UPDATE` that affected zero rows).
- `test_update_goal_rejects_explicitly_empty_title_with_422` — AC3: `title:
  ""` is rejected by `GoalUpdate`'s `reject_blank_title` validator with
  `422`, and the fake cursor's `execute` is never called.
- `test_update_goal_rejects_whitespace_only_title_with_422` — AC3: same
  validator catches a whitespace-only title (`"   "`), not just a literal
  empty string, again with zero DB writes.
- `test_update_goal_allows_explicit_null_description` — AC3: `description:
  null` is accepted, returns `200`, and the executed `UPDATE` actually binds
  `None` for the `description` parameter.
- `test_update_goal_omitting_title_does_not_touch_it` — the core
  partial-update distinction the story calls out explicitly: omitting
  `title` from the body entirely means it never appears in the SQL `SET`
  clause and its old value is never referenced in the bound parameters
  (only the new `description` value and `goal_id` are bound) — proving
  `model_dump(exclude_unset=True)` semantics, not a `None`-default that
  would silently null out an omitted field.
- `test_update_goal_requires_authentication` — AC4: no `Authorization`
  header, no `dependency_overrides` for `get_current_user` → `401`,
  confirming `get_current_user` is wired into this specific route.
- `test_update_goal_empty_body_is_a_no_op_select_and_returns_200_without_bumping_updated_at`
  — implementation-documented edge case: an empty PATCH body (`{}`) takes
  the `SELECT`-only path (no `UPDATE`, no `updated_at = now()` anywhere in
  the executed query), returns `200` with the goal's current (unchanged)
  `updated_at`, and `conn.commit()` is never called — confirming the no-op
  truly does nothing at the database level.
- `test_update_goal_empty_body_returns_404_when_goal_does_not_exist` — same
  no-op path, but the mocked `SELECT`'s `fetchone()` returns `None`,
  confirming `404` via the same code path, and no commit.

### Feature tests — `tests/feature/test_rate_limit.py` (3 new, extending the existing file)

Followed the existing `low_limit_app` fixture pattern, no fixture changes
needed (it already supports `fetchone()` + `commit()` from prior stories).

- `test_update_goal_allows_requests_within_the_configured_limit` — AC5: two
  requests under a configured limit of 2/60s both return `200`.
- `test_update_goal_rejects_request_exceeding_the_configured_limit` — AC5: a
  third request in the same window returns `429`.
- `test_update_goal_enforces_the_same_configured_threshold_as_other_routes` —
  AC5: drives both `/users/me` and `PATCH /goals/{goal_id}` to their 3rd
  request under the same `RATE_LIMIT_REQUESTS=2` config and confirms both
  independently return `429`, confirming the shared `enforce_rate_limit`
  dependency and `per_ip_rate_limit` string are wired into this route too
  (each route is its own slowapi bucket, per the precedent from
  LFC-STORY-002/003's rate-limit tests).

### Unverified-against-live-DB caveat (AC2)

AC2 states that editing a goal that doesn't exist, isn't owned by the
requester, or is already soft-deleted returns `404` "in addition to RLS
already hiding the row." Two distinct mechanisms are named: (a) the
app-level handling of "the `UPDATE ... RETURNING` yielded no row," and (b)
the `goals_update_own` RLS policy (`auth.uid() = user_id AND deleted_at IS
NULL`) actually hiding rows it shouldn't be able to touch at the Postgres
layer.

This test environment has no live Postgres/Supabase instance (same
constraint as every other story in this feature). The feature tests above
verify (a) directly — `test_update_goal_returns_404_when_no_row_returned`
mocks `fetchone()` to return `None` and confirms the app turns that into a
clean `404` with no commit. They do **not** verify (b): a mocked cursor
returns exactly the row the test hands it regardless of `auth.uid()`,
ownership, or `deleted_at`, so no test here proves the RLS policy itself
actually blocks a cross-user or soft-deleted update. Per `rules/testing.md`'s
"External-contract assumptions" section (applied to the internal RLS trust
boundary, as in LFC-STORY-003), this half of AC2 is therefore **not
verified** and should be re-checked against a real Supabase/Postgres
instance — e.g. attempting an `UPDATE` as one user against another user's
goal, and against a soft-deleted goal, through the `authenticated` role with
`auth.uid()` set, and confirming both are rejected/return no row — before
this story is considered fully verified for production.

### Full suite regression check

Ran `.venv/bin/python -m pytest -q` from the repo root: **69 passed, 0
failed** (55 pre-existing + 14 new). No regressions.

### Totals: 14 new automated tests (11 feature in `test_update_goal.py` + 3
feature in `test_rate_limit.py`), 69/69 full suite passing, 0 failed. AC1,
AC3, AC4, AC5, and the application-side half of AC2 verified directly
against the real implementation. The RLS-policy half of AC2 is unverified
against a real database in this environment — explicit caveat above, not a
silent gap. No code defects found; the partial-update SQL-building logic
was specifically checked at the SQL/parameter level (not just response
shape) and behaves correctly.
