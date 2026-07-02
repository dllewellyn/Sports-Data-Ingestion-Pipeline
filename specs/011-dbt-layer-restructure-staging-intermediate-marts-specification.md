---
id: 011
title: dbt Layer Restructure to staging/intermediate/marts + Asset & Conform Reorganisation
slug: dbt-layer-restructure-staging-intermediate-marts
status: implemented
created: 2026-07-01
user_stories: []
source_commits: [2dc3910]
investigation: null
related_specs: [003, 006, 008, 010]
---

# dbt Layer Restructure to staging/intermediate/marts + Asset & Conform Reorganisation

## 1. Summary

The dbt project's model hierarchy is renamed from a non-standard `silver`/`gold` layout to
dbt community-standard naming: `staging` (raw projections, `stg_*` views), `intermediate`
(canonical entities, `int_*` tables), and `marts` (analytical facts and exports, `fct_*`).
The Dagster Python assets are reorganised into `assets/ingestion/` and `assets/intermediate/`
subdirectories to mirror the layer they feed. The monolithic `matchbook/conform.py` module
is split into a `matchbook/conform/` package with dedicated sub-modules for engine
orchestration, scoring, reversal, and overrides. The restructure is strictly behaviour-
preserving: no data-value changes occur, no model logic is altered, and all 237 tests pass
after the rename.

## 2. Background & context

This is a **retrospective specification reconstructed from commit `2dc3910`**, written after
the fact. There were no pre-written user stories.

Earlier specs introduced the silver/gold layer names:
- **Spec 003** (DuckLake model migration) established the `silver/canonical/` subfolder for
  canonical entities and the `gold/` folder for analytical models, all under
  `dbt_project.yml` schema config.
- **Spec 006** (Matchbook conform) introduced `matchbook/conform.py` as a single module
  containing engine, scoring, reversal, and override logic.
- **Spec 008** (Completed matches gold layer) introduced the `completed_matches` gold dbt
  table and its export.
- **Spec 010** (link table rename) renamed the `*_match_link` / `*_event_link` tables to
  `espn_match_link`, `matchbook_event_link`, etc. — these are renamed again here to the
  `int_` prefix.

The silver/gold naming conflated layer semantics (presentation layer vs. intermediate
computation) with the medallion bronze/silver/gold metaphor used for raw → staged →
canonical data, making it ambiguous where provider-linking tables and canonical entities
belonged. The rename aligns the project with the dbt convention that uses `staging`,
`intermediate`, and `marts` as named layers regardless of a broader data lakehouse metaphor.

This restructure is a **naming and layout change only**. Model SQL logic, column names,
dbt test coverage, Dagster job definitions, and data values are unchanged.

## 3. Goals & non-goals

**Goals**

1. Align dbt model folder naming with community-standard `staging`, `intermediate`, and
   `marts` layers, removing the ambiguous `silver` and `gold` folder names.
2. Rename all canonical entity models with the `int_` prefix (`int_league`, `int_season`,
   `int_team`, `int_match`, `int_espn_match_link`, `int_matchbook_event_link`, etc.).
3. Rename the gold analytical fact table from `completed_matches` to `fct_completed_matches`.
4. Update `dbt_project.yml` to configure `+schema` and `+materialized` for each new layer.
5. Update all `ref()` calls within model SQL to use the new `int_*`/`fct_*` names.
6. Update all Dagster `AssetKey` references from `["silver", ...]` and `["gold", ...]` to
   `["staging", ...]`, `["intermediate", ...]`, and `["marts", ...]`.
7. Reorganise Dagster Python bronze/ingest assets into `assets/ingestion/` and intermediate
   Python assets into `assets/intermediate/` subdirectories.
8. Split `matchbook/conform.py` into a `matchbook/conform/` package with explicit sub-modules
   (`engine`, `scoring`, `reversal`, `overrides`) and a public `__init__.py`.
9. Maintain all 237 existing tests green after the rename.

**Non-goals (explicitly out of scope)**

