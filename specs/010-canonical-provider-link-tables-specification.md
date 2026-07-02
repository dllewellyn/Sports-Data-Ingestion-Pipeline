---
id: "010"
title: Canonical Provider Link Tables & Retirement of the Users Demo Pipeline
slug: canonical-provider-link-tables
status: implemented
created: 2026-07-01
user_stories: []
source_commits: [090497f, 74a3d8c]
investigation: null
related_specs: ["002", "004", "006", "011"]
---

# Canonical Provider Link Tables & Retirement of the Users Demo Pipeline

## 1. Summary

Four canonical provider-to-entity link tables are introduced that map ESPN and
Matchbook provider identifiers to the canonical `league` and `team` entities already
established in the silver layer. Concurrently, the demo users medallion pipeline
shipped with the platform foundation (Spec 004) is fully retired: the `raw_users`
Dagster asset, `publish_gold_parquet` asset, `stg_users` dbt model,
`dim_users_by_city` and `users_by_city_export` dbt gold models, the associated
`_schema.yml` entries, `_sources.yml` entry, and the `api_base_url` / `gold_dir`
config properties are all removed.

The link tables — originally introduced under `models/silver/canonical/` and later
renamed to `int_*` under `models/intermediate/` by Spec 011 — give downstream gold
and conform models a stable cross-walk between raw provider entity keys and canonical
surrogate IDs, without requiring any Python asset to open a DuckLake connection.

## 2. Background & context

This is a **retrospective specification reconstructed from commits `090497f` and
`74a3d8c`**, written after the fact to document already-shipped behaviour; there were
no user stories.

**Spec 004** (Platform Foundation) shipped a demo users medallion pipeline
(`raw_users` → `stg_users` → `dim_users_by_city` → `users_by_city_export` →
`publish_gold_parquet`) to validate end-to-end platform wiring. By the time
specs 002, 005, and 006 had landed real data sources (ESPN and Matchbook), the demo
pipeline had served its purpose and introduced noise: its `api_base_url` config
field pointed at `jsonplaceholder.typicode.com` (a public test API) and its gold
models occupied the gold layer alongside sports analytics models. This commit removes
it cleanly.

**Specs 002 and 006** established the canonical entity tables (`league`, `season`,
`team`, `match`) and match-link tables (`espn_match_link`, `matchbook_event_link`).
A structural gap remained: no cross-walk existed from raw ESPN league slugs or team
IDs to canonical `league_id` / `team_id`, and no cross-walk existed from Matchbook
sport/category or team names to canonical IDs. Downstream gold models wishing to
annotate results with provider keys had to reconstruct these mappings inline. The
four link tables introduced here fill that gap as first-class dbt intermediate models.

**Note on naming:** The models were introduced under `models/silver/canonical/` as
`espn_league_link.sql`, `espn_team_link.sql`, `matchbook_league_link.sql`,
`matchbook_team_link.sql`. Spec 011 subsequently renamed them to
`int_espn_league_link`, `int_espn_team_link`, `int_matchbook_league_link`, and
`int_matchbook_team_link` under `models/intermediate/`. The behaviour described in
this spec is the current post-rename implementation; the rename itself is documented
by Spec 011, not here.

## 3. Goals & non-goals

**Goals**

1. Provide a stable, dbt-managed cross-walk from raw ESPN league slugs to canonical
   `league_id` values (`int_espn_league_link`).
2. Provide a stable cross-walk from raw ESPN team IDs and names to canonical
   `team_id` values, preferring seed-alias resolution over md5 hashing when both
   match (`int_espn_team_link`).
3. Provide a stable cross-walk from Matchbook sport/category pairs to canonical
   `league_id` values, derived by joining the `matchbook_resolved_links` Parquet with
   the `matchbook_events` bronze source (for `sport_id`/`category-id` from `raw_event`)
   and the canonical `int_match` → `int_season` chain (`int_matchbook_league_link`).
4. Provide a stable cross-walk from Matchbook team names (parsed from event names)
   to canonical `team_id` values, derived from `matchbook_resolved_links` joined with
   the `matchbook_events` bronze source (for the `event_name` to parse)
   (`int_matchbook_team_link`).
