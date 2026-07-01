---
id: "008"
title: Completed Matches Gold Layer — Analytical Table, Parquet Export, and Notebook
slug: completed-matches-gold-layer
status: implemented
created: 2026-06-30
user_stories: []
investigation: null
related_specs: ["002", "006"]
---

# Completed Matches Gold Layer — Analytical Table, Parquet Export, and Notebook

## 1. Summary

A gold dbt table (`completed_matches`) and a corresponding external Parquet export
(`completed_matches_export`) combine the silver canonical layer — `match`, `season`,
`league`, `team` — into a single, human-readable, analysis-ready view of every finished
soccer fixture. "Finished" is defined as `ft_score IS NOT NULL` in the canonical `match`
table. A companion Jupyter notebook (`notebooks/completed_matches.ipynb`) reads the
exported Parquet and provides four ready-to-run query cells for common analytical
questions. Together, these artefacts give analysts and engineers a stable, provider-
agnostic record of completed matches — including which team was the Matchbook pre-match
favourite where odds data was available.

## 2. Background & context

Specs 002 and 006 established:

- **ESPN bronze → silver canonical** (Spec 002): `match`, `season`, `league`, `team`
  tables in DuckLake; `match.ft_score` is populated when ESPN marks a fixture
  `status_completed = true`; `match.favourite_team_id` is populated by the T-60
  Matchbook enrichment pipeline (Spec 006).
- **Matchbook conform + T-60 enrichment** (Spec 006): The T-60 enrichment asset writes
  `data/silver/matchbook_t60_enrichment.parquet`; `match.sql` LEFT JOINs this to
  populate `favourite_team_id`. `favourite_team_id` is a VARCHAR column storing a
  canonical `team_id` (resolved from runner name fuzzy-matching); it is `NULL` when no
  Matchbook odds data exists for a match.

Prior to this spec there was no gold-layer view that joined all these entities into a
single, queryable surface. Analysts querying the canonical silver tables directly would
need to know the DuckLake connection details and write multi-table JOINs — both of which
violate the repo's architectural rule that Python (and notebooks) read Parquet files, not
DuckLake catalog tables.

This spec documents what was built (reverse-engineering pass): the code is already
implemented and deployed. The status is `implemented`.

## 3. Goals & non-goals

**Goals**

1. A gold dbt table `completed_matches` is materialized in DuckLake with one row per
   fixture where `ft_score IS NOT NULL`, joining all human-readable dimension data
   (league name, season display name, home/away team names, favourite team name) and
   ordering results by `kickoff_time DESC`.
2. A gold external dbt model `completed_matches_export` writes the table to
   `$DATA_DIR/gold/completed_matches.parquet` as the canonical Parquet artefact for
   downstream Python and notebook consumers.
3. A Jupyter notebook (`notebooks/completed_matches.ipynb`) reads `completed_matches.parquet`
   and provides four pre-written analytical queries: all matches, per-league counts,
   league-filtered view, and matches with a Matchbook favourite.
4. All three artefacts are idempotent — rebuilding produces the same output when the
   upstream silver data is unchanged.

**Non-goals (explicitly out of scope)**

- Writing to DuckLake or any database from Python or the notebook — the notebook reads
  Parquet only, consistent with the repo architectural rule.
- Adding new canonical identity — this gold layer makes no canonical decisions; all
  `match_id` values originate from the silver canonical layer.
- Covering pre-match fixtures (`ft_score IS NULL`) — fixtures that have not yet been
  played are excluded by design.
- Providing a live / streaming view — this is a batch artefact rebuilt on each dbt run.
- Enriching or modifying `favourite_team_id` — the gold layer reads it as-is from
  `match`; the T-60 enrichment logic is defined in Spec 006.
- Rugby-union or other sports — the `match` canonical table is currently populated from
  ESPN soccer data only; `completed_matches` inherits that scope.
- Automated tests for the notebook cells — the notebook is an exploratory artefact;
  correctness is covered by upstream dbt tests on the silver canonical layer.

## 4. Actors & triggers

