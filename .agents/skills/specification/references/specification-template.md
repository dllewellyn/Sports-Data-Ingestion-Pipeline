# Specification template

This is the **exact output format** for `specs/NNN-<slug>/spec.md`. Copy the skeleton below and fill
every **mandatory** section; include **optional** sections only when relevant (remove them entirely
when they don't apply — don't leave "N/A"). Keep heading text and order unchanged: the structural
linter (`_shared/spec-helpers/validate-spec.py`) and downstream phases key off these headings.

The machine-readable threading contract is **not** in this file — it lives in `.specify/feature.json`
(`feature_directory`), written by the specification skill. This document is the human-and-test-facing
spec.

> **Domain exception.** Stay outcome-focused and technology-agnostic *unless the domain vocabulary is
> itself the requirement*. For a data project, outcomes are naturally expressed in domain terms —
> bronze/silver/gold layers, Parquet artifacts, partitioning, encoding (e.g. latin-1), schema/frame
> validation, idempotency. Use that vocabulary where it defines the outcome; still avoid prescribing
> internal code design (classes, function names, library choices).

---

```markdown
# Feature Specification: [FEATURE NAME]

**Feature directory**: `specs/NNN-<slug>/`
**Created**: YYYY-MM-DD
**Status**: Draft   <!-- Draft | Clarified | Planned | Implemented -->
**Input**: "<the free-text feature description this spec was generated from>"

## User Scenarios & Testing *(mandatory)*

<!--
  User stories are PRIORITISED user journeys (P1, P2, P3…), P1 most critical. Each must be
  INDEPENDENTLY TESTABLE — implementing just one still yields a viable slice that delivers value.
  Acceptance scenarios are BDD Given/When/Then and must describe OBSERVABLE outcomes you can assert
  (e.g. "a bronze Parquet file is written under football_main/ partitioning", not "the data is
  processed").
-->

### User Story 1 - [Brief title] (Priority: P1)

[The journey in plain language.]

**Why this priority**: [value / why it ranks here]

**Independent Test**: [how this slice can be tested on its own and what value it proves]

**Acceptance Scenarios**:

1. **Given** [context], **When** [action], **Then** [observable outcome]
2. **Given** [context], **When** [action], **Then** [observable outcome]

---

### User Story 2 - [Brief title] (Priority: P2)

[…repeat the shape above. Add as many stories as the feature needs, each prioritised.]

---

### Edge Cases

<!-- Boundaries and unhappy paths with EXPECTED behaviour, not just the risk. A table works well. -->

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | [condition: bad/empty/malformed input, encoding, partial failure, re-run/idempotency, limits, upstream down] | [what the system must do] |

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST [specific, testable capability]
- **FR-002**: Users MUST be able to [key interaction]
<!-- Mark only genuinely blocking unknowns, max 3 total across the whole spec: -->
- **FR-00N**: System MUST [capability] [NEEDS CLARIFICATION: specific question]

### Key Entities *(include only if the feature involves data)*

- **[Entity]**: [what it represents, key attributes/relationships — no implementation detail]

## Success Criteria *(mandatory)*

<!-- Measurable, technology-agnostic outcomes. Each verifiable without knowing the implementation. -->

- **SC-001**: [measurable outcome, e.g. "all valid rows from a source file land in the silver model and pass its tests"]
- **SC-002**: [measurable outcome]

## Constraints & things to be aware of *(mandatory)*

<!--
  What an implementer must respect. Pull relevant principles from .specify/memory/constitution.md
  (the canonical governance source) and any project CLAUDE.md / ARCHITECTURE.md if present:
  dependencies on other features; non-functional bounds (volume, latency, throughput); data
  contracts, formats, encodings, partitioning, layer (bronze/silver/gold), schema evolution,
  idempotency; security/privacy. Do not contradict the constitution — reference it.
-->

- [Constraint or dependency, referencing the governing constitution principle where relevant]

## Assumptions *(mandatory)*

<!-- Everything taken as true (reasonable defaults chosen where the description was silent). Visible so it can be challenged. -->

- [Assumption / chosen default]

## Open Questions *(mandatory)*

<!--
  Anything unresolved. Promote any [NEEDS CLARIFICATION] marker that BLOCKS implementation to here
  and label it **BLOCKER**. If none, write "None."
-->

- [Open question] — **BLOCKER** *(remove the BLOCKER label if it doesn't block build)*
```
