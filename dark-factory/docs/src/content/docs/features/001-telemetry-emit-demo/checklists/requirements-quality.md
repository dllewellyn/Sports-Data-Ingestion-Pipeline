---
title: "Requirements-Quality & Testability Checklist: Telemetry Emit Demo"
---

# Requirements-Quality & Testability Checklist: Telemetry Emit Demo

**Purpose**: Unit-tests-for-English gate on `spec.md` — validates that the requirements are clear, complete, consistent, measurable, and testable before planning. Focus: requirements clarity + testability for a small CLI telemetry emitter.
**Created**: 2026-06-30
**Feature**: [spec.md](../spec.md)

<!--
Focus areas (recorded, non-interactive): requirements clarity + testability (top-2 relevance clusters for a small CLI emitter).
Depth: Standard. Audience/timing: Reviewer at PR / pre-plan gate.
This file is distinct from checklists/requirements.md (the specification skill's 16-item content-quality list); it is not a duplicate and does not replace it.
-->

## Requirement Completeness

- [x] CHK001 Are requirements defined for all three signal outcomes — both emitted, span-only failure, event-only failure? [Completeness, Spec §FR-008, §E2]
- [x] CHK002 Is the behaviour with no active feature-run context (`temp/telemetry/current.json` absent) specified as a requirement, not only as an edge case? [Completeness, Spec §E6, Assumptions]
- [x] CHK003 Are the required stdout contents enumerated (span name, event body, label, per-signal destination)? [Completeness, Spec §FR-007]
- [x] CHK004 Is the test obligation (collector-free pytest covering label propagation, default label, non-zero-on-failure) stated as a requirement? [Completeness, Spec §FR-011]
- [x] CHK005 Are the dependencies and reused surfaces (emit.py `send_span`/`send_logs`, endpoint resolution, `FEATURE_OTLP_HTTP_ENDPOINT`) documented? [Completeness, Spec §FR-003, §FR-009]

## Requirement Clarity

- [x] CHK006 Is "searchable in Grafana" given a concrete model (span attribute for Tempo, structured metadata for Loki under the documented label model) rather than left vague? [Clarity, Spec §FR-004, Constraints]
- [x] CHK007 Is "sensible / recognisable default label" pinned to a stable, documented value (deferred to build-time but constrained in §Assumptions)? [Clarity, Spec §FR-005, Assumptions]
- [x] CHK008 Is "exactly one span and exactly one log event" unambiguous (cardinality stated, no multi-span tree)? [Clarity, Spec §FR-002]
- [x] CHK009 Is the distinction between stdout (success reporting) and stderr (failure reporting) clearly assigned? [Clarity, Spec §FR-007, §FR-008]

## Requirement Consistency

- [x] CHK010 Do the success criteria (SC-001..SC-005) map one-to-one onto functional requirements without conflict? [Consistency, Spec §SC, §FR]
- [x] CHK011 Is the tension between emit.py's fire-and-forget exit-0 design and FR-008's non-zero-on-failure resolved consistently (boolean-return inspection) rather than left contradictory? [Consistency, Spec §Constraints, §Open Questions]
- [x] CHK012 Are the endpoint references consistent (OTLP/HTTP `14318` reused, not a new variable, distinct from gRPC `14317`)? [Consistency, Spec §Constraints, §FR-009]

## Acceptance Criteria Quality (Measurability)

- [x] CHK013 Can SC-001 (one matching span in Tempo + one matching event in Loki, both labelled) be objectively verified? [Measurability, Spec §SC-001]
- [x] CHK014 Is the exit-code contract objectively checkable (0 iff both emitted; non-zero otherwise)? [Measurability, Spec §FR-008, §SC-002, §SC-003]
- [x] CHK015 Is SC-004 (zero third-party runtime dependencies) objectively verifiable? [Measurability, Spec §SC-004, §FR-010]
- [x] CHK016 Does SC-005 define genuinely red-able tests (a label-propagation test and a failed-emission-exit test that fail when the behaviour is wrong)? [Measurability, Test-First, Spec §SC-005, §FR-011]

## Scenario & Edge-Case Coverage

- [x] CHK017 Are primary (P1 labelled run), alternate (P2 default label), and exception (P2 failure) scenario classes all covered by requirements? [Coverage, Spec §US1-3]
- [x] CHK018 Is the empty/whitespace-only `--label` input given a defined rejection behaviour? [Edge Case, Spec §E4, §FR-006]
- [x] CHK019 Is the partial-failure case (one signal succeeds, one fails) addressed in requirements, not just narrative? [Coverage, Exception Flow, Spec §E2, §FR-008]
- [x] CHK020 Is the endpoint-override path (`FEATURE_OTLP_HTTP_ENDPOINT`) covered as a requirement? [Coverage, Spec §E5, §FR-009]

## Scope, Dependencies & Assumptions

- [x] CHK021 Is scope bounded against feature creep (no metrics/dashboards/multi-span trees/extra config beyond `--label`)? [Scope, Spec §Constraints]
- [x] CHK022 Are the build-time-deferred strings (default label, span name, metadata key) recorded as explicit assumptions rather than left as silent gaps? [Assumption, Spec §Assumptions]
- [x] CHK023 Is the assumption that manual Grafana lookup (not automated query-back) verifies SC-001 stated and justified? [Assumption, Spec §Assumptions]
- [x] CHK024 Is the reuse constraint (no duplicated OTLP/HTTP code, no faked emission outside fixtures) tied to a governing principle? [Traceability, Spec §Constraints, Constitution II]

## Notes

- Items reference spec sections or carry `[Gap]`/`[Ambiguity]`/`[Assumption]`/`[Conflict]` markers; >80% traceability satisfied.
- Build-time-deferred exact strings (default label, span name, metadata key) are evaluated as *documented assumptions* (CHK007, CHK022), not as clarity gaps — per the spec's deliberate deferral in §Assumptions.
