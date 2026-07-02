---
title: "Feature Specification: Bidirectional Identity Reconciliation"
---

# Feature Specification: Bidirectional Identity Reconciliation

**Feature directory**: `specs/013-bidirectional-identity-reconciliation/`
**Created**: 2026-07-02
**Status**: Draft
**Input**: "Bidirectional identity reconciliation between ESPN and Matchbook conform pipelines. When either provider mints a team/match under a name-spelling the other provider would resolve differently, bridge the two names to one canonical id — in both directions (not just Matchbook→ESPN, which is the currently-broken direction)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A team minted by either provider resolves to one canonical id, regardless of mint order (Priority: P1)

Today, when a provider's conform step encounters a team name that has no seed alias, it mints a
brand-new canonical team of its own. If ESPN mints "Manchester United" and Matchbook independently
mints "Man Utd" for the same real-world club, the canonical layer ends up with two teams, two ids,
and — because match identity is derived from team id — two separate canonical matches for what is
actually one fixture. This happens in whichever order the providers first see the name, so fixing
only the Matchbook→ESPN direction (as exists today) leaves the reverse direction (ESPN mints first,
Matchbook mints a different spelling later) still broken.

**Why this priority**: This is the core defect the feature exists to fix. Without it, downstream
consumers (gold layer, notebooks, dbt tests) see duplicated teams and duplicated matches whenever two
providers spell the same club differently, silently corrupting match counts and team-level analytics.

**Independent Test**: Seed bronze data so ESPN mints a team under name A in one pipeline run, then
Matchbook data referencing the same club under a differently-spelled name B arrives in a later run.
After reconciliation runs, the next full rebuild resolves name B to the SAME canonical team_id minted
for name A — verified by comparing team_id values and by asserting only one row exists for that club
in the canonical team model. The reverse order (Matchbook first, ESPN second) delivers the same
result, since this is the direction not covered by the reverse-only checks.

**Acceptance Scenarios**:

1. **Given** ESPN has already minted a canonical team under name A (no seed alias existed), **When**
   Matchbook bronze data later contains a differently-spelled but semantically-equivalent name B for
   the same club, scoring at or above the high-confidence threshold against name A, **Then** the next
   full pipeline rebuild resolves name B to the same canonical team_id as name A, and the canonical
   team model contains exactly one row for that club.
2. **Given** Matchbook has already minted a canonical team under name B (no seed alias existed),
   **When** ESPN bronze data later contains name A for the same club, scoring at or above the
   high-confidence threshold, **Then** the next full pipeline rebuild resolves name A to the same
   canonical team_id already minted for name B (the previously-broken direction), and the canonical
   team model contains exactly one row for that club.
3. **Given** a canonical match was minted twice — once via each provider's own spelling, as two
   distinct match_ids — **When** the team-name bridge for that club is learned, **Then** the next full
   pipeline rebuild converges the two match rows onto a single match_id, with no manual cleanup step.

---

### User Story 2 - Ambiguous or low-confidence name pairs are never silently merged (Priority: P2)

Not every spelling difference should trigger a bridge. Two entirely different real-world teams that
happen to have similar names must never be merged into one canonical identity — that kind of error
corrupts historical data permanently and is hard to detect after the fact. The system needs a
consistent, auditable policy for what counts as confident enough to bridge automatically versus what
is recorded for later manual review.

**Why this priority**: Protects data correctness. A false-positive merge is far more costly than a
leftover duplicate (which is merely noisy, not wrong), so the confidence policy is the safety
mechanism for User Story 1.

**Independent Test**: Feed a raw name that scores below any candidate's medium-confidence threshold
against the canonical team pool, and separately a raw name that scores exactly tied between two
different candidates. Confirm neither produces an automatic bridge, and both leave their originating
provider free to self-mint a new canonical team as it does today.

**Acceptance Scenarios**:

1. **Given** a raw team name whose best match against the canonical team pool scores at or above the
   high-confidence threshold, **When** reconciliation runs, **Then** a bridge is recorded and applied
   automatically (equivalent to the codebase's existing `auto_confirmed` outcome for high-confidence
   fuzzy matches).
2. **Given** a raw team name whose best (single) match scores at or above the medium-confidence
   threshold but below the high-confidence threshold, **When** reconciliation runs, **Then** a bridge
   is recorded and applied, tagged for later human review (equivalent to the codebase's existing
   `needs_review` outcome), so it takes effect immediately but remains auditable.
3. **Given** a raw team name whose best match scores below the medium-confidence threshold, **When**
   reconciliation runs, **Then** no bridge is recorded; the name is left for its provider's normal
   self-mint path, unchanged from current behaviour.
4. **Given** a raw team name that scores above the medium-confidence threshold against two or more
   different canonical teams with an exactly tied top score, **When** reconciliation runs, **Then** no
   bridge is recorded (an ambiguous tie is treated the same as "below threshold" — it is never
   auto-resolved by guessing).

---

### User Story 3 - Every automatic bridge is traceable (Priority: P3)