| Actor | Trigger |
|-------|---------|
| Dagster scheduler / engineer | The `espn_ingestion` job (or any job that runs the gold dbt models) rebuilds `completed_matches` and `completed_matches_export` as part of the dbt `@dbt_assets` build. |
| dbt CLI | `dbt build --select completed_matches completed_matches_export` rebuilds both models; idempotent. |
| Analyst / engineer | Opens `notebooks/completed_matches.ipynb` in JupyterLab (`:8888` in Docker) after the Dagster job has produced the Parquet; runs cells interactively. |

## 5. Behaviour specification (BDD)

### Capability A: Gold `completed_matches` table

**Scenario A1: Completed fixtures are joined and emitted in reverse-chronological order**
- **Given** the silver canonical tables (`match`, `season`, `league`, `team`) contain
  data for a set of fixtures, some with `ft_score IS NOT NULL` and some with
  `ft_score IS NULL`
- **When** `dbt build --select completed_matches` runs
- **Then** the `completed_matches` DuckLake table contains exactly one row per fixture
  where `ft_score IS NOT NULL`
- **And** each row has columns `match_id`, `kickoff_time`, `league`, `season`,
  `home_team`, `away_team`, `ft_score`, `favourite_team`
- **And** rows are ordered by `kickoff_time DESC`
- **And** pre-match fixtures (`ft_score IS NULL`) are absent from the table

**Scenario A2: league and season columns contain human-readable display values**
- **Given** a completed fixture whose silver `league.name = 'eng.1'` and
  `season.name = '2024-25'`
- **When** the `completed_matches` table is queried
- **Then** the `league` column contains `'eng.1'` and the `season` column contains
  `'2024-25'`

**Scenario A3: home_team and away_team resolve to canonical team names**
- **Given** a completed fixture with `home_team_id` and `away_team_id` pointing to rows
  in the `team` silver table
- **When** the `completed_matches` table is queried
- **Then** `home_team` contains the canonical `team.name` for the home side
- **And** `away_team` contains the canonical `team.name` for the away side

**Scenario A4: favourite_team is NULL when no Matchbook odds data exists**
- **Given** a completed fixture for which no T-60 Matchbook tick was recorded
  (`match.favourite_team_id IS NULL`)
- **When** the `completed_matches` table is queried for that fixture
- **Then** `favourite_team` is `NULL`
- **And** the row is still present in `completed_matches` (the join is a LEFT JOIN)

**Scenario A5: favourite_team is populated when Matchbook odds data exists**
- **Given** a completed fixture where `match.favourite_team_id` is non-NULL (set by
  T-60 enrichment, Spec 006)
- **When** the `completed_matches` table is queried
- **Then** `favourite_team` contains the canonical `team.name` for the predicted favourite
- **And** the value matches the `team.name` looked up by casting `favourite_team_id` to
  varchar and joining to `team.team_id`

**Scenario A6: Rebuild is idempotent**
- **Given** the silver canonical tables are unchanged between two dbt runs
- **When** `completed_matches` is built twice in succession
- **Then** the resulting table contains the same rows and values both times
  (full-rebuild `+materialized: table`)

---

### Capability B: Parquet export (`completed_matches_export`)

**Scenario B1: External materialization writes a Parquet file at the expected path**
- **Given** the `completed_matches` dbt table has been built
- **When** `dbt build --select completed_matches_export` runs
- **Then** the file `$DATA_DIR/gold/completed_matches.parquet` exists and contains the
  same rows as `completed_matches`
- **And** all eight columns (`match_id`, `kickoff_time`, `league`, `season`, `home_team`,
  `away_team`, `ft_score`, `favourite_team`) are present in the Parquet schema

**Scenario B2: Re-run overwrites the Parquet file (idempotent)**
- **Given** `$DATA_DIR/gold/completed_matches.parquet` already exists from a prior run
- **When** `completed_matches_export` is rebuilt with the same upstream data
- **Then** the file is overwritten with identical content (no duplication, no error)

