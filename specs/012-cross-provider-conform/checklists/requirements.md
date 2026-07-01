# Requirements Checklist: Cross-Provider Conform — Symmetric Resolve-or-Mint

**Purpose**: Quality gate for `specs/012-cross-provider-conform/spec.md` — verifies the spec is
outcome-focused, complete, testable, and consistent with the constitution before planning.
**Created**: 2026-07-01
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] CHK001 No implementation detail beyond the data-domain exception (dbt models, Parquet, seed
  resolution, `canonical_match_id` are domain vocabulary that *defines* the outcome — permitted; no
  class/function-design prescriptions).
- [x] CHK002 Focused on user/domain value (referential integrity, no duplicate clubs, legible
  cross-provider conform) rather than code mechanics.
- [x] CHK003 All mandatory sections present (User Scenarios, Requirements, Success Criteria,
  Constraints, Assumptions, Open Questions) in the required order.
- [x] CHK004 Metadata preamble present (Feature directory, Created, Status, Input).

## Requirement Completeness

- [x] CHK005 Every functional requirement (FR-001…FR-014) is a single testable `MUST` statement.
- [x] CHK006 Success criteria (SC-001…SC-007) are measurable and technology-agnostic (counts of
  orphans/duplicates/matches, gate pass/fail), verifiable without knowing internal design.
- [x] CHK007 Each user story is prioritised (P1/P1/P2/P2/P3) and independently testable with a stated
  Independent Test.
- [x] CHK008 Happy path, rule variations (seed-hit vs unseen, both-providers-same-fixture), and failure
  modes (orphan team, blank name, no-match) all have acceptance scenarios with observable outcomes.
- [x] CHK009 Edge cases (E1–E8) state expected behaviour, not just the risk.
- [x] CHK010 Scope is bounded: football-data conform explicitly scaffolded-not-implemented; T-60 logic
  explicitly not rewritten; auto-mint-on-every-no-match explicitly rejected.
- [x] CHK011 Dependencies and assumptions identified (Specs 002/006/010/011; `team_aliases` +
  new `league_aliases` seeds; bronze-data-present caveat; neutral-location choice).
- [x] CHK012 Zero `[NEEDS CLARIFICATION]` markers and zero blockers — the league-identity decision is
  resolved (user chose the `league_aliases` seed; encoded as FR-002/FR-012/FR-015). Remaining Open
  Questions are non-blocking plan-level details.

## Feature Readiness

- [x] CHK013 No constitution principle contradicted; contradictions/knock-on effects surfaced (the
  `md5('matchbook_football')` league bug is now fixed structurally via FR-012/FR-015; the full-chain
  integrity knock-on — int_league/int_season must also accept minted rows — is captured in US1/FR-001/
  FR-003/FR-004; the stale `models/silver/canonical/` docs are flagged for correction).
- [x] CHK014 `.specify/feature.json` points at `specs/012-cross-provider-conform`.
- [x] CHK015 `validate-spec.py` passes on `spec.md`.
- [x] CHK016 Beneficial objective-linked changes the user did not raise are included (Matchbook link-
  table FK tests — Spec 010 OQ3; the minted-league identity bug — FR-012/OQ1; the four-doc ripple).

## Notes

- Structural linter result: `OK … 0 warning(s)`, exit 0.
- Revised after review: OQ1 (minted-match league identity) resolved by the user's decision to add a
  human-curated `league_aliases` seed mirroring `team_aliases` (ESPN stays the canonical anchor; other
  providers' league keys map onto `md5(league_slug)`). Knock-on folded in: full-chain integrity — the
  provider-additions + `read_parquet` UNION pattern now applies to ALL FOUR canonical tables
  (`int_match`/`int_team`/`int_season`/`int_league`), each with its FK relationships test kept green by
  fixing the data path, never by weakening tests. Corrected the `read_parquet`-errors-on-missing-file
  fact (all four additions files bootstrap-written empty; FR-016). Zero blockers remain.
