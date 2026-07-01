# Implementation Plan: Cross-Provider Conform — Symmetric Resolve-or-Mint for Every Provider

**Feature directory**: `specs/012-cross-provider-conform/`
**Date**: 2026-07-01
**Spec**: `spec.md`
**Status**: Done

## Summary

Make "conform" (resolve raw provider records onto canonical entities — link to an existing canonical row
OR mint a new one) a first-class CROSS-PROVIDER concern with full referential integrity: no minted match
without its complete season→league→team chain, and no duplicate club/competition. The approach: (1) relocate
the Python engine from `src/data_platform/matchbook/conform/` to a neutral `src/data_platform/conform/`
(per-provider modules + a shared `resolve.py` identity authority), removing the old path outright
(constitution I); (2) add a human-curated `league_aliases` seed and route every provider's league minting
through it (killing the bogus `md5('matchbook_football')` constant); (3) extend `int_team`/`int_league`/
`int_season` with the same `read_parquet` + `UNION ALL` provider-additions pattern `int_match` already uses,
so minting a match emits its whole seed-resolved chain into four bootstrap-empty additions files per
provider; (4) add the two missing Matchbook link-table FK relationships tests (Spec 010 OQ3); (5) scaffold
football-data to the shared contract without implementing its matching; (6) ripple the four docs. Correctness
is proven by dbt relationships/unique/not_null tests, pytest over the shared resolver, and Pandera on the
addition frames — never by weakening a gate.

## Technical Context

**Language/Version**: Python 3.12 (`>=3.12,<3.13`); dbt SQL (dbt-duckdb 1.10.1+).
**Primary Dependencies**: Dagster, dbt-duckdb, DuckDB (>=1.5.2, DuckLake), pandas, Pandera, Pydantic v2, pytest.
**Storage**: Parquet on local FS (bronze + silver additions/exports); canonical tables in DuckLake (Postgres-backed catalog).
**Testing**: dbt tests (relationships/unique/not_null/singular) via `dbt build`; pytest under `tests/`; Pandera per addition frame.
**Target Platform**: Local CLI + scheduled Dagster jobs.
**Project Type**: single project (medallion data platform).
**Performance Goals**: N/A (correctness/structure feature, not throughput).
**Constraints**: Python assets MUST NOT open a DuckLake connection (even read-only); single-writer `warehouse.duckdb`; `read_parquet` errors on missing file → bootstrap-empty; dbt AssetKey = schema-folder prefix only; no `from __future__ import annotations` in asset modules; config via `pydantic-settings`; ruff `E,W,F,I,UP,B,C4,SIM`.
**Scale/Scope**: 4 canonical tables, 1 new seed, 2 new exports, 2 new FK tests, ~4 new Python modules (1 relocated engine, 1 shared resolver, 1 football-data placeholder, contracts), 4 ripple docs.

## Constitution Check

| Principle (constitution) | Compliance in this plan |
|--------------------------|-------------------------|
| I. No Backward Compatibility | Old `src/data_platform/matchbook/conform/` is REMOVED outright (S3); no re-export shim. `matchbook_canonical_additions.parquet` is RENAMED to `_match_additions` in one clean replace (S5), not dual-read. The bogus `md5('matchbook_football')` is deleted, not left as a fallback. |
| II. No Reward Hacking | No placeholder/stub outside test contexts (the football-data body is a documented `NotImplementedError` interface, explicitly in-scope per US5 — but its additions bootstrap is real). No dbt relationships/unique/not_null test is weakened, narrowed, `xfail`ed, or dropped to admit minted rows — every step fixes the DATA PATH. Any constraint-bypass is escalated (Open Questions), never self-approved. |
| III. Test-First | Every step writes a genuinely-failing-first check before the code: dbt relationships tests go red for an orphaned chain (S6), the composite-unique singular test goes red on a dup (S4), pytest parity tests fail before `resolve.py` exists (S2), the blank-name guard test fails before the guard (S8), the FK-link tests bite on an absent id (S9). |
| IV. Honesty & Permission to Fail | Green criteria are exact commands; a failing gate is reported, not bypassed. The football-data placeholder is honestly labelled not-implemented (spec Assumption 1). |
| V. Surface Contradictions | Knock-on effects surfaced in Open Questions (the `team_aliases` seed has NO data tests today; `_seeds.yml` does not exist; `dbt_utils` availability for the composite test). |

## Project Structure

```text
specs/012-cross-provider-conform/
├── spec.md
├── plan.md            # this file
├── research.md        # Phase 0 — D1–D10 decisions
├── data-model.md      # Phase 1 — canonical entities, seeds, additions, exports, resolver
├── contracts/
│   ├── shared_resolver.md          # conform/resolve.py pure-function contract
│   └── provider_conform_interface.md  # per-provider module + four-file additions contract
├── quickstart.md      # Phase 1 — 8 runnable validation scenarios
└── tasks.md           # Phase 2 — produced later by the `tasks` skill, NOT here
```

**Source layout touched**:
- NEW `src/data_platform/conform/` — `resolve.py` (shared), `matchbook.py` (relocated engine),
  `football_data.py` (placeholder), `__init__.py`, + relocated Matchbook helpers
  (`event_name.py`, `overrides.py`, `scoring.py` under a `conform/matchbook_*` grouping).