- Any change to model SQL logic, column names, or output data values.
- Any change to Dagster job, schedule, or resource definitions beyond import path updates.
- Any new tests — the existing suite is unchanged.
- Adding or removing dbt tests.
- Migrating the data in DuckLake (the rename is a model/code rename; the catalog tables are
  rebuilt by a full `dbt build` run).
- Changing the bronze Parquet layout or any bronze asset logic.

## 4. Actors & triggers

| Actor | Trigger |
|-------|---------|
| Developer (refactor commit) | Triggered by the desire to align with dbt community naming conventions and resolve the silver/gold ambiguity. One-off commit to the main branch. |
| dbt CLI / Dagster | A subsequent `dbt build` rebuilds all renamed models in DuckLake under the new schema names (`staging`, `intermediate`, `marts`). |
| Dagster code location load | On next startup, imports succeed from the new `assets/ingestion/` and `assets/intermediate/` paths. |
| Python test suite (`pytest`) | The test suite imports from the new `matchbook/conform/` package paths; all 237 tests pass. |

## 5. Behaviour specification (BDD)

### Capability A: dbt model layer names and schema config

**Scenario A1: Staging models materialise as views in the `staging` schema**
- **Given** `dbt_project.yml` configures `staging: { +materialized: view, +schema: staging }`
- **When** `dbt build --select staging.*` runs
- **Then** all `stg_*` models materialise as views in the `staging` schema on DuckLake
- **And** no model under `models/staging/` is absent from the build

**Scenario A2: Intermediate models materialise as tables in the `intermediate` schema**
- **Given** `dbt_project.yml` configures `intermediate: { +materialized: table, +schema: intermediate }`
- **When** `dbt build --select intermediate.*` runs
- **Then** all `int_*` models materialise as tables in the `intermediate` schema on DuckLake
- **And** `int_league`, `int_season`, `int_team`, `int_match`, `int_espn_match_link`,
  `int_espn_team_link`, `int_espn_league_link`, `int_matchbook_event_link`,
  `int_matchbook_league_link`, `int_matchbook_team_link`, and `int_football_data_match_link`
  are all present and pass their dbt tests

**Scenario A3: Marts models materialise as tables in the `marts` schema; exports as external**
- **Given** `dbt_project.yml` configures `marts: { +materialized: table, +schema: marts }` with
  `exports: { +materialized: external }`
- **When** `dbt build --select marts.*` runs
- **Then** `fct_completed_matches` materialises as a DuckLake table in the `marts` schema
- **And** `canonical_match_export`, `canonical_team_export`, and `completed_matches_export`
  materialise as external Parquet files at the on-disk paths they had **before** the
  restructure, which were deliberately left unchanged: `canonical_match_export` →
  `$DATA_DIR/silver/canonical/match.parquet`, `canonical_team_export` →
  `$DATA_DIR/silver/canonical/team.parquet`, `completed_matches_export` →
  `$DATA_DIR/gold/completed_matches.parquet` (the `marts/exports/` location is the dbt
  model folder, not the output path)

**Scenario A4: Seeds write to the `staging` schema**
- **Given** `dbt_project.yml` configures `seeds: { data_platform: { +schema: staging } }`
- **When** `dbt seed` runs
- **Then** the `team_aliases` seed materialises in the `staging` schema alongside `stg_*` views

**Scenario A5: All `ref()` calls resolve under new names**
- **Given** all model SQL files have been updated to reference `int_*` and `fct_*` names
- **When** `dbt parse` runs
- **Then** no unresolved `ref()` errors are emitted
- **And** `dbt build` succeeds across the full model graph

### Capability B: Dagster AssetKey alignment

**Scenario B1: Staging dbt models surface with `["staging", ...]` AssetKeys**
- **Given** `stg_espn_events` and `stg_matchbook_odds` live under `models/staging/`
- **When** Dagster loads the dbt manifest via `BronzeAwareTranslator`
- **Then** the AssetKey for `stg_espn_events` is `AssetKey(["staging", "stg_espn_events"])`
- **And** the AssetKey for `team_aliases` seed is `AssetKey(["staging", "team_aliases"])`