**Scenario B3: `DATA_DIR` is resolved from the environment variable**
- **Given** the `DATA_DIR` environment variable is set (e.g. to `/workspace/data`)
- **When** the `completed_matches_export` model materializes
- **Then** the Parquet file is written to `/workspace/data/gold/completed_matches.parquet`
- **And** if `DATA_DIR` is unset, the fallback path `/app/data/gold/completed_matches.parquet`
  is used

---

### Capability C: Jupyter notebook queries

**Scenario C1: Analyst reads all completed matches**
- **Given** `$DATA_DIR/gold/completed_matches.parquet` exists and is non-empty
- **When** the analyst runs the `all_matches` cell in the notebook
- **Then** a DataFrame is returned with all rows ordered by `kickoff_time DESC`
- **And** a count is printed as `N completed matches`

**Scenario C2: Analyst counts matches per league**
- **Given** the Parquet contains completed matches from multiple leagues
- **When** the analyst runs the `by_league` cell
- **Then** a DataFrame is returned with `league` and `matches` columns, ordered by
  `matches DESC`

**Scenario C3: Analyst filters to a specific league**
- **Given** the Parquet contains completed matches including some for `league = 'eng.1'`
- **When** the analyst sets `LEAGUE = "eng.1"` and runs the `filter_league` cell
- **Then** only rows where `league = 'eng.1'` are returned, ordered by `kickoff_time DESC`
- **And** the result includes columns `kickoff_time`, `season`, `home_team`, `away_team`,
  `ft_score`, `favourite_team`

**Scenario C4: Analyst queries matches with a Matchbook favourite**
- **Given** the Parquet contains at least one row where `favourite_team IS NOT NULL`
- **When** the analyst runs the `with_favourite` cell
- **Then** only rows where `favourite_team IS NOT NULL` are returned, ordered by
  `kickoff_time DESC`
- **And** the result includes `kickoff_time`, `league`, `home_team`, `away_team`,
  `ft_score`, `favourite_team`

**Scenario C5: Notebook runs when no Matchbook favourite data exists**
- **Given** the Parquet contains completed matches but `favourite_team` is `NULL` for
  all rows (T-60 enrichment has not run or found no matches)
- **When** all four notebook cells are executed
- **Then** cells C1, C2, C3 return results normally
- **And** cell C4 returns an empty DataFrame (no error)

---

## 6. Edge cases & error handling

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | `$DATA_DIR/gold/completed_matches.parquet` does not exist when the notebook runs | The `duckdb.query(read_parquet(...))` call raises a file-not-found error; the notebook displays a Python traceback. The notebook does not attempt to fall back to the DuckLake catalog. The prerequisite cell documents that the Dagster `espn_ingestion` job must run first. |
| E2 | The silver `match` table contains zero rows with `ft_score IS NOT NULL` (e.g. first run before any matches have been played) | `completed_matches` materializes as an empty table (zero rows); `completed_matches_export` writes an empty Parquet with the correct schema; the notebook cells return zero-row DataFrames without error. |
| E3 | `match.favourite_team_id` stores an INT32-typed value (from the T-60 enrichment Parquet) that does not match the VARCHAR `team_id` in the `team` table | The gold model casts `favourite_team_id` to varchar before the LEFT JOIN (`cast(m.favourite_team_id as varchar)`), ensuring the type comparison succeeds. If the cast value still has no matching `team_id`, `favourite_team` is NULL for that row (LEFT JOIN). |
| E4 | A `team_id` referenced by `home_team_id` or `away_team_id` in `match` is absent from the `team` table | The `match.sql` INNER JOINs `home`/`away` teams; an unresolved team_id would cause that fixture to be absent from `completed_matches`. This is guarded upstream by the `relationships` dbt test on `match.home_team_id → team.team_id`. |
| E5 | `DATA_DIR` environment variable is unset when dbt runs the export model | The `env_var('DATA_DIR', '/app/data')` call falls back to `/app/data`; the export writes to `/app/data/gold/completed_matches.parquet`. No error. |
| E6 | `completed_matches_export` runs without `completed_matches` having been built first | dbt resolves the dependency via `ref('completed_matches')` and builds `completed_matches` first automatically when the select includes both, or raises a dependency error if only `completed_matches_export` is selected in isolation. |
| E7 | Duplicate `match_id` values reach `completed_matches` (e.g. from an upstream bug) | The `QUALIFY row_number() … = 1` clause in `match.sql` ensures each `match_id` appears at most once in the silver `match` table. No further deduplication is required in the gold layer. |
| E8 | The notebook `LEAGUE` variable is set to a value that exists in no rows | The `filter_league` query returns an empty DataFrame with the correct column schema and no error. |