- REMOVED `src/data_platform/matchbook/conform/` (entire package).
- `src/data_platform/assets/intermediate/matchbook_conform.py` — imports rewired to `...conform.matchbook`;
  bootstrap extended to four additions files; AssetKey unchanged (D2).
- `src/data_platform/config.py` — rename additions property; add league/season canonical export awareness if needed.
- `dbt/data_platform/seeds/league_aliases.csv` (NEW) + `dbt/data_platform/seeds/_seeds.yml` (NEW).
- `dbt/data_platform/models/intermediate/` — `int_team.sql`, `int_league.sql`, `int_season.sql` gain the
  additions UNION; `int_match.sql` renamed additions path + stale-comment fix; `_intermediate.yml` gains 2 FK tests.
- `dbt/data_platform/models/marts/exports/` — `canonical_league_export.sql`, `canonical_season_export.sql` (NEW).
- `dbt/data_platform/tests/` — singular composite-unique test for `league_aliases` (if no `dbt_utils`).
- `tests/conform/` (relocated from `tests/matchbook/test_conform.py`) + new resolver/parity/guard tests.
- Docs: `CLAUDE.md`, `ARCHITECTURE.md`, `ERD.md`, `data flows.md`.

## Skills to use

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| Establish the missing `league_aliases`/additions/bootstrap conventions | `create-rule` | available (invoked in S1) |
| dbt model + tests / warehouse change | (no dedicated dbt-build skill) — plan explicitly from existing `int_*` patterns | — (proceed without; capture via `self-learn`) |
| Architecture conformance of the relocation | `code-architecture-review` | available (S3 self-review) |
| Verify the change actually runs (Dagster queued run) | `verify` / `run` | available (S7, S11) |
| Per-step diff review | `code-review` | available (each step self-review) |
| Capture learnings afterwards | `self-learn` | available (post-build) |
| Add a new bronze source (if football-data conform lands later) | `bronze-ingest-source` | available (out of scope here) |

Gap note: there is no "build a dbt canonical model" skill; the union/keep-one pattern is followed from the
existing `int_match.sql` and `int_team.sql`. This is a repeatable pattern — flagged for `self-learn` to
codify a rule/skill after the build, not a blocker.

## Convention & rule audit (resolved before implementation)

| Artifact type | Governing convention | Status |
|---------------|----------------------|--------|
| New Python module (`conform/*.py`) | CLAUDE.md *Python conventions* (PEP8/ruff, `pathlib.Path`, Pydantic at boundaries, type-annotate); constitution I (remove legacy) | exists |
| Dagster asset module (relocated import) | CLAUDE.md: no `from __future__ import annotations`; AssetKey/`deps` wiring; `BronzeAwareTranslator` source-map | exists |
| Config field (`pydantic-settings`) | CLAUDE.md: add typed field/property in `config.py`, check for property-name collision (matchbook_* props at 99–129) | exists |
| New dbt model (`int_*` union; exports) | CLAUDE.md gold two-file export pattern + `int_match.sql` UNION-ALL additions pattern; `+database: lake` | exists |
| dbt relationships/unique/not_null tests | `_intermediate.yml` existing tests; constitution II/III (never weaken) | exists |
| **Provider four-file additions convention** (`<provider>_canonical_{match,team,league,season}_additions.parquet`) naming + seed-first resolution + bootstrap-empty discipline | CLAUDE.md documents match-additions + bootstrap for `int_match`/t60 only; the FOUR-file generalisation is NOT yet a written rule | **created this run (S1, via `create-rule`) — pending user approval; recorded as OQ-A** |
| **`league_aliases` seed** (columns, composite-unique key, ESPN-anchor invariant, seed-only no-auto-learn) | `team_aliases` precedent exists but has NO data tests and there is NO `_seeds.yml`; the league seed's key/tests are a NEW convention | **created this run (S1, via `create-rule` + new `_seeds.yml`) — pending user approval; recorded as OQ-A** |
| **New FK relationships-test guardrail** for `int_matchbook_team_link`/`int_matchbook_league_link` | `_intermediate.yml` relationships-test pattern exists (espn links, matchbook event link) | exists (pattern) — applied in S9 |
| pytest unit tests + `tests/` layout | CLAUDE.md pytest section; harness EXISTS (`tests/matchbook/`, `tests/conform/` to be added mirroring it) | exists |
| Pandera frame contract (additions frames) | CLAUDE.md boundary-validation rule; `models/validation.py` + `tests/matchbook/test_contracts.py` pattern | exists |
| Singular dbt test (composite-unique) | standard dbt `tests/*.sql` returns-rows-⇒-fail; no in-repo precedent but a core dbt facility | exists (dbt built-in) |

**Gate:** no step below depends on a row still marked `gap`. The two `created this run` rows (the four-file
additions convention + the `league_aliases` seed convention) are authored in **S1 via `create-rule`** and
committed BEFORE the steps that depend on them (S4–S10). Because this run is **non-interactive**, S1 drafts
the rule and records it as **OQ-A (needs user sign-off)** rather than auto-committing a rule on the user's
behalf — see Open Questions. No `gap` rows remain.