Because bridges directly affect canonical identity, anyone auditing the canonical team pool (or
investigating an apparent duplicate/merge) needs to see, for any bridged name, which raw name was
matched, which provider it came from, what canonical team it was bridged to, the confidence score, and
which method produced the decision.

**Why this priority**: Supports trust and debuggability of an automated identity-merging mechanism,
but is not itself required for the core duplicate-elimination behaviour to work.

**Independent Test**: After a reconciliation run that produces at least one high-confidence and one
medium-confidence bridge, inspect the recorded output and confirm every bridge row carries the raw
name, resolved team_id, source provider, confidence score, and match method/tag.

**Acceptance Scenarios**:

1. **Given** reconciliation has produced one or more bridges in a run, **When** the output is
   inspected, **Then** every bridge is traceable to its raw name, source provider, resolved
   canonical team_id, confidence score, and match method (`auto_confirmed` or `needs_review`).

---

### Edge Cases

- **Heavy abbreviations below threshold** (e.g. "Man Utd" vs. "Manchester United", which scores below
  even the medium-confidence threshold): stays unresolved by this feature. Expected behaviour: the
  providers continue to mint separate canonical teams, exactly as today; closing this gap is the
  responsibility of manual `team_aliases.csv` seed curation, a separate and parallel effort.
- **Canonical team pool changes between reconciliation and the next conform run** (a new team is
  minted by a third pipeline step after reconciliation already ran): expected behaviour is that this
  is not treated as an error — the affected name simply isn't bridged until the *following*
  reconciliation run sees the updated pool, since conform reprocesses all bronze data from scratch
  every cycle and self-heals within one or two runs.
- **A name is already covered by the curated `team_aliases` seed**: expected behaviour is that the
  seed alias always takes precedence; reconciliation only considers names with no existing seed match
  (mirroring how learned aliases must never contend with curated seed data).
- **The same raw name appears with two different confidence outcomes across two different runs**
  (e.g. the canonical pool changed and a new candidate now scores higher): expected behaviour is that
  the most recent reconciliation run's result is authoritative, since bridges are recomputed from
  scratch each cycle, not accumulated.
