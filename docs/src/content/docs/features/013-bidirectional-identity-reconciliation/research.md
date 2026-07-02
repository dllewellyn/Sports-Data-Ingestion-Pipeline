---
title: "Research: Bidirectional Identity Reconciliation"
---

# Research: Bidirectional Identity Reconciliation

**Feature directory**: `specs/013-bidirectional-identity-reconciliation/`

Phase 0 output. Every unknown from the spec resolved to a Decision, with Rationale and Alternatives
considered. No `[NEEDS CLARIFICATION]` markers remain in `spec.md`; this file resolves the *technical*
unknowns the spec deliberately left to planning.

## 1. Where does the fuzzy-comparison method and its confidence thresholds live?

**Decision**: Extract `HIGH_CONFIDENCE`, `MEDIUM_CONFIDENCE`, `HIGH_THRESHOLD`, `MEDIUM_THRESHOLD`
from `src/data_platform/conform/matchbook_scoring.py` into a new `src/data_platform/conform/scoring.py`
holding only those four provider-agnostic constants. `matchbook_scoring.py` keeps
`KICKOFF_TOLERANCE_MINUTES`, `_parse_start_utc`, and `_score_candidate` (genuinely
event/match-specific — they reason about kickoff time, which team-name bridging never does) and
imports the four constants from `conform/scoring.py` instead of defining them. `reconcile.py`
(new, this feature) imports the same constants.

**Rationale**: The constants are already algorithm-agnostic (a confidence tier, not a match-specific
formula); the only reason they lived in `matchbook_scoring.py` was that team-name bridging didn't
exist yet. `matchbook_scoring.py`'s own module docstring ("Scoring logic for the Matchbook conform
engine") becomes actively misleading once a second, non-Matchbook-specific consumer imports from it.
This is a minimal, single-purpose extraction — not a new abstraction layer — consistent with CLAUDE.md
"do not overengineer."

**Alternatives considered**:
- *Leave the constants in `matchbook_scoring.py`, import cross-module.* Rejected — cements a
  misleading module name and a reconciliation module depending on something branded "Matchbook".
- *Put the constants in `conform/resolve.py`.* Rejected — `resolve.py`'s docstring is explicit that it
  holds pure identity-formula functions mirroring dbt macros byte-for-byte; confidence thresholds are
  scoring policy, not identity formula, and mixing them muddies that module's single responsibility.
- *New algorithm/thresholds specific to team names.* Rejected per explicit confirmation with the user
  during specification — reuse the existing tiers as-is (see spec Assumptions).

## 2. How does `identity_reconciliation` read each provider's raw team names without a DuckLake connection?

**Decision**:
- ESPN: read `data/bronze/espn/**/*.parquet` directly via `pd.read_parquet` (glob), select
  `home_team_name` / `away_team_name` columns — already flattened, faithful-to-source columns on the
  bronze frame (confirmed against `espn/ingest.py` and `models/schemas.py`; `stg_espn_events.sql`
  reads these same column names straight off `{{ source('bronze', 'espn_events') }}` with no JSON
  extraction needed for team names).
