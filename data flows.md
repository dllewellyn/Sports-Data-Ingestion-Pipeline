# Data Flows

End-to-end description of how data enters, gets linked, and is enriched across the pipeline.

## Sources

| Source | What it provides | Schedule |
|---|---|---|
| **ESPN API** | Match fixtures, final scores, team/league metadata | Every 6 hours (`espn_every_6h`) |
| **Matchbook events API** | Open betting events, kickoff times, total liquidity | Every 6 hours (`matchbook_every_6h`, offset 15 min from ESPN) |
| **Matchbook odds** (Redis ingestor) | Pre/in-play prices per market and runner, volumes, WoM | Continuously (separate service) |

---

## Bronze layer — faithful ingest

Raw data written as Parquet, one file per logical partition. No enrichment or joining here.

### ESPN (`espn_ingestion` job → `espn_bronze` asset)
- Fetches scoreboards for each configured league and season window from the ESPN soccer API.
- Writes `data/bronze/espn/<league_slug>/<season_year>.parquet`
- Each row: `espn_event_id`, `kickoff_time`, `home_team_name`, `away_team_name`, `home_score`, `away_score`, `status_name`, `status_completed`, plus verbatim `raw_event` JSON.
- Scores are `NULL` until ESPN marks `status_completed = true` — subsequent ingest runs overwrite the file with the final score populated.

### Matchbook events (`matchbook_ingestion` job → `matchbook_events_bronze` asset)
- Fetches open events from the Matchbook API, filtered to football and rugby union.
- Writes `data/bronze/matchbook_events/<sport>/<date>/<batch_ts>.parquet`
- Each row: `event_id`, `event_name`, `sport_id`, `status`, `start_utc`, `volume`, `raw_event` JSON.

### Matchbook odds (Redis ingestor — separate service)
- A long-lived daemon (`matchbook/ingestor/`, the `matchbook-ingestor` compose service)
  subscribes to the Redis `matchbook_odds_stream` pub/sub channel and writes ZSTD Parquet
  to `data/bronze/matchbook_odds/year=YYYY/month=MM/day=DD/part-<ts>.parquet` (flush every
  5 000 ticks or 60 s).
- Each row: `event_id`, `market_id`, `runner_id`, `ingested_at`, `best_back_price`, `best_lay_price`, depths, volumes, WoM, `kickoff_ms`.
- Because it runs continuously (not a batch pull), Dagster does **not** materialize it. Its
  output is represented by the `matchbook_odds_bronze` **observable source asset** — this
  gives `stg_matchbook_odds` a real upstream node in the asset graph and records freshness
  (age of the newest tick Parquet) via the `matchbook_odds_observe` job + its `odds_stream_fresh`
  check (WARNs when no ticks have landed for over an hour).

---

## Silver layer — canonical model (dbt + Python)

The canonical model is built by a **symmetric cross-provider conform layer**: ESPN
conforms in **SQL** and is the **union base**; every other provider conforms in
**Python** and contributes canonical rows *additively*. Each `int_<entity>` model is
`ESPN base CTE UNION ALL read_parquet(<provider>_canonical_<entity>_additions.parquet)`,
keep-one on the id.

### Step 1 — Canonical dimensions: ESPN base (dbt, part of `espn_ingestion` AND `matchbook_ingestion`)

ESPN bronze is the **union base for match identity**. These dbt models
(`models/intermediate/int_*`) rebuild after each ESPN ingest, and *also* after each
Matchbook conform step (below) within the same `matchbook_ingestion` run — they union
every provider's contributions and are not "owned" by either job. Each provider's
`<provider>_canonical_<entity>_additions.parquet` is read via a dbt `source()` (not a
raw `read_parquet()` literal), registered in `_sources.yml` and mapped in
`BronzeAwareTranslator` to the asset that produces it; that's what makes Dagster
schedule the canonical rebuild immediately after that provider mints something, instead
of only picking it up whenever `espn_ingestion` next happens to run:

| Model | What it builds |
|---|---|
| `stg_espn_events` | Staging view over all ESPN bronze Parquet |
| `int_league` | Canonical leagues: `league_id = md5(league_slug)` (+ per-provider additions) |
| `int_season` | Canonical seasons: `season_id = md5(league_id \| season_year)` (+ additions) |
| `int_team` | Canonical teams, alias-resolved via the `team_aliases` seed (+ additions) |
| `int_match` | One row per fixture — `match_id` is a deterministic surrogate over (league, season, kickoff date, home team, away team). `ft_score` populated when `status_completed = true`, else `NULL`. `favourite_team_id` joined from T-60 enrichment (below). Unions ESPN + per-provider additions. |
| `int_espn_match_link` | Maps `espn_event_id → match_id` |

**Key design decision:** `match_id` is computed by the `canonical_match_id` macro over *canonical* resolved identifiers — never raw provider IDs. This means a Matchbook or football-data event describing the same real-world fixture lands on the **same** `match_id` once resolved. Non-ESPN providers resolve their whole `season → league → team` chain **seed-first**: `team_aliases` for teams, `league_aliases` (`seeds/league_aliases.csv`, registered in `seeds/_seeds.yml`) for leagues, then the shared `canonical_match_id` replica for the match.