**Scenario B2: Intermediate dbt models surface with `["intermediate", ...]` AssetKeys**
- **Given** `int_match`, `int_league`, etc. live under `models/intermediate/`
- **When** Dagster loads the manifest
- **Then** the AssetKey for `int_match` is `AssetKey(["intermediate", "int_match"])`
- **And** the AssetKey for `int_espn_match_link` is
  `AssetKey(["intermediate", "int_espn_match_link"])`
- **And** no AssetKey carries `["silver", ...]` or `["silver", "canonical", ...]`

**Scenario B3: Marts dbt models surface with `["marts", ...]` AssetKeys**
- **Given** `fct_completed_matches` lives under `models/marts/core/` and exports live under
  `models/marts/exports/`
- **When** Dagster loads the manifest
- **Then** `fct_completed_matches` has AssetKey `AssetKey(["marts", "fct_completed_matches"])`
- **And** `canonical_match_export` has AssetKey `AssetKey(["marts", "canonical_match_export"])`
- **And** no AssetKey carries `["gold", ...]`

**Scenario B4: `definitions.py` AssetSelection groups use new key prefixes**
- **Given** `definitions.py` references explicit `AssetKey` objects for group selections
- **When** the Dagster code location loads
- **Then** `espn_assets` refers to `AssetKey(["staging", "stg_espn_events"])` and
  `AssetKey(["intermediate", "int_match"])`, etc.
- **And** `matchbook_conform_assets` refers to `AssetKey(["intermediate", "int_matchbook_event_link"])`
  and `AssetKey(["marts", "canonical_match_export"])`, etc.

### Capability C: Dagster Python asset subdirectory reorganisation

**Scenario C1: Ingestion assets importable from `assets/ingestion/`**
- **Given** `espn.py`, `espn_postgres_migration.py`, `football_extra.py`, `football_main.py`,
  `matchbook_events.py`, and `matchbook_postgres_migration.py` are under `assets/ingestion/`
- **When** `definitions.py` imports `from .assets.ingestion.espn import espn_bronze` etc.
- **Then** all imports succeed at code-location load time
- **And** the Dagster UI shows the same bronze asset names as before the rename

**Scenario C2: Intermediate assets importable from `assets/intermediate/`**
- **Given** `matchbook_conform.py` and `matchbook_t60.py` are under `assets/intermediate/`
- **When** `definitions.py` imports `from .assets.intermediate.matchbook_conform import matchbook_conform`
- **Then** both imports succeed and the `matchbook_conform` and `matchbook_t60_enrichment`
  assets load correctly

### Capability D: `matchbook/conform/` package split

**Scenario D1: Conform package is importable as a package**
- **Given** `matchbook/conform/` contains `__init__.py`, `engine.py`, `scoring.py`,
  `reversal.py`, and `overrides.py`
- **When** Python imports `from data_platform.matchbook.conform import run_conform`
- **Then** the import succeeds without error
- **And** `run_conform`, `ConformReport`, `compute_canonical_match_id`, `load_overrides`,
  `parse_event_name`, `HIGH_CONFIDENCE`, and `MEDIUM_CONFIDENCE` are all available from the
  package's public surface (`__init__.py`)

**Scenario D2: Each sub-module has a single responsibility**
- **Given** the package structure
- **When** examining the modules
- **Then** `engine.py` contains the `run_conform` orchestrator and `ConformReport`
- **And** `scoring.py` contains confidence thresholds and candidate-scoring logic
- **And** `reversal.py` contains `parse_event_name` (event title → team-name parsing)
- **And** `overrides.py` contains `load_overrides` (human override file loading)
- **And** `engine.py` (the orchestrator) composes the other modules by importing directly
  from its siblings (`from .overrides import load_overrides`, `from .reversal import
  parse_event_name`, `from .scoring import …`); the leaf modules (`scoring`, `reversal`,
  `overrides`) do not import one another. `__init__.py` re-exports the public API but is
  not an internal import hub.

**Scenario D3: All conform-dependent tests pass after split**
- **Given** tests under `tests/matchbook/` import from `data_platform.matchbook.conform`
- **When** `pytest tests/matchbook/` runs
- **Then** all conform-related tests pass with no `ImportError` or `ModuleNotFoundError`

