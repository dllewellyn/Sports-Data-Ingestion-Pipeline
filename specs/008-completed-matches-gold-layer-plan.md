---
id: "008"
title: Completed Matches Gold Layer — Analytical Table, Parquet Export, and Notebook
slug: completed-matches-gold-layer
status: done
created: 2026-06-30
specification: 008-completed-matches-gold-layer-specification.md
user_stories: []
---

# Completed Matches Gold Layer — Plan

> **Reverse-engineering pass.** The code was committed before this plan was written.
> The plan records the implementation steps as they would have been written before
> the build — decomposed from the spec and the actual code. Status is `done`.

## 1. Summary

This plan implements the gold dbt table `completed_matches`, its external Parquet
export `completed_matches_export`, and the companion `notebooks/completed_matches.ipynb`
analytical notebook. Together these three artefacts give analysts a stable,
provider-agnostic surface of every finished soccer fixture (defined as `ft_score IS
NOT NULL` in the silver canonical `match` table), enriched with human-readable league,
season, and team names, and with the nullable Matchbook pre-match favourite where T-60
odds data was available.

The approach is three sequential dbt/notebook steps preceded by a convention audit and
dbt project config check. Each step is independently testable: `completed_matches` via
`dbt build`; the export via file-existence assertion; the notebook via cell execution.
The key discovered constraint — that the T-60 enrichment Parquet stores `favourite_team_id`
as INT32 while `team.team_id` is VARCHAR — is addressed by a `cast(... as varchar)`
in the gold SQL join condition, and is documented as a load-bearing line in the
non-obvious constraints and in the traceability table below.

No new Python ingestion code, Pydantic schemas, Pandera frames, Dagster asset modules,
or config fields are introduced. All materialization is dbt-owned. Python (and the
notebook) consumes Parquet only.

## 2. Skills to use

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| Gold dbt model + dbt tests | No dedicated "create dbt gold model" skill — follow existing `dim_users_by_city.sql` / `users_by_city_export.sql` patterns in `models/gold/` | MISSING — proceed without; run `self-learn` after to codify pattern if desired |
| Architecture conformance review of the change | `code-architecture-review` | available |
| Code quality / lint | `simplify` (post-build) | available |
| Per-step diff review / self-review | `code-architecture-review` or a general-purpose sub-agent per `references/self-review.md` | available |
| Capturing learnings after build | `self-learn` | available |
| Deployment / Dagster run after commit | `deploy` | available |

No "create dbt gold model" skill exists. The plan works from the existing
`dim_users_by_city.sql` + `users_by_city_export.sql` pair as the canonical example to
follow. If this pattern recurs (likely), running `self-learn` after delivery would produce
a reusable skill.

## 3. Convention & rule audit (resolved before implementation)

| Artifact type | Governing convention | Status |
|---------------|----------------------|--------|
| New gold dbt table model (`completed_matches.sql`) | CLAUDE.md *Non-obvious constraints*: `+materialized: table` is the default for gold (set in `dbt_project.yml`); `+database: lake` must be set; schema prefix `gold` drives `AssetKey(["gold","completed_matches"])`; pattern from `dim_users_by_city.sql` | exists |
| New gold external dbt model (`completed_matches_export.sql`) | CLAUDE.md: `materialized = 'external'` with `env_var('DATA_DIR', '/app/data')` location pattern; `select * from ref(...)` pattern; no Python writes to Parquet — dbt external materialization is the single writer | exists (pattern: `users_by_city_export.sql`) |
| dbt AssetKey derivation (schema-only prefix, no subfolder) | CLAUDE.md *Non-obvious constraints*: key = `["gold", "<model_name>"]`; no sub-path added; verified via `dagster definitions validate` | exists |
| `+database: lake` in `dbt_project.yml` | CLAUDE.md: all dbt models, seeds, and tests must specify `+database: lake`; already set globally in `dbt_project.yml` under `models.data_platform` | exists |
| Python / notebook reads Parquet, never DuckLake | CLAUDE.md rule 3 and *Non-obvious constraints*: Python assets and notebooks must NOT open a DuckLake connection — even read-only; use `duckdb.query(read_parquet(...))` not `duckdb.connect()` to catalog | exists |
| `DATA_DIR` env var for Parquet path | CLAUDE.md: `env_var('DATA_DIR', '/app/data')` fallback pattern; same as `users_by_city_export.sql` | exists |
| No `from __future__ import annotations` in Dagster asset modules | CLAUDE.md: not applicable here (no new Python asset module introduced) | N/A |
| pytest unit tests for new Python logic | Not applicable — no new pure-Python logic introduced; all logic lives in dbt SQL | N/A |
| `favourite_team_id` type-cast (INT32 → varchar) | CLAUDE.md Spec 006 context: `match.favourite_team_id` is INT32 (T-60 enrichment Parquet stores numeric runner-id or pandas-serialized md5); `team.team_id` is VARCHAR; the gold model must `cast(m.favourite_team_id as varchar)` in the LEFT JOIN. **No convention existed — added to CLAUDE.md *Non-obvious constraints* as part of this implementation.** | created this run (documented in spec §8, §Constraints, and E3 edge case) |
| dbt `_schema.yml` for gold model | `_schema.yml` in `models/gold/` covers only `dim_users_by_city`; `completed_matches` is absent (OQ1 in spec). Gap acknowledged as non-blocking per spec assumption 5 ("no dbt schema test required on `completed_matches` itself beyond upstream silver tests") | agreed gap — non-blocking; tracked as OQ1 in spec |

