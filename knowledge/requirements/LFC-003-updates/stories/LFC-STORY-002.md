# LFC-STORY-002: MCP server scaffold and record_update tool

## Description

As an MCP client acting on behalf of a signed-in user, I want to record a
new coaching update linked to one of my goals, so that whatever the AI
and I agreed on is persisted for future reference and context.

## Acceptance criteria

1. An MCP tool server is mounted on the existing FastAPI app (same
   process), exposing tools at a dedicated path (e.g. `/mcp`), without
   changing any existing REST route's behavior.
2. The MCP Python SDK's actual JWT/authentication support is confirmed
   against its current documentation before being implemented — the
   chosen mechanism is explicitly verified, not guessed, and any
   uncertainty is reported rather than silently resolved (per
   `agents/backend.md`'s external-integration rule and
   `JWT-VERIFICATION-INCIDENT.md`'s precedent).
3. A `record_update` tool accepts `goal_id`, a required `content` summary,
   and an optional `transcript`, verifies the caller's Supabase JWT using
   the same verification logic as the existing REST endpoints, and stores
   a new update row with `user_id` always set from the verified JWT
   subject — never from caller-supplied input. The tool makes no
   assumption about whether the AI or the user originated the underlying
   suggestion — it only records the agreed outcome the caller provides.
   The tool does not accept a `source` parameter at all — every row it
   inserts is always `source = 'coaching_update'`, the table's default;
   there is no way to call this tool and produce a `checkin` row.
4. Calling `record_update` with a `goal_id` that doesn't exist, isn't
   owned by the caller, or is soft-deleted fails (no row is inserted) —
   enforced by RLS's `updates_insert_own` policy.
5. A missing, malformed, or expired JWT is rejected before any tool logic
   runs or any database call is made.
6. `record_update` calls are rate-limited, consistent with the existing
   REST endpoints.
7. The `record_update` tool's MCP-exposed description (the text the
   calling LLM reads to decide when/how to use the tool) explicitly
   instructs the caller to: (a) call this tool only once the AI and user
   have settled on something concrete, not after every message in the
   conversation, and (b) write a concise summary into `content`, not the
   raw conversation. This is the only mechanism available to influence
   the calling LLM's behavior, since the backend itself cannot detect
   "an agreement was reached" — verify the description text is present
   and says this, not just that the tool exists.

## Requirements implemented

- Requirement 4, 5, 7, 8

## Agents likely needed

- [ ] frontend
- [x] backend
- [ ] infrastructure

## Status

- [ ] Implemented
- [ ] Tested
- [ ] Committed