5. Remove all demo users pipeline artefacts (Dagster assets, dbt models, config
   fields) so the platform contains only production data sources.

**Non-goals (explicitly out of scope)**

- Introducing new canonical identity: these link tables map TO existing canonical
  IDs; they do not mint new ones. New canonical rows go through the conform layers
  (Specs 002 and 006).
- Match-level linking: `int_espn_match_link` and `int_matchbook_event_link` are
  pre-existing intermediate models (Specs 002 and 006); this spec adds league and
  team granularity only.
- A football-data.co.uk league or team link: that source's conform layer is not yet
  implemented.
- Any Python Dagster asset that writes or reads the link tables: they are pure
  dbt-computed models populated from existing bronze and silver sources.
- Populating Matchbook link tables from a dedicated Matchbook conform asset: the
  Matchbook link tables derive from the already-resolved `matchbook_resolved_links`
  bronze source produced by Spec 006 (joined with the `matchbook_events` bronze source
  for event metadata such as `sport_id`, `category-id`, and `event_name`); no new
  Python conform step is added here.

## 4. Actors & triggers

| Actor | Trigger |
|-------|---------|
| dbt CLI / Dagster `@dbt_assets` | `dbt build --select int_espn_league_link int_espn_team_link int_matchbook_league_link int_matchbook_team_link` or any build job that includes intermediate models. |
| dbt relationships test | Runs against `int_espn_league_link.league_id → int_league.league_id` and `int_espn_team_link.team_id → int_team.team_id` as part of `dbt test`. |
| Engineer / CI | Removes the dead users pipeline; `dbt build` no longer errors on missing `users.parquet` for that branch of the DAG. |

## 5. Behaviour specification (BDD)

### Capability A: ESPN league link (`int_espn_league_link`)

**Scenario A1: Every distinct ESPN league slug appears exactly once**
- **Given** `stg_espn_events` contains rows with non-null `league_slug` values
  covering multiple leagues
- **When** `dbt build --select int_espn_league_link` runs
- **Then** `int_espn_league_link` contains exactly one row per distinct `league_slug`
- **And** `link_id` is `md5('espn_league|' || league_slug)` — unique per row

**Scenario A2: league_id is deterministically derived from slug**
- **Given** a row with `league_slug = 'eng.1'`
- **When** `int_espn_league_link` is queried
- **Then** `league_id = md5('eng.1')` for that row
- **And** `match_method = 'deterministic'` and `confidence = 1.0`

**Scenario A3: league_id FK is satisfied**
- **Given** `int_espn_league_link` is built after `int_league`
- **When** the dbt `relationships` test runs on `int_espn_league_link.league_id`
- **Then** every `league_id` in `int_espn_league_link` exists in `int_league.league_id`

---

### Capability B: ESPN team link (`int_espn_team_link`)

**Scenario B1: Teams resolved via seed alias take the seed team_id**
- **Given** `stg_espn_events` contains a team whose `espn_team_name` matches an
  alias in the `team_aliases` seed
- **When** `int_espn_team_link` is built
- **Then** the row for that team has `team_id = seed.team_id` and
  `match_method = 'seed_alias'`

**Scenario B2: Unrecognised teams get a deterministic md5 team_id**
- **Given** `stg_espn_events` contains a team whose `espn_team_name` matches no seed alias
- **When** `int_espn_team_link` is built
- **Then** the row has `team_id = md5(lower(espn_team_name))` and
  `match_method = 'deterministic_md5'`

**Scenario B3: Each ESPN team ID appears at most once (deduplication)**
- **Given** the same `espn_team_id` matches both a seed alias and falls through to
  md5 (e.g. two aliases map to the same ESPN team)
- **When** `int_espn_team_link` is built
- **Then** exactly one row exists per `espn_team_id`
- **And** the `seed_alias` method is preferred over `deterministic_md5` (via
  `QUALIFY row_number() OVER (PARTITION BY espn_team_id ORDER BY match_method DESC) = 1`)