- Matchbook: read `data/bronze/matchbook_events/**/*.parquet` directly, and parse team names out of
  the raw `event_name` field via the existing `conform/matchbook_event_name.parse_event_name`
  function (mirrors how `matchbook_conform.py`'s own mint path already gets raw team names).

**Rationale**: CLAUDE.md's Python-conform constraint applies uniformly: "Python conform modules never
open a DuckLake connection (even read-only): they read bronze Parquet + the `canonical_*` external
-Parquet exports." Both providers' bronze already contain the raw names as either a direct column
(ESPN) or a parseable field (Matchbook), so no new bronze schema or ingest change is needed.

**Alternatives considered**:
- *Read via `stg_espn_events` (a dbt/DuckLake view).* Rejected — violates the "no DuckLake connection
  from Python" rule (ARCHITECTURE.md rule 3, reinforced in CLAUDE.md's Non-obvious constraints).
- *Add a new bronze column/asset for "raw team name."* Rejected — the data already exists in bronze
  in a directly-usable shape; no ingestion change is needed.

## 3. How does `identity_reconciliation` get the current canonical team pool to fuzzy-match against?

**Decision**: Read `data/silver/canonical/team.parquet` (the existing `canonical_team_export` dbt
mart, columns `team_id, name, similar_names`) as a plain Parquet file — the exact file
`matchbook_conform.py` already reads via `settings.matchbook_conform_canonical_dir`. No new export is
needed.

**Rationale**: This file already IS the canonical team pool, already exported for exactly this kind of
Python-side consumption, already accepted as "possibly a few minutes stale, harmless because
idempotent" (documented in `assets/dbt.py`'s `espn_assets` comment). Reusing it avoids a new mart and
keeps the self-healing story (SC-001/FR-010) intact — a stale read just means a bridge is found on the
next cycle instead of this one, matching the spec's own "within one additional full pipeline run"
success criterion.

**Alternatives considered**:
- *A new, dedicated canonical-pool export just for reconciliation.* Rejected — pure duplication of an
  existing artifact with the exact shape needed.

## 4. Does `identity_reconciliation`'s output need a Dagster `deps=[...]` edge into the dbt models, or a dbt `source()` mapping?

**Decision**: **No `{{ source(...) }}` reference in any dbt model SQL.** `int_team.sql`,
`int_match.sql` (the `espn_matches` CTE), and `int_espn_team_link.sql` read
`data/silver/learned_team_aliases.parquet` via a **raw `read_parquet()` literal**, exactly mirroring
how `int_match.sql` already reads `matchbook_t60_enrichment.parquet`. `learned_team_aliases` IS still
registered in `_sources.yml` and mapped in `BronzeAwareTranslator._SOURCE_ASSET_KEYS` for
documentation/consistency — mirroring how `matchbook_t60_enrichment` is registered there too even
though no model actually references it via the `source()` macro. The only *real* Dagster dependency
edge this feature adds is a plain Python-asset-to-Python-asset one:
`matchbook_conform`'s `deps=[...]` gains `AssetKey(["identity_reconciliation"])` (in addition to its
existing `AssetKey(["matchbook_events_bronze"])`).

**Rationale — this is the single highest-risk design decision in this feature, and it is grounded in
an already-documented, already-hit failure mode in this exact codebase**, not a guess:

`int_match.sql` carries this comment (lines 118–124), verified by reading the file directly:

> "Deliberately a raw read_parquet literal, NOT the dbt source() macro: int_match already depends on
> matchbook_conform (via the canonical_additions source above); adding a SECOND cross-op dependency on
> matchbook_t60_enrichment ... is a 3-tier ordering requirement dagster-dbt's automatic step-subsetting
> cannot resolve (it splits a `@dbt_assets` op into at most 2 steps around ONE external dependency, not
> a chain of two) — attempting it raises a circular-dependency error at Definitions build time."

`int_team.sql` and `int_match.sql` are **already at that one-external-dependency ceiling** today —
`matchbook_conform` is the sole `source()`-tracked external Python asset feeding them (via the four
`matchbook_canonical_*_additions` sources, which all map onto the single `AssetKey(["matchbook_conform"])`,
so they count as one tier, not four). `football_data`'s additions are *also* deliberately read via raw
`read_parquet()`, not `source()`, for the same reason (there is no room for a second tier even for a
provider with a real conform body).

If `identity_reconciliation`'s bridge file were *also* `source()`-tracked into these same models, the
`dbt_models` op — in `matchbook_job`, where **both** `identity_reconciliation` and `matchbook_conform`
are selected, and `matchbook_conform` itself depends on `identity_reconciliation` — would need a
genuine 3-tier resolution (`identity_reconciliation → matchbook_conform → int_team`, plus
`identity_reconciliation → int_team` directly). This is structurally identical to the exact case the
`int_match.sql` comment says dagster-dbt "cannot resolve." Choosing the raw-literal path avoids
re-hitting a documented `CircularDependencyError` by construction, rather than discovering it during
implementation.

