---
title: "Implementation Plan: Bidirectional Identity Reconciliation"
---

# Implementation Plan: Bidirectional Identity Reconciliation

**Feature directory**: `specs/013-bidirectional-identity-reconciliation/`
**Date**: 2026-07-02
**Spec**: `spec.md`
**Status**: Draft

## Summary

When either ESPN or Matchbook mints a canonical team under a raw name spelling the other provider
would never produce, the two providers currently end up with two canonical teams (and, because match
identity derives from team identity, two canonical matches) for one real-world club — in whichever
mint order the providers happen to see the name first. This plan adds a third resolution tier —
**learned bridge** — between the existing curated seed (`team_aliases.csv`) and each provider's
self-mint fallback: a new `identity_reconciliation` Dagster asset fuzzy-matches each provider's
unseeded raw names against the current canonical team pool (reusing the confidence tiers and
`token_sort_ratio` comparison already established for Matchbook's event-to-match linking) and records
bridges in `data/silver/learned_team_aliases.parquet`. Every code path that resolves a raw team name to
a `team_id` — three dbt models and the shared Python `resolve_team_id` — is extended to the same
three-tier `coalesce(seed, learned, self-mint)` formula via one dbt macro and one Python parameter,
guaranteeing cross-path identity parity. The riskiest technical decision — how `identity_reconciliation`'s
output is wired into the dbt asset graph — is resolved analytically in `research.md` §4 against a
documented, already-hit `CircularDependencyError` failure mode in this codebase, not left to
implementation-time discovery.

## Technical Context

**Language/Version**: Python 3.12 (`.python-version` / `pyproject.toml` pin, unchanged)
**Primary Dependencies**: Dagster, dbt-duckdb, pandas, rapidfuzz (`token_sort_ratio` — already a
dependency via `matchbook_scoring.py`), pydantic-settings
**Storage**: Parquet on local FS (`data/silver/learned_team_aliases.parquet`, new; reads existing
`data/bronze/espn/**`, `data/bronze/matchbook_events/**`, `data/silver/canonical/team.parquet`), DuckLake
(catalog for the three touched dbt models — no new tables, existing `int_team`/`int_match`/
`int_espn_team_link` change resolution logic only)
**Testing**: pytest (existing `tests/conform/` harness), dbt tests via `dbt build` (new singular test +
extended existing tests), Pandera/Pydantic not applicable (this feature has no new external-boundary
ingest — it derives from already-validated bronze)
**Target Platform**: Dagster-scheduled job (`espn_ingestion`, `matchbook_ingestion`), local `dagster dev`
for development
**Project Type**: single project (existing medallion pipeline monorepo)
**Performance Goals**: N/A — reconciliation runs once per scheduled 6h cycle over bronze volumes
already handled by existing conform steps; no new latency-sensitive path
**Constraints**: no live DuckLake connection from Python (ARCHITECTURE.md rule 3); dagster-dbt's
documented single-external-dependency-tier ceiling on a `@dbt_assets` multi-asset op (research.md §4);
single-writer DuckDB rule (unaffected — no `warehouse.duckdb` access)
**Scale/Scope**: 3 dbt model files changed, 1 new dbt macro, 1 new dbt singular test, 2 new/relocated
Python modules (`conform/scoring.py`, `conform/reconcile.py`), 1 extended Python module
(`conform/resolve.py`), 1 new Dagster asset module, `definitions.py` job-selection + deps wiring, 1
new config property, test extensions across 3 existing pytest files + 1 new pytest file

## Constitution Check

| Principle (constitution) | Compliance in this plan |
|---|---|
| I. No Backward Compatibility | The three-tier resolution formula *replaces* the two-tier one at every call site in the same commit set — no flag, no dual code path. `resolve_team_id`'s new `learned_aliases` parameter defaults to `None`/empty so *behaviour* is unchanged when absent, which is a genuine optional input (not every caller has learned data available at every call site — e.g. a synthetic unit test), not a legacy-compat shim. |
| II. No Reward Hacking | No placeholders/mocks/stubs. The `needs_review` tag is applied and persisted for real (not silently discarded or silently promoted) — S6's self-review explicitly checks this. No gate is weakened: `dbt build`, `ruff`, and `pre-commit` all run as-is. |
| III. Test-First | Every step (S0–S8) writes a failing test before implementation — pytest for pure logic (S0, S1, S4, S5), dbt test for the SQL formula (S2), artifact assertion for the Dagster asset (S6), and an empirical Dagster-run assertion for orchestration wiring (S7), per `tdd-and-guardrails.md`'s per-unit facility table. |
| IV. Honesty & Permission to Fail | research.md §4 documents the CircularDependencyError risk explicitly and states the chosen mitigation's basis rather than asserting false confidence; S7's guardrail still empirically re-verifies it. |
| V. Surface Contradictions | research.md §4 surfaces the tension between FR-009's literal "every provider" wording and the mechanical risk of `source()`-tracking a second external tier, and resolves it by scoping "same-run" to the one place FR-009's own origin (the seed write-up) actually meant it — the Python mint step — documented explicitly rather than silently narrowed. |

## Project Structure

```text
specs/013-bidirectional-identity-reconciliation/
├── spec.md
├── plan.md           # this file
├── research.md        # Phase 0 — 7 resolved decisions
├── data-model.md      # Phase 1 — Learned Team Alias entity + resolution formula
├── quickstart.md      # Phase 1 — 4 runnable validation scenarios
└── tasks.md           # Phase 2 — produced later by the `tasks` skill, NOT here
```

**Source layout touched**:
- `src/data_platform/conform/scoring.py` (new — relocated constants)
- `src/data_platform/conform/matchbook_scoring.py` (modified — imports from `scoring.py`)
- `src/data_platform/conform/reconcile.py` (new — `find_learned_aliases`)
- `src/data_platform/conform/resolve.py` (modified — `resolve_team_id` gains `learned_aliases` param)
- `src/data_platform/conform/matchbook.py` (modified — mint path passes learned aliases)
- `src/data_platform/assets/intermediate/identity_reconciliation.py` (new — Dagster asset)
- `src/data_platform/config.py` (modified — new `learned_team_aliases_path` property)
- `src/data_platform/definitions.py` (modified — job selections + `deps=` wiring)
- `dbt/data_platform/macros/resolve_team_id_expr.sql` (new)
- `dbt/data_platform/models/intermediate/int_team.sql` (modified)
- `dbt/data_platform/models/intermediate/int_match.sql` (modified — `espn_matches` CTE only)
- `dbt/data_platform/models/intermediate/int_espn_team_link.sql` (modified)
- `dbt/data_platform/models/_sources.yml` (modified — doc-only `learned_team_aliases` entry)
- `src/data_platform/assets/dbt.py` (modified — `BronzeAwareTranslator` mapping entry, doc-only)
- `dbt/data_platform/tests/assert_team_resolution_formula_parity.sql` (new singular test)
- `tests/conform/test_scoring.py` (new), `test_reconcile.py` (new), `test_resolve.py` (extended),
  `test_mint_chain.py` (extended), `test_parity.py` (extended)

## Skills to use

| Work area | Skill to use | Status |
|---|---|---|
| New dbt model/macro change + tests | (no dedicated build skill) | MISSING — proceed from existing repo pattern (`ARCHITECTURE.md` intermediate-model guide, `int_espn_team_link.sql`/`canonical_match_id.sql` as the nearest analogues); run `self-learn` after the build since this exact kind of work has now recurred across specs 006/008/010/012/013 without a dedicated skill |
| New Dagster asset module + job wiring | (no dedicated build skill) | MISSING — proceed from `assets/intermediate/matchbook_conform.py` / `matchbook_t60.py` as the nearest analogues; same `self-learn` follow-up |
| Architecture conformance of the change | `code-architecture-review` | available |
| Per-step diff review | `code-review` | available |
| Verify the change actually runs (Dagster daemon/queued run) | `verify` / `run` | available |
| Capturing learnings afterwards | `self-learn` | available |
| Execution of this plan's tasks | `implementor` (downstream, after `tasks`) | available |

No skill is silently assumed beyond this session's confirmed inventory (project + global + plugin
skills surfaced this session). Both MISSING rows are genuinely repeatable work classes for this repo
(a fourth spec touching the same `int_team`/`int_match`/conform-asset shape); flagged per
`skill-discovery.md` rather than proceeding silently. Given the shape is already well-precedented in
three prior specs, this plan proceeds without creating a new skill now and defers the
create-a-skill decision to the post-build `self-learn` pass, rather than detouring into
`skill-creator` mid-plan for an unrequested tooling investment.