**Scenario B4: link_id is unique per ESPN team ID**
- **Given** `int_espn_team_link` is built
- **When** the dbt `unique` test runs on `link_id`
- **Then** no two rows share the same `link_id`

**Scenario B5: team_id FK is satisfied**
- **Given** `int_espn_team_link` is built after `int_team`
- **When** the dbt `relationships` test runs on `int_espn_team_link.team_id`
- **Then** every `team_id` in `int_espn_team_link` exists in `int_team.team_id`

---

### Capability C: Matchbook league link (`int_matchbook_league_link`)

**Scenario C1: League is resolved by joining through int_match → int_season**
- **Given** `matchbook_resolved_links` bronze source contains a row with a non-empty
  `match_id`, and `int_match` contains that `match_id` with a `season_id` that
  resolves to a `league_id` via `int_season`
- **When** `int_matchbook_league_link` is built
- **Then** the resulting row contains the correct `league_id` for that
  `(sport_id, category_id)` combination
- **And** `match_method` and `confidence` are propagated from `matchbook_resolved_links`

**Scenario C2: Only the highest-confidence link per (sport_id, category_id, league_id) is kept**
- **Given** multiple resolved events map the same `(sport_id, category_id)` pair to
  the same `league_id` with different confidence scores
- **When** `int_matchbook_league_link` is built
- **Then** only the row with the highest confidence is retained
  (`WHERE rn = 1` after `ROW_NUMBER() OVER (... ORDER BY confidence DESC)`)

**Scenario C3: category_id defaults to 'unknown' when absent from raw event**
- **Given** a Matchbook event whose `raw_event` JSON has no `category-id` field
- **When** `int_matchbook_league_link` is built
- **Then** `matchbook_category_id = 'unknown'` for that row (via `COALESCE`)

**Scenario C4: Events with null or empty match_id are excluded**
- **Given** `matchbook_resolved_links` contains rows where `match_id IS NULL` or
  `match_id = ''`
- **When** `int_matchbook_league_link` is built
- **Then** those events do not appear in the output (filtered in the `resolved` CTE)

---

### Capability D: Matchbook team link (`int_matchbook_team_link`)

**Scenario D1: Home and away team names are parsed from ' vs ' event names**
- **Given** a Matchbook event with `event_name = 'Arsenal vs Chelsea'`
- **When** `int_matchbook_team_link` is built
- **Then** rows exist for both `matchbook_team_name = 'Arsenal'` and
  `matchbook_team_name = 'Chelsea'`
- **And** `team_id` for Arsenal is `int_match.home_team_id` and Chelsea is
  `int_match.away_team_id` for the resolved canonical match

**Scenario D2: Events without ' vs ' separator are excluded**
- **Given** a Matchbook event whose `event_name` does not contain ` vs `
  (e.g. an outright market)
- **When** `int_matchbook_team_link` is built
- **Then** no team-name rows are produced from that event

**Scenario D3: Highest-confidence link wins per team name**
- **Given** the same `matchbook_team_name` appears across multiple events resolved
  at different confidence levels
- **When** `int_matchbook_team_link` is built
- **Then** only the highest-confidence `team_id` mapping is retained per
  `matchbook_team_name`

**Scenario D4: Blank team names after trim are excluded**
- **Given** an event name that produces an empty string after splitting and trimming
- **When** `int_matchbook_team_link` is built
- **Then** that empty-string team name is not emitted (`WHERE matchbook_team_name != ''`)

---

### Capability E: Users demo pipeline retired

**Scenario E1: `raw_users` Dagster asset no longer exists**
- **Given** the codebase post-commit `090497f`
- **When** `dagster definitions validate` runs
- **Then** no asset with `AssetKey(["raw_users"])` is registered
- **And** no import of `src/data_platform/assets/bronze.py` (users bronze) is present

**Scenario E2: `publish_gold_parquet` Dagster asset no longer exists**
- **Given** the codebase post-commit `090497f`
- **When** `dagster definitions validate` runs
- **Then** no asset with key `publish_gold_parquet` (the users gold publisher) is registered
- **And** no import of `src/data_platform/assets/gold.py` (users gold) is present