### Step 2 — Canonical data exported for Python (dbt external models)

Because Python assets must not open a DuckLake connection, external Parquet exports bridge dbt → Python (regenerated each `espn_ingestion` run):
- `data/silver/canonical/match.parquet` (`canonical_match_export`)
- `data/silver/canonical/team.parquet` (`canonical_team_export`)
- (+ league/season exports for the seed-first chain resolution)

### Step 3 — Python conform per provider (`conform/`, symmetric)

Each non-ESPN provider has a module under `src/data_platform/conform/`
(`matchbook.py` live; `football_data.py` scaffolded), all sharing the `resolve.py`
identity authority. A provider's conform asset reads bronze events + the canonical
Parquet exports, fuzzy-matches on team-name similarity + kickoff proximity, applies
human overrides, and **mints canonical rows** for fixtures ESPN doesn't have. It
writes **four** additions files plus links/exceptions. For Matchbook this runs inside
the single `matchbook_ingestion` job (bronze -> conform -> the Step 1 canonical rebuild
above -> T-60), so a freshly-minted team/league/season/match is visible by the end of
that same run — not a separately-scheduled job hours later:
- `data/silver/<provider>_canonical_{match,team,league,season}_additions.parquet` — one per canonical entity the minted match's `season → league → team` chain references; unioned back into `int_{match,team,league,season}` via `read_parquet` + `UNION ALL`. These are **bootstrap-written empty** (correct columns, zero rows) by `conform.bootstrap_additions_files` so the `int_*` `read_parquet` unions stay green before a provider mints anything (`read_parquet` errors on a missing file — it does not silently return zero rows, so the empty file must exist).
- `data/silver/<provider>_resolved_links.parquet` — linked events with `<provider>_event_id → match_id`, confidence, review status → `int_<provider>_*_link` (dbt).
- `data/exceptions/<provider>_unresolved.parquet` — events that couldn't be matched.

Matchbook current resolution rate: ~18% (142/791 football events). Low rate reflects ESPN's limited league coverage vs Matchbook's global footprint — it improves as ESPN data grows. football-data's conform body is a `NotImplementedError` scaffold; its four additions files bootstrap empty so `int_*` stays green.

### Step 4 — T-60 enrichment (`matchbook_t60_enrichment` Python asset)

Reads the resolved links and the odds bronze lake. Finds the best-back price per team at T−60 minutes before kickoff, determines which team was the market favourite, and writes `data/silver/matchbook_t60_enrichment.parquet`.

`int_match` left-joins this file → `favourite_team_id` column on the canonical match table.

---

## What's currently in each table

| Table | Row count (approx) | Key columns |
|---|---|---|
| `match` | 5,493 | `match_id`, `ft_score` (populated post-match), `favourite_team_id` |
| `team` | 1,000 | `team_id`, `name` |
| `league` | 94 | `league_id`, `name`, `is_tournament` |
| `espn_match_link` | 5,496 | `espn_event_id → match_id` |
| `matchbook_event_link` | 142 | `matchbook_event_id → match_id` |

---

## Gold layer — analytics-ready views

### `completed_matches` (dbt gold table + Parquet export)

One row per finished fixture. Filters `match` to rows where `ft_score IS NOT NULL`
and joins in all human-readable context:

| Column | Source |
|---|---|
| `match_id` | canonical surrogate |
| `kickoff_time` | UTC timestamp |
| `league` | `league.name` (league slug, e.g. `eng.1`) |
| `season` | `season.name` (display name, e.g. `2024-25`) |
| `home_team` / `away_team` | `team.name` |
| `ft_score` | `match.ft_score` (e.g. `2-1`) |
| `favourite_team` | `team.name` for the pre-match Matchbook favourite (NULL when no odds data) |

Written to `data/gold/completed_matches.parquet` by `completed_matches_export` (dbt external materialization).

**Notebook:** `notebooks/completed_matches.ipynb` — query the Parquet directly with DuckDB; cells for all matches, per-league breakdown, league filter, and matches with a Matchbook favourite.

## How raw odds and scores come together (future gold)

The completed_matches gold table does not yet expose raw pre-match odds ticks.
To build a deeper analytics view, join:

```
completed_matches (match_id, ft_score, favourite_team)
  ↑ match_id
matchbook_event_link (matchbook_event_id → match_id)
  ↑ matchbook_event_id = event_id
stg_matchbook_odds (market_id, runner_id, best_back_price, ingested_at, kickoff_ms)
  filter: ingested_at < kickoff_time  -- pre-match only
```

---

## Update policy

**Keep this file current whenever the data flow changes.** Specifically update it when:
- A new data source is added (new bronze asset)
- A new dbt model is added to the silver or gold layer
- The conform or enrichment logic changes materially
- Row counts change significantly (after a bulk backfill or new league coverage)
- A gold analytics model is built

This file is the primary reference for understanding how the pipeline fits together end-to-end.