## Convention & rule audit (resolved before implementation)

| Artifact type | Governing convention | Status |
|---|---|---|
| Pure-Python identity/scoring module (`conform/reconcile.py`, `conform/scoring.py`) | `conform/resolve.py`'s docstring convention (pure functions, no I/O, no DuckLake) + CLAUDE.md "Python conventions" | exists |
| dbt macro | `macros/canonical_match_id.sql` (single-responsibility Jinja macro, documented header) | exists |
| dbt intermediate model change | `CLAUDE.md` "canonical domain schema" + `int_team.sql`/`int_espn_team_link.sql` existing patterns; the raw-`read_parquet()`-vs-`source()` choice governed by the documented `int_match.sql` comment (research.md §4) | exists |
| dbt singular test | `dbt/data_platform/tests/assert_resolver_provider_agnostic.sql` (non-tautological, reconstructs independently) | exists |
| New Dagster asset module | `assets/intermediate/matchbook_conform.py` (thin wrapper, `@asset`, `AssetKey`, `MaterializeResult`, OTel span, **no** `from __future__ import annotations`) | exists |
| Config field | `config.py` `@property` pattern (`pydantic-settings`, `pathlib.Path`) | exists |
| Job/`AssetSelection` wiring | `definitions.py`'s explicit-per-job-selection convention (no `AssetSelection.all()`) | exists |
| pytest unit tests | `tests/conform/*.py` (importlib mode, unique basenames, mirrors `src/data_platform/` layout) — harness already established, confirmed via `test_resolve.py`/`test_parity.py`/`test_mint_chain.py` already present | exists |

No gap. Every artifact type this plan touches has a governing convention or directly-analogous
existing pattern already in the tree; no new rule needs authoring before implementation.

## Testable units (BDD → tests)

