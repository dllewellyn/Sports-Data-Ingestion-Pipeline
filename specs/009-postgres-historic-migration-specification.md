---
id: 009
title: ESPN & Matchbook Historic-Data Migration from sports-gaming-engine PostgreSQL
slug: postgres-historic-migration
status: implemented
created: 2026-07-01
user_stories: []
source_commits: [7d26b00, 2dc3910]
investigation: null
related_specs: [002, 005, 006]
---

# ESPN & Matchbook Historic-Data Migration from sports-gaming-engine PostgreSQL

## 1. Summary

Two one-off Dagster assets extract historic event records from the upstream
`sports-gaming-engine` PostgreSQL database and write them to the bronze Parquet
layer in the same path structure as the corresponding live-ingest assets. The
ESPN migration merges two source tables (`bronze.espn_restored_summaries` and
`bronze.provider_match_cache`), deduplicates by `espn_event_id`, groups by
`(league_slug, season_year)`, and writes one Parquet per group at
`data/bronze/espn/<league_slug>/<season_year>.parquet`. The Matchbook migration
reads `bronze.provider_match_cache` for `provider = 'matchbook'`, groups by
sport, and writes one Parquet per sport under
`data/bronze/matchbook_events/<sport>/<run_date>/migration_<batch_ts>.parquet`.
Both assets validate every row through Pydantic and Pandera before writing,
tag migrated rows with `"_migration_source": "postgres"` in the `raw_event`
column, use atomic temp-file-and-rename writes, and produce a structured
`MigrationReport`. Neither asset is included in any scheduled or
`AssetSelection.all()`-based job; both are run on demand from the Dagster UI.

## 2. Background & context

This is a **retrospective specification reconstructed from commit `7d26b00`**
(`feat(migration): add ESPN and Matchbook postgres migration assets`, 2026-06-30),
written after the fact to document already-shipped behaviour. Commit `2dc3910`
(`refactor: align dbt layers to staging/intermediate/marts convention`) also
touched these files — it relocated the asset wrappers from `assets/` to
`assets/ingestion/` (a layout-only change; behaviour is unchanged) and is
therefore included in `source_commits`.