**Scenario E3: Users dbt models are absent from the manifest**
- **Given** `dbt parse` is run against the current codebase
- **When** the manifest is inspected
- **Then** `stg_users`, `dim_users_by_city`, and `users_by_city_export` (users pipeline)
  are absent from the manifest node list

**Scenario E4: `api_base_url` and `gold_dir` config properties are absent**
- **Given** the current `src/data_platform/config.py`
- **When** the `Settings` class is instantiated
- **Then** no `api_base_url` field exists (it pointed at `jsonplaceholder.typicode.com`)
- **And** no `gold_dir` property computed from `data_dir / "gold"` exists in the
  demo form

## 6. Edge cases & error handling

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | `stg_espn_events` is empty (no ESPN bronze data) | `int_espn_league_link` and `int_espn_team_link` materialize as zero-row tables; dbt tests pass (no FK violations from an empty set). |
| E2 | `matchbook_resolved_links` bronze source is empty or absent | `int_matchbook_league_link` and `int_matchbook_team_link` materialize as zero-row tables. |
| E3 | The same ESPN team name matches multiple seed aliases that resolve to different `team_id` values | The `QUALIFY row_number()` clause retains only one row per `espn_team_id`, ordered by `match_method DESC` (alphabetically `seed_alias` > `deterministic_md5`). If two seed aliases for the same ESPN team ID resolve to different `team_id` values, the row ordering within the `seed_alias` partition is non-deterministic — this is a seed data quality issue, not a model bug. |
| E4 | `int_match` has no `league_id` column (the pre-bug-fix state) | `int_matchbook_league_link` would fail at runtime with a column-not-found error. Fix commit `74a3d8c` corrects this by joining `int_match → int_season` to reach `league_id`. Do not remove the `int_season` join. |
| E5 | A Matchbook `category-id` JSON key uses a hyphen rather than underscore | `json_extract_string(raw_event, '$.category-id')` is used explicitly; the hyphen is load-bearing. |
| E6 | `int_espn_team_link.team_id` FK test fails (team not in `int_team`) | Indicates an ESPN team that went through `deterministic_md5` path but whose md5 does not exist in `int_team`. This should not happen if `int_team` is built from the same `stg_espn_events` source, but would surface if the two models are built with different underlying data. |

## 7. Acceptance criteria

- [ ] AC1 — `int_espn_league_link` contains one row per distinct non-null `league_slug`
  in `stg_espn_events`; `link_id` is unique; `league_id` satisfies the FK relationship
  to `int_league.league_id`.
- [ ] AC2 — `int_espn_team_link` contains at most one row per `espn_team_id`;
  `link_id` is unique; `team_id` satisfies the FK relationship to `int_team.team_id`;
  `seed_alias` rows are preferred over `deterministic_md5` rows for the same `espn_team_id`.
- [ ] AC3 — `int_matchbook_league_link` contains at most one row per
  `(matchbook_sport_id, matchbook_category_id, league_id)` triple; `link_id` is
  unique; `match_method` and `confidence` are propagated from the resolved-links source.
- [ ] AC4 — `int_matchbook_team_link` contains at most one row per `matchbook_team_name`;
  `link_id` is unique; team names are parsed from ` vs `-separated event names only.
- [ ] AC5 — All four link models rebuild idempotently from the same upstream data.
- [ ] AC6 — `dbt build --select int_espn_league_link int_espn_team_link
  int_matchbook_league_link int_matchbook_team_link` passes all dbt tests defined in
  `_intermediate.yml`. Note the test coverage is **not uniform**: `link_id` carries
  `not_null`/`unique` on all four models, and a `relationships` FK test to the canonical
  target exists on the **ESPN** link tables (`int_espn_league_link.league_id`,
  `int_espn_team_link.team_id`) but is **absent** on the **Matchbook** link tables
  (`int_matchbook_league_link.league_id`, `int_matchbook_team_link.team_id`) — see OQ3.