## 7. Acceptance criteria

- [ ] AC1 — `completed_matches` contains exactly the rows from the silver `match` table
  where `ft_score IS NOT NULL`; rows with `ft_score IS NULL` are absent.
- [ ] AC2 — Each row in `completed_matches` has exactly these eight columns with the
  correct types: `match_id` (VARCHAR), `kickoff_time` (TIMESTAMP), `league` (VARCHAR),
  `season` (VARCHAR), `home_team` (VARCHAR), `away_team` (VARCHAR), `ft_score` (VARCHAR),
  `favourite_team` (VARCHAR or NULL).
- [ ] AC3 — `league` contains `season.league → league.name` (the league slug, e.g.
  `'eng.1'`); `season` contains `season.name` (the display name, e.g. `'2024-25'`);
  `home_team` and `away_team` contain `team.name` for the respective canonical team ids.
- [ ] AC4 — `favourite_team` is `NULL` for rows where `match.favourite_team_id IS NULL`;
  it contains a canonical `team.name` when `match.favourite_team_id` is non-NULL and
  resolves to a known `team.team_id`.
- [ ] AC5 — Rows are ordered by `kickoff_time DESC` in the `completed_matches` DuckLake
  table (ordering defined in the dbt model itself).
- [ ] AC6 — `completed_matches_export` produces a Parquet file at
  `$DATA_DIR/gold/completed_matches.parquet` containing all rows from `completed_matches`
  with all eight columns present in the Parquet schema.
- [ ] AC7 — Re-running `dbt build --select completed_matches completed_matches_export`
  over unchanged upstream silver data produces identical output (idempotent).
- [ ] AC8 — The notebook `all_matches` cell returns a non-empty DataFrame when the
  Parquet exists and has data; `by_league` returns league-count aggregates; `filter_league`
  filters by the `LEAGUE` variable; `with_favourite` returns only rows where
  `favourite_team IS NOT NULL`.
- [ ] AC9 — The notebook uses `duckdb.query(f"select * from read_parquet('{PARQUET}') …")`
  — it does NOT open a DuckLake connection or connect to `warehouse.duckdb`.
- [ ] AC10 — `completed_matches` and `completed_matches_export` are built as part of the
  standard `@dbt_assets` Dagster asset group and do not require a separate job to be
  registered; they participate in any Dagster job that builds gold dbt models.

## 8. Things to be aware of / constraints

### Repo-level constraints (from CLAUDE.md)

- **Python (and notebooks) must not open DuckLake connections.** The notebook reads
  the exported Parquet via `duckdb.query(read_parquet(...))` — this is an in-process
  ephemeral DuckDB query, not a catalog connection. Do not add a `duckdb.connect()` call
  to the notebook that opens `warehouse.duckdb` or the DuckLake URI.
- **dbt owns the DuckLake catalog.** `completed_matches` and `completed_matches_export`
  are dbt-managed models. No Python asset writes to or reads from the `completed_matches`
  DuckLake table directly; downstream consumers read the Parquet file.
- **dbt external materialization needs `DATA_DIR` at runtime.** The `env_var('DATA_DIR', '/app/data')`
  call in `completed_matches_export.sql` is resolved when dbt executes — not at parse
  time. `dbt parse` succeeds without `DATA_DIR` set; `dbt run`/`dbt build` require it.