The upstream `sports-gaming-engine` PostgreSQL database holds historic event
data that pre-dates this repo's live-ingest pipelines. This migration bridges
the gap: it populates the bronze ESPN and Matchbook events layers with data
that the live assets would never reach because it originates from a prior
system. Migrated rows occupy the same paths and honour the same Pydantic/
Pandera schemas as live rows, so they are immediately consumable by the dbt
silver staging models, the Matchbook conform layer (spec 006), and the T-60
enrichment (spec 006). CLAUDE.md notes one material consequence: migration rows
carry `ingested_at` set to the time the migration ran (approximately June 30 2026),
which is more recent than live events ingested earlier that day, causing migration
rows to win the recency dedup in `t60.py` over live rows with the same event ID
even though migration rows carry no market/runner data. The downstream T-60
enrichment therefore prefers rows with `markets` in `raw_event` before
sorting by `ingested_at` (the fix is documented in CLAUDE.md under "Migration
`ingested_at` is the migration timestamp").

This spec relates to:
- **Spec 002** (ESPN ingestion) — the ESPN migration targets the same
  `espn_bronze_dir` and the same `EspnEventRecord` schema used by live ESPN ingest.
- **Spec 005** (Matchbook odds ingestion) — the Matchbook migration targets
  `matchbook_events_bronze_dir`, not the odds Parquet; it is complementary, not
  overlapping.
- **Spec 006** (Matchbook/ESPN conform and T-60 enrichment) — the conform and
  T-60 layers consume the bronze Parquet produced by these migration assets,
  which is why migration `ingested_at` semantics matter there.

## 3. Goals & non-goals

**Goals**
- Extract all ESPN events from `bronze.espn_restored_summaries` and supplement
  with matching `bronze.provider_match_cache` rows (provider='espn'), producing
  de-duplicated bronze Parquet files partitioned by `(league_slug, season_year)`.
- Extract all Matchbook events from `bronze.provider_match_cache`
  (provider='matchbook'), producing bronze Parquet files partitioned by sport.
- Validate every migrated row at the Pydantic boundary (`EspnEventRecord` /
  `MatchbookEventRecord`) and at the Pandera frame level before writing.
- Stamp migrated rows with `"_migration_source": "postgres"` (and
  `"_migration_table"`) in `raw_event` so downstream can distinguish them from
  live-ingest rows.
- Use atomic temp-file-and-rename writes to ensure no partial files are visible.
- Provide per-unit/per-sport failure isolation so a bad group does not abort the
  rest of the migration.
- Surface a `MigrationReport` via Dagster `MaterializeResult` metadata.
- Register both assets as first-class Dagster assets (group `bronze`), runnable
  on demand from the Dagster UI.

**Non-goals (explicitly out of scope)**
- Running the migration on a schedule or as part of any existing pipeline job.
- Re-fetching or refreshing data that has already been written (no skip-existing
  logic; each run overwrites the target Parquet files for affected groups).
- Migrating the full original API payload — the Matchbook `raw_event` is a
  synthetic JSON reconstructed from the Postgres columns (the original Matchbook
  API payload is not preserved in the source table).
- Creating canonical silver records directly — migrated rows follow the same
  bronze-first path as live ingest and reach the canonical layer via the existing
  dbt conform pipeline.
- Handling the ESPN `provider_match_cache` "all" bucket rows — rows with
  `competition_name = 'all'` or `competition_name = ''` have no usable league
  context and are intentionally skipped.
- Cleaning up or removing the Postgres source after migration.

## 4. Actors & triggers

- **Operator** — a human who triggers the Dagster asset from the Dagster UI
  (Materialize button) when the historic back-fill is needed. The asset does not
  fire automatically.
- **`sports-gaming-engine` PostgreSQL database** — the upstream source, queried
  once per asset run via `psycopg2`. Tables: `bronze.espn_restored_summaries`,
  `bronze.provider_match_cache`.
- **Dagster asset executor** — runs `espn_postgres_migration` and/or
  `matchbook_postgres_migration` in response to an operator materialize trigger.
- **dbt silver staging / conform pipeline** — downstream consumer of the bronze
  Parquet produced by these assets (same paths as live ingest).

## 5. Behaviour specification (BDD)

### Capability: ESPN migration — fetch and merge

**Scenario: Restored summaries are primary; cache rows supplement**
- **Given** `SPORTS_GAMING_ENGINE_POSTGRES_URL` is set and points to a reachable
  PostgreSQL instance
- **When** `run_espn_postgres_migration` runs
- **Then** it fetches all rows from `bronze.espn_restored_summaries` (all leagues,
  ordered by `league_id` then competition date) and from `bronze.provider_match_cache`
  where `provider = 'espn'` and `competition_name` is neither `'all'` nor `''`
- **And** restored-summary rows are inserted into the merge dict first; cache rows
  are added only for `espn_event_id` values not already present (summaries take
  priority).

**Scenario: Rows are grouped by (league_slug, season_year) and one Parquet per group is written**
- **Given** the merged, de-duplicated set of ESPN events
- **When** grouped by `(league_slug, season_year)` and iterated
- **Then** each group produces exactly one Parquet file at
  `<espn_bronze_dir>/<league_slug>/<season_year>.parquet`
- **And** groups with no valid rows after Pydantic filtering produce no file (recorded
  as skipped).

**Scenario: Season year is inferred from kickoff month for cache-sourced rows**
- **Given** a `provider_match_cache` row with a `kickoff_utc` timestamp
- **When** the season year is derived
- **Then** a kickoff in months January–June yields `year - 1`, and July–December
  yields `year`, mirroring the football `season.py` July-rollover convention.

**Scenario: Restored-summary rows carry full game-summary payload with provenance tags**
- **Given** a row from `bronze.espn_restored_summaries`
- **When** mapped to a flat dict
- **Then** the `raw_event` column contains the original `payload` JSON with two
  additional keys injected: `"_migration_source": "postgres"` and
  `"_migration_table": "bronze.espn_restored_summaries"`.

**Scenario: Cache-sourced rows carry a synthetic raw_event**
- **Given** a row from `bronze.provider_match_cache` (ESPN)
- **When** mapped to a flat dict
- **Then** the `raw_event` column contains a synthetic JSON reconstructed from the
  available Postgres columns, tagged with `"_migration_source": "postgres"` and
  `"_migration_table": "bronze.provider_match_cache"`.

### Capability: ESPN migration — validation and writes

**Scenario: Every row is Pydantic-validated before DataFrame construction**
- **Given** a group of candidate flat rows
- **When** each row is passed to `EspnEventRecord.model_validate`
- **Then** rows that fail validation are dropped with a warning (noting `espn_event_id`,
  `league_slug`, `season_year`) and counted as `failed_rows`; only valid rows enter
  the DataFrame.

**Scenario: Pandera schema validates the DataFrame before writing**
- **Given** a non-empty DataFrame of valid rows for a group
- **When** `espn_bronze_schema.validate(df)` is called
- **Then** on success the DataFrame is written to Parquet; on failure the group is
  recorded as failed and no file is written for that group.

**Scenario: Parquet files are written atomically**
- **Given** a validated DataFrame for a `(league_slug, season_year)` group
- **When** the file is written
- **Then** it is first written to `<path>.tmp` and then renamed to the final
  `<league_slug>/<season_year>.parquet` path, so no partial file is ever visible.

**Scenario: Missing SPORTS_GAMING_ENGINE_POSTGRES_URL raises immediately**
- **Given** `settings.sports_gaming_engine_postgres_url` is an empty string
- **When** `espn_postgres_migration` is materialized
- **Then** it raises `ValueError` with a message naming the missing env var before
  any Postgres connection is attempted.

### Capability: Matchbook migration — fetch and group

**Scenario: All Matchbook events are fetched from provider_match_cache**
- **Given** `SPORTS_GAMING_ENGINE_POSTGRES_URL` is set
- **When** `run_matchbook_postgres_migration` runs
- **Then** it queries `bronze.provider_match_cache` for all rows where
  `provider = 'matchbook'`, ordered by `sport` then `kickoff_utc NULLS LAST`
- **And** rows are grouped by the `sport` field.

**Scenario: Rows with unmapped sport or NULL kickoff are skipped**
- **Given** a `provider_match_cache` row where `sport` is not in `SPORT_ID_MAP`
  (currently `football` → 15 and `rugby_union` → 2) or `kickoff_utc` is NULL
- **When** `_to_event_dict` processes it
- **Then** it returns `None`, the row is counted as a failure, a warning is logged,
  and it is not included in the event rows for that sport.

**Scenario: Matchbook raw_event is a synthetic JSON with provenance**
- **Given** a valid `provider_match_cache` Matchbook row
- **When** mapped to a flat dict
- **Then** the `raw_event` column contains a JSON object reconstructed from the
  available Postgres columns (`id`, `name`, `sport-id`, `status`, `start`,
  `volume`, `competition`, `home_team_name`, `away_team_name`) plus
  `"_migration_source": "postgres"` and
  `"_migration_table": "bronze.provider_match_cache"`.

**Scenario: Event name is constructed from team names or falls back to competition**
- **Given** a row with non-empty `home_team_name` and `away_team_name`
- **When** mapped to a flat dict
- **Then** `event_name` is `"<home> vs <away>"`; if either is empty,
  `event_name` falls back to `competition_name`.

**Scenario: Missing status defaults to "open"**
- **Given** a row where the `status` column is NULL
- **When** mapped
- **Then** `status` is set to `"open"` in the output dict.

### Capability: Matchbook migration — validation and writes

**Scenario: Output Parquet is partitioned by sport**
- **Given** valid rows for a sport
- **When** written
- **Then** the file path is
  `<matchbook_events_bronze_dir>/<sport>/<run_date>/migration_<batch_ts>.parquet`
  where `run_date` is the UTC date of the run and `batch_ts` is the UTC datetime
  in `%Y%m%dT%H%M%SZ` format.

**Scenario: Per-sport failure isolation**
- **Given** a migration run over multiple sports
- **When** writing the Parquet for one sport raises an unexpected exception
- **Then** that sport is recorded as failed in the returned `MigrationReport` and the
  run continues for remaining sports; the migration does **not** re-raise — it returns
  the report with the failed sport recorded, so Parquet files for the successful sports
  persist and the failure surfaces in the asset's metadata rather than failing the run.

**Scenario: Sport with no valid rows produces no file**
- **Given** a sport group where every row fails Pydantic validation
- **When** processing completes for that sport
- **Then** no Parquet file is written, the sport is recorded as skipped, and a warning
  is logged.

### Capability: Dagster asset registration and reporting

**Scenario: Both assets are registered under the bronze group without schedules**
- **Given** the Dagster code location is loaded
- **When** the asset graph is inspected
- **Then** `espn_postgres_migration` and `matchbook_postgres_migration` both appear
  under the `bronze` asset group with `compute_kind = python`
- **And** neither is included in any `define_asset_job` selection (they are absent
  from `football_backfill`, `espn_ingestion`, `matchbook_events_ingestion`, and
  `matchbook_conform_job`) nor on any schedule; each is materialised on demand only.

**Scenario: MaterializeResult reports outcome metrics**
- **Given** a successful run
- **When** the Dagster asset returns
- **Then** `MaterializeResult.metadata` includes counts for units/sports written,
  skipped, and failed; total valid and failed row counts; and the list of output
  Parquet paths.

## 6. Edge cases & error handling

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | `SPORTS_GAMING_ENGINE_POSTGRES_URL` not set (empty string) | Asset raises `ValueError` before opening any Postgres connection. |
| E2 | Postgres connection fails | `psycopg2.connect` raises; asset propagates the exception and the run fails. |
| E3 | ESPN row missing `competitions` array in payload | `_row_from_summary` returns `None`; row is silently skipped. |
| E4 | ESPN row missing home or away competitor | `_row_from_summary` returns `None`; row is silently skipped. |
| E5 | ESPN event fails `EspnEventRecord.model_validate` | Row is dropped with a warning; counted as `failed_rows`. |
| E6 | ESPN group with zero valid rows | No Parquet is written; recorded as skipped in `MigrationReport`. |
| E7 | ESPN group Pandera validation fails | Group recorded as failed; no file written for that group; other groups continue. |
| E8 | Matchbook row with unmapped sport | `_to_event_dict` returns `None`; row counted as failure; warning logged. |
| E9 | Matchbook row with NULL `kickoff_utc` | `_to_event_dict` returns `None`; row counted as failure; warning logged. |
| E10 | Matchbook row fails `MatchbookEventRecord.model_validate` | Row dropped with warning; counted as failure. |
| E11 | Matchbook sport group with zero valid rows | No Parquet written; sport recorded as skipped. |
| E12 | Unexpected exception during a single group/sport write | Per-unit isolation catches the exception; group/sport recorded as failed in the `MigrationReport`; other groups continue; the migration returns normally (does **not** re-raise) — the failure surfaces in the asset's `MaterializeResult` metadata, not as a failed run. |
| E13 | ESPN `provider_match_cache` rows with `competition_name = 'all'` or `''` | Excluded by the SQL `WHERE` clause; never processed. |
| E14 | `ingested_at` timestamp set to migration run time | Downstream T-60 recency dedup may prefer migration rows over live rows; resolved in spec 006 by preferring rows with `markets` in `raw_event`. |

## 7. Acceptance criteria

- [ ] FR-001 / AC1 — `SPORTS_GAMING_ENGINE_POSTGRES_URL` is configured as a `str`
  field in `Settings` (default empty string); when empty at asset execution time,
  the asset raises `ValueError` before any network call.
- [ ] FR-002 / AC2 — `espn_postgres_migration` queries `bronze.espn_restored_summaries`
  and `bronze.provider_match_cache WHERE provider='espn' AND competition_name NOT IN
  ('all', '')`, merges on `espn_event_id` (summaries take priority), and writes one
  Parquet per `(league_slug, season_year)` group to
  `<espn_bronze_dir>/<league_slug>/<season_year>.parquet`.
- [ ] FR-003 / AC3 — Season year for cache-sourced ESPN rows is derived using a July
  rollover: months 1–6 → `year - 1`, months 7–12 → `year`.
- [ ] FR-004 / AC4 — `matchbook_postgres_migration` queries `bronze.provider_match_cache
  WHERE provider='matchbook'`, groups by sport, and writes one Parquet per sport to
  `<matchbook_events_bronze_dir>/<sport>/<run_date>/migration_<batch_ts>.parquet`.
- [ ] FR-005 / AC5 — Matchbook rows with unmapped sport (not in `SPORT_ID_MAP`) or
  NULL `kickoff_utc` are skipped and counted; currently mapped sports are `football`
  (sport_id=15) and `rugby_union` (sport_id=2).
- [ ] FR-006 / AC6 — Every row passes Pydantic validation (`EspnEventRecord` /
  `MatchbookEventRecord`) before entering the DataFrame; rows that fail are dropped
  with a warning and counted.
- [ ] FR-007 / AC7 — Every DataFrame passes Pandera schema validation before writing;
  a group/sport that fails Pandera is recorded as failed and no file is written for it.
- [ ] FR-008 / AC8 — All Parquet files are written via atomic temp-file-and-rename
  (`<path>.tmp` → `<path>`).
- [ ] FR-009 / AC9 — All migrated rows have `"_migration_source": "postgres"` and
  `"_migration_table": "<source_table>"` in the `raw_event` JSON column.
- [ ] FR-010 / AC10 — Both assets are registered in the Dagster code location under
  asset group `bronze` with no associated schedule, and excluded from all scheduled
  and `AssetSelection.all()`-based jobs.
- [ ] FR-011 / AC11 — `MaterializeResult.metadata` for each asset includes
  units written/skipped/failed counts, total valid and failed row counts, and a list
  of output Parquet paths.
- [ ] FR-012 / AC12 — Failure in one (league/season or sport) group does not abort
  remaining groups; each group is attempted and any group-level failure is recorded in
  the `MigrationReport` / `MaterializeResult` metadata. The migration returns normally
  and does **not** re-raise on group-level failures (only a missing
  `SPORTS_GAMING_ENGINE_POSTGRES_URL` or a Postgres connection error raises — see E1/E2).

## 8. Things to be aware of / constraints

- **Migration `ingested_at` overrides live rows in T-60 dedup.** The migration runs
  set `ingested_at` to the time the migration asset executed (approximately 2026-06-30).
  For Matchbook events that also have live-ingest rows (ingested June 29), the migration
  row's `ingested_at` is more recent and wins the recency dedup in `t60.py` even though
  migration rows contain no market/runner data. The T-60 enrichment therefore deduplicates
  by preferring rows with `markets` in `raw_event` before falling back to `ingested_at`
  order. Do not remove or backdate the migration `ingested_at` — the fix lives in the
  consumer (spec 006), not here.
- **Matchbook `raw_event` is synthetic, not the original API payload.** The
  `provider_match_cache` table stores flattened columns, not the original Matchbook
  API response. The `raw_event` JSON is reconstructed from those columns; fields
  such as market odds are not available in the migrated data.
- **Python must not open a DuckLake connection.** These assets write Parquet files;
  they do not read from or write to the DuckLake catalog. Any future enrichment of
  migrated data must follow the same Python-reads-Parquet architectural rule.
- **No skip-existing logic.** Each run of these assets overwrites Parquet files for
  all groups it processes. Running the asset a second time produces identical output
  (idempotent in content if the source DB is unchanged), but does not skip files
  that already exist.
- **`psycopg2-binary` dependency.** The migration introduces `psycopg2-binary` as a
  runtime Python dependency (in `pyproject.toml`). This is distinct from the
  `postgres_catalog_url` connection used by DuckLake — `psycopg2` directly connects
  to the sports-gaming-engine Postgres, not the DuckLake catalog.
- **ESPN cache "all" bucket is excluded by design.** Rows with
  `competition_name = 'all'` or `competition_name = ''` in `provider_match_cache`
  have no usable league context and are filtered in the SQL query. This is
  intentional; those events cannot be partitioned into the bronze path structure.
- **Migration rows and live-ingest rows coexist in the same Parquet files.** Because
  the ESPN migration writes to `<espn_bronze_dir>/<league_slug>/<season_year>.parquet`
  (the same paths used by live ESPN ingest), a subsequent live-ingest run for the
  same `(league_slug, season_year)` will overwrite the migration-produced file. If
  re-running the migration after live ingest, any additional live rows in the
  existing file would be lost. The ordering of migration vs. live-ingest runs is
  operator responsibility.
- **Assets are excluded from every `define_asset_job` selection and all schedules** — they
  are materialised on demand only, never swept in by a scheduled or all-assets job.
  `definitions.py` registers the migration assets but does not include them in any
  `define_asset_job` selection. They are run exclusively on demand.

## 9. Assumptions

- The `sports-gaming-engine` PostgreSQL database is reachable from the operator's
  environment when the asset is triggered; no retry or reconnect logic is implemented.
- `bronze.espn_restored_summaries` holds approximately 955 events with full
  game-summary payloads (as documented in the module docstring); `provider_match_cache`
  holds supplementary events across multiple providers.
- The `SPORT_ID_MAP` (`football` → 15, `rugby_union` → 2) represents the sports
  present in the `provider_match_cache` for the Matchbook provider; sports outside
  this map are genuinely unmappable with the available column data.
- The July-rollover season logic (shared with `football/season.py`) is the correct
  approximation for ESPN soccer seasons (Aug–May), aligning Jan–Jul kickoffs with
  the prior year's season.
- The migration is intended as a one-off or occasional back-fill. It does not
  include deduplication against already-written Parquet (no comparison with existing
  bronze files before writing).

## 10. Open questions

All items are **unverified intent**; none block the existing implementation.

- **Is this truly a one-off migration or a repeatable back-fill?** Both asset
  docstrings say "one-off", and the assets have no schedule, but nothing prevents
  re-running them. Whether there is a deliberate intent to run these again (e.g.
  if the source DB grows) is not recoverable from the code or commit message.
- **Is the sports-gaming-engine PostgreSQL still accessible?** The source DB is an
  external dependency. Whether it remains operational, who owns it, or whether it
  has a deprecation timeline is not expressed in the codebase.
- **Should the assets be removed or disabled after the migration is confirmed
  complete?** Nothing marks them as expired or scheduled for removal. Whether they
  should be cleaned up from the Dagster asset graph post-migration is unresolved.
- **Are additional sports expected for Matchbook?** `SPORT_ID_MAP` contains two
  entries (`football`, `rugby_union`). Whether other sports exist in the
  `provider_match_cache` and are intentionally excluded (vs. being absent from the
  source data) is not documented.
- **Does ESPN `provider_match_cache` contain events not in `espn_restored_summaries`
  for all leagues?** The "all" bucket is excluded, but the total count and league
  distribution of supplementary cache-only events vs. the 955 restored summaries
  is not recoverable from the code; the comment "955 events" in the docstring is
  from the introducing commit and may not reflect the live table state.
- **Does re-running the ESPN migration after live ingest produce a correct merged
  Parquet?** The migration overwrites without reading existing files. If live ingest
  has already written rows for a `(league_slug, season_year)`, a re-run of the
  migration would drop those live rows. Whether a merge/union strategy is intended
  for re-runs is not specified.

## 11. Traceability

| Source commit | Behaviour introduced | Spec acceptance criteria |
|---------------|----------------------|--------------------------|
| `7d26b00` | All functional behaviour: ESPN fetch/merge/dedup/season-inference/validate/write; Matchbook fetch/group/sport-map/synthesise-raw_event/validate/write; both Dagster asset wrappers; `SPORTS_GAMING_ENGINE_POSTGRES_URL` config; `psycopg2-binary` dep; `MigrationReport`; atomic writes; provenance tags; per-group failure isolation | AC1–AC12 (all) |
| `2dc3910` | Relocated asset wrappers from `assets/` to `assets/ingestion/` (import paths updated); no behaviour change | AC10 (registration path) |