### Capability E: Full test suite green

**Scenario E1: All 237 tests pass after the rename**
- **Given** the complete rename has been applied across models, SQL, Python assets, and
  `definitions.py`
- **When** `PYTHONPATH=src uv run pytest` runs
- **Then** all 237 tests pass and no test is skipped due to import failures

## 6. Edge cases & error handling

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | A `ref()` call in a model SQL that still uses an old name (e.g. `ref('league')` instead of `ref('int_league')`) | `dbt parse` raises an unresolved ref error; the model is not built. Fix: update the `ref()` call in the model file. |
| E2 | A Dagster `AssetKey` that still uses `["silver", ...]` or `["gold", ...]` | The key does not resolve to any dbt manifest node; Dagster silently drops the edge or raises at job definition time. Fix: update all explicit `AssetKey` references in `definitions.py`. |
| E3 | A Python import still referencing `assets/espn.py` (old flat path) | `ModuleNotFoundError` at code-location load time. Fix: update the import to `assets/ingestion/espn`. |
| E4 | A Python import still referencing `matchbook.conform` as a module (not a package) | If the old `conform.py` was deleted and the package created, imports that bypassed `__init__.py` raise `ImportError`. Fix: import from the package (`from .conform import ...`). |
| E5 | `dbt build` run without a prior `dbt parse` after the rename | The old manifest (if cached) references the old model names and will fail to resolve. Fix: run `dbt parse` first to regenerate the manifest (documented in CLAUDE.md). |
| E6 | A test that hard-codes an old `AssetKey` prefix (`["silver", ...]`) | The test fails with an assertion error. Fix: update the expected key in the test. |

## 7. Acceptance criteria

- [ ] AC1 — `dbt_project.yml` defines `staging`, `intermediate`, and `marts` as named layers
  under `models.data_platform`, each with the correct `+schema` and `+materialized` default.
  Seeds write to `+schema: staging`.
- [ ] AC2 — `models/staging/` contains `stg_espn_events.sql` and `stg_matchbook_odds.sql`
  (and `_staging.yml`); no `models/silver/` folder exists.
- [ ] AC3 — `models/intermediate/` contains all 11 canonical entity and provider-link models
  (`int_league`, `int_season`, `int_team`, `int_match`, `int_espn_match_link`,
  `int_espn_team_link`, `int_espn_league_link`, `int_matchbook_event_link`,
  `int_matchbook_league_link`, `int_matchbook_team_link`, `int_football_data_match_link`);
  no `models/silver/canonical/` folder exists.
- [ ] AC4 — `models/marts/core/` contains `fct_completed_matches.sql`; `models/marts/exports/`
  contains `canonical_match_export.sql`, `canonical_team_export.sql`, and
  `completed_matches_export.sql`; no `models/gold/` folder exists.
- [ ] AC5 — All `ref()` calls in model SQL use the new `int_*`/`fct_*` names; `dbt parse`
  exits zero.
- [ ] AC6 — `src/data_platform/assets/ingestion/` contains all six bronze/ingest asset
  modules (`espn.py`, `espn_postgres_migration.py`, `football_extra.py`, `football_main.py`,
  `matchbook_events.py`, `matchbook_postgres_migration.py`); no flat `assets/espn.py` etc.
  exists.
- [ ] AC7 — `src/data_platform/assets/intermediate/` contains `matchbook_conform.py` and
  `matchbook_t60.py`; no flat `assets/matchbook_conform.py` etc. exists.
- [ ] AC8 — `src/data_platform/matchbook/conform/` is a Python package with `__init__.py`,
  `engine.py`, `scoring.py`, `reversal.py`, and `overrides.py`; no
  `matchbook/conform.py` flat module exists.
- [ ] AC9 — `from data_platform.matchbook.conform import run_conform, ConformReport,
  compute_canonical_match_id, load_overrides, parse_event_name, HIGH_CONFIDENCE,
  MEDIUM_CONFIDENCE` succeeds without error.
- [ ] AC10 — All explicit `AssetKey` references in `definitions.py` use the
  `["staging", ...]`, `["intermediate", ...]`, or `["marts", ...]` prefixes; no
  `["silver", ...]` or `["gold", ...]` keys remain.