## Testable units (BDD → tests)

| Unit | Spec trace (scenario / FR / SC) | Test facility | Failing-first assertion |
|------|----------------------------------|---------------|-------------------------|
| U1 `resolve_team_id` mirrors dbt seed resolution | US2 AC1/AC2 / FR-002 / SC-002 | pytest | seeded name → seed team_id, unseen → md5(lower(name)); fails before `resolve.py` exists |
| U2 `resolve_league_id` seed-first + provider-scoped mint | US2 AC3/AC4 / FR-002,FR-012 / SC-008 | pytest | mapped key → md5(league_slug); unmapped → deterministic provider-scoped id; NOT md5('matchbook_football') |
| U3 `derive_season_id` = md5(league_id\|year) | US2 AC3 / FR-012 | pytest | equals dbt `int_season` formula; fails before helper exists |
| U4 `compute_canonical_match_id` == dbt macro (parity) | US3 AC2 / FR-005,FR-007 / SC-003,E8 | pytest | Python output == recomputed dbt macro output for same inputs |
| U5 Blank parsed name is NOT minted, routed to exceptions | E5 / FR-013 | pytest | a blank home/away name produces an exception row, no addition row |
| U6 Minting a match emits full un-resolved chain (team×2, season, league) | US1 AC1 / FR-001 / SC-001 | pytest + Pandera | mint emits 4 additions files' rows for un-resolved members; frames validate |
| U7 `league_aliases` seed loads with correct tests | FR-015 | dbt test | `league_id` not_null & NOT unique; `(provider,provider_key)` unique (singular); provider accepted_values |
| U8 `int_team` unions provider team additions, keep-one | US1 AC2 / FR-003 / E3 | dbt test | minted team row appears; `unique(team_id)` holds; fails before UNION added |
| U9 `int_league` unions provider league additions, keep-one | US1 AC2 / FR-003 / E3 | dbt test | minted league row appears; `unique(league_id)` holds |
| U10 `int_season` unions provider season additions, keep-one | US1 AC2 / FR-003 | dbt test | minted season row appears; season→league relationships passes |
| U11 `int_match` renamed additions path + full chain resolves | US1 AC2/AC3 / FR-001 / SC-001 | dbt test | all four int_match/int_season relationships tests pass with minted chain (red today) |
| U12 Two providers same fixture → one match_id | E2 / SC-003 | dbt test + pytest | duplicate collapses to 1 row via keep-one; parity confirms same match_id |
| U13 `int_matchbook_team_link.team_id` FK test bites | US4 AC1/AC2 / FR-009 / SC-005 | dbt test | passes with chain present; RED when a team_id is absent from int_team |
| U14 `int_matchbook_league_link.league_id` FK test bites | US4 AC1 / FR-009 / SC-005 | dbt test | relationships test present + passes; RED when league_id absent |
| U15 `canonical_league_export`/`canonical_season_export` produce Parquet | FR-011 | artifact assertion | files at silver/canonical/{league,season}.parquet with correct columns |
| U16 Old `matchbook/conform` path removed; imports rewired | US3 AC1/AC3 / FR-006 / SC-004 | pytest + grep | `grep matchbook/conform src tests` empty; conform output equivalent pre/post move |
| U17 Asset relocation keeps lineage (queued run) | FR-008 | artifact/run assertion | `dagster job execute -j matchbook_conform_job` launches; bronze→conform→dbt edges resolve |
| U18 football-data scaffold green-when-empty | US5 AC1/AC2 / FR-010 / SC-006 | dbt test + pytest | `dbt build int_match int_team` green with empty football_data additions; module declares interface |
| U19 Docs describe symmetric cross-provider conform | FR-014 / SC-007 | artifact assertion (grep) | no "canonical is ESPN-only"/"conform is Matchbook-only"/stale `try_read_parquet` text remains |

## Guardrail register

| Guardrail | How verified in place | Covered by step |
|-----------|------------------------|-----------------|
| ruff check + format (pre-commit) | `uv run pre-commit run --all-files` clean on changed files (pre-existing SIM105 in MCP server is not ours) | all steps; verified S3, S8, S10 |
| pre-commit installed | `uv run pre-commit install` (once per clone) | S0 |
| pytest harness works | trivial red→green confirmed; `PYTHONPATH=src uv run pytest tests/conform` | S0/S2 |
| dbt tests via `dbt build` (relationships/unique/not_null/singular) | `dbt parse` then `dbt build --select <model>` green; NEVER weaken a test | S4,S6,S9,S10 |
| Boundary validation (Pandera on addition frames) | a malformed additions frame raises; conforming passes | S6 |
| Idempotency / re-run safety | run conform twice; keep-one collapses; identical output | S6,S11 |
| Python NEVER opens DuckLake (even read-only) | conform reads only bronze + silver/canonical Parquet exports; grep for `duckdb.connect` in conform = none | S2,S6 |
| Bootstrap-empty additions files (read_parquet errors on missing) | all four files per provider present before dbt; `dbt build` green with no minting | S6,S8 |
| dbt AssetKey / lineage intact after relocation (DAEMON/queued path, not just `definitions validate`) | `dagster job execute -j matchbook_conform_job` launches and edges resolve | S7,S11 |
| No `from __future__ import annotations` in asset module | asset module unchanged in that respect; ruff/`dagster definitions validate` | S3,S7 |
| Constitution I/II/III | old path removed; no weakened gate; test-first per step | all |