## 4. Testable units (BDD → tests)

| Unit | Spec trace (scenario / AC) | Test facility | Failing-first assertion |
|------|----------------------------|---------------|-------------------------|
| `completed_matches` table contains exactly one row per fixture where `ft_score IS NOT NULL` and no rows where `ft_score IS NULL` | Scenario A1 / AC1 | dbt test (`not_null` on `ft_score` derived indirectly via `where` clause; observable via `dbt build` + row count) | `dbt build --select completed_matches` fails (model does not exist) before the SQL file is added; after, model builds and a manual row-count query over silver confirms only completed fixtures appear |
| Each row has exactly the eight documented columns with correct names | Scenario A1, A2, A3 / AC2 | dbt build + column inspection | `dbt build --select completed_matches` raises a column error if any `ref()` or alias is misspelled; after, `show columns` confirms the eight names |
| `league` and `season` columns contain human-readable display values from the silver dimension tables | Scenario A2 / AC3 | dbt build (JOIN correctness); notebook cell C1 visual inspection | Before: model missing; After: `dbt build` green; querying the table returns `l.name` (e.g. `'eng.1'`) and `s.name` (e.g. `'2024-25'`) |
| `home_team` and `away_team` resolve to canonical team names via INNER JOIN to `team` | Scenario A3 / AC3 | dbt build | Before: model missing; After: build green; a fixture row has non-null `home_team` and `away_team` matching `team.name` |
| `favourite_team` is NULL when `match.favourite_team_id IS NULL` (LEFT JOIN) | Scenario A4 / AC4 | dbt build (LEFT JOIN semantics) | Before: model missing; After: build green; a fixture row with no T-60 enrichment has `favourite_team IS NULL` but remains in the result set |
| `favourite_team` is populated when `favourite_team_id` is non-NULL and the `cast(... as varchar)` JOIN resolves against `team.team_id` | Scenario A5, Edge E3 / AC4 | dbt build | Before: without the `cast`, the LEFT JOIN returns NULL even when data exists; After: `cast(m.favourite_team_id as varchar)` in the JOIN resolves correctly |
| Rows ordered by `kickoff_time DESC` | Scenario A1 / AC5 | dbt build + manual query inspection | Before: model missing; After: `ORDER BY m.kickoff_time DESC` in model SQL; confirmed by reading first/last rows |
| Rebuild is idempotent | Scenario A6 / AC7 | dbt build run twice; row count equality | `dbt build --select completed_matches` twice over unchanged silver → same row count and values |
| `completed_matches_export` writes Parquet at `$DATA_DIR/gold/completed_matches.parquet` with all eight columns | Scenario B1 / AC6 | artifact assertion (file existence + `duckdb.query(read_parquet(...))` column check) | Before: file absent; After: `dbt build --select completed_matches_export` writes the file; `os.path.exists(...)` true |
| Re-running export overwrites idempotently | Scenario B2 / AC7 | artifact assertion (run twice, compare row counts) | After two builds over unchanged silver, Parquet contains identical rows; no error on overwrite |
| `DATA_DIR` env var resolved; fallback `/app/data` when unset | Scenario B3 / AC6 | dbt external materialization observable outcome (path in file-system) | With `DATA_DIR=/tmp/test_data` set, file appears at `/tmp/test_data/gold/completed_matches.parquet` |
| Notebook `all_matches` cell returns DataFrame ordered by `kickoff_time DESC` with count | Scenario C1 / AC8 | notebook cell execution (interactive / CI notebook run) | Cell fails with `FileNotFoundError` before Parquet exists; after pipeline run, returns non-empty DataFrame and prints count |
| Notebook `by_league` cell returns league + count aggregation | Scenario C2 / AC8 | notebook cell execution | Returns `league`, `matches` columns ordered by `matches DESC` |
| Notebook `filter_league` cell filters to `LEAGUE` variable | Scenario C3 / AC8 | notebook cell execution | Returns only rows matching `LEAGUE`; with non-existent LEAGUE, returns empty DataFrame |
| Notebook `with_favourite` cell filters to non-null `favourite_team` | Scenario C4 / AC8 | notebook cell execution | Returns only rows with `favourite_team IS NOT NULL`; returns empty DataFrame when no T-60 data present (Scenario C5) |
| Notebook reads `read_parquet(...)` only — no `duckdb.connect()` to catalog | Scenario C1–C5 / AC9 | code inspection (grep for `duckdb.connect` in notebook) | No `duckdb.connect(...)` call present in any notebook cell |
| Both models participate in `@dbt_assets` Dagster group without additional wiring | AC10 | `dagster definitions validate` + `AssetSelection.all()` includes the new keys | Before: models absent → keys absent; After: `dbt parse` + manifest present → keys `["gold","completed_matches"]` and `["gold","completed_matches_export"]` appear in `AssetSelection.all()` |