**Consequence for FR-009 ("reconciliation runs before that provider's conform/mint step in the same
run")**: this requirement is satisfied *exactly* for the one place it names a distinct, separately
-orderable "mint step" — Matchbook's Python conform/mint asset — via the plain `deps=[identity_reconciliation]`
edge (zero dbt-graph risk, identical in kind to any other Dagster asset dependency). ESPN has no
separate mint step; its resolution *is* the dbt SQL itself, so "same run" visibility for the ESPN dbt
path is not mechanically guaranteed by a Dagster edge — but this does not violate the spec, because
SC-001 already states convergence happens "within one additional full pipeline run," and this is
exactly the same next-run-picks-it-up behaviour CLAUDE.md already documents and accepts for
T-60 ("favourite-team enrichment lands on whichever run rebuilds int_match after T-60 has already
written this file"). The **Dagster orchestration wiring guardrail** (§ below) requires launching a real
queued run to empirically confirm no cycle is introduced and that the intended within-job ordering
(`identity_reconciliation` before `matchbook_conform`, in `matchbook_job`) actually holds — this is not
skipped just because the design is analytically well-grounded.

**Alternatives considered**:
- *`source()`-track `identity_reconciliation` into `int_team`/`int_match`/`int_espn_team_link`.*
  Rejected — reproduces the documented `CircularDependencyError` failure mode.
- *Drop `matchbook_conform`'s existing `source()` tracking instead, to make room for
  `identity_reconciliation`'s.* Rejected — `matchbook_conform`'s additions need same-run visibility for
  its own newly-minted canonical rows to appear in the canonical models within the run that minted
  them (this is exactly the T038/Spec-012 fix CLAUDE.md documents); trading that away to make room
  would reintroduce a worse, already-fixed bug.
- *Run `identity_reconciliation` as a genuinely separate job/schedule, decoupled from same-run
  ordering entirely.* Rejected — this is what the *original* Matchbook conform design did
  (`matchbook_events_ingestion` + a separately-scheduled `matchbook_conform_job`) and CLAUDE.md records
  it as a bug that was deliberately fixed by merging into one end-to-end job; repeating the same
  mistake for reconciliation is exactly backwards.

## 5. Where does the Python mint-path (`resolve_team_id`) get its learned aliases from, and in what precedence?

**Decision**: `resolve.resolve_team_id(name, aliases, learned_aliases=None)` gains an optional third
parameter. Precedence, matching the SQL macro exactly: **seed alias → learned alias → self-mint**.
`matchbook.py`'s mint path loads `learned_team_aliases.parquet` (written by `identity_reconciliation`,
guaranteed present in the same run via the new `deps=` edge — Decision 4) the same way it already
loads `team_aliases.csv`, and passes it through.

**Rationale**: Mirrors the existing two-tier `coalesce(seed, self-mint)` pattern already in
`resolve.py`/`int_team.sql`/`int_espn_team_link.sql` exactly, just inserting one more tier — this is
the literal shape FR-006 requires ("identical canonical `team_id`... across every code path").

**Alternatives considered**: None genuinely different — the three-tier coalesce is the only shape that
satisfies FR-006's cross-path parity requirement once a learned-alias tier is introduced at all.

## 6. What confidence policy governs an automatic bridge?

**Decision**: Confirmed with the user during specification (see spec Assumptions / User Story 2). A
single high-confidence candidate (`HIGH_THRESHOLD`) auto-bridges tagged `auto_confirmed`; failing
that, a single medium-confidence candidate (`MEDIUM_THRESHOLD`) auto-bridges tagged `needs_review`
(applied immediately, flagged for later audit — mirrors `matchbook.py`'s existing
`fuzzy_high`/`auto_confirmed` vs. `fuzzy_medium`/`needs_review` outcome shape at lines 465–479
exactly, reusing an established codebase pattern rather than inventing a new one). No candidate above
threshold, or a tie at the top score, produces no bridge.

**Rationale**: Already resolved via `AskUserQuestion` before drafting `spec.md`; recorded here for
traceability from technical decision back to that resolution.

**Alternatives considered**: (see spec — the rejected alternative was "auto-bridge only at
`HIGH_THRESHOLD`; leave `MEDIUM_THRESHOLD` matches unresolved").

## 7. Test-harness convention

**Decision**: Use the existing `tests/conform/` pytest harness (already established — `PYTHONPATH=src
uv run pytest`, importlib mode, unique basenames, mirrors `src/data_platform/` layout). No new harness
setup step is needed.

**Rationale**: `CLAUDE.md`'s *Commands* section documents this harness as already in place, and
`tests/conform/test_resolve.py`, `test_parity.py`, `test_mint_chain.py` already exist and exercise the
exact identity-resolution surface this feature extends. (Note: the plan skill's own
`tdd-and-guardrails.md` reference still says "there is no Python unit-test suite" — that line is stale
relative to the current `CLAUDE.md`; the harness has since been established. Flagged here, not acted
on, since correcting that reference file is out of scope for this feature.)

**Alternatives considered**: N/A — a harness already exists; nothing to decide.