- [ ] AC11 — Dagster code-location loads without error after the rename.
- [ ] AC12 — All 237 tests pass (`PYTHONPATH=src uv run pytest`).

## 8. Things to be aware of / constraints

### Dagster AssetKey derivation vs. dbt node selector — load-bearing split

**AssetKey = schema-prefix folder only (deeper subfolders are dropped).**
A dbt model at `models/intermediate/int_match.sql` gets `AssetKey(["intermediate", "int_match"])`.
A model at `models/marts/core/fct_completed_matches.sql` gets
`AssetKey(["marts", "fct_completed_matches"])` — the `core/` subfolder is dropped.
Likewise `models/marts/exports/completed_matches_export.sql` →
`AssetKey(["marts", "completed_matches_export"])` — `exports/` is dropped.

**dbt node selector DOES include the subfolder.**
The correct selector for intermediate models is `intermediate.*` (e.g.
`dbt build --select intermediate.int_match`); `intermediate.canonical.int_match` selects
nothing and gives a vacuous green. For marts:
`dbt build --select marts.core.fct_completed_matches` is correct;
`dbt build --select marts.fct_completed_matches` selects nothing.

This split is the source of silent mis-wiring: if you name an `AssetKey` based on the dbt
selector (including subfolder), the Dagster asset edge is not formed. Always derive keys
from the manifest's `schema` field (the first-level folder name), not the full path.

### Layer-to-schema mapping is exact

`+schema: staging` → DuckLake schema `staging`; `+schema: intermediate` → `intermediate`;
`+schema: marts` → `marts`. These are not abbreviations or overrides — the schema name
exactly matches the layer folder name. Adding a model to the wrong folder changes its schema
and will break any downstream SQL that qualifies table references by schema.

### Export on-disk paths were NOT renamed to match the `marts` layer

Despite the dbt layer being renamed to `marts`, the external materialization export models
kept their pre-restructure on-disk output paths — and these do **not** all live under one
directory:

- `canonical_match_export` → `$DATA_DIR/silver/canonical/match.parquet`
- `canonical_team_export` → `$DATA_DIR/silver/canonical/team.parquet`
- `completed_matches_export` → `$DATA_DIR/gold/completed_matches.parquet`

So two of the three exports still write under `$DATA_DIR/silver/canonical/` and one under
`$DATA_DIR/gold/` — the `marts/exports/` location names only the dbt *model folder*, not
the output path. Python assets and notebooks that read these files must continue to use the
existing `silver/canonical/` and `gold/` paths — do not "fix" them to `marts/`.

### `stg_matchbook_odds` AssetKey warning from spec 005

Spec 005 documented the then-current AssetKey as `["silver", "stg_matchbook_odds"]`. After
this restructure, the correct key is `["staging", "stg_matchbook_odds"]`. Spec 005 §8 is
therefore stale on this point; this spec supersedes it.

### `completed_matches` renamed to `fct_completed_matches`

Spec 008 documented the gold table as `completed_matches` and its export as
`completed_matches_export`. After this restructure: the DuckLake table is
`fct_completed_matches` (under the `marts` schema); the export file path is unchanged
(`$DATA_DIR/gold/completed_matches.parquet`). Any hard-coded `ref('completed_matches')`
in downstream SQL must be updated to `ref('fct_completed_matches')`.

### `dbt parse` required after the rename

Changing model folder structure invalidates any cached manifest. Always run `dbt parse`
(or `dagster dev`, which calls `dbt_project.prepare_if_dev()`) before running Dagster or
`dbt build` to regenerate `target/manifest.json`. `dbt parse` exits 0 even without a live
Postgres catalog (it only reads model SQL), so it is safe to run offline.

### No data migration required

DuckLake tables are dbt-managed and rebuilt from source Parquet on each `dbt build`. The
rename does not require any manual data migration or `ALTER SCHEMA` DDL. A full `dbt build`
after the rename creates the new `staging`, `intermediate`, and `marts` schemas from
scratch. Old `silver` and `gold` schemas in DuckLake are orphaned and may be dropped
manually.