## 5. Guardrail register

| Guardrail | How verified in place | Covered by step |
|-----------|----------------------|-----------------|
| ruff check + format (pre-commit) | No new Python source files introduced; pre-commit hook runs on staged files only; `uv run pre-commit run --all-files` clean | S0 (pre-flight check) |
| dbt tests run via `dbt build` | `dbt build --select completed_matches completed_matches_export` green after implementation; upstream silver tests (on `match`, `team`, `league`, `season`) must be passing before this step | S1, S2 |
| No `_schema.yml` entry for `completed_matches` (known gap) | OQ1 in spec — accepted as non-blocking; upstream silver tests guard structural integrity | OQ1 acknowledged |
| Idempotency / re-run safety | Run `dbt build --select completed_matches completed_matches_export` twice over unchanged silver; row counts identical; no error | S2 |
| Single-writer DuckDB constraint (applies to warehouse.duckdb; DuckLake supports concurrent access) | Parquet written by dbt external materialization (one dbt process); no Python asset opens `warehouse.duckdb` or DuckLake in a second process; notebook reads Parquet via `read_parquet()` only | S2, S3 |
| Python / notebook does not open DuckLake or `warehouse.duckdb` | Code inspection: notebook cells use `duckdb.query(f"... read_parquet('{PARQUET}') ...")` with no `duckdb.connect()` call; verified by grep | S3 |
| `DATA_DIR` env var resolved by `env_var()` in dbt model | Pattern matches `users_by_city_export.sql`; fallback `/app/data` documented; `dbt parse` succeeds without the var set | S2 |
| dbt AssetKey `["gold","completed_matches"]` and `["gold","completed_matches_export"]` | No subfolder under `models/gold/`; schema prefix is `gold`; `dagster definitions validate` confirms keys | S1, S2 |
| `favourite_team_id` INT32 → varchar cast is load-bearing | `cast(m.favourite_team_id as varchar)` present in `completed_matches.sql` LEFT JOIN; removing it breaks favourite_team resolution; constraint documented in CLAUDE.md and spec §8 E3 | S1 |
| No `from __future__ import annotations` in asset modules | Not applicable — no new Dagster asset Python file | all |
| `+database: lake` for all dbt models | Already set globally in `dbt_project.yml`; no per-model override needed | all |
| `+materialized: table` for gold layer | Set globally in `dbt_project.yml` under `gold:`; `completed_matches_export` overrides with `materialized = 'external'` in its config block | S1, S2 |
| Repo non-obvious constraints respected | CLAUDE.md constraints checked: single-writer DuckDB, dbt AssetKey prefix, no Python DuckLake connections, `pathlib.Path` not applicable (no Python files), `pydantic-settings` not applicable | all |