- [ ] AC7 — No file named `bronze.py` (users) or `gold.py` (users) exists under
  `src/data_platform/assets/`; no `AssetKey(["raw_users"])` or `publish_gold_parquet`
  asset is registered in the Dagster definitions.
- [ ] AC8 — `stg_users`, `dim_users_by_city`, and `users_by_city_export` (users demo)
  are absent from the dbt project manifest.
- [ ] AC9 — `Settings` in `config.py` has no `api_base_url` field (the `jsonplaceholder`
  demo URL) and no `gold_dir` property in the form removed here.
- [ ] AC10 — `dbt parse` and `dagster definitions validate` both succeed after the removal.

## 8. Things to be aware of / constraints

### Non-obvious constraints from CLAUDE.md

- **dbt AssetKey uses schema-prefix only, not subfolder prefix.** The link models
  under `models/intermediate/` get `AssetKey(["intermediate", "<model_name>"])`. Any
  cross-asset `deps=[]` wiring in Python must use this key, not one that includes a
  deeper subfolder path. The dbt _selector_ uses dot-separated folders (e.g.
  `intermediate.int_espn_team_link`); the Dagster AssetKey uses the schema prefix
  only — these are two different namings.
- **Python assets must NOT open a DuckLake connection, even read-only.** The link
  tables are pure dbt models. Any downstream Python asset that needs cross-walk data
  must consume a dbt external Parquet export, not connect to DuckLake directly.
- **`int_matchbook_league_link` reaches `league_id` via `int_season`, not directly
  from `int_match`.** `int_match` has no `league_id` column; the canonical path is
  `int_match.season_id → int_season.league_id`. The bug introduced in `090497f`
  (selecting `league_id` from `int_match` directly) was fixed in `74a3d8c`. Do not
  revert to the direct `int_match` join.
- **`QUALIFY row_number()` ordering is alphabetically `seed_alias > deterministic_md5`.**
  The `ORDER BY match_method DESC` clause in `int_espn_team_link` resolves ties in
  favour of `seed_alias` because 's' > 'd' lexicographically. This is intentional
  but implicit — if a new `match_method` value is added that should rank higher,
  the ordering expression must be made explicit (e.g. via a `CASE`).
- **Canonical team identity is the md5 surrogate from `int_team`, not a raw provider
  ID.** `int_espn_team_link.team_id` is always a canonical surrogate (either from the
  seed or from `md5(lower(espn_team_name))`). Never use ESPN's numeric `team_id` as
  a canonical identifier; the link table is the cross-walk seam.
- **The `relationships` FK tests in `_intermediate.yml` are the primary correctness
  gates** for `int_espn_league_link.league_id` and `int_espn_team_link.team_id`. No
  Python test covers these; `dbt test` is the assertion point.

### Domain constraints

- **Matchbook team names are parsed, not looked up.** `int_matchbook_team_link`
  extracts team names from the free-text `event_name` field using ` vs ` as a
  separator. Variations in name casing, punctuation, or abbreviation across events
  may produce multiple link rows for what is semantically the same team — the highest-
  confidence row wins, but name normalisation is not performed.
- **Matchbook category resolution depends on the conform layer having run.** Both
  Matchbook link tables draw from **two** bronze sources: `matchbook_resolved_links`
  (produced by the Matchbook conform Dagster asset, Spec 006) for the resolved
  `match_id`/`match_method`/`confidence`, **and** `matchbook_events` for event metadata
  (`sport_id`, `category-id`, and the `event_name` string parsed for team names). If the
  conform asset has not run, `matchbook_resolved_links` is absent and these link tables
  are empty even when `matchbook_events` bronze data exists.
- **ESPN link tables are purely dbt-computed from bronze.** `int_espn_league_link`
  and `int_espn_team_link` read only from `stg_espn_events` and the `team_aliases`
  seed. No Python conform asset is required; they populate as part of any dbt build
  that includes the intermediate layer.

## 9. Assumptions

