# LFC-STORY-001: goals.progress_percent migration

## Description

As a backend system, I want a nullable, range-checked
`progress_percent` column on `goals`, so that subsequent MCP tools have
somewhere to read and write a self-reported progress estimate.

## Acceptance criteria

1. A new Alembic migration adds `progress_percent` (integer, nullable, no
   default) to the existing `goals` table.
2. A `CHECK` constraint enforces `progress_percent IS NULL OR
   (progress_percent BETWEEN 0 AND 100)`.
3. Existing rows are unaffected (column is nullable, no backfill needed —
   existing goals simply have `progress_percent IS NULL`, meaning "no
   estimate yet").
4. No RLS policy changes are needed or made — confirm the existing
   `goals_select_own`/`goals_update_own` policies already cover this new
   column (they operate at the row level, not per-column).
5. `downgrade()` cleanly drops the constraint and the column, with nothing
   left over.

## Requirements implemented

- Requirement 1

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