| Unit | Spec trace (scenario / FR / SC) | Test facility | Failing-first assertion |
|---|---|---|---|
| `scoring.py` constants importable at new location, `matchbook_scoring` still exposes them | setup — enables S1/S4 | pytest | `from data_platform.conform.scoring import HIGH_THRESHOLD` fails (module doesn't exist) before S0; passes with correct values after |
| `find_learned_aliases` bridges a single high-confidence candidate | User Story 2 Scenario 1 / FR-003 | pytest | Feeding one raw name scoring ≥`HIGH_THRESHOLD` against one candidate returns a row tagged `auto_confirmed`; fails (function doesn't exist / wrong tag) before S1 |
| `find_learned_aliases` bridges a single medium-confidence candidate, tagged for review | User Story 2 Scenario 2 / FR-004 | pytest | Same, at `[MEDIUM_THRESHOLD, HIGH_THRESHOLD)`, tagged `needs_review` |
| `find_learned_aliases` produces no bridge below threshold | User Story 2 Scenario 3 / FR-005 | pytest | A name scoring < `MEDIUM_THRESHOLD` against every candidate yields no row |
| `find_learned_aliases` produces no bridge on an exact tie | User Story 2 Scenario 4 / Edge case (ambiguous tie) / FR-005 | pytest | Two candidates tied at the top score ≥ threshold yields no row for that name |
| `find_learned_aliases` never bridges a name already in the seed | Edge case (seed precedence) | pytest | A raw name with a seed alias is excluded from the input set / never appears bridged |
| `resolve_team_id_expr` macro produces the 3-tier coalesce | FR-006 (SQL side) | dbt test (singular) | `dbt build --select <macro's using models>`/compile fails before the macro exists; the new singular test asserts `coalesce(seed, learned, self-mint)` shape against real rows after |
| `int_team`/`int_match`/`int_espn_team_link` resolve a bridged name onto the seed/self-minted `team_id`, not a fresh one | FR-006, FR-007 (SQL side), Edge case (seed precedence) | dbt test + artifact assertion | `dbt build --select intermediate.int_team+ --indirect-selection=empty` fails (old 2-tier coalesce ignores the bridge) before S3; passes and canonical team count for a known-duplicate pair collapses to one after |
| `resolve.resolve_team_id` 3-tier, both mint orders | User Story 1 (core), FR-006/FR-007 (Python side) | pytest | A synthetic `learned_aliases` frame bridging name B onto name A's `team_id`, exercised in both directions (A-then-B and B-then-A framing), fails to converge before S4; converges after |
| `resolve.resolve_team_id` unaffected when `learned_aliases` is `None`/empty | Constitution I (no backward-compat shim, but no regression either) | pytest | Existing `test_resolve.py` cases keep passing unmodified — regression guardrail, not new red/green |
| dbt macro output == independently-reconstructed Python formula | FR-006, SC-005 | pytest (parity, mirrors `test_parity.py`'s non-tautological pattern) | A hand-built "macro-shape" reconstruction (not calling `resolve_team_id`) diverges from `resolve_team_id`'s bridged output before the 3-tier logic is added identically on both sides; matches after |
| `identity_reconciliation` writes a well-formed, bootstrap-safe `learned_team_aliases.parquet` from real ESPN + Matchbook bronze fixtures | FR-001, FR-002, FR-008, FR-012, FR-013, User Story 3 | pytest (artifact assertion) | Asserting the file exists with all 5 columns non-null per row fails before S6 (asset doesn't exist); passes after, given seeded bronze fixtures |
| `identity_reconciliation` never opens a DuckLake connection | Constraints (ARCHITECTURE.md rule 3) | pytest (static/behavioural check) | Test asserts no `duckdb.connect` call occurs during the asset body (mock/patch and assert not-called, or a source-scan check) |
| `matchbook_conform` runs after `identity_reconciliation` within `matchbook_ingestion`; both jobs launch without `CircularDependencyError` | FR-009, FR-012, Constraints (asset-graph visibility) | artifact assertion (real Dagster run, per quickstart Scenario 4) | Launching a queued `matchbook_ingestion` run before S7 either doesn't exist (asset unwired) or would raise `CircularDependencyError` if wired the risky way; after S7, the run launches and step ordering shows `identity_reconciliation` before `matchbook_conform` |
| End-to-end: a team minted by ESPN first, later bridged from a Matchbook spelling (and the reverse order), converges to one canonical `team_id`/`match_id` within one additional run | User Story 1 Acceptance Scenarios 1–3, SC-001, SC-004, FR-010 | pytest (`test_mint_chain.py` extension) + `dbt build` | Simulating both orderings through `run_conform` + the learned-alias bridge fails to converge before S8; converges (single row, matching id) after |
| Learned bridges are never written back into `team_aliases.csv` | FR-011 | pytest (self-review checkpoint, S1/S6) | Asserts `team_aliases.csv`'s mtime/content is unchanged after a reconciliation run that produces bridges |

## Guardrail register

| Guardrail | How verified in place | Covered by step |
|---|---|---|
| ruff check + format (pre-commit) | `uv run pre-commit run --all-files` clean on changed files | all steps |
| dbt tests run via `dbt build` | New singular test (S2) + `int_team`/`int_match`/`int_espn_team_link` schema tests unaffected; `dbt build --select intermediate.int_team+ --indirect-selection=empty` green | S2, S3, S8 |
| Boundary validation (Pydantic/Pandera) | N/A — no new external-boundary ingest; `identity_reconciliation` derives from already-validated bronze | — |
| Idempotency / re-run safety | `learned_team_aliases.parquet` fully recomputed each run (no accumulation); re-running `identity_reconciliation` + `matchbook_conform` twice produces identical output the second time | S6, S8 |
| No live DuckLake connection from Python | S6 self-review explicitly checks for `duckdb.connect`/catalog access in `identity_reconciliation` and `reconcile.py` | S1, S6 |
| Dagster orchestration wiring launches cleanly (daemon/queued path, not just `dagster definitions validate`) | Launch a real queued run of both `espn_ingestion` and `matchbook_ingestion` through the UI/daemon; confirm no `CircularDependencyError` and correct step ordering (quickstart Scenario 4) | S7 |
| Constitution principles respected | II No-reward-hacking · III Test-first · I No-backward-compat | all |

## Implementation Steps

### Step S0 — Extract shared confidence-threshold constants into `conform/scoring.py`
- **Goal:** Relocate `HIGH_CONFIDENCE`, `MEDIUM_CONFIDENCE`, `HIGH_THRESHOLD`, `MEDIUM_THRESHOLD` out of
  the misleadingly-named `matchbook_scoring.py` into a new provider-agnostic `conform/scoring.py`, with
  `matchbook_scoring.py` re-exporting them so no existing caller (`matchbook.py`, `test_conform.py`)
  needs to change.
- **Spec trace:** setup — enables S1 (`reconcile.py`) and S4 (`resolve.py`) to import the same tiers
  research.md decided to reuse (Assumptions, User Story 2).
- **Red (failing test first):** `tests/conform/test_scoring.py` — `from data_platform.conform.scoring
  import HIGH_CONFIDENCE, MEDIUM_CONFIDENCE, HIGH_THRESHOLD, MEDIUM_THRESHOLD` and assert their values
  (0.95, 0.75, 0.85, 0.70); fails with `ModuleNotFoundError` before the module exists.
- **Implementation:** create `conform/scoring.py` with the four constants (module docstring: "Shared
  fuzzy-match confidence tiers, reused by event-to-match linking and team-name reconciliation.");
  change `matchbook_scoring.py` to `from .scoring import HIGH_CONFIDENCE, MEDIUM_CONFIDENCE,
  HIGH_THRESHOLD, MEDIUM_THRESHOLD` instead of defining them; leave `KICKOFF_TOLERANCE_MINUTES` and the
  event/match-specific functions in place.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/conform/test_scoring.py` passes; existing
  `PYTHONPATH=src uv run pytest tests/conform/test_conform.py` still passes unmodified (regression
  proof that the re-export preserves every existing import path).
- **Guardrails to satisfy:** ruff clean on `scoring.py` + `matchbook_scoring.py`.
- **Self-review checkpoint:** confirm `matchbook_scoring.py` no longer *defines* the four constants
  (only imports them); confirm no other file was touched to keep existing imports working (the
  re-export, not a find-replace, is what preserves compatibility); confirm no behaviour changed
  (values identical).

### Step S1 — `conform/reconcile.py`: `find_learned_aliases`
- **Goal:** Pure function fuzzy-matching a set of raw names against the canonical team pool, applying
  the confirmed confidence policy (User Story 2).
- **Spec trace:** User Story 2 (all 4 acceptance scenarios), FR-001–FR-005, FR-011 (no seed write-back).
- **Red (failing test first):** `tests/conform/test_reconcile.py` — five cases (high-confidence bridge,
  medium-confidence `needs_review` bridge, below-threshold no-bridge, tied-candidates no-bridge,
  already-seeded name excluded), each asserting on `find_learned_aliases`'s output shape/tags; all fail
  with `ImportError` before the module exists.
- **Implementation:** `find_learned_aliases(raw_names: pd.Series, canonical_teams: pd.DataFrame,
  high_threshold=HIGH_THRESHOLD, medium_threshold=MEDIUM_THRESHOLD) -> pd.DataFrame` — for each raw
  name, score against `canonical_teams.name` and each entry of `canonical_teams.similar_names` via
  `rapidfuzz.fuzz.token_sort_ratio`, take the best-scoring candidate per name, apply the tiered
  decision, return `raw_name, team_id, confidence, match_method` rows (no `source_provider` — the
  caller stamps that, since one call handles one provider's names at a time). No I/O, no DuckLake
  (mirrors `resolve.py`'s discipline).
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/conform/test_reconcile.py` passes, all 5
  cases green.
- **Guardrails to satisfy:** ruff clean; no DuckLake connection (static check — no `duckdb` import in
  `reconcile.py`).
- **Self-review checkpoint:** confirm each test can genuinely fail (revert the threshold comparison and
  confirm tests turn red); confirm the tie-handling and below-threshold cases don't silently default to
  the highest-scoring candidate (that would be reward-hacking against FR-005); confirm no seed-file I/O
  anywhere in the module (FR-011).

### Step S2 — dbt macro `resolve_team_id_expr` + singular test for its shape
- **Goal:** One macro implementing `coalesce(seed, learned, self-mint)`, callable identically from all
  three SQL sites, plus a non-tautological singular test proving the shape (mirrors
  `assert_resolver_provider_agnostic.sql`'s independent-reconstruction pattern).
- **Spec trace:** FR-006 (SQL side of cross-path parity).
- **Red (failing test first):** `dbt/data_platform/tests/assert_team_resolution_formula_parity.sql` —
  written FIRST against the macro's intended contract (compile fails: macro doesn't exist yet, so
  `dbt parse` errors referencing an undefined macro).
- **Implementation:** `dbt/data_platform/macros/resolve_team_id_expr.sql` —
  `{% macro resolve_team_id_expr(seed_id_col, learned_id_col, name_col) %}
  coalesce({{ seed_id_col }}, {{ learned_id_col }}, md5(lower({{ name_col }}))) {% endmacro %}`,
  documented header mirroring `canonical_match_id.sql`'s style. The singular test independently
  reconstructs `coalesce(seed, learned, md5(lower(name)))` via raw SQL (not calling the macro) over a
  small `values(...)` fixture covering all three tiers, and asserts equality with the macro's own
  output — non-tautological by the same construction as `test_parity.py`.
- **Green criterion:** `( cd dbt/data_platform && uv run --project ../.. dbt parse --profiles-dir . )`
  succeeds; `dbt build --select test_name:assert_team_resolution_formula_parity` (or equivalent
  singular-test selector) passes against a running DuckLake catalog.
- **Guardrails to satisfy:** dbt tests via `dbt build`.
- **Self-review checkpoint:** confirm the singular test does NOT call `resolve_team_id_expr` on both
  sides of its assertion (that would be tautological); confirm it fails if the macro's precedence order
  is deliberately broken (e.g. swap `learned_id_col` and `seed_id_col`) — prove non-triviality by
  breaking it once and observing red.

### Step S3 — Wire the macro + raw `read_parquet()` bridge read into the three dbt call sites
- **Goal:** `int_team.sql`, `int_match.sql`'s `espn_matches` CTE, and `int_espn_team_link.sql` each
  resolve ESPN raw names through the new three-tier formula, reading
  `data/silver/learned_team_aliases.parquet` via a raw `read_parquet()` literal (never `{{ source(...)
  }}`) — per research.md §4's `CircularDependencyError`-avoidance decision. Register
  `learned_team_aliases` in `_sources.yml` and `BronzeAwareTranslator._SOURCE_ASSET_KEYS` for
  documentation/consistency only (mirroring the `matchbook_t60_enrichment` precedent — present in both
  places, referenced via `source()` in neither model).
- **Spec trace:** FR-006, FR-007 (SQL side of both-order bidirectionality), Edge case (seed alias
  precedence, stale-pool tolerance).
- **Red (failing test first):** Extend the dbt build/artifact check: seed a canonical team pool +
  bridge file where a name is bridged onto an *existing* `team_id`; before this step, `int_team`
  produces a *second*, self-minted `team_id` for that name (old 2-tier formula ignores the bridge) —
  captured as a failing assertion in the S3/S8 end-to-end check (`dbt build` + row-count assertion).
- **Implementation:** In each SQL file's resolution CTE, replace `coalesce(s.team_id,
  md5(lower(e.name)))` with a `left join read_parquet('{{ env_var("DATA_DIR", "/app/data")
  }}/silver/learned_team_aliases.parquet') l on e.name = l.raw_name` and
  `{{ resolve_team_id_expr('s.team_id', 'l.team_id', 'e.name') }}`. `learned_team_aliases.parquet` is
  bootstrap-written empty by `identity_reconciliation` (S6) the same way `matchbook_conform` bootstraps
  its four additions files — `read_parquet` errors on a missing path, so this ordering matters
  (captured as a dependency note in Sequencing).
- **Green criterion:** `dbt build --select intermediate.int_team+ --indirect-selection=empty` green;
  the canonical team count for a seeded known-duplicate pair (one bridged name) is 1, not 2.
- **Guardrails to satisfy:** dbt tests; no `{{ source(...) }}` reference to `learned_team_aliases`
  anywhere in the three model files (grep-verifiable).
- **Self-review checkpoint:** confirm the `left join` is on the raw (pre-resolution) name column, not
  the already-resolved `team_id` (a join on the wrong column would silently never match); confirm the
  three call sites use the macro identically (same argument order) — a copy-paste divergence here is
  exactly the kind of drift FR-006 exists to prevent; confirm the seed always still wins when both a
  seed alias and a learned bridge exist for the same name (precedence order in the `coalesce`).

### Step S4 — Python `resolve_team_id` three-tier + Matchbook mint-path wiring
- **Goal:** `resolve.resolve_team_id` gains the middle tier; `matchbook.py`'s mint path loads and passes
  `learned_team_aliases.parquet`.
- **Spec trace:** FR-006, FR-007 (Python side) — User Story 1's core claim, proven here first at the
  cheapest (pure pytest) level before the heavier Dagster/dbt proof in S8.
- **Red (failing test first):** Extend `tests/conform/test_resolve.py` — a case where `resolve_team_id`
  is called with a `learned_aliases` frame bridging name B onto an existing `team_id` for name A;
  asserts `resolve_team_id("A", seed, learned) == resolve_team_id("B", seed, learned)`. Run in BOTH
  framings (A minted first vs. B minted first — since the resolver is stateless, this literally means:
  the SAME assertion holds regardless of which name is queried first in the test, proving the formula
  itself has no order-dependence, which is what makes both real-world mint orders converge). Fails
  (`TypeError`: unexpected keyword) before the parameter exists.
- **Implementation:** `resolve_team_id(name: str, aliases: pd.DataFrame, learned_aliases: pd.DataFrame |
  None = None) -> str` — seed lookup first (unchanged), then `learned_aliases` lookup on
  `raw_name == name` if provided and non-empty, then the unchanged self-mint fallback.
  `matchbook.py`'s mint path reads `learned_team_aliases.parquet` (via `settings
  .learned_team_aliases_path`, new config property added here) the same way it already reads
  `team_aliases.csv`, and passes it through every `resolve_team_id` call in its mint chain.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/conform/test_resolve.py` passes, including
  the new bidirectional case; every pre-existing case in the file still passes unmodified (the
  `learned_aliases=None` default preserves old behaviour — Constitution I compliance, not a compat
  shim).
- **Guardrails to satisfy:** ruff clean; no DuckLake access (unchanged — `matchbook.py` already reads
  only Parquet files).
- **Self-review checkpoint:** confirm the new test genuinely exercises the middle tier (temporarily
  removing the `learned_aliases` branch turns it red); confirm `matchbook.py`'s wiring passes the SAME
  `learned_aliases` frame to every `resolve_team_id` call site in its mint chain (a missed call site
  would silently reintroduce a duplicate-mint risk for that one path).

### Step S5 — Cross-path parity test (dbt macro ↔ Python `resolve_team_id`)
- **Goal:** Prove the SQL formula (S2/S3) and the Python formula (S4) can never silently drift, mirroring
  `test_parity.py`'s existing non-tautological independent-reconstruction pattern for
  `canonical_match_id`.
- **Spec trace:** FR-006, SC-005.
- **Red (failing test first):** Extend `tests/conform/test_parity.py` with a case that independently
  reconstructs `coalesce(seed, learned, md5(lower(name)))` via raw `hashlib`/dict lookups (NOT calling
  `resolve_team_id`), for a name present in a synthetic seed, a name present only in a synthetic learned
  frame, and a name in neither; asserts equality against `resolve.resolve_team_id`'s real output for all
  three. Fails before S4's implementation exists (the function doesn't accept `learned_aliases` yet).
- **Implementation:** No production code change — this step is purely the parity test itself (S4 already
  implements the function under test).
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/conform/test_parity.py` passes, all cases
  including the three new ones.
- **Guardrails to satisfy:** none beyond ruff/pytest.
- **Self-review checkpoint:** confirm the "expected" side of every new assertion is built WITHOUT
  calling `resolve.resolve_team_id` (non-tautological, per the file's own documented convention);
  deliberately break `resolve_team_id`'s tier order and confirm this test (not just S4's own test) turns
  red — proving it's a genuine independent check, not a duplicate of S4's test.

### Step S6 — `identity_reconciliation` Dagster asset
- **Goal:** The end-to-end asset: read both providers' raw bronze names, read the canonical team pool,
  call `find_learned_aliases` per provider, bootstrap-write-empty then write
  `data/silver/learned_team_aliases.parquet`.
- **Spec trace:** FR-001, FR-002, FR-008, FR-010 (bootstrap-empty discipline), FR-012, FR-013, User
  Story 3 (traceability columns).
- **Red (failing test first):** A new artifact-level pytest (or an extension of the asset test pattern
  used for `matchbook_conform`) that seeds minimal ESPN bronze + Matchbook bronze fixtures (one provider
  minting first) plus a canonical-team-pool fixture, invokes the asset's underlying function directly
  (not through Dagster's execution harness — mirrors how `run_conform` is tested), and asserts
  `learned_team_aliases.parquet` is written with the expected bridge row. Fails (module doesn't exist)
  before this step.
- **Implementation:** `assets/intermediate/identity_reconciliation.py` — thin `@asset` wrapper (no
  `from __future__ import annotations`), `AssetKey(["identity_reconciliation"])`,
  `deps=[AssetKey(["espn_bronze"]), AssetKey(["matchbook_events_bronze"])]`; body: read ESPN bronze
  Parquet (`pd.read_parquet` glob over `settings.espn_bronze_dir`) for `home_team_name`/`away_team_name`,
  read Matchbook bronze Parquet (`settings.matchbook_events_bronze_dir`) and parse team names via
  `conform.matchbook_event_name.parse_event_name`, read
  `settings.matchbook_conform_canonical_dir / "team.parquet"` as the candidate pool, call
  `reconcile.find_learned_aliases` once per provider (stamping `source_provider`), concatenate, write
  atomically (tmp-file + rename, mirroring `_ensure_empty_parquet`'s pattern) to a new
  `settings.learned_team_aliases_path` config property (`silver_dir / "learned_team_aliases.parquet"`);
  bootstrap-write-empty first if absent, mirroring `_bootstrap_additions`. OTel span via
  `otel.get_tracer()`, matching `matchbook_conform`'s pattern.
- **Green criterion:** The new pytest passes; `PYTHONPATH=src uv run pytest tests/` (full suite) stays
  green (no regression).
- **Guardrails to satisfy:** ruff clean; no DuckLake connection (grep/static check — no `duckdb.connect`
  anywhere in the new file, confirmed by the S1-style self-review); atomic write pattern (tmp + rename).
- **Self-review checkpoint:** confirm the asset reads bronze Parquet directly (glob over
  `espn_bronze_dir`/`matchbook_events_bronze_dir`), never `stg_espn_events` or any DuckLake connection;
  confirm `source_provider` is correctly stamped per input set (an ESPN row must never be tagged
  `matchbook` or vice versa); confirm the write is atomic and the bootstrap-empty path is exercised by a
  test (first-ever-run case, mirroring `matchbook_conform`'s own bootstrap test coverage).

### Step S7 — `definitions.py` wiring: job selections, `deps=`, and the empirical orchestration guardrail
- **Goal:** `identity_reconciliation` is materialized in both `espn_job` and `matchbook_job`;
  `matchbook_conform` gains a real same-run dependency on it; both jobs launch cleanly through the real
  daemon/queued path with no `CircularDependencyError`.
- **Spec trace:** FR-009 (same-run visibility for the Python mint path — research.md §4), FR-012 (every
  provider covered), Constraints (asset-dependency-graph visibility).
- **Red (failing test first):** Per `plan` skill's Dagster-orchestration rule, the falsifiable check here
  is NOT `dagster definitions validate` alone — it's a real queued run. Before this step: `defs` doesn't
  reference `identity_reconciliation` at all, so a queued `matchbook_ingestion` run would not execute it,
  and `matchbook_conform`'s mint decisions would not see same-run bridges (directly observable: run the
  Scenario-1 bidirectional fixture from quickstart.md through a queued run and see it NOT converge).
- **Implementation:** In `definitions.py`: add `identity_reconciliation` to the `assets=[...]` list;
  add `AssetKey(["identity_reconciliation"])` (or the asset itself) to both `espn_assets` and
  `matchbook_assets` `AssetSelection`s; change `matchbook_conform`'s `deps=` to include
  `AssetKey(["identity_reconciliation"])` alongside its existing `AssetKey(["matchbook_events_bronze"])`.
  No change to `dbt_models`' own construction (S3 already made its SQL-level dependency untracked by
  design).
- **Green criterion:** `uv run dagster definitions validate -w workspace.yaml` passes (necessary, not
  sufficient); then, per quickstart Scenario 4, a **queued** run (through the UI/daemon, not `dagster job
  execute`) of `matchbook_ingestion` launches without `CircularDependencyError` and its step-order shows
  `identity_reconciliation` completing before `matchbook_conform` starts; a queued `espn_ingestion` run
  also launches cleanly and executes `identity_reconciliation`.
- **Guardrails to satisfy:** the Dagster orchestration wiring guardrail (guardrail register) — real
  queued-run verification, not just static validation.
- **Self-review checkpoint:** independently launch both queued runs (not by trusting the implementer's
  report) and inspect the actual step ordering in the Dagster UI/run logs; confirm no
  `CircularDependencyError` at `Definitions` build time; confirm `identity_reconciliation` appears in
  BOTH job selections, not just one (FR-012's most likely failure mode is silently covering only one
  provider's job).

### Step S8 — End-to-end bidirectional convergence proof
- **Goal:** Demonstrate, through the full stack (bronze fixtures → `identity_reconciliation` →
  `matchbook_conform`/dbt resolution), that a team minted by ESPN first and later bridged from a
  differently-spelled Matchbook name converges to one canonical `team_id`/`match_id` — and that the
  reverse mint order does too.
- **Spec trace:** User Story 1 (all 3 acceptance scenarios — the feature's primary reason to exist),
  SC-001, SC-002 (no false-positive merges, using a known-negative pair), SC-004, FR-010.
- **Red (failing test first):** Extend `tests/conform/test_mint_chain.py` with two new cases — (a) ESPN
  mints under name A, then a synthetic Matchbook event under fuzzy-matching name B is run through
  `run_conform` with the S6-shaped learned-alias bridge already present, asserting the resulting
  `home_team_id`/`away_team_id` equal ESPN's `team_id`, not a fresh mint; (b) the reverse order
  (Matchbook mints first, ESPN's dbt-side resolution — simulated via `resolve_team_id_expr`'s Python
  parity twin — resolves onto Matchbook's id). Both fail before S3/S4/S6 land (today, each provider
  independently self-mints, producing two different ids). Also add one known-negative case (two
  genuinely different clubs whose names happen to score below threshold) asserting NO convergence — this
  is the SC-002 false-positive guard.
- **Implementation:** No new production code — this step wires S1–S7's pieces together in a single
  end-to-end test and, separately, a real `dbt build` pass proving the SQL side converges too (extending
  S3's green criterion to a full `dbt build --select intermediate.int_team+
  intermediate.int_match+ intermediate.int_espn_team_link+ --indirect-selection=empty` against seeded
  bronze fixtures for both orderings).
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/conform/test_mint_chain.py` passes including
  the 3 new cases; the extended `dbt build` selection passes with the expected single-row convergence
  for the bridged pair and continued separation for the known-negative pair.
- **Guardrails to satisfy:** dbt tests; full pytest suite green (`PYTHONPATH=src uv run pytest`);
  `uv run pre-commit run --all-files` clean.
- **Self-review checkpoint:** this is the step where a reviewer should be MOST adversarial — confirm the
  "both orders converge" claim is tested as two genuinely distinct scenarios (not one test parameterized
  to look like two); confirm the known-negative case is a real pair that would otherwise be a plausible
  false-positive risk (not a trivially-dissimilar pair that proves nothing); confirm SC-004 (match-level
  convergence, not just team-level) is actually asserted on `int_match`/`match_id`, not just `int_team`.

## Sequencing & dependencies

```
S0 (scoring constants)
 ├─▶ S1 (reconcile.py, needs S0's constants)
 └─▶ S4 (resolve.py + matchbook.py wiring, needs S0's constants indirectly via S1's later use, but
         directly only needs its own new parameter — can run parallel to S1)

S2 (dbt macro) ─▶ S3 (wire macro into 3 SQL sites, needs S2's macro to exist)

S1 + S3 ─▶ S6 (identity_reconciliation asset — needs reconcile.py from S1 for scoring, and needs S3's
                bootstrap-empty file shape/location settled so the asset writes what dbt expects to read)

S4 ─▶ S5 (parity test needs S4's real implementation to test against)

S6 ─▶ S7 (definitions.py wiring needs the asset module from S6 to exist before it can be selected)

S3 + S4 + S6 + S7 ─▶ S8 (end-to-end proof needs every piece: SQL formula, Python formula, the asset
                          producing real bridges, and the job wiring executing them in order)
```

Repo-gotcha-driven edges: S3 must follow S2 (macro must exist before it's called). S6 must follow S1
(needs `find_learned_aliases`) and should follow S3 (so the bootstrap-empty file it writes matches what
`int_team.sql`'s `read_parquet()` literal already expects at the settled path — avoids a rework if the
path/columns were decided independently in each step). S7 is Dagster-wiring-only and therefore last
before the full-stack proof (S8), consistent with this repo's existing precedent of wiring job selection
only once the underlying assets are real (mirrors how `matchbook_conform` itself was built before being
added to `matchbook_assets`).

## Complexity Tracking

None. No Constitution Check violation requires justification — the plan adds one new asset, one new
pure module, one relocated module, one new macro, and extends three existing dbt models with the same
formula each; no new architectural layer, no new abstraction beyond what FR-006's cross-path parity
requirement mechanically demands.

## Assumptions

- Everything listed in `spec.md`'s own *Assumptions* section carries forward unchanged (reused
  confidence tiers, self-healing convergence with no backfill task, team-identity-only scope, two
  providers today).
- `research.md`'s Decision 4 (raw `read_parquet()`, not `source()`, for the bridge file in dbt SQL) is
  the load-bearing technical assumption of this plan — if S7's empirical guardrail somehow shows the
  3-tier `source()` approach would NOT actually raise `CircularDependencyError` in current
  dagster-dbt (e.g. because of a library upgrade since the `int_match.sql` comment was written), that
  would be a genuine, welcome discovery, but should not change the plan's *design* — the raw-literal
  approach has zero downside risk and identical eventual-convergence behaviour to the source-tracked one
  under this codebase's existing self-healing philosophy, so there's no reason to take on the risk even
  if it turned out to be unnecessary.
- The existing `tests/conform/` pytest harness, `uv run pytest` invocation, and importlib test-discovery
  mode are assumed stable for this feature's new/extended test files (no harness changes needed).
- `canonical_team_export.parquet`'s existing "possibly a few minutes stale" tolerance (already accepted
  for `matchbook_conform`) is assumed acceptable for `identity_reconciliation`'s read of the same file —
  consistent with the spec's own Edge Case on canonical-pool staleness.

## Open Questions

- None.

## Traceability

| Spec scenario / FR / SC | Unit(s) | Step(s) | Guardrail(s) |
|---|---|---|---|
| User Story 1 Scenario 1 (ESPN-first) | end-to-end convergence | S8 | dbt build, pytest |
| User Story 1 Scenario 2 (Matchbook-first, previously-broken direction) | end-to-end convergence | S8 | dbt build, pytest |
| User Story 1 Scenario 3 (match-level convergence) | end-to-end convergence | S8 | dbt build, pytest |
| User Story 2 Scenario 1 (high-confidence auto-bridge) | `find_learned_aliases` | S1 | pytest |
| User Story 2 Scenario 2 (medium-confidence needs_review) | `find_learned_aliases` | S1 | pytest |
| User Story 2 Scenario 3 (below-threshold no-bridge) | `find_learned_aliases` | S1 | pytest |
| User Story 2 Scenario 4 (ambiguous tie no-bridge) | `find_learned_aliases` | S1 | pytest |
| User Story 3 Scenario 1 (traceability columns) | `identity_reconciliation` artifact | S6 | pytest (artifact assertion) |
| FR-001 (identify unmatched raw names) | `identity_reconciliation` | S6 | pytest |
| FR-002 (fuzzy comparison + score) | `find_learned_aliases` | S1 | pytest |
| FR-003 (high-confidence auto-bridge) | `find_learned_aliases` | S1 | pytest |
| FR-004 (medium-confidence needs_review) | `find_learned_aliases` | S1 | pytest |
| FR-005 (no bridge below threshold / on tie) | `find_learned_aliases` | S1 | pytest |
| FR-006 (cross-path formula parity) | macro + `resolve_team_id` + parity test | S2, S3, S4, S5 | dbt test, pytest |
| FR-007 (order-independent bridging) | `resolve_team_id` both-order case, SQL 3-tier | S3, S4, S8 | pytest, dbt build |
| FR-008 (bridge traceability columns) | `identity_reconciliation` schema | S6 | pytest |
| FR-009 (same-run visibility for Matchbook mint path) | `matchbook_conform` deps edge | S7 | real queued run |
| FR-010 (idempotent self-healing convergence) | recompute-from-scratch design + S8 proof | S6, S8 | pytest, dbt build |
| FR-011 (no seed write-back) | static check | S1, S6 self-review | self-review checkpoint |
| FR-012 (every provider covered) | job selection wiring | S7 | real queued run |
| FR-013 (no DuckLake connection) | static check | S1, S6 self-review | self-review checkpoint |
| SC-001 (convergence within one additional run) | end-to-end | S8 | pytest, dbt build |
| SC-002 (zero false-positive merges) | known-negative case | S8 | pytest |
| SC-003 (100% bridge traceability) | `identity_reconciliation` schema | S6 | pytest |
| SC-004 (match-level convergence) | end-to-end, `int_match` | S8 | dbt build |
| SC-005 (cross-path parity) | parity test | S5 | pytest |