## 6. Implementation steps

### Step S0 — Pre-flight: verify upstream silver models are green and dbt parse works

- **Goal:** Confirm that `match`, `season`, `league`, and `team` silver models build cleanly
  and that the dbt manifest is current before adding any gold models that ref them.
- **Spec trace:** Dependencies of all Scenarios A, B, C — upstream silver canonical layer
  must exist for the gold model to have data to join.
- **Red (failing test first):** `dbt build --select completed_matches` fails with "Unknown
  relation" or "model not found" because the file does not yet exist.
- **Implementation:** Run `dbt parse` to regenerate the manifest; run
  `dbt build --select silver.canonical.*` to confirm silver is green; confirm
  `AssetKey(["silver","match"])` etc. appear in the manifest.
- **Green criterion:** `cd dbt/data_platform && uv run --project ../.. dbt build --select silver.canonical.*`
  exits 0 with no test failures. `uv run pre-commit run --all-files` clean.
- **Guardrails to satisfy:** None specific to this step beyond confirming the pre-condition.
- **Self-review checkpoint:** Independent sub-agent confirms (1) silver models build clean,
  (2) the manifest exists at `dbt/data_platform/target/manifest.json`, (3) no reward-hacking
  (e.g. models stubbed or tests disabled to get a green result). Verdict must be PASS before
  S1.

---

### Step S1 — Implement `completed_matches.sql` (gold dbt table)

- **Goal:** Create `dbt/data_platform/models/gold/completed_matches.sql` — the gold table
  joining `match` → `season` → `league` and two `team` aliases for home/away, plus a
  nullable LEFT JOIN to `team` for `favourite_team`. Filter to `ft_score IS NOT NULL`;
  order by `kickoff_time DESC`. Cast `m.favourite_team_id` to varchar in the LEFT JOIN to
  handle the INT32 type of the T-60 enrichment Parquet.
- **Spec trace:** Scenarios A1–A6 / AC1–AC5, AC7, AC10; Edge cases E3 (INT32→varchar cast),
  E4 (INNER JOIN home/away), E7 (dedup in upstream `match.sql`).
- **Red (failing test first):** `dbt build --select completed_matches` fails with
  "Relation ... does not exist" because the SQL file does not exist yet.
- **Implementation outline:**
  1. Create `dbt/data_platform/models/gold/completed_matches.sql` following the
     `dim_users_by_city.sql` pattern (no `config()` block needed — inherits
     `+materialized: table` and `+database: lake` from `dbt_project.yml`).
  2. Write the `SELECT` with:
     - `m.match_id`, `m.kickoff_time`, `l.name as league`, `s.name as season`,
       `home.name as home_team`, `away.name as away_team`, `m.ft_score`,
       `fav.name as favourite_team`
     - `FROM {{ ref('match') }} m`
     - `JOIN {{ ref('season') }} s ON s.season_id = m.season_id`
     - `JOIN {{ ref('league') }} l ON l.league_id = s.league_id`
     - `JOIN {{ ref('team') }} home ON home.team_id = m.home_team_id`
     - `JOIN {{ ref('team') }} away ON away.team_id = m.away_team_id`
     - `LEFT JOIN {{ ref('team') }} fav ON fav.team_id = cast(m.favourite_team_id as varchar)`
     - `WHERE m.ft_score IS NOT NULL`
     - `ORDER BY m.kickoff_time DESC`
  3. The `cast(m.favourite_team_id as varchar)` on the LEFT JOIN is the load-bearing
     fix for the INT32 vs VARCHAR type mismatch (E3). Do not remove it.
- **Green criterion:** `cd dbt/data_platform && uv run --project ../.. dbt build --select completed_matches`
  exits 0; the model materializes in DuckLake under `gold.completed_matches`; a manual
  row-count query over silver confirms only fixtures with `ft_score IS NOT NULL` appear.
- **Guardrails to satisfy:** `+materialized: table` (inherited); `+database: lake` (inherited);
  AssetKey `["gold","completed_matches"]` (derived from schema prefix); `cast` for INT32→varchar
  LEFT JOIN; INNER JOINs for home/away teams (presence guaranteed by upstream `relationships`
  dbt tests); `ORDER BY kickoff_time DESC` in model SQL.