- **A provider that has not yet minted anything for a club** (its data hasn't been ingested yet):
  expected behaviour is that there is nothing to bridge until that provider's bronze data exists;
  reconciliation only acts on names actually present in bronze.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST identify, from each provider's bronze data, raw team names that have no
  match in the curated `team_aliases` seed and no existing learned bridge from a prior reconciliation
  run.
- **FR-002**: For each such unmatched raw name, system MUST compare it against the current canonical
  team pool (the union of teams already known across all providers) using a fuzzy string-similarity
  comparison and produce a confidence score per candidate.
- **FR-003**: System MUST automatically record and apply a bridge (raw name → canonical team_id) when
  exactly one candidate scores at or above the high-confidence threshold.
- **FR-004**: System MUST automatically record and apply a bridge, tagged for human review, when no
  candidate meets the high-confidence threshold but exactly one candidate scores at or above the
  medium-confidence threshold (mirroring the codebase's existing `auto_confirmed` /
  `needs_review` distinction used for event-to-match fuzzy linking).
- **FR-005**: System MUST NOT create a bridge when no candidate meets the medium-confidence threshold,
  or when two or more candidates are tied at the top score at or above the medium-confidence
  threshold — the raw name remains unresolved and its provider's conform step continues to self-mint
  a new canonical team, exactly as it does today.
- **FR-006**: The team-identity resolution formula (curated seed alias → learned bridge → self-minted
  deterministic id, in that precedence order) MUST produce the identical canonical `team_id` for a
  given raw name across every code path that resolves a raw team name to a `team_id` — this includes
  every dbt model resolving ESPN names and the shared Python resolution used by non-ESPN providers'
  conform steps.
- **FR-007**: Bridging MUST work regardless of which provider mints a canonical team first — a team
  minted by ESPN under name A and later observed from Matchbook under a fuzzy-matching name B resolves
  to the same canonical `team_id` as the reverse ordering (Matchbook mints first under name B, ESPN
  later uses name A).
- **FR-008**: Each learned bridge MUST be recorded with the raw name, the canonical `team_id` it
  resolved to, the source provider, a confidence score, and a match method/tag distinguishing
  high-confidence from medium-confidence outcomes.
- **FR-009**: Reconciliation MUST run before a provider's distinct, separately-orderable mint step
  (today: Matchbook's Python conform/mint asset), so a bridge learned in a given run is available to
  that same run's minting decisions rather than only the next run. A provider whose resolution has no
  separate mint step of its own (today: ESPN, whose raw-name resolution is the warehouse transform
  itself, not a distinct step) is not required to see a same-run bridge — for that path, convergence
  within one additional full pipeline run (per SC-001) is sufficient and expected.
- **FR-010**: The reconciliation and downstream conform steps MUST be idempotent and self-healing —
  after a new bridge is learned, the next full pipeline rebuild MUST cause any canonical team or match
  that was previously duplicated (minted separately before the bridge existed) to converge onto the
  bridged canonical id, without a separate manual migration or backfill step.
- **FR-011**: System MUST NOT write learned bridges back into the curated `team_aliases` seed file —
  seed curation remains a distinct, manual process, unaffected by this feature.
- **FR-012**: Reconciliation MUST cover raw names sourced from every provider whose conform/mint path
  resolves team identity (currently ESPN and Matchbook), not only one direction.
- **FR-013**: The reconciliation step MUST derive its canonical-team comparison pool from data already
  exported for that purpose (an existing canonical team export artifact), consistent with this
  project's existing rule that Python pipeline code never opens a live connection to the shared
  catalog.

### Key Entities *(include if feature involves data)*

- **Learned Team Alias (bridge)**: a record produced by reconciliation linking a provider's raw,
  unseeded team-name spelling to an existing canonical `team_id`. Attributes: raw name, resolved
  canonical `team_id`, source provider, confidence score, match method (`auto_confirmed` or
  `needs_review`). Consumed by every team-identity resolution path as the second-priority source of
  truth, after the curated seed and before self-minting.
- **Canonical Team Pool**: the existing set of canonical teams already known to the platform (from the
  curated seed, ESPN's own resolution, and every provider's prior minting), used as the comparison
  target for fuzzy-matching a new raw name.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any pair of differently-spelled names referring to the same real-world team, scoring
  at or above the medium-confidence threshold against each other, the two resolve to one canonical
  team_id within one additional full pipeline run after both spellings have been ingested — regardless
  of which provider's spelling was minted first.
- **SC-002**: Zero false-positive bridges: distinct real-world teams that are not genuinely the same
  club are never merged into a single canonical id by this feature (verified against a known-negative
  test set of similarly-named-but-different teams).
- **SC-003**: 100% of automatically-created bridges are traceable to a raw name, source provider,
  resolved team_id, confidence score, and match method.
- **SC-004**: A canonical match that was previously duplicated across two providers (two match_ids for
  one real fixture) converges to a single match_id within one additional full pipeline run after the
  underlying team bridge is learned, with no manual intervention.
- **SC-005**: Every code path in the canonical layer that resolves a raw team name to a `team_id`
  agrees on the same id for the same (seed state, learned-bridge state, raw name) triple — verified by
  a cross-path parity check.

## Constraints & things to be aware of *(mandatory)*

- **No live catalog connection from Python.** Per this project's architectural boundary (also
  reflected in Constitution Principle II's "no reward hacking via shortcuts" spirit — do the correct
  thing, not the convenient one), Python pipeline code reads canonical team data from an already
  -exported Parquet artifact, never by opening a connection to the shared DuckLake catalog, even
  read-only.
- **Reconciliation output must be visible to the asset-dependency graph**, not just present on disk —
  otherwise nothing schedules a rebuild after new bridges are learned, reproducing a class of bug this
  project has hit before with un-tracked provider-addition files.
- **Existing seed-then-self-mint precedence must be preserved and extended, not replaced.** The
  learned bridge sits strictly between the curated seed (highest precedence) and self-minting (lowest
  precedence, unchanged fallback) — this feature must not change resolution behaviour for any name
  already covered by the seed.
- **Idempotency (Constitution: predictable, non-accreting change).** Bridges are recomputed from the
  current bronze + canonical-pool state on every run, not accumulated or hand-edited; this is what
  makes the self-healing convergence in FR-010/SC-001/SC-004 possible without a bespoke backfill.
- **Test-First (Constitution Principle III, NON-NEGOTIABLE).** Both the confidence-scoring logic and
  the bidirectional (both-order) convergence behaviour must have a failing test written and observed
  red before the corresponding implementation exists.
- **No Reward Hacking (Constitution Principle II, NON-NEGOTIABLE).** The medium-confidence
  `needs_review` tag must genuinely mean "applied but flagged," not silently discarded or silently
  promoted to full confidence — narrowing this distinction to make tests pass would violate this
  principle.
- Out of scope: bridging league or season identity (the existing `league_aliases` seed mechanism for
  leagues is untouched by this feature); closing high-abbreviation name gaps below the
  medium-confidence threshold (remains `team_aliases.csv` curation work).

## Assumptions *(mandatory)*

- The confidence thresholds and fuzzy-comparison method already established in this codebase for
  event-to-match linking (a high-confidence "auto-confirmed" tier and a medium-confidence
  "needs-review" tier, using token-sort-ratio string similarity) are reused as-is for team-name
  bridging, rather than introducing a new algorithm or new thresholds — confirmed with the user as the
  intended behaviour for this feature.
- Existing canonical teams/matches that were minted as duplicates *before* this feature ships are
  expected to converge automatically the next time the full pipeline rebuilds after reconciliation is
  deployed and has learned the relevant bridge — no separate one-time backfill/cleanup task is in
  scope, because conform already reprocesses all bronze data from scratch on every run.
- Scope is limited to team identity; match identity is fixed as a side effect because it derives from
  team identity, but no separate match-bridging mechanism is introduced.
- The two providers in scope today are ESPN and Matchbook; a future third provider (e.g.
  football-data) participates automatically once it has a conform/mint path that resolves team names,
  without requiring changes to this feature's design.

## Open Questions *(mandatory)*

- None.