## 9. Assumptions

1. The existing 237 tests are a sufficient regression gate to confirm the rename is
   behaviour-preserving; no additional tests were required.
2. The `BronzeAwareTranslator` in `assets/dbt.py` derives AssetKeys from the dbt manifest's
   `schema` field (the top-level folder under `models/`), which correctly maps to
   `staging`, `intermediate`, or `marts` after the rename. The *rule* (schema-prefix-only
   key derivation) is documented in CLAUDE.md, but note CLAUDE.md's worked example still
   uses the pre-restructure `silver/canonical/…` → `["silver", …]` paths — CLAUDE.md was
   **not** updated to the new layer names by commit `2dc3910` (see Open question OQ4).
3. On-disk export paths (`$DATA_DIR/silver/canonical/*.parquet` and
   `$DATA_DIR/gold/*.parquet`) were intentionally left unchanged to avoid breaking existing
   notebook and Python consumer paths that were already in production.
4. The `matchbook/conform/` package split was done atomically with the model rename in a
   single commit (`2dc3910`) to avoid a transient state where the package is partially
   split.
5. The `definitions.py` explicit `AssetKey` lists for `espn_assets` and
   `matchbook_conform_assets` are kept explicit (not derived from the manifest at load time)
   to maintain clear, readable job scope definitions — the AssetKey values are updated
   manually as part of this rename.

## 10. Open questions

| # | Question | Blocker? | Best-guess resolution |
|---|----------|----------|-----------------------|
| OQ1 | Should the on-disk export directories (`$DATA_DIR/silver/canonical/` for the two canonical exports, `$DATA_DIR/gold/` for the completed-matches export) be renamed to `$DATA_DIR/marts/` for consistency with the dbt layer name? | Non-blocker | No — changing the paths would break existing notebooks and any ops tooling that reads them. The layer rename is a dbt convention, not a file-system convention; the exports keep their original `silver/canonical/` and `gold/` disk paths. |
| OQ2 | Are the orphaned `silver` and `gold` DuckLake schemas dropped automatically on the next `dbt build`, or do they persist? | Non-blocker | They persist; dbt does not drop schemas it no longer writes to. An operator should DROP the orphaned schemas manually. No automated cleanup was included in this commit. |
| OQ3 | The `_intermediate.yml` and `_staging.yml` schema YAML files were also renamed/restructured. Are the original `_schema.yml` files fully deleted, or do stale copies remain? | Non-blocker (confirmed by commit diff) | The commit diff shows `models/silver/_schema.yml` and `models/gold/_schema.yml` deleted; the content was moved to the new layer YAML files. No stale copies remain as of `2dc3910`. |
| OQ4 | `CLAUDE.md` and `data flows.md` were not updated by this commit and still describe the old `silver`/`gold` layers (architecture diagram, canonical-path bullets, the AssetKey worked example, data-flow narration). Was leaving them stale intentional? | Non-blocker | Almost certainly unintentional debt — the restructure was behaviour-preserving so the docs "still worked" as prose, but they now give misleading layer names. A follow-up doc-refresh pass should rewrite the CLAUDE.md architecture diagram and constraint examples (and `data flows.md`) to `staging`/`intermediate`/`marts`. Flagged here as unverified intent. |

## 11. Traceability

| Source commit | Behaviour introduced | Scenarios | Acceptance criteria |
|---------------|---------------------|-----------|---------------------|
| `2dc3910` | All dbt model renames (`staging`/`intermediate`/`marts`), `dbt_project.yml` layer config, all `ref()` updates, `fct_completed_matches` rename, all Dagster AssetKey updates, `assets/ingestion/` + `assets/intermediate/` subdirs, `matchbook/conform/` package split, 237 tests passing | A1–A5, B1–B4, C1–C2, D1–D3, E1 | AC1–AC12 |

> This spec documents a single-commit structural rename. All scenarios and acceptance
> criteria are delivered by the one source commit. Coverage maps in both directions: every
> AC traces to `2dc3910`, and `2dc3910` delivers every scenario.