1. **`int_league` is populated before `int_espn_league_link` is tested.** The FK
   relationship test passes because both models share the same `md5(league_slug)`
   identity formula; `int_league` is built from the same `stg_espn_events` source.
   If `int_league` is rebuilt with different upstream data, the FK test may fail —
   this is a data quality signal, not a model bug.

2. **The `team_aliases` seed is the single source of truth for canonical team identity.**
   `int_espn_team_link` uses the seed exclusively for alias resolution; there is no
   secondary fuzzy-matching step. Teams absent from the seed receive an md5 surrogate
   that matches what `int_team` also mints for the same name.

3. **The Matchbook `raw_event` JSON key is `category-id` (with a hyphen).** The
   `json_extract_string(raw_event, '$.category-id')` call is load-bearing; any change
   to the upstream bronze JSON field name would break category extraction.

4. **Retiring `gold_dir` from config does not break other config consumers.** No
   other module in `src/data_platform/` referenced `settings.gold_dir`. Gold Parquet
   paths in active gold dbt models use `env_var('DATA_DIR')` directly, not the
   Python `Settings` object.

5. **The `api_base_url` config field was used exclusively by the removed `raw_users`
   asset.** No other asset or module in the codebase referenced `settings.api_base_url`
   after the removal. Removing it is therefore safe and leaves no dangling references.

## 10. Open questions

| # | Question | Blocker? | Notes |
|---|----------|----------|-------|
| OQ1 | Why was the users demo pipeline removed at this commit rather than earlier or as a standalone cleanup? | Non-blocker (unverified intent) | Likely timed to coincide with the addition of real link tables so the gold layer remained coherent. Cannot be confirmed from commit message alone. |
| OQ2 | Are the Matchbook link tables (`int_matchbook_league_link`, `int_matchbook_team_link`) currently populated from a living conform asset, or only if the Spec 006 resolved-links Parquet exists from a prior run? | Non-blocker (operational) | Both tables depend on `matchbook_resolved_links` bronze source; if that source is absent they materialise empty. No new conform step was added in this spec. |
| OQ3 | Should the Matchbook link tables carry FK `relationships` tests to their canonical targets — `int_matchbook_team_link.team_id` → `int_team.team_id` and `int_matchbook_league_link.league_id` → `int_league.league_id`? | Non-blocker | The current `_intermediate.yml` entries for both Matchbook link tables list the FK columns with a description but **no** `relationships` test, whereas both ESPN link tables have them. Adding them for Matchbook would catch resolution drift; currently omitted (likely an oversight rather than a deliberate decision — intent unverified). |
| OQ4 | Is the `ORDER BY match_method DESC` tie-break in `int_espn_team_link` robust if new match methods are added? | Non-blocker (future risk) | Currently safe because only `seed_alias` and `deterministic_md5` exist. A third method (e.g. `fuzzy`) would require an explicit priority `CASE` expression. |

## 11. Traceability

> **Note:** No user stories were pre-created for this feature. The spec was produced
> as a retrospective reverse-engineering pass over commits `090497f` and `74a3d8c`.
> Traceability is to source commits, not user story work items. `user_stories: []`
> in the frontmatter reflects this.

| Source commit | Description | Scenarios | Acceptance criteria |
|---------------|-------------|-----------|---------------------|
| `090497f` | Deletes users bronze/gold assets, `stg_users`, `dim_users_by_city`, `users_by_city_export`, users config fields; introduces `espn_league_link`, `espn_team_link`, `matchbook_league_link`, `matchbook_team_link` under `models/silver/canonical/` | A1, A2, A3, B1, B2, B4, B5, C1, C2, C3, C4, D1, D2, D3, D4, E1, E2, E3, E4 | AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10 |
| `74a3d8c` | Fixes `int_matchbook_league_link` to join through `int_season` for `league_id`; adds `QUALIFY row_number()` deduplication to `int_espn_team_link` | B3, C1 (corrected join), E4 | AC2 (dedup), AC3 (correct league join) |
| Spec 011 (rename) | Renames models from `silver/canonical/` to `intermediate/int_*` — behaviour unchanged | All | All — naming change only, no logic change |