## Implementation Steps

### Step S0 — Confirm pytest + pre-commit harness and dbt parse baseline
- **Goal:** Establish the known-good baseline so every later red/green is meaningful; confirm the existing pytest harness runs and `dbt parse` succeeds.
- **Spec trace:** setup — enables S2–S11.
- **Red (failing test first):** Run `PYTHONPATH=src uv run pytest tests/matchbook/test_conform.py` and `( cd dbt/data_platform && uv run --project ../.. dbt parse --profiles-dir . )`; capture current green baseline. Add one trivial `tests/conform/test_smoke.py::test_placeholder_fails` asserting `False`, confirm RED, then delete/flip — proves the (new) `tests/conform/` dir is collected.
- **Implementation:** `uv run pre-commit install`; create `tests/conform/` dir; no product code.
- **Green criterion:** existing suite green; `dbt parse` exit 0; smoke test collected and controllable.
- **Guardrails to satisfy:** pre-commit installed; pytest harness works.
- **Self-review checkpoint:** independent agent confirms the harness is real (a deliberately-broken assertion is RED), no product code smuggled in, and the baseline is honestly recorded.

### Step S1 — Author the missing conventions (four-file additions + league_aliases seed) via create-rule
- **Goal:** Close the two `created this run` audit rows BEFORE any dependent step: (a) the provider four-file additions convention (naming, seed-first resolution, bootstrap-empty discipline, no-DuckLake); (b) the `league_aliases` seed convention (columns, composite `(provider,provider_key)` unique, `league_id` not-unique/not-null, ESPN-anchor additive, seed-only).
- **Spec trace:** FR-014,FR-015,FR-016,FR-003 (convention hard gate) — enables S4,S6,S8,S9,S10.
- **Red (failing test first):** N/A (rule-authoring). The "failure" is the audit gate itself: `validate-plan.py` fails if a row stays `gap`. Draft the rule text; verify it reads true/false-framed.
- **Implementation:** Invoke `create-rule` to draft both rules targeting project `CLAUDE.md` *Non-obvious constraints*. Because this run is non-interactive, DO NOT auto-commit on the user's behalf — record the drafted rule text and mark **OQ-A (needs sign-off)**. Commit as a `docs:` atomic commit only after approval.
- **Green criterion:** rule text drafted, duplicate-checked against CLAUDE.md, recorded in OQ-A; `validate-plan.py` convention-audit gate has zero `gap` rows.
- **Guardrails to satisfy:** constitution V (surface, don't silently commit); convention-before-code hard gate.
- **Self-review checkpoint:** reviewer confirms the drafted rules are concrete/true-false, match the spec's FR-015/FR-016 wording, and that the plan does not treat an unapproved rule as committed.

### Step S2 — Shared resolver `conform/resolve.py` (pure functions) with parity tests
- **Goal:** Create the single identity authority: `resolve_team_id`, `resolve_league_id`, `mint_provider_scoped`, `derive_season_id`, `compute_canonical_match_id`, `is_mintable_name`.
- **Spec trace:** US2 AC1-4 / FR-002,FR-005,FR-007,FR-012 / SC-003,SC-008 / E8 — units U1,U2,U3,U4.
- **Red (failing test first):** `tests/conform/test_resolve.py`: seeded-name→seed id, unseen→md5(lower(name)); mapped league key→md5(league_slug), unmapped→provider-scoped and NOT md5('matchbook_football'); `derive_season_id`==md5(league_id\|year); `compute_canonical_match_id` matches the macro's concat_ws('|')+md5 shape. Fails (module absent).
- **Implementation:** Write `conform/resolve.py` as pure functions taking a seed DataFrame; move `compute_canonical_match_id` from `engine.py:77-85`. No DuckLake, no I/O.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/conform/test_resolve.py` green; ruff clean.
- **Guardrails to satisfy:** Python-never-opens-DuckLake; pytest; ruff.
- **Self-review checkpoint:** reviewer confirms the formulas are byte-identical to `int_team.sql:27`, `int_season.sql:22`, and `macros/canonical_match_id.sql`; the tests can fail (revert a formula → red); no hardcoded ids.

### Step S3 — Relocate Matchbook engine to conform/matchbook.py; remove old package (constitution I)
- **Goal:** Move `matchbook/conform/{engine,event_name,overrides,scoring}.py` to `conform/`, rewire to use `resolve.py`, remove `src/data_platform/matchbook/conform/` outright, update the asset import.
- **Spec trace:** US3 AC1-3 / FR-006,FR-008 / SC-004 — units U16,U17 (U17 fully in S7/S11).
- **Red (failing test first):** `tests/conform/test_relocation.py`: `grep`-style assertion that `import data_platform.matchbook.conform` raises `ModuleNotFoundError`, and that `from data_platform.conform.matchbook import run_conform` succeeds. Plus move `tests/matchbook/test_conform.py` → `tests/conform/test_conform.py` and assert conform output equivalent to a captured pre-move fixture (byte-for-byte resolved/exceptions/additions for identical input). Fails before the move.
- **Implementation:** Relocate modules; delete old package; update `assets/intermediate/matchbook_conform.py` import to `...conform.matchbook`; keep AssetKey `["matchbook_conform"]` (D2) so `assets/dbt.py:35` + `deps` need no change.
- **Green criterion:** `grep -rn "matchbook/conform\|matchbook\.conform" src tests` empty; `PYTHONPATH=src uv run pytest tests/conform` green; `dbt parse` + `dagster definitions validate` succeed.
- **Guardrails to satisfy:** constitution I (no shim); ruff; no `from __future__ import annotations` re-added to the asset module.
- **Self-review checkpoint:** `code-architecture-review` confirms the old path is GONE (not aliased), the module boundary is clean (Matchbook parsing not in `resolve.py`), and output equivalence holds.

### Step S4 — Add league_aliases seed + _seeds.yml + composite-unique test
- **Goal:** Create `seeds/league_aliases.csv` (with the minimum ESPN+Matchbook Premier-League rows to make US2 testable) and `seeds/_seeds.yml` with the FR-015 tests.
- **Spec trace:** US2 AC3 / FR-015 / SC-002 — unit U7.
- **Red (failing test first):** `dbt build --select league_aliases` with `_seeds.yml` tests present FAILS before the CSV/tests exist; add a deliberate duplicate `(provider,provider_key)` row and confirm the composite-unique singular test goes RED, then remove it.
- **Implementation:** CSV columns `league_id,canonical_name,provider,provider_key`; rows record ESPN's `eng.1` mapping + a Matchbook `15|<category>` row onto the same `md5('eng.1')`. `_seeds.yml`: `league_id` not_null (NOT unique), `provider_key` not_null, `provider` not_null+accepted_values, and the composite-unique via a singular test in `dbt/data_platform/tests/` (D6; use `dbt_utils.unique_combination_of_columns` only if already installed).
- **Green criterion:** `dbt build --select league_aliases` green with all tests; ESPN `int_league`/`int_match` unchanged (byte-for-byte).
- **Guardrails to satisfy:** dbt tests; never weaken (the composite-unique must genuinely bite).
- **Self-review checkpoint:** reviewer confirms `league_id` is NOT unique-tested, the composite test bites on a dup, and ESPN identity is untouched (`md5('eng.1')` recorded, not redefined).

### Step S5 — Rename matchbook_canonical_additions → _match_additions (clean replace)
- **Goal:** Rename the match-additions file consistently across all consumers (constitution I, no dual-read).
- **Spec trace:** FR-003 / spec Assumption 3 / E4.
- **Red (failing test first):** `tests/conform/test_additions_naming.py` asserts the engine writes `matchbook_canonical_match_additions.parquet` and that no code references the old name. Fails before rename.
- **Implementation:** Update engine write path, `config.py` property, `int_match.sql:83-85` `read_parquet`, `_sources.yml:77-80` source name+location, and `matchbook_conform.py:44-47` bootstrap — together.
- **Green criterion:** `grep -rn "matchbook_canonical_additions\b" src dbt` finds only the new `_match_additions` name; `dbt parse` succeeds; conform+`dbt build --select int_match` green.
- **Guardrails to satisfy:** constitution I; dbt tests.
- **Self-review checkpoint:** reviewer confirms the OLD name is gone everywhere (no fallback read), and `int_match` still builds.

### Step S6 — Extend conform to mint the full chain into four additions files (Matchbook)
- **Goal:** Replace `_mint_canonical_addition` (engine.py:211-244) so minting a match resolves league via `league_aliases` (killing `md5('matchbook_football')`), derives season_id correctly, resolves teams via `team_aliases`, and emits team/season/league additions for un-resolved chain members; bootstrap all four files empty; read canonical exports (incl. new league/season) to detect already-resolved members. Add Pandera schemas for the four frames.
- **Spec trace:** US1 AC1-3 / FR-001,FR-002,FR-003,FR-011,FR-012,FR-013,FR-016 / SC-001,SC-008 / E1,E5,E9,E10 — units U5,U6,U15(read),U8-U11(data).
- **Red (failing test first):** `tests/conform/test_mint_chain.py`: minting a match with an unseen team + unmapped league emits a team-addition (md5(lower(name))), a season-addition, a league-addition (provider-scoped), and a match-addition; a seeded team reuses the seed id; a mapped league yields md5(league_slug); a blank name → exceptions, no addition (E5). Pandera rejects a malformed frame. Fails before the new minting logic.
- **Implementation:** Rewrite the mint path in `conform/matchbook.py` using `resolve.py`; extend `_write_conform_outputs` to write four additions files; extend the asset bootstrap (`matchbook_conform.py`) to four files; read `silver/canonical/{league,season}.parquet` (produced in S8) for resolution. Add Pandera schemas.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/conform/test_mint_chain.py` green; ruff clean; no `duckdb.connect` in `conform/`.
- **Guardrails to satisfy:** Python-never-opens-DuckLake; Pandera boundary; bootstrap-empty; idempotency (run twice → same additions).
- **Self-review checkpoint:** reviewer confirms `md5('matchbook_football')` is GONE, every minted match emits its full un-resolved chain, blank names route to exceptions (not minted), and the parity with dbt formulas holds.

### Step S7 — Add canonical_league_export + canonical_season_export; wire asset deps
- **Goal:** Produce the two new external-Parquet exports the Python conform reads for resolution (FR-011).
- **Spec trace:** FR-011 — unit U15.
- **Red (failing test first):** `tests/conform/test_exports.py` (artifact assertion) expects `silver/canonical/league.parquet` and `season.parquet` with the correct columns after `dbt build --select canonical_league_export canonical_season_export`. Fails before the models exist.
- **Implementation:** Add the two export models mirroring `canonical_team_export.sql`; add `AssetKey(["marts","canonical_league_export"])` and `canonical_season_export` to the conform asset `deps` and the `matchbook_conform_assets` selection so lineage/order is correct.
- **Green criterion:** `dbt build --select canonical_league_export canonical_season_export` writes both files; `dagster job execute -j matchbook_conform_job` launches with the new deps (daemon/queued-path check, not just `definitions validate`).
- **Guardrails to satisfy:** dbt external-materialisation pattern; lineage-via-queued-run.
- **Self-review checkpoint:** reviewer confirms the exports match the two-file convention, the asset `deps` form real edges (queued run resolves them), and Python reads the FILE not the catalog.

### Step S8 — Union provider additions into int_team / int_league / int_season (keep-one)
- **Goal:** Make the three canonical tables the union of ESPN + per-provider additions, de-duped keep-one on the id (mirrors `int_match`).
- **Spec trace:** US1 AC2/AC3 / FR-003 / SC-001,SC-002 / E3 — units U8,U9,U10.
- **Red (failing test first):** With a minted Matchbook chain present (from S6) but the UNIONs NOT yet added, `dbt build --select int_match int_season` FAILS the relationships tests (orphaned team/season/league). This IS the red-today state (SC-001). Confirm red, then add the UNIONs to go green.
- **Implementation:** Add to each of `int_team.sql`/`int_league.sql`/`int_season.sql` a `read_parquet('$DATA_DIR/silver/matchbook_canonical_<entity>_additions.parquet')` (and football_data's, bootstrap-empty) UNION-ALL CTE, then `distinct`/`qualify row_number() ... = 1` keep-one on the id.
- **Green criterion:** `dbt build --select int_team int_league int_season int_match` green; `unique`/`not_null`/relationships all pass with minted rows present.
- **Guardrails to satisfy:** dbt tests (NOT weakened); bootstrap-empty; keep-one idempotency.
- **Self-review checkpoint:** reviewer confirms no relationships/unique test was weakened, the keep-one collapses seed-duplicates to one row (E3), and the four int_match/int_season relationships tests are GREEN because the chain now exists (fixed data path, not a softened test).

### Step S9 — Add the two missing Matchbook link-table FK relationships tests
- **Goal:** Add `relationships` tests: `int_matchbook_team_link.team_id`→`int_team.team_id` and `int_matchbook_league_link.league_id`→`int_league.league_id` (Spec 010 OQ3).
- **Spec trace:** US4 AC1/AC2 / FR-009 / SC-005 — units U13,U14.
- **Red (failing test first):** Add both `relationships` tests to `_intermediate.yml`. Introduce a Matchbook team-link row whose `team_id` is absent from `int_team` and confirm the team-link test goes RED (proves it bites), then remove the bad row.
- **Implementation:** Edit `_intermediate.yml` `int_matchbook_team_link.team_id` and `int_matchbook_league_link.league_id` to add the `relationships` blocks (matching the espn-link pattern at :217-219, :238-241).
- **Green criterion:** `dbt build --select int_matchbook_team_link int_matchbook_league_link` green with Stories 1–2 in place; the mutation-red check confirmed.
- **Guardrails to satisfy:** dbt tests bite; never weaken.
- **Self-review checkpoint:** reviewer confirms both tests exist, reference the right target/field, and genuinely fail on an absent id (not vacuously green).

### Step S10 — Scaffold football-data to the shared contract (placeholder + four-file wiring)
- **Goal:** `conform/football_data.py` declaring the shared resolve-or-mint interface with a documented `NotImplementedError` matching body, and its four bootstrap-empty additions files unioned by the canonical models.
- **Spec trace:** US5 AC1/AC2 / FR-010 / SC-006 — unit U18.
- **Red (failing test first):** `tests/conform/test_football_data_scaffold.py`: asserts the module declares the interface (the four additions filenames, the resolver imports) and that `dbt build --select int_match int_team` stays green with football_data additions bootstrap-empty. Fails before the module + union exist.
- **Implementation:** Add `conform/football_data.py` (interface + bootstrap; matching body raises `NotImplementedError` with a clear message); ensure S8's UNIONs already include football_data additions files (bootstrap-empty). A small bootstrap step (asset or fixture) writes the empty football_data files.
- **Green criterion:** `dbt build --select int_match int_team` green with zero football_data rows; module interface test green.
- **Guardrails to satisfy:** constitution II (placeholder is the explicitly-in-scope interface, honestly labelled — not a hidden stub); bootstrap-empty; dbt green-when-empty.
- **Self-review checkpoint:** reviewer confirms the not-implemented body is clearly documented (spec Assumption 1), the additions union contributes 0 rows and does not error, and the interface matches the Matchbook contract.

### Step S11 — Cross-provider de-dup + full-run parity verification (queued run)
- **Goal:** End-to-end proof: two providers describing the same fixture land on one match_id; the conform job runs through the daemon and the whole chain is green.
- **Spec trace:** E2 / SC-003,SC-006 / FR-008 — units U12,U17.
- **Red (failing test first):** `tests/conform/test_parity.py`: for a fixture whose league is mapped in `league_aliases`, the Python-computed match_id == the dbt macro output (recomputed from canonical tables) — a parity assertion that fails if the resolver and macro drift.
- **Implementation:** No new product code beyond wiring already done; run the full conform job and `dbt build` over intermediate+marts.
- **Green criterion:** `dagster job execute -j matchbook_conform_job` launches and completes; `dbt build` over intermediate+marts green; `int_match` has ONE row for the shared fixture; parity test green.
- **Guardrails to satisfy:** lineage-via-queued-run (not just `definitions validate`); idempotency; all dbt tests green.
- **Self-review checkpoint:** reviewer confirms the queued run actually launched (no `DagsterCodeLocationNotFoundError`), one canonical match for the shared fixture, and parity holds.

### Step S12 — Ripple the four docs
- **Goal:** Update `CLAUDE.md`, `ARCHITECTURE.md`, `ERD.md`, `data flows.md` to describe symmetric cross-provider conform, the `league_aliases` seed + `_seeds.yml`, the four additions files, and fix stale `models/silver/canonical/`, "canonical from ESPN", "conform lives in matchbook", and `try_read_parquet` references.
- **Spec trace:** FR-014 / SC-007 — unit U19.
- **Red (failing test first):** artifact assertion (grep): after editing, `grep -rn "try_read_parquet\|conform lives in matchbook\|canonical.*ESPN-only\|models/silver/canonical" CLAUDE.md ARCHITECTURE.md ERD.md "data flows.md"` finds no stale statement. Fails before the edits.
- **Implementation:** Edit the four docs; correct the stale `int_match.sql` `try_read_parquet` comments too (FR-014). Add the `league_aliases` seed + four-additions-file convention to CLAUDE.md *Non-obvious constraints* (this is where S1's rule lands after approval).
- **Green criterion:** grep finds no stale text; docs describe the symmetric model; `pre-commit run --all-files` clean.
- **Guardrails to satisfy:** constitution V; docs-in-same-change discipline (CLAUDE.md "living documentation").
- **Self-review checkpoint:** reviewer confirms every stale claim is corrected and the new conventions are documented consistently across all four docs + `int_match.sql` comment.

## Sequencing & dependencies

```
S0 (baseline) ─▶ S1 (conventions, hard gate) ─▶ S2 (resolve.py)
                                                   │
S2 ─▶ S3 (relocate+remove old) ─▶ S5 (rename additions file)
S2 ─▶ S4 (league_aliases seed)
S4,S5,S7 ─▶ S6 (mint full chain) ─▶ S8 (union into team/league/season) ─▶ S9 (FK link tests)
S6 needs S7 (canonical league/season exports to read) ; S7 before S6's read path
S8 ─▶ S10 (football-data scaffold, unions must already include its files)
S8,S9,S10 ─▶ S11 (queued-run parity) ─▶ S12 (docs)
```

Repo-gotcha edges made explicit:
- **S6 before S8, but S8 supplies the "red today" proof:** S6 produces a minted chain; S8's relationships
  tests are RED until S8 adds the unions — this is the deliberate red→green for SC-001. (S6 tests use pytest
  on the emitted frames; the dbt relationships red/green is S8.)
- **S7 (exports) before S6's resolution read:** the Python conform reads `silver/canonical/league.parquet`
  + `season.parquet`, which only exist after S7's export models build. Order S7 ahead of S6's read path.
- **Bootstrap-empty before any `dbt build` touching the canonical models** (`read_parquet` errors on a
  missing file) — S6/S10 write all four files per provider empty before dbt runs.
- **Asset relocation (S3) keeps AssetKey `["matchbook_conform"]`** (D2) so `assets/dbt.py:35` source-map and
  `deps`/selections need no edit; S7/S11 verify lineage via a real **queued run**, not `definitions validate`.
- **S1 is a hard gate:** its conventions must be approved+committed before S4/S6/S8/S9/S10 (all depend on
  the four-file additions + league_aliases conventions). Non-interactive → recorded as OQ-A for sign-off.

## Complexity Tracking

None. (The football-data `NotImplementedError` body is not a constitution-II violation: it is the
explicitly-in-scope US5 interface scaffold, honestly labelled, with a real additions bootstrap — spec
Assumption 1. No gate is weakened anywhere.)

## Assumptions

1. The existing pytest harness + `tests/` layout is the test home; new tests live in `tests/conform/`
   mirroring `tests/matchbook/`. (Confirmed: `tests/matchbook/test_conform.py` exists.)
2. The relocated asset keeps AssetKey `["matchbook_conform"]` (D2) — the neutral-ness is delivered by the
   module path, not the key string.
3. ESPN stays in-SQL and emits no additions files (D3); it is the union base of each canonical model.
4. Matchbook `provider_key` in `league_aliases` = `"<sport_id>|<category_id>"` (D4).
5. `canonical_league_export`/`canonical_season_export` write to `silver/canonical/{league,season}.parquet`
   alongside the existing team/match exports (D7).
6. `dbt build` green requires bronze data present (spec Assumption 8, CLAUDE.md environmental IO note);
   SC checks are evaluated with bronze materialised.
7. `team_aliases` seed and its (absent) tests are left as-is; only `league_aliases` gets a `_seeds.yml`
   (the first in the repo). If the user wants `team_aliases` tests too, that's an additive follow-up.
8. `dbt_utils` is NOT assumed present; the composite-unique test is a zero-dependency singular test (D6).

## Open Questions

- **OQ-A (needs user sign-off — convention hard-gate, NON-blocking to planning but blocking to S4/S6+):**
  This run is non-interactive, so S1 DRAFTS but does not auto-commit the two new conventions (the provider
  four-file additions convention + the `league_aliases` seed convention) into `CLAUDE.md`. They are required
  before implementation. Recorded here for explicit sign-off per the skill's rule that a missing convention
  must be drafted and approved, never silently committed on the user's behalf. If approved as-drafted, S1
  commits them; the audit rows flip from `created this run (pending)` to committed. **Not a product decision
  — a governance sign-off.**
- OQ1/OQ2/OQ3 from spec.md are RESOLVED in research.md (D2, D3, D4) — recorded as settled best-guesses with
  rationale; not blockers.
- Minor: whether the football-data empty-bootstrap files are written by a tiny dedicated asset or reuse the
  Matchbook conform asset's bootstrap helper. Best-guess: a small shared bootstrap helper in
  `conform/__init__.py` called by both provider asset wrappers (KISS). Settled in tasks/impl; not a blocker.

## Traceability

| Spec scenario / FR / SC | Unit(s) | Step(s) | Guardrail(s) |
|-------------------------|---------|---------|--------------|
| Convention hard gate (FR-014,FR-015,FR-016 pre-req) | (audit) | S1 | convention-before-code gate |
| US1 AC1 / FR-001 | U6 | S6 | Pandera, pytest, Python-no-DuckLake |
| US1 AC2 / FR-003 (additions files) | U8,U9,U10,U11 | S8 | dbt tests (not weakened), bootstrap-empty |
| FR-003 (rename match-additions file, clean replace) | U16 | S5 | constitution I, dbt tests |
| US1 AC3 / SC-001 | U11 | S6,S8 | dbt relationships (fixed data path) |
| US2 AC1/AC2 / FR-002 | U1 | S2 | pytest, ruff |
| US2 AC3 / FR-002,FR-012 / SC-008 | U2,U3 | S2,S4,S6 | pytest, dbt tests |
| US2 AC4 / FR-012 / E9 | U2 | S2,S6 | pytest |
| US2 AC5 / SC-002 / E3 | U8,U9,U12 | S8 | dbt unique (keep-one) |
| US2 AC6 / FR-005,FR-007 / SC-003 / E8 | U4,U12 | S2,S11 | pytest parity |
| US3 AC1 / FR-006 / SC-004 | U16 | S3 | grep, constitution I |
| US3 AC2 / FR-007 | U4 | S2,S3 | pytest, code-architecture-review |
| US3 AC3 / SC-004 | U16 | S3 | output-equivalence test |
| US4 AC1 / FR-009 / SC-005 | U13,U14 | S9 | dbt relationships (bites) |
| US4 AC2 / SC-005 | U13 | S9 | dbt mutation-red check |
| US5 AC1 / FR-010 / SC-006 | U18 | S10 | dbt green-when-empty |
| US5 AC2 / FR-010 | U18 | S10 | interface test |
| FR-004 (tests not weakened) | U8,U9,U10,U11,U13,U14 | S8,S9 | constitution II/III |
| FR-005 | U4 | S2 | pytest parity |
| FR-008 | U17 | S3,S7,S11 | queued-run lineage |
| FR-011 | U15 | S7 | Python-no-DuckLake, exports |
| FR-012 / SC-008 | U2 | S2,S6 | pytest, dbt |
| FR-013 | U1–U6 | S2,S6 | pytest, Pandera, dbt |
| FR-014 / SC-007 | U19 | S12 | grep, docs-in-change |
| FR-015 | U7 | S4 | dbt seed tests (composite-unique bites) |
| FR-016 / E4 | U6,U8,U18 | S6,S8,S10 | bootstrap-empty |
| E1 | U6 | S6 | pytest |
| E2 / SC-003 | U12 | S11 | dbt keep-one, parity |
| E5 | U5 | S6 | pytest (exceptions route) |
| E6 (no auto-mint) | (unchanged behaviour) | S3,S6 | output-equivalence, pytest |
| E7 (seed dup surfaced) | U7 | S4 | dbt unique holds; surfaced not papered |
| E9 | U2 | S2,S6 | pytest provider-scoped mint |
| E10 | U9,U10 | S6,S8 | league-addition emitted; relationships bites |
