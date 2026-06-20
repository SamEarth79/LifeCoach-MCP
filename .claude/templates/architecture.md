# Architecture: {{FEATURE_NAME}}

> Filled in by `draft.md` during `/design`, informed by `analysis.md`.
> Describes the technical approach before any code is written.

## Approach

{{1-2 paragraphs describing the overall technical approach for this
feature.}}

## Components touched

{{Explicitly list which parts of the system this feature adds to or
modifies.}}

- **Frontend**: {{components/pages touched or added, or "none"}}
- **Backend**: {{services/routes/modules touched or added, or "none"}}
- **Infrastructure**: {{config/deployment/CI changes needed, or "none"}}

## Data flow

{{Describe how a request/action moves through the system for this feature —
sequence of steps from user action to response/persistence.}}

1.
2.
3.

## Data model changes

{{New or modified schema/tables/models, with fields and types. State "none"
if this feature requires no data model changes.}}

## Key decisions

{{Notable technical decisions and why this approach was chosen over
alternatives. Only include decisions that weren't obvious/default — skip
this section's entries if there was nothing to decide.}}

- **Decision**: {{what was decided}}
  **Rationale**: {{why, including alternatives considered}}