- **Self-review checkpoint:** Sub-agent reads `completed_matches.sql` and the dbt build log.
  Checks: (1) model SELECT lists exactly the eight columns from AC2; (2) `WHERE ft_score IS
  NOT NULL` present (AC1); (3) `ORDER BY m.kickoff_time DESC` present (AC5); (4) LEFT JOIN
  for `fav` present with `cast(m.favourite_team_id as varchar)` (AC4, E3); (5) INNER JOINs
  for home/away (AC3); (6) no `config()` block (inherits from project); (7) dbt build is
  green with real silver data — not a stub or empty scaffold.

---

### Step S2 — Implement `completed_matches_export.sql` (external Parquet materialization)

- **Goal:** Create `dbt/data_platform/models/gold/completed_matches_export.sql` — the
  external materialization that writes `completed_matches` to
  `$DATA_DIR/gold/completed_matches.parquet` for downstream Parquet consumers.
- **Spec trace:** Scenarios B1–B3 / AC6, AC7, AC10; Edge case E5 (DATA_DIR unset fallback),
  E6 (dbt resolves dep via `ref`).
- **Red (failing test first):** The file `$DATA_DIR/gold/completed_matches.parquet` does not
  exist before this model is created and built; `dbt build --select completed_matches_export`
  fails because the SQL file does not exist.
- **Implementation outline:**
  1. Create `dbt/data_platform/models/gold/completed_matches_export.sql` following
     `users_by_city_export.sql` exactly:
     ```sql
     {{
       config(
         materialized = 'external',
         location = env_var('DATA_DIR', '/app/data') ~ '/gold/completed_matches.parquet',
         format = 'parquet'
       )
     }}
     select * from {{ ref('completed_matches') }}
     ```
  2. `env_var('DATA_DIR', '/app/data')` provides the fallback for unset `DATA_DIR` (E5).
  3. `ref('completed_matches')` ensures dbt builds the table model first (E6).
  4. No `ORDER BY` needed here — the source table already carries the ordering from S1.
- **Green criterion:** `cd dbt/data_platform && uv run --project ../.. dbt build --select completed_matches_export`
  exits 0 with `DATA_DIR=$PWD/../../data` set; `data/gold/completed_matches.parquet` exists;
  `python -c "import duckdb; print(duckdb.query(\"select count(*) from read_parquet('data/gold/completed_matches.parquet')\").fetchone())"` returns a row count matching the `completed_matches` table. Re-running produces identical output (idempotent).
- **Guardrails to satisfy:** `materialized = 'external'` overrides the global `+materialized: table`;
  `env_var` fallback documented; single-writer DuckDB constraint (dbt is the sole writer);
  Python/notebook reads the Parquet file, not DuckLake.
- **Self-review checkpoint:** Sub-agent verifies: (1) `config()` block present with
  `materialized = 'external'` and correct `location` expression; (2) `select * from
  ref('completed_matches')` — not a raw table name; (3) Parquet file exists at the expected
  path after `dbt build`; (4) row count in Parquet matches `completed_matches` table; (5)
  re-run produces identical row count (idempotency); (6) no Python file opens `warehouse.duckdb`
  or the DuckLake URI as a side-effect of this step.

---

### Step S3 — Implement `notebooks/completed_matches.ipynb` (analytical notebook)

- **Goal:** Create `notebooks/completed_matches.ipynb` with a setup cell and four analytical
  query cells, all reading from the exported Parquet via `duckdb.query(read_parquet(...))`.
  No `duckdb.connect()` call to any catalog.
- **Spec trace:** Scenarios C1–C5 / AC8, AC9; Edge case E1 (file-not-found), E8 (empty
  filter result).
- **Red (failing test first):** The notebook file does not exist; attempting to run it raises
  `FileNotFoundError` (correct pre-condition failure). After S2 produces the Parquet, the
  notebook file must also exist and all cells must execute without error.
