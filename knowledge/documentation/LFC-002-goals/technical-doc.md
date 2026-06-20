# Technical Deep Dive: Goals (LFC-002)

## What this feature is

The first user-facing domain resource in the app: freeform goals that an
authenticated user can create, list, edit, and soft-delete. No categories,
tags, templates, or fixed taxonomy — a goal is just a `title` (required) and
an optional `description`, per `knowledge/strategy.md`. There is no UI yet;
this is a plain REST surface (FastAPI), matching the scope boundary set by
`LFC-001-auth-infra-baseline`.

Four endpoints, all gated behind the same `get_current_user` dependency
established in LFC-001:

- `POST /goals` — create a goal owned by the requester.
- `GET /goals` — list the requester's own active goals.
- `PATCH /goals/{goal_id}` — partially update a goal's `title`/`description`.
- `DELETE /goals/{goal_id}` — soft-delete a goal.

## Components

| File | Responsibility |
|---|---|
| `app/schemas.py` | New module (first of its kind in this repo): `GoalCreate`, `GoalUpdate`, `GoalResponse` Pydantic models for request/response validation. |
| `app/main.py` | New route handlers: `create_goal`, `list_goals`, `update_goal`, `delete_goal`, added alongside the existing `/health` and `/users/me` routes. |
| `migrations/versions/2ae062d3817c_create_goals_table.py` | Alembic migration creating the `goals` table, its RLS policies, and a supporting index. |

## The `goals` table and RLS-enforced soft delete

### Schema

```
goals
  id           uuid        PRIMARY KEY, default gen_random_uuid()
  user_id      uuid        NOT NULL, FK -> auth.users.id ON DELETE CASCADE
  title        text        NOT NULL
  description  text        NULL
  created_at   timestamptz NOT NULL DEFAULT now()
  updated_at   timestamptz NOT NULL DEFAULT now()
  deleted_at   timestamptz NULL  -- NULL = active, non-NULL = soft-deleted
```

Index: `ix_goals_user_id_deleted_at` on `(user_id, deleted_at)`, to keep the
list query's implicit per-user/active-only scan efficient as goal counts
grow.

### RLS policies — soft delete enforced at the database layer, not in query code

```sql
CREATE POLICY goals_select_own ON goals
  FOR SELECT USING (auth.uid() = user_id AND deleted_at IS NULL);

CREATE POLICY goals_insert_own ON goals
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY goals_update_own ON goals
  FOR UPDATE USING (auth.uid() = user_id AND deleted_at IS NULL);
```

