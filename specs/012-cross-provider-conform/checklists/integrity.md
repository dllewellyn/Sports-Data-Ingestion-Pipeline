# Integrity & Scope Requirements-Quality Checklist: Cross-Provider Conform

**Purpose**: Requirements-quality gate ("unit tests for the English") focused on the four
highest-value dimensions for THIS feature — a structural refactor establishing cross-provider
resolve-or-mint with referential-integrity invariants, a new `league_aliases` seed, and a package
relocation. It validates that the spec's requirements are **testable/measurable**, that **scope is
bounded** (the football-data OUT line and the ESPN-anchor invariant), that the **four-canonical-table
integrity story is complete**, and that there is **no ambiguity or internal contradiction**.
This tests the requirements themselves, NOT the implementation.

**Created**: 2026-07-01
**Feature**: [spec.md](../spec.md)
**Focus dimensions**: Testability/Measurability · Scope Boundedness · Four-table Integrity Completeness · Ambiguity/Contradiction
**Companion**: [requirements.md](./requirements.md) (general spec-quality gate authored at specification time)

## Testability & Measurability

- [x] CHK001 Is every functional requirement (FR-001…FR-016) written as a single objectively
  pass/fail `MUST`/`MUST NOT` statement rather than an aspiration? [Clarity, Spec §FR-001..FR-016]
- [x] CHK002 Are the success criteria (SC-001…SC-008) each measurable with a concrete observable —
  a count (0 orphaned FKs, exactly 1 row, 1 vs 2 matches), a gate verdict (tests pass/fail), or a
  text-absence assertion — rather than a subjective quality? [Measurability, Spec §SC-001..SC-008]
- [x] CHK003 Does each user story carry an **Independent Test** phrased as an executable
  observation (seed X, run `dbt build --select …`, assert green/red)? [Acceptance Criteria, Spec §US1..US5]
- [x] CHK004 Is the "these tests genuinely bite" property specified as a requirement (a mutation that
  SHOULD turn the FK/link test red is called out), not merely "tests exist"? [Measurability, Spec §US4 IT, §SC-005, §E8]
- [x] CHK005 Is the de-dup / same-`match_id` guarantee stated as a verifiable parity check between the
  shared Python resolver and the dbt path, rather than an untestable "should agree"? [Measurability, Spec §SC-003, §FR-007, §E8]
- [x] CHK006 Is the "pure move, no behaviour change" requirement (US3) given an objective criterion
  (byte-for-byte-equivalent resolved-links/additions/exceptions output for identical input)? [Measurability, Spec §US3 AC3, §SC-004]

## Scope Boundedness

- [x] CHK007 Is the football-data OUT line unambiguous — that this feature scaffolds football-data to
  the shared contract but does NOT implement its record-matching/minting engine? [Scope, Spec §US5, §FR-010, §Assumptions 1]
- [x] CHK008 Is the scaffolded-not-implemented boundary made testable (US5 IT asserts `dbt build`
  stays green with **zero** football-data additions and the module declares the interface as a
  documented placeholder)? [Measurability+Scope, Spec §US5 IT/AC1/AC2, §FR-010]
- [x] CHK009 Is the ESPN-anchor invariant bounded and explicit — `league_id` stays `md5(league_slug)`,
  `league_aliases` is **additive/recording** and never redefines ESPN identity, and ESPN's
  `int_league`/`int_match`/`int_espn_*_link` output MUST be unchanged? [Scope+Consistency, Spec §FR-015, §Constraints (ESPN-anchored)]
- [x] CHK010 Is the resolve-or-mint scope bounded so it does NOT become resolve-or-**always**-mint —
  i.e. minting is for authoritative/override decisions and a no-match still routes to the exceptions
  queue, never auto-mint? [Scope, Spec §E6, §Constraints (exceptions queue), §Key Entities (Exceptions queue)]
- [x] CHK011 Are the explicitly-excluded items enumerated (T-60 not rewritten; no backward-compat
  shim / re-export from the old path; no auto-learn write-back into either seed)? [Scope, Spec §Assumptions 7, §FR-006, §FR-015]
- [x] CHK012 Is the "which providers" surface bounded — ESPN conforms in SQL (not forced through the
  additions convention), Python providers use the four-file convention — with the ESPN-in-SQL choice
  recorded rather than left open? [Scope+Ambiguity, Spec §OQ2, §Assumptions 2]

## Four-Canonical-Table Integrity Completeness

- [x] CHK013 Does a requirement cover **all four** canonical tables (`int_team`, `int_league`,
  `int_season`, `int_match`) gaining a provider-additions union — not just `int_match`? [Completeness, Spec §FR-003, §Assumptions 4]
- [x] CHK014 Is the full minted-match chain requirement complete — a mint of a match MUST emit the
  team-, season-, AND league-additions it references, with an explicit "no code path mints a match
  without its complete season→league→team chain"? [Completeness, Spec §FR-001, §US1]
- [x] CHK015 Are all four FK `relationships` invariants named as requirements
  (`int_match.home_team_id`/`away_team_id` → `int_team`; `int_match.season_id` → `int_season`;
  `int_season.league_id` → `int_league`) and required to stay green with minted rows present? [Completeness, Spec §FR-004, §SC-001]