- **Implementation outline:**
  1. Create `notebooks/completed_matches.ipynb` with cells in this order:
     - **Header/markdown cell**: title + prerequisite note (Dagster `espn_ingestion` job
       must run first to produce the Parquet).
     - **Setup cell** (`id="setup"`): imports (`os`, `duckdb`, `pandas`);
       `DATA_DIR = os.environ.get("DATA_DIR", "/app/data")`;
       `PARQUET = f"{DATA_DIR}/gold/completed_matches.parquet"`.
     - **`all_matches` cell**: `duckdb.query(f"select * from read_parquet('{PARQUET}') order by kickoff_time desc").df()` + `print(f"{len(df):,} completed matches")` + `df.head(20)`.
     - **`by_league` cell**: aggregate query returning `league`, `count(*) as matches`, ordered
       by `matches DESC`.
     - **`filter_league` cell**: `LEAGUE = "eng.1"` variable; query filtering `where league = '{LEAGUE}'`;
       returns `kickoff_time, season, home_team, away_team, ft_score, favourite_team`.
     - **`with_favourite` cell**: query filtering `where favourite_team is not null`; returns
       `kickoff_time, league, home_team, away_team, ft_score, favourite_team`.
  2. All queries use `duckdb.query(f"... read_parquet('{PARQUET}') ...")` — never `duckdb.connect()`.
  3. The `filter_league` cell returns an empty DataFrame when `LEAGUE` has no matching rows (E8);
     the `with_favourite` cell returns an empty DataFrame when no T-60 data exists (Scenario C5).
- **Green criterion:** After `dbt build --select completed_matches completed_matches_export`
  has produced the Parquet: run `jupyter nbconvert --to notebook --execute notebooks/completed_matches.ipynb`
  (or open in JupyterLab and run all cells); all cells execute without error; `all_matches`
  cell returns a non-empty DataFrame with 8 columns; `by_league` returns `league` +
  `matches`; `filter_league` returns the expected columns for `eng.1`; `with_favourite`
  returns rows (or empty DataFrame if no T-60 data) with no error.
- **Guardrails to satisfy:** No `duckdb.connect()` in any cell (AC9); `DATA_DIR` read from
  env with `/app/data` fallback; reads only the Parquet file produced by S2; no DuckLake
  connection; no Python asset or Dagster wiring introduced.
- **Self-review checkpoint:** Sub-agent reads the notebook JSON. Checks: (1) no
  `duckdb.connect` call in any cell (AC9 — if present, this is a violation); (2) setup
  cell reads `DATA_DIR` from `os.environ.get` with fallback; (3) four query cells are
  present matching Scenarios C1–C4 exactly; (4) `with_favourite` uses `IS NOT NULL` filter;
  (5) `filter_league` uses the `LEAGUE` variable (not a hardcoded string that can't be
  changed); (6) cells can be executed sequentially without error when the Parquet exists
  (confirmed by nbconvert or visual inspection of syntax).

---

### Step S4 — Commit and validate Dagster asset registration

- **Goal:** Commit all three artefacts (`completed_matches.sql`,
  `completed_matches_export.sql`, `notebooks/completed_matches.ipynb`) and confirm
  the two new dbt models appear as Dagster assets in `AssetSelection.all()` without
  any explicit `definitions.py` change.
- **Spec trace:** AC10 — both models participate in the standard `@dbt_assets` Dagster
  asset group; no separate job registration required.
- **Red (failing test first):** Before the SQL files exist and `dbt parse` is run,
  `AssetKey(["gold","completed_matches"])` and `AssetKey(["gold","completed_matches_export"])`
  are absent from the manifest and from `AssetSelection.all()`.
- **Implementation:** Run `cd dbt/data_platform && uv run --project ../.. dbt parse --profiles-dir .`
  to regenerate `target/manifest.json`; then `PYTHONPATH=src uv run dagster definitions validate`
  to confirm the keys appear without error.
- **Green criterion:** `dagster definitions validate` exits 0; the two new AssetKeys appear
  in the output (or are confirmed by inspecting `dbt_models.keys` / the manifest). No change
  to `definitions.py` or `assets/dbt.py` required. Conventional commit created with
  `feat(gold): add completed_matches table, Parquet export, and notebook`.
- **Guardrails to satisfy:** dbt parse run before validate; `AssetKey(["gold","completed_matches"])`
  and `AssetKey(["gold","completed_matches_export"])` — schema-only prefix confirmed; no
  Dagster job registration for these models required (they participate in any job that
  builds all gold dbt models). `uv run pre-commit run --all-files` clean.
