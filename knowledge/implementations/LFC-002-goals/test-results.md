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
