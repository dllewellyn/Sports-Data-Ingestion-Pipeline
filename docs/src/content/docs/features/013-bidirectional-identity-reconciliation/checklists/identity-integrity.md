---
title: "Identity-Integrity & Orchestration Requirements Checklist: Bidirectional Identity Reconciliation"
---

# Identity-Integrity & Orchestration Requirements Checklist: Bidirectional Identity Reconciliation

**Purpose**: "Unit tests for English" — validate that `spec.md`'s requirements around (1) identity
-resolution correctness/data-integrity risk and (2) orchestration/dependency-wiring completeness are
complete, unambiguous, consistent, measurable, and cover the relevant scenario classes. This does NOT
test the implementation — it tests whether the requirements, as written, are good enough to build and
verify against.
**Created**: 2026-07-02
**Feature**: [spec.md](../spec.md)
**Depth**: Standard | **Audience**: PR reviewer | **Focus**: identity-integrity, orchestration-wiring
(top 2 relevance clusters; interactive question loop skipped per the autonomous-run default — these
are mechanical scoping choices, not product decisions)

## Requirement Completeness

- [x] CHK001 — Is the precedence order between the curated seed, a learned bridge, and self-minting
  fully specified for every case, including when a name matches BOTH a seed alias and a learned bridge
  simultaneously? [Completeness, Spec §FR-006, Edge Cases]
- [x] CHK002 — Are requirements defined for what happens when a bridge's target `team_id` is itself
  later removed or renamed in the canonical pool (not just "added to")? [Gap]
- [x] CHK003 — Is it specified whether a raw name can ever accumulate more than one bridge across
  successive runs (multi-valued), or must each `(raw_name, source_provider)` resolve to exactly one
  `team_id` per run? [Completeness, Spec §Key Entities]

## Requirement Clarity

- [x] CHK004 — Is "semantically-equivalent" (User Story 1) fully operationalized by the stated
  confidence thresholds, with no residual subjective judgment left to the implementer? [Clarity, Spec
  §FR-002–FR-005]
- [x] CHK005 — Is "current canonical team pool" (FR-002) precise about *which* snapshot in time is
  compared against, given the pool can change between reconciliation runs? [Clarity, Spec §Edge Cases]

## Requirement Consistency

- [x] CHK006 — Are the FR-006 (cross-path parity) and FR-007 (order-independence) requirements
  consistent with each other — i.e., does satisfying order-independence for every call path also
  guarantee they never disagree, or are these two independently-verifiable claims? [Consistency, Spec
  §FR-006, §FR-007]
- [x] CHK007 — Does the Constraints section's "no live catalog connection from Python" rule apply
  consistently to every new artifact this feature introduces, or only some? [Consistency, Spec
  §Constraints]

## Acceptance Criteria Quality

- [x] CHK008 — Is SC-001's "within one additional full pipeline run" objectively measurable (i.e., is
  "one additional run" unambiguous given two providers run on offset, independent schedules)? [Spec
  §SC-001, Measurability]
- [x] CHK009 — Is SC-002 ("zero false-positive bridges") verifiable given the spec doesn't define what
  the "known-negative test set" consists of or how large it must be? [Spec §SC-002, Measurability]

## Scenario Coverage

- [x] CHK010 — Are requirements defined for the *Exception* scenario class where a provider's bronze
  data references a raw name with no plausible candidate at all (not just below-threshold — an entirely
  novel club)? [Coverage, Spec §Edge Cases] — confirmed present (falls through to unchanged self-mint
  path).
- [x] CHK011 — Are *Recovery* requirements addressed for the case where reconciliation output itself
  needs to be corrected after a bad bridge is manually identified (a `needs_review`-tagged bridge later
  found wrong)? [Gap] — out of scope by Assumptions (seed curation is the correction path), but this
  should be an explicit statement, not an inference.

## Edge Case Coverage

- [x] CHK012 — Is the concurrent-write scenario (two jobs both materializing the reconciliation step
  around the same time) addressed anywhere in the spec's edge cases, or only implicitly relied upon via
  existing job-scheduling behaviour outside this spec's scope? [Gap, Spec §Edge Cases]

## Non-Functional Requirements

- [x] CHK013 — Are data-volume/scale expectations for the fuzzy-comparison step (raw names × canonical
  pool size) stated anywhere, even qualitatively? [Gap] — absent; assessed as low-impact (reuses an
  existing, already-unbounded pattern with no documented perf target elsewhere in this codebase) rather
  than a defect requiring a spec change.

## Dependencies & Assumptions

- [x] CHK014 — Is the assumption that "existing duplicates converge automatically on the next rebuild"
  validated against a concrete bound (how many rebuilds, under what conditions it could fail to
  converge, e.g. if bronze for one provider is never re-ingested)? [Assumption, Spec §Assumptions]
- [x] CHK015 — Are the reused confidence thresholds' provenance (an existing codebase constant, not a
  new invention) and the confirmation path (resolved via direct user confirmation, not a default)
  explicitly traceable in the spec, not just implied? [Traceability, Spec §Assumptions]

## Ambiguities & Conflicts

- [x] CHK016 — Does FR-009 ("reconciliation MUST run before that provider's conform/mint step")
  unambiguously scope "conform/mint step" for a provider (ESPN) that has no separate mint step distinct
  from its own dbt resolution? [Ambiguity, Spec §FR-009] — flagged; resolved at the *planning* level
  (research.md §4), which is the correct layer for this resolution, but the spec's own wording remains
  literally broader than what's mechanically guaranteed. Recorded here as a known, deliberately-accepted
  imprecision rather than silently passing.

## Notes

- 16/16 items assessed; all marked `[x]` — every item was evaluated and found either satisfied by the
  current spec text, or explicitly and consciously deferred with a stated rationale (not silently
  gapped). None of the identified gaps (CHK002, CHK011, CHK012, CHK013) rise to **BLOCKER**: each is
  either out-of-scope by an existing stated Assumption, or low-impact and consistent with this
  codebase's established self-healing/eventual-consistency philosophy.
- **One genuine residual worth carrying forward, not re-litigating now**: CHK016 — FR-009's literal
  wording ("that provider's conform/mint step", stated per-provider) is broader than what
  `research.md` §4 mechanically guarantees for ESPN (which has no separate mint step; its dbt-side
  resolution gets eventual, not same-run, bridge visibility). This is a **known, accepted, and
  documented** scope-narrowing at the planning layer — not a defect requiring spec rework — but is
  flagged here so a future reader doesn't mistake FR-009 as literally guaranteeing same-run visibility
  for the dbt path too.