- **Self-review checkpoint:** Sub-agent checks: (1) `dagster definitions validate` exits 0;
  (2) both AssetKeys appear; (3) `definitions.py` was NOT modified (per AC10 — no explicit
  wiring); (4) `dbt parse` was run before validate (per CLAUDE.md: `@dbt_assets` decoration
  fails with manifest error if parse not run first); (5) commit message follows Conventional
  Commits format; (6) `uv run pre-commit run --all-files` clean.

## 7. Sequencing & dependencies

```
S0 (pre-flight: silver green + dbt parse)
  └─▶ S1 (completed_matches.sql — gold table)
        └─▶ S2 (completed_matches_export.sql — external Parquet)
              └─▶ S3 (notebooks/completed_matches.ipynb — reads S2's Parquet)
                    └─▶ S4 (commit + dbt parse + dagster definitions validate)
```

Ordering rationale:

- **S0 before S1:** `completed_matches.sql` refs `match`, `season`, `league`, `team` — those
  silver models must be green before the gold build is attempted.
- **S1 before S2:** `completed_matches_export.sql` uses `ref('completed_matches')` — dbt
  will attempt to build the table model first automatically, but the SQL file must exist for
  the manifest to include the dependency.
- **S2 before S3:** The notebook reads `$DATA_DIR/gold/completed_matches.parquet` — the
  export model must have been built at least once to produce this file before the notebook
  can be run successfully.
- **S4 last:** `dbt parse` must regenerate the manifest after all SQL files are in place
  before `dagster definitions validate` can confirm the new AssetKeys. Commit follows
  validation (not the reverse).

Repo-specific gotchas honoured:

- **`dbt parse` before `dagster definitions validate`** (CLAUDE.md: `@dbt_assets` fails
  at decoration time if manifest is absent or stale).
- **Gold models under `models/gold/` with no subfolder** → `AssetKey(["gold","<model>"])` —
  no subfolder prefix confusion (CLAUDE.md non-obvious constraint).