The key design choice in this feature: `deleted_at IS NULL` is baked
directly into the `USING` clauses of `goals_select_own` and
`goals_update_own`, rather than left to application code to remember as a
`WHERE deleted_at IS NULL` filter on every query. This means `GET /goals`
and `PATCH /goals/{goal_id}` issue plain, unfiltered queries — no
`WHERE deleted_at IS NULL` appears anywhere in `app/main.py` — and a
soft-deleted (or another user's) row is invisible and uneditable purely
because Postgres won't return it under RLS, not because the route handler
happened to filter correctly. A future endpoint that forgets to add such a
filter still can't see or edit a deleted row.

**There is no `DELETE` RLS policy at all**, by design. `DELETE /goals/{goal_id}`
issues a SQL `UPDATE`, never a SQL `DELETE`:

```sql
UPDATE goals
SET deleted_at = now()
WHERE id = %s AND deleted_at IS NULL
RETURNING id
```

Because no `DELETE` policy exists, a SQL `DELETE` against `goals` issued
through the RLS-scoped (`authenticated`-role) connection would be rejected
by Postgres regardless of what application code does — hard-delete is
structurally impossible for this feature's code path, not just avoided by
convention. (`app/db.py`'s raw, RLS-bypassing connection — used only for
infra tasks like migrations and `/health` — is never used for goal data, so
that escape hatch doesn't apply here either.)

App-level ownership checks are not layered on top of RLS for `goals` the way
`GET /users/me` re-checks the fetched row's id — instead, `PATCH` and
`DELETE` rely on "no row returned from `RETURNING`" to mean "not
visible/owned/already-deleted," returning `404` in that case. This is a
narrower form of the same defense-in-depth idea: the app never assumes a row
matched just because a `WHERE id = %s` was supplied, it checks the actual
`RETURNING` result.

## Partial updates: `PATCH /goals/{goal_id}` and `exclude_unset`

`GoalUpdate` (`app/schemas.py`) makes both `title` and `description`
optional. The handler calls:

```python
update_fields = goal_update.model_dump(exclude_unset=True)
```

`exclude_unset=True` is what makes this a true partial update: a field that
was never present in the request JSON is excluded entirely from
`update_fields`, so it never appears in the dynamically built `SET` clause
or the bound parameters — the column keeps its current value untouched. This
is distinct from sending `"description": null`, which **is** present in the
request and **does** get applied (binds `NULL`). Omission and explicit null
are different operations, and the implementation (and its tests, see
`test_update_goal_omitting_title_does_not_touch_it` in
`knowledge/implementations/LFC-002-goals/test-results.md`) treats them that
way deliberately.

If the request body is empty (`update_fields` is empty), the handler takes a
`SELECT`-only no-op path instead of issuing an `UPDATE` — no write, no
`commit()`, and `updated_at` is not bumped. This avoids issuing a
meaningless `UPDATE ... SET updated_at = now()` with no actual field changes
just because a client sent `{}`.

## Dependency ordering: rate limit before identity, reused from LFC-001

Every `/goals` route repeats the exact dependency order LFC-001 established
for `GET /users/me`:

```python
async def create_goal(
    goal: GoalCreate,
    _rate_limit: None = Depends(enforce_rate_limit),
    current_user: CurrentUser = Depends(get_current_user),
) -> GoalResponse:
```

`enforce_rate_limit` is declared and therefore resolved before
`get_current_user`. FastAPI resolves `Depends(...)` in declaration order, so
a request over the configured per-IP threshold is rejected with `429` before
`get_current_user`'s JWT verification (and its `users` upsert) ever runs.
Declaring rate limiting via `@limiter.limit(...)` as a route decorator
instead would only wrap the call *after* all dependencies — including ones
that hit the database — had already resolved, which would defeat the point
of rate-limiting an authentication-adjacent endpoint. No new rate-limiting
mechanism was introduced for this feature; all four `/goals` routes reuse
the same module-level `limiter`/`per_ip_rate_limit` built once in
`app/main.py` from `Settings`.

## New: `app/schemas.py`

This feature is the first in the repo with body-validated endpoints, so
request/response shapes live in a dedicated `app/schemas.py` module rather
than inline in `app/main.py` — per `coding-style.md`'s one-responsibility
rule, once a file would mix routing with multiple unrelated data-shape
definitions, the concern is split out. `GoalCreate` and `GoalUpdate` both
reject a blank or whitespace-only `title` via a shared-shape
`field_validator` (`reject_blank_title`); `GoalCreate` requires `title`,
`GoalUpdate` makes it optional but applies the same blank-rejection when
present. Neither schema has a `user_id` field — Pydantic v2's default model
config silently drops any unrecognized field in the request body (verified
against the installed `pydantic` version during testing, not assumed), so a
client cannot influence which user a goal is attributed to even by sending
an extra `user_id` field; the verified JWT subject is the only source of
truth for ownership.

## Known gap: RLS enforcement was never verified against a live database

Every story in this feature except `POST /goals` (which has no read/update
path to mis-scope) depends on the `goals_select_own`, `goals_insert_own`,
and `goals_update_own` RLS policies actually behaving correctly under a real
Postgres session with `auth.uid()` set via the `authenticated` role. No
Docker daemon or local Postgres was available in the implementation
environment, so:

- The migration's `CREATE TABLE`/`ENABLE ROW LEVEL SECURITY`/`CREATE POLICY`
  statements were verified only via Alembic's `--sql` dry-run output, never
  executed against a real database.
- Cross-user isolation and soft-delete exclusion on `GET /goals` and
  `PATCH`/`DELETE /goals/{goal_id}` were verified only at the
  application-boundary level (the code adds no conflicting client-side
  filter and passes the correct user id into the RLS-scoped connection) —
  not by actually exercising the RLS policies against seeded rows for two
  different users plus a soft-deleted row.

This is a real, explicitly-flagged risk, not a silent gap — see the "Feature
Summary" section of
`knowledge/implementations/LFC-002-goals/test-results.md` for the full
rundown of exactly which behaviors remain unverified and what
re-verification against a live Supabase/Postgres instance should cover
before this feature is trusted in production.

## Extending this safely

Any future feature that references `goals` (the strategy doc names
suggestions and check-ins as likely candidates) must account for
soft-deleted rows:

1. **Joining to `goals`**: query through `get_rls_connection`, the same as
   every other per-user table in this app. Because `deleted_at IS NULL` is
   already enforced inside `goals_select_own`, a join through the
   RLS-scoped connection automatically excludes soft-deleted goals — do not
   add a redundant `WHERE deleted_at IS NULL` unless the new feature
   genuinely needs to see soft-deleted goals (e.g. an audit view), in which
   case it needs its own explicit RLS policy decision, not an app-level
   workaround.
2. **Never query `goals` through the raw, RLS-bypassing connection**
   (`get_connection()`) for per-user data — that connection exists only for
   infra tasks (migrations, `/health`) and would see soft-deleted and
   cross-user rows alike.
3. **If a future feature needs to restore a soft-deleted goal**: this is
   explicitly out of scope for this feature (no undelete endpoint exists).
   Adding one means adding a new `UPDATE` path that sets `deleted_at` back
   to `NULL` — be aware the existing `goals_update_own` policy's `USING`
   clause requires `deleted_at IS NULL` to even select the row to update, so
   an undelete cannot go through the existing policy as written; it would
   need either a separate policy or an app-bypassing path you'd have to
   design deliberately, not accidentally enable.
4. **Foreign keys from a new table into `goals.id`**: should reference
   `goals.id` directly (not duplicate `user_id`), and that new table should
   get its own `user_id`-scoped RLS policies following the same pattern
   `goals` itself follows from `users` — see
   `knowledge/documentation/LFC-001-auth-infra-baseline/technical-doc.md`'s
   "Extending this safely" section for the full step-by-step.
5. **Partial-update pattern**: if a future endpoint needs partial updates,
   reuse the `model_dump(exclude_unset=True)` + dynamic `SET` clause pattern
   from `update_goal` rather than inventing a new one — it's now the
   established convention in this codebase for "update only what was sent."