- **dbt AssetKey for gold models is prefixed by schema only.** `completed_matches` gets
  `AssetKey(["gold", "completed_matches"])`; `completed_matches_export` gets
  `AssetKey(["gold", "completed_matches_export"])`. No subfolder prefix is added (there
  are no subfolders under `models/gold/`).
- **`+materialized: table` is the default for gold models** (set in `dbt_project.yml`).
  `completed_matches_export` overrides this with `materialized = 'external'` via its
  `config()` block.
- **`favourite_team_id` type mismatch — cast is load-bearing.** The T-60 enrichment
  Parquet stores `favourite_team_id` as INT32 (a Matchbook runner ID). The silver
  `team.team_id` is VARCHAR (an md5 surrogate). The gold model's
  `cast(m.favourite_team_id as varchar)` JOIN condition is therefore required for the
  LEFT JOIN to resolve correctly. Removing the cast breaks the favourite_team resolution
  for all rows.

### Domain constraints

- **"Completed" = `ft_score IS NOT NULL`.** The gold layer does not inspect
  `status_completed` directly; it relies on `match.sql` having already populated
  `ft_score` only when `status_completed = true` in the ESPN bronze. Any fixture that
  `match.sql` emits with `ft_score IS NOT NULL` is, by construction, complete.
- **`league.name` is the league slug** (e.g. `'eng.1'`), not a human-formatted name
  like "English Premier League". This is the upstream convention from ESPN's league
  slugs — the gold model reflects it faithfully. Consumers requiring a display-friendly
  name must either maintain a lookup table or map slugs externally.
- **`season.name` is the display name** (e.g. `'2024-25'`), set by the `season.sql`
  silver model. It is human-readable.
- **`favourite_team` is always nullable** — no Matchbook data → NULL. Consumers must
  handle NULL and should not assume the column is always populated.
- **Ordering is defined in the dbt model, not enforced at the Parquet level.** Parquet
  has no inherent row order. The `ORDER BY kickoff_time DESC` in `completed_matches.sql`
  is preserved in the DuckLake materialization but may not be preserved by all Parquet
  readers. Notebook cells that depend on ordering re-apply `ORDER BY` explicitly.
- **The notebook reads from `DATA_DIR`**, which defaults to `/app/data` inside Docker and
  should be set to `$PWD/data` in local development (matching the `dagster dev` command
  in CLAUDE.md).

### Dependencies on upstream specs

- Requires **Spec 002** (ESPN bronze ingestion) — without ESPN data in the silver
  canonical layer, `completed_matches` is empty.
- Requires **Spec 006** (Matchbook conform + T-60 enrichment) for `favourite_team` to be
  non-NULL for any row. The gold layer works correctly with `favourite_team = NULL`
  everywhere when Spec 006 has not been run.

## 9. Assumptions

1. **`league.name` contains the ESPN league slug**, not a formatted display name. This is
   consistent with the ESPN bronze ingestion (Spec 002) and the `league.sql` silver model.
   If a more human-friendly league label is needed, a seed or mapping table would need to
   be added — that is out of scope here.

2. **The `completed_matches` dbt model is included in the existing `@dbt_assets` asset
   group** via the standard `dbt parse` manifest scan. No explicit Dagster asset
   registration or `deps=` wiring is required beyond placing the SQL file under
   `models/gold/`.

3. **The notebook is run interactively** by analysts after the Dagster pipeline has
   materialized the Parquet. There is no scheduled or automated notebook execution.

4. **The `DATA_DIR` environment variable is available in the notebook environment.** In
   Docker (JupyterLab service), `DATA_DIR` is set in `docker-compose.yml`. Locally,
   analysts should set `DATA_DIR=$PWD/data` or the notebook will use the fallback path
   `/app/data` (and likely not find the file).

5. **No dbt schema test is required on `completed_matches` itself** beyond what the
   upstream silver tests already cover (uniqueness of `match_id`, FK constraints on
   `team_id`, etc.). The gold layer is a projection — if silver tests pass, the gold
   output is structurally correct.