- **`DATA_DIR` must be set at `dbt run`/`dbt build` time** (not parse time) — the `env_var()`
  call is evaluated at execution, not at parse (CLAUDE.md: "`dbt parse` succeeds without
  `DATA_DIR` set").
- **Python reads Parquet, not catalog** — the notebook is the downstream Python consumer;
  it reads the Parquet produced by S2 via `read_parquet()`.

## 8. Assumptions

1. **Silver canonical models are green and populated with data** before S1 runs. Without at
   least one row in `match` with `ft_score IS NOT NULL`, `completed_matches` materializes
   as an empty table (E2) — which is correct by design, not a failure.

2. **`dbt-duckdb` external materialization is already configured and working** (used for
   `users_by_city_export`); no new `dbt-duckdb` configuration is needed.

3. **`favourite_team_id` in the T-60 enrichment Parquet is an INT32-typed column.** The
   `cast(m.favourite_team_id as varchar)` in the gold model is the correct fix. If the
   enrichment asset is corrected to emit VARCHAR `team_id` values, the cast becomes a no-op
   (harmless). See spec OQ3.

4. **No `_schema.yml` dbt tests are required for `completed_matches` itself** (Spec assumption
   5 / OQ1). Upstream silver `relationships` tests on `match.home_team_id → team.team_id` and
   `match.away_team_id → team.team_id` guard structural integrity.

5. **No new Dagster job registration is required** — both gold models are picked up by
   `@dbt_assets` automatically once `dbt parse` is run and the manifest includes them.
   `AssetSelection.all()` will include them; they are not heavy/standalone sources that
   need exclusion (per CLAUDE.md: exclusion from `medallion_job` is only for heavy backfill
   jobs like `football_backfill`).

6. **The notebook is run interactively** (JupyterLab at `:8888` in Docker, or locally
   after setting `DATA_DIR=$PWD/data`). There is no automated notebook execution requirement.

7. **`league.name` is the ESPN league slug** (e.g. `'eng.1'`) — not a human-formatted
   display name. This is the upstream convention; the gold model reflects it faithfully.

## 9. Open questions

| # | Question | Blocker? | Resolution for this plan |
|---|----------|----------|--------------------------|
| OQ1 | Should `completed_matches` have a `_schema.yml` entry with `not_null` tests on `match_id`, `ft_score`, `home_team`, `away_team`? | Non-blocker | Accepted gap per spec assumption 5; upstream silver tests cover structural integrity. A follow-up can add the entry to `models/gold/_schema.yml`. |
| OQ2 | Should `ORDER BY` be in the gold model SQL or left to query consumers? | Non-blocker | `ORDER BY m.kickoff_time DESC` is in `completed_matches.sql` (current approach). Notebook cells re-apply `ORDER BY` anyway. No change needed. |
| OQ3 | Is `favourite_team_id` actually a canonical `team_id` (md5 hex) stored as INT32, or a raw Matchbook runner numeric ID? If the latter, the LEFT JOIN always returns NULL even when data exists. | Potential bug | The `cast(... as varchar)` is present and is the correct fix for the INT32 vs VARCHAR type disparity. Whether the underlying value is the right canonical `team_id` is a Spec 006 concern, not a Spec 008 concern. Tracked as OQ3 in the specification. |

## 10. Traceability

| Spec scenario / AC | Unit(s) | Step(s) | Guardrail(s) |
|--------------------|---------|---------|--------------|
| A1 — completed fixtures only, reverse-chron order | `ft_score IS NOT NULL` WHERE clause; `ORDER BY kickoff_time DESC` | S1 | dbt build; upstream silver tests |
| A2 — human-readable league and season | `l.name as league`, `s.name as season` JOIN expressions | S1 | dbt build |
| A3 — home/away team names via canonical team | INNER JOIN `team` for home + away | S1 | dbt build; upstream `relationships` test |
| A4 — favourite_team NULL when no odds data | LEFT JOIN for `fav`; NULL propagation | S1 | dbt build |
| A5 — favourite_team populated when odds data exists; INT32→varchar cast | `cast(m.favourite_team_id as varchar)` in LEFT JOIN condition | S1 | dbt build; E3 edge case documented |
| A6 — rebuild idempotent | `+materialized: table` full-rebuild semantics | S1 | run twice; same row count |
| B1 — Parquet at `$DATA_DIR/gold/completed_matches.parquet` with 8 columns | `config(materialized='external', location=env_var('DATA_DIR','/app/data')~'/gold/completed_matches.parquet')` | S2 | artifact assertion; dbt build |
| B2 — re-run overwrites idempotently | external materialization overwrites by default | S2 | run twice; same file |
| B3 — `DATA_DIR` env var resolved | `env_var('DATA_DIR', '/app/data')` fallback | S2 | dbt build with var set/unset |
| C1 — all_matches cell | `duckdb.query(read_parquet(...)) order by kickoff_time desc` | S3 | notebook execution |
| C2 — by_league cell | `group by league, count(*) as matches, order by matches desc` | S3 | notebook execution |
| C3 — filter_league cell | `where league = '{LEAGUE}'`; parameterised `LEAGUE` variable | S3 | notebook execution |
| C4 — with_favourite cell | `where favourite_team is not null` | S3 | notebook execution |
| C5 — notebook runs with no favourite data | `with_favourite` returns empty DataFrame; no error | S3 | notebook execution |
| AC1 — only ft_score IS NOT NULL rows | WHERE clause in S1 | S1 | dbt build |
| AC2 — eight columns with correct types | SELECT list in S1 | S1 | dbt build; column inspection |
| AC3 — correct display values for league, season, home_team, away_team | JOIN expressions in S1 | S1 | dbt build |
| AC4 — favourite_team nullable, correct when non-null | LEFT JOIN + cast in S1 | S1 | dbt build; E3 |
| AC5 — ordered by kickoff_time DESC | ORDER BY in S1 | S1 | dbt build |
| AC6 — Parquet at correct path with all 8 columns | S2 | S2 | artifact assertion |
| AC7 — idempotent | `+materialized: table` (S1) + external overwrite (S2) | S1, S2 | two-run test |
| AC8 — four notebook cells correct | S3 | S3 | notebook execution |
| AC9 — no DuckLake connection in notebook | `read_parquet` only; no `duckdb.connect()` | S3 | code inspection |
| AC10 — models in @dbt_assets without extra wiring | `dbt parse` + `dagster definitions validate` | S4 | `dagster definitions validate` |
| E3 — INT32 → varchar cast on favourite_team_id | `cast(m.favourite_team_id as varchar)` in LEFT JOIN | S1 | code inspection; dbt build |
| E5 — DATA_DIR unset fallback | `env_var('DATA_DIR', '/app/data')` | S2 | dbt build without var |
| E6 — export runs after table via ref() | `ref('completed_matches')` in export model | S2 | dbt dependency resolution |