- [x] CHK016 Are the `unique`/`not_null` invariants on each canonical id specified so cross-provider
  minting cannot introduce duplicate clubs/competitions (dedup to one row per id)? [Completeness, Spec §FR-004, §US2 AC5, §E3]
- [x] CHK017 Is the missing-additions-file behaviour completely specified — all four files
  bootstrap-written empty because `read_parquet` errors on a missing file (NOT `try_read_parquet`)? [Completeness+Edge Case, Spec §FR-016, §E4]
- [x] CHK018 Is the Matchbook link-table FK-test gap completely closed — BOTH
  `int_matchbook_team_link.team_id` → `int_team` and `int_matchbook_league_link.league_id` →
  `int_league` tests required (Spec 010 OQ3)? [Completeness, Spec §FR-009, §US4]
- [x] CHK019 Is the resolution data-source path complete for RESOLVE (not just mint) — new
  `canonical_league_export`/`canonical_season_export` external-Parquet models added so Python can
  resolve leagues/seasons without a DuckLake connection? [Completeness, Spec §FR-011, §Clarifications Q2]
- [x] CHK020 Is the seed-resolution + `canonical_match_id` derivation required to be a single shared
  helper used by every Python provider AND to agree with ESPN's SQL, so identity is complete and
  consistent across all four tables? [Completeness+Consistency, Spec §FR-005, §FR-007, §E8]

## Ambiguity & Contradiction

- [x] CHK021 Is the `league_aliases` natural key unambiguous — composite `(provider, provider_key)`
  is `unique`; `league_id` is intentionally NON-unique; `league_id`/`provider_key` `not_null`? [Ambiguity resolved, Spec §FR-015, §Clarifications Q1]
- [x] CHK022 Is the minted-league identity formula unambiguous and free of the prior contradiction —
  `coalesce(league_aliases.league_id_for(...), mint_provider_scoped(...))` replaces the bogus
  `md5('matchbook_football')` constant that could never equal an ESPN `league_id`? [Contradiction resolved, Spec §FR-012, §SC-008, §US2]
- [x] CHK023 Are the two dbt namings (Dagster `AssetKey(["intermediate","int_x"])` vs node selector
  `intermediate.int_x`) disambiguated so the conform-asset re-home does not silently drop a lineage
  edge? [Ambiguity, Spec §Constraints (AssetKey), §FR-008]
- [x] CHK024 Is the stale-docs contradiction surfaced and required to be corrected — the actual tree
  is `models/{staging,intermediate,marts}/int_*` (Spec 011), while CLAUDE.md/ERD.md/ARCHITECTURE.md
  still say `models/silver/canonical/`? [Contradiction, Spec §Constraints (model tree), §FR-014, §SC-007]
- [x] CHK025 Is the unseen-league graceful-degrade path free of contradiction with the FK invariant —
  a provider-scoped `league_id` is minted AND emitted to the league/season additions so the chain
  stays green (E9), and a broken seed mapping (E10) is surfaced, not papered over? [Consistency, Spec §E9, §E10, §FR-004]
- [x] CHK026 Are the blank-name and seed-split edge cases free of contradiction with the `not_null`
  invariant — a blank parsed name routes to exceptions (never a null-name addition), and a
  double-alias seed error is a seed-curation concern that keeps `unique` intact? [Consistency+Edge Case, Spec §E5, §E7]
- [x] CHK027 Are there zero `[NEEDS CLARIFICATION]` markers and zero declared blockers, with the
  three remaining Open Questions confirmed plan-level (module path, ESPN-in-SQL, Matchbook
  `provider_key` format) rather than requirement-blocking? [Ambiguity, Spec §Open Questions, §Clarifications]

## Notes

- **Gate outcome: PASS.** No CRITICAL requirements-quality item fails. All 27 items validate against
  `spec.md` at HEAD (2026-07-01, Status: Draft).
- **Critical dimensions checked, all green:**
  - *Untestable/ambiguous requirement* → none (CHK001–CHK006, CHK021–CHK027).
  - *Unbounded scope* → none; football-data OUT (CHK007–CHK008), ESPN-anchor additive invariant
    (CHK009), resolve-or-mint ≠ resolve-or-always-mint (CHK010) are all explicitly bounded and testable.
  - *Internal contradiction* → none; the `md5('matchbook_football')` bug (CHK022) and the stale
    `models/silver/canonical/` docs (CHK024) are surfaced as contradictions the spec resolves/requires-fixing,
    not left latent.
  - *Missing referential-integrity guarantee* → none; the four-table union (CHK013), full chain mint
    (CHK014), all four FK relationships (CHK015), uniqueness (CHK016), missing-file bootstrap (CHK017),
    and Matchbook link-table FK tests (CHK018) are all specified.
- **One non-blocking observation (does not fail any item):** FR-015 asserts the canonical `league_id`
  is `md5(league_slug)` and calls this "mirroring how `team_aliases` maps names onto
  `md5(lower(canonical_name))`". The mirror is imperfect — league identity keys on the slug, team
  identity on the lowercased canonical name — but both anchor identity on an ESPN-derived surrogate,
  so the requirement is unambiguous and testable as written (CHK009/CHK021 pass). Worth a one-line
  clarification of the `provider_key` for ESPN rows (`league_slug`) vs the derived `league_id` at plan
  time; captured as Spec §OQ3-adjacent, not a spec defect.