6. **`favourite_team_id` cast to varchar in the gold model is the correct resolution** for
   the INT32 vs VARCHAR type mismatch between the T-60 enrichment Parquet and
   `team.team_id`. This assumption holds as long as the T-60 enrichment asset stores
   canonical `team_id` values (md5 hex strings) as integers — which would be a bug in
   the enrichment asset. If the enrichment asset is corrected to emit VARCHAR `team_id`
   values, the cast becomes a no-op and can be removed.

## 10. Open questions

| # | Question | Blocker? | Best-guess resolution |
|---|----------|----------|-----------------------|
| OQ1 | Should `completed_matches` include a `_schema.yml` entry with column descriptions and dbt tests (e.g. `not_null` on `match_id`, `ft_score`, `home_team`, `away_team`)? | Non-blocker | Yes — adding `not_null` tests on the four non-nullable columns would surface upstream data quality issues early. The current `_schema.yml` only covers `dim_users_by_city`. Best guess: add a `completed_matches` entry in a follow-up. |
| OQ2 | Should `completed_matches` ORDER BY be a dbt-model-level order (current) or left to query consumers? | Non-blocker | Current approach (ORDER BY in model SQL) is acceptable for a gold analytical table. The notebook cells re-apply ORDER BY anyway. No change needed. |
| OQ3 | The `favourite_team_id` INT32 type in the T-60 enrichment Parquet suggests it may be stored as a Matchbook runner numeric ID rather than a canonical `team_id`. If so, the LEFT JOIN to `team.team_id` will always return NULL even when the field is populated. | Potential bug — investigate | This is a known type mismatch acknowledged in the spec context. The cast is present in the gold model. Whether the underlying value is a canonical `team_id` or a raw runner ID needs to be verified against the T-60 enrichment output. If it is a raw runner ID, the join condition is wrong and `favourite_team` will always be NULL even when data exists. Best guess: the T-60 enrichment asset (Spec 006, AC9) resolves to canonical `team_id` via fuzzy-matching — the INT32 storage type is a Parquet artefact of how pandas/pyarrow serializes what is logically a hex string. |

## 11. Traceability

> **Note:** No ADO user stories were pre-created for this feature. The spec was produced
> as a reverse-engineering pass over already-implemented code. Traceability is therefore
> to the implementation inputs described in the skill invocation context
> (`IMP-008-1` through `IMP-008-3`), not to user story work items. `user_stories: []`
> in the frontmatter reflects this.

| Implementation input | Requirements covered | Scenarios | Spec acceptance criteria |
|----------------------|----------------------|-----------|--------------------------|
| IMP-008-1: `completed_matches.sql` — gold dbt table joining match/season/league/team | Completed match projection; column list; ordering; favourite_team nullable join; ft_score IS NOT NULL filter; INT32→varchar cast | A1, A2, A3, A4, A5, A6 | AC1, AC2, AC3, AC4, AC5, AC7 |
| IMP-008-2: `completed_matches_export.sql` — external dbt materialization to Parquet | Parquet export at `$DATA_DIR/gold/completed_matches.parquet`; idempotent overwrite; DATA_DIR env var with fallback | B1, B2, B3 | AC6, AC7, AC10 |
| IMP-008-3: `notebooks/completed_matches.ipynb` — four-cell analytical notebook | All matches; per-league counts; league filter; favourite_team filter; read_parquet pattern; no catalog connection | C1, C2, C3, C4, C5 | AC8, AC9 |
| Design decision: "completed" = ft_score IS NOT NULL | Completion definition; pre-match exclusion | A1 | AC1 |
| Design decision: favourite_team uses LEFT JOIN (nullable) | favourite_team nullability; no data loss for matches without odds | A4, A5, C5 | AC4 |
| Design decision: INT32 → varchar cast on favourite_team_id | Type-safe join to team.team_id | A5, E3 | AC4 |
| Repo constraint: Python reads Parquet, not DuckLake | Notebook uses read_parquet, not duckdb.connect to catalog | C1–C5 | AC9 |
| Repo constraint: dbt owns DuckLake; gold layer adds no canonical identity | Non-goals; no Python writes to DuckLake | A6, B2 | AC7, AC10 |
