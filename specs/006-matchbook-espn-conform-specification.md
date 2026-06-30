---
id: "006"
title: Matchbook & ESPN Conform Layer — Canonical Linkage, T-60 Enrichment, and Exceptions UI
slug: matchbook-espn-conform
status: draft
created: 2026-06-29
user_stories: []
investigation: null
related_specs: ["002", "003", "004", "005"]
---

# Matchbook & ESPN Conform Layer — Canonical Linkage, T-60 Enrichment, and Exceptions UI

## 1. Summary

After bronze ingestion of Matchbook events (Spec 004) and ESPN scoreboards (Spec 002), a
new set of conform layers and enrichment pipelines links provider records to canonical
match entities, enriches the canonical `match` table with pre-match favourite data from
the Matchbook odds lake (Spec 005), and surfaces unresolved events in a human-reviewable
Streamlit exceptions queue. The result is a fully connected canonical domain model — every
Matchbook football event either links to an existing canonical match (with confidence and
review status), creates a new canonical entity, or lands in a human-review queue.
Unresolved events that the human confirms are stored as durable overrides and consumed
on the next pipeline run, completing the linkage loop without operator-level database
intervention.

## 2. Background & context

Specs 002 and 004 established the two upstream bronze layers this spec consumes:

- **ESPN bronze** (`espn_bronze` asset, `data/bronze/espn/**/*.parquet`) — soccer
  scoreboards providing canonical `league`, `season`, `team`, `match`, and
  `espn_match_link` rows. `match.favourite_team_id` is already a column in the dbt
  model (`match.sql`) but currently always `NULL` (no favourites data yet).
- **Matchbook events bronze** (`matchbook_events_bronze` asset,
  `data/bronze/matchbook_events/<sport>/<date>/<batch-ts>.parquet`) — open Matchbook
  football and rugby-union events, each with `event_id`, `event_name` (format
  "Team A v Team B"), `start_utc`, and the full `raw_event` JSON.
- **Matchbook odds bronze** (Spec 005, `data/bronze/matchbook_odds/**/*.parquet`) — high-
  frequency tick data with `event_id`, `market_type`, `runner_id`, `best_back_price`,
  `kickoff_ms`, and `ingested_at`.

The `matchbook_event_link` model is currently an empty typed scaffold
(`select cast(null …) limit 0`). This spec populates it. The linkage design (fuzzy
matching, confidence tiers, exceptions queue) and the persistence mechanism for human
decisions (Parquet overrides file) were established up-front in the feature description.

ESPN score enrichment already works: `match.ft_score` is populated when
`status_completed = true` in the ESPN bronze, and the ESPN job re-derives canonical rows
deterministically on each run.

---

## 3. Goals & non-goals

**Goals**

1. A Python `matchbook_conform` Dagster asset runs after `matchbook_events_bronze` and
   links each Matchbook football event to a canonical `match` row (or creates one), using
   multi-tier fuzzy matching plus human-override lookups.
2. Unresolvable Matchbook events are written to `data/exceptions/matchbook_unresolved.parquet`
   for human review.
3. A dbt model (`matchbook_event_link.sql`) is replaced from its empty scaffold with a
   real model reading from the resolved-links Parquet produced by the Python conform asset,
   and writing a fully-typed `matchbook_event_link` table in DuckLake.
4. A Python `matchbook_t60_enrichment` Dagster asset reads the Matchbook odds bronze lake,
   filters to ticks at approximately `kickoff_time − 60 minutes` (±15 min tolerance),
   identifies the favourite team (runner with the lowest `best_back_price` in the
   "Match Odds" market), and writes `data/silver/matchbook_t60_enrichment.parquet`.
5. A dbt model reads the T-60 enrichment Parquet and updates `match.favourite_team_id`.
6. A Streamlit app (added to `docker-compose.yml`) reads
   `data/exceptions/matchbook_unresolved.parquet`, presents candidate canonical matches,
   and records human decisions to `data/manual_links/matchbook_overrides.parquet`.
7. The `matchbook_conform` asset reads `matchbook_overrides.parquet` on every run and
   treats its decisions as definitive (`confidence = 1.0`, `review_status = 'human_confirmed'`).
8. The ESPN score enrichment pipeline is documented as already working; the ESPN job is
   confirmed to re-trigger a dbt build so new final scores are picked up automatically.
9. All new Dagster assets are excluded from `medallion_hello_world`; a dedicated
   `matchbook_conform_job` runs the conform + enrichment assets.

**Non-goals (explicitly out of scope)**

- Rugby-union Matchbook event linkage — this spec covers football events only (sport-id 15).
- Matchbook market or runner name enrichment from an external catalogue — market/runner ids
  are used as-is from the odds lake.
- Merging two existing canonical records in DuckLake directly from the Streamlit UI —
  the UI writes a merge decision to the overrides Parquet; the Python asset acts on it in
  the next pipeline run (no direct DuckLake writes from the UI or any Python conform asset).
- Football-data.co.uk linkage (`football_data_match_link` population) — remains an empty
  scaffold; deferred to a separate spec.
- Re-fetching Matchbook API data for historical events not in bronze — the conform layer
  reads only what is in the bronze Parquet lake.
- Real-time / streaming linkage — this is a scheduled batch pipeline.
- Automated CI tests that require a live DuckLake catalog or Matchbook API — tests cover
  pure-Python logic only (matching engine, parsing, score extraction).
- Gold-layer aggregations using `matchbook_event_link` or `favourite_team_id` — this spec
  delivers the silver conform layer only.

---

## 4. Actors & triggers

| Actor | Trigger |
|-------|---------|
| Dagster scheduler | `matchbook_events_schedule` (`0 */6 * * *`) completes `matchbook_events_bronze`; the downstream `matchbook_conform` asset is then triggered by the `matchbook_conform_job` schedule. |
| Dagster scheduler | `espn_every_6h` runs `espn_ingestion` job; the dbt build inside it re-derives `match.ft_score` automatically. |
| Dagster scheduler | `matchbook_conform_job` (suggested: `0 1,7,13,19 * * *`) runs `matchbook_conform` → `matchbook_t60_enrichment` → dbt build of the affected silver models. |
| Engineer | Manual job launch via Dagster UI for any of the above jobs. |
| Human reviewer | Opens the Streamlit exceptions UI; reviews unresolved events; submits decisions. |
| Streamlit app | On form submission, appends/overwrites the `matchbook_overrides.parquet` file. |

---

## 5. Behaviour specification (BDD)

### Capability A: Matchbook conform — event parsing and name extraction

**Scenario A1: Parse "Team A v Team B" event name into home/away team names**
- **Given** a Matchbook event with `event_name = "Arsenal v Chelsea"`
- **When** the conform engine processes the event
- **Then** the home team name is `"Arsenal"` and the away team name is `"Chelsea"`
- **And** the split is performed on the literal string ` v ` (space-v-space)

**Scenario A2: Event name does not contain " v " separator**
- **Given** a Matchbook event with `event_name` that does not contain ` v `
  (e.g. a non-football or malformed event)
- **When** the conform engine processes the event
- **Then** the event is written to the exceptions Parquet with
  `unresolved_reason = 'unparseable_event_name'`
- **And** no link row is produced for this event

---

### Capability B: Matchbook conform — override lookup (human-confirmed decisions)

**Scenario B1: Human override exists for a Matchbook event**
- **Given** `data/manual_links/matchbook_overrides.parquet` contains a row for
  `matchbook_event_id = X` with a confirmed `match_id` (or `action = 'new_canonical'`
  or `action = 'merge'`)
- **When** the conform asset runs and processes event X
- **Then** the override row is used directly: `confidence = 1.0`,
  `review_status = 'human_confirmed'`, `match_method = 'human_override'`
- **And** the fuzzy matching engine is NOT consulted for event X
- **And** the resolved-links Parquet contains this row

**Scenario B2: Override file is absent (first run, no human reviews yet)**
- **Given** `data/manual_links/matchbook_overrides.parquet` does not exist
- **When** the conform asset runs
- **Then** the asset proceeds normally with zero overrides (no error)
- **And** only fuzzy matching is applied to all events

---

### Capability C: Matchbook conform — HIGH CONFIDENCE auto-link

**Scenario C1: Home and away team fuzzy match above threshold, kickoff within tolerance**
- **Given** a parsed Matchbook event with home team `"Man City"`, away team
  `"Tottenham"`, and kickoff `2026-08-10T15:00:00Z`
- **And** the canonical `match` table contains a match with home `team.name = "Manchester City"`,
  away `team.name = "Tottenham Hotspur"` (or their aliases), and
  `kickoff_time = 2026-08-10T14:30:00Z`
- **And** the fuzzy team-name ratio (rapidfuzz `token_sort_ratio`) is ≥ 0.85 for both
  home AND away, AND the kickoff time difference is ≤ 90 minutes
- **When** the conform engine evaluates the event
- **Then** the link is auto-confirmed: `confidence = 0.95` (exact constant),
  `review_status = 'auto_confirmed'`, `match_method = 'fuzzy_high'`
- **And** the resolved-links Parquet contains one row for this event pointing to that
  `match_id`

**Scenario C2: Team name scores meet HIGH threshold but kickoff difference exceeds 90 min**
- **Given** a Matchbook event with team names that score ≥ 0.85 against a canonical match
- **And** the kickoff difference between the Matchbook `start_utc` and the canonical
  `kickoff_time` is > 90 minutes
- **When** the conform engine evaluates the event
- **Then** the HIGH CONFIDENCE path does not apply
- **And** the MEDIUM CONFIDENCE path is attempted next

---

### Capability D: Matchbook conform — MEDIUM CONFIDENCE auto-link with flag

**Scenario D1: MEDIUM confidence — uniquely resolved to one canonical match**
- **Given** a parsed Matchbook event that does NOT meet HIGH CONFIDENCE criteria
- **And** the fuzzy team-name ratio is ≥ 0.70 for both home AND away (but less than
  0.85 for at least one), AND the kickoff difference is ≤ 90 minutes
- **And** exactly one canonical match satisfies these criteria
- **When** the conform engine evaluates the event
- **Then** the link is auto-linked with review flag: `confidence = 0.75` (exact constant),
  `review_status = 'needs_review'`, `match_method = 'fuzzy_medium'`
- **And** the resolved-links Parquet contains one row for this event

**Scenario D2: MEDIUM confidence — more than one candidate canonical match**
- **Given** a parsed Matchbook event where multiple canonical matches satisfy the
  MEDIUM threshold
- **When** the conform engine evaluates the event
- **Then** no auto-link is made
- **And** the event is written to the exceptions Parquet with
  `unresolved_reason = 'multiple_candidates'`

---

### Capability E: Matchbook conform — NO MATCH → exceptions queue

**Scenario E1: No canonical match satisfies any confidence tier**
- **Given** a Matchbook football event for which no canonical match meets the MEDIUM
  threshold (no team-name pair scores ≥ 0.70 and kickoff ≤ 90 min)
- **When** the conform engine evaluates the event
- **Then** the event is written to
  `data/exceptions/matchbook_unresolved.parquet` with:
  - `matchbook_event_id`, `event_name`, `home_team_parsed`, `away_team_parsed`,
    `start_utc`, `unresolved_reason = 'no_match'`
  - A `candidates` column containing a JSON array of up to 5 nearest canonical
    match candidates (sorted by combined fuzzy score), each with `match_id`,
    `home_team`, `away_team`, `kickoff_time`, `score`
- **And** no row for this event appears in the resolved-links Parquet

**Scenario E2: Exceptions Parquet is appended across runs, not truncated**
- **Given** a prior exceptions Parquet exists with N unresolved events
- **When** the conform asset runs and finds M new unresolved events
- **Then** the resulting exceptions Parquet contains all previously unresolved events
  that have NOT been resolved by a human override, plus the M new ones
- **And** events that now have a human override are removed from the exceptions Parquet

---

### Capability F: Matchbook conform — new canonical entity creation

**Scenario F1: Human confirms "new canonical record" for an unresolved event**
- **Given** a human reviewer marks a Matchbook event in the exceptions UI with
  `action = 'new_canonical'`
- **And** the decision is written to `matchbook_overrides.parquet`
- **When** the conform asset runs on the next pipeline run
- **Then** a new canonical `match_id` is minted using the `canonical_match_id` logic
  (md5 over league/season/date/home/away canonical surrogates) — using a best-effort
  league/season surrogate derived from the Matchbook event's sport category and kickoff
  year
- **And** the link row is written to the resolved-links Parquet with
  `confidence = 1.0`, `review_status = 'human_confirmed'`, `match_method = 'human_override'`

> **Note (OQ1 resolved):** When the Python conform engine processes a human-confirmed
> `action = 'new_canonical'` event, it writes that row to
> `data/silver/matchbook_canonical_additions.parquet` (in addition to the standard
> resolved-links Parquet). `match.sql` includes a UNION ALL of this Parquet source
> (as a second CTE, only when the file exists) so that Matchbook-minted `match_id`
> values appear in the `match` table. The dbt `relationships` test on
> `matchbook_event_link.match_id → match.match_id` then passes for all rows, including
> `new_canonical` ones. No separate model is needed.

---

### Capability G: dbt `matchbook_event_link` model

**Scenario G1: dbt model reads resolved-links Parquet and produces typed link table**
- **Given** the resolved-links Parquet exists at
  `data/silver/matchbook_resolved_links.parquet`
- **When** dbt runs the `matchbook_event_link` model (replacing the empty scaffold)
- **Then** the DuckLake `silver.matchbook_event_link` table contains one row per resolved
  Matchbook event with columns:
  - `link_id` (PK, deterministic surrogate md5(matchbook_event_id))
  - `match_id` (FK → `match.match_id`)
  - `matchbook_event_id` (the provider reference)
  - `match_method` (`'fuzzy_high'` | `'fuzzy_medium'` | `'human_override'`)
  - `confidence` (DOUBLE, 0.0–1.0)
  - `review_status` (`'auto_confirmed'` | `'needs_review'` | `'human_confirmed'`)
- **And** a `not_null` and `unique` test on `link_id` passes
- **And** a `relationships` test on `match_id → ref('match')` passes for all rows where
  the canonical match exists

**Scenario G2: Re-run of dbt over the same resolved-links Parquet is idempotent**
- **Given** the resolved-links Parquet content is unchanged between two runs
- **When** `matchbook_event_link` dbt model runs twice
- **Then** the resulting table contains the same rows (full-rebuild table materialization)

---

### Capability H: T-60 enrichment — favourite team identification

**Scenario H1: T-60 tick exists for a known Matchbook event**
- **Given** a `matchbook_event_link` row links `matchbook_event_id = X` to `match_id = M`
- **And** the odds Parquet (`matchbook_odds`) contains ticks for event X in the
  "Match Odds" market (`market_type = 'match_odds'`)
- **And** at least one tick has `ingested_at` within the window
  `[kickoff_ms − 4500000 ms, kickoff_ms − 2700000 ms]` (i.e. T-60 min ± 15 min, in
  epoch milliseconds)
- **When** the `matchbook_t60_enrichment` asset runs
- **Then** for each runner in that window, the runner with the lowest `best_back_price`
  across all ticks in the window is identified as the favourite
- **And** a row is written to `data/silver/matchbook_t60_enrichment.parquet` with:
  - `match_id = M`, `matchbook_event_id = X`, `favourite_runner_id` (the winning runner_id),
    `best_back_price_at_t60`, `tick_count_in_window`, `window_start_ms`, `window_end_ms`
- **And** `favourite_team_id` is resolved by: (1) reading `raw_event["runners"]` from
  the Matchbook events bronze Parquet for the linked `event_id`; (2) fuzzy-matching
  each runner `name` against `home_team_name`/`away_team_name` from
  `canonical_match_export` Parquet (`settings.matchbook_conform_canonical_dir /
  "match.parquet"`) using `rapidfuzz.fuzz.token_sort_ratio`; (3) assigning home/away
  runner IDs to the best match ≥ 0.70; (4) at T-60 window, picking the runner with
  the lower `best_back_price` as the favourite. If no runner reaches 0.70,
  `favourite_team_id` remains NULL for that match.

**Scenario H2: No T-60 tick exists for a linked event**
- **Given** a `matchbook_event_link` row for event X
- **And** the odds Parquet contains no ticks for event X in the T-60 window
- **When** the `matchbook_t60_enrichment` asset runs
- **Then** no row for match M is written to the T-60 enrichment Parquet
- **And** `match.favourite_team_id` remains `NULL` for that match

**Scenario H3: dbt model reads T-60 Parquet and updates `match.favourite_team_id`**
- **Given** `data/silver/matchbook_t60_enrichment.parquet` exists with a row for `match_id = M`
- **When** dbt runs the updated `match.sql` (or a new companion model)
- **Then** `match.favourite_team_id` for match M is set to the resolved `favourite_team_id`
  from the T-60 enrichment Parquet
- **And** the update is idempotent: re-running over the same T-60 Parquet yields the same
  value

---

### Capability I: ESPN score enrichment (documentation scenario)

**Scenario I1: ESPN job picks up new final scores on each run**
- **Given** a canonical `match` row with `ft_score = NULL` (pre-match fixture)
- **And** the ESPN scoreboard API now reports `status_completed = true` with
  `home_score = 2`, `away_score = 1` for the same `espn_event_id`
- **When** the `espn_ingestion` Dagster job runs (bronze ingest → dbt build)
- **Then** `match.ft_score` for that row is updated to `'2-1'`
- **And** the match_id is unchanged (deterministic surrogate over canonical fields)
- **And** no operator action is required beyond the scheduled job running

> This scenario documents existing behaviour (already implemented in `match.sql`
> via `status_completed` and the `qualify row_number()` dedup clause). The ESPN job
> (`espn_ingestion`) already triggers a `dbt build` via `dbt_models` which rebuilds the
> `match` table. No new implementation is needed for this capability.

---

### Capability J: Streamlit exceptions UI

**Scenario J1: Human views unresolved Matchbook events**
- **Given** `data/exceptions/matchbook_unresolved.parquet` exists and contains one or
  more rows
- **When** the human opens the Streamlit app (served on port 8501 by default)
- **Then** each unresolved event is displayed with: event name, parsed home/away team,
  start UTC, unresolved reason, and a sorted list of candidate canonical matches (by
  match score descending)

**Scenario J2: Human confirms a specific candidate match**
- **Given** the Streamlit UI shows an unresolved event with candidate matches
- **When** the human selects one candidate and clicks "Confirm"
- **Then** a row is appended to `data/manual_links/matchbook_overrides.parquet` with:
  - `matchbook_event_id`, `action = 'link'`, `match_id` (the confirmed canonical match),
    `decided_at` (UTC timestamp), `decided_by = 'human_ui'`
- **And** the event is removed from the exceptions view (shown as "resolved")

**Scenario J3: Human marks event as a new canonical record**
- **Given** the Streamlit UI shows an unresolved event
- **When** the human clicks "New Canonical Record" (no existing match applies)
- **Then** a row is appended to `matchbook_overrides.parquet` with:
  - `matchbook_event_id`, `action = 'new_canonical'`, `match_id = NULL`,
    `decided_at`, `decided_by = 'human_ui'`

**Scenario J4: Human flags two canonical records as duplicates (merge)**
- **Given** the Streamlit UI shows an unresolved event with multiple close candidates
- **When** the human clicks "Merge Duplicates" and selects two candidate `match_id` values
- **Then** a row is appended to `matchbook_overrides.parquet` with:
  - `matchbook_event_id`, `action = 'merge'`, `match_id` (the surviving canonical record),
    `merge_source_match_id` (the to-be-retired record), `decided_at`, `decided_by = 'human_ui'`
- **And** on the next pipeline run, `matchbook_conform` uses the surviving `match_id` for
  this event and records `confidence = 1.0`, `review_status = 'human_confirmed'`

**Scenario J5: Exceptions Parquet is absent (no unresolved events)**
- **Given** `data/exceptions/matchbook_unresolved.parquet` does not exist or is empty
- **When** the human opens the Streamlit app
- **Then** the app displays "No unresolved events" and does not error

---

## 6. Edge cases & error handling

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | `matchbook_events_bronze` Parquet directory is empty or absent | `matchbook_conform` asset produces zero link rows and an empty exceptions Parquet; logs a warning; does not raise |
| E2 | `matchbook_odds` Parquet contains no ticks for a linked event | T-60 enrichment skips that event; `favourite_team_id` remains NULL; no error |
| E3 | `kickoff_ms` is NULL for a tick (field is nullable per Spec 005 schema) | Ticks with NULL `kickoff_ms` are excluded from the T-60 window calculation for that event |
| E4 | `event_name` contains more than one ` v ` (e.g. "Real Madrid v FC v Barcelona") | Conform engine splits on the FIRST ` v ` occurrence only; second part is the full away-team string; or event is quarantined if result is implausible (empty home/away after strip) |
| E5 | Re-run of `matchbook_conform` with identical bronze input | Resolved-links Parquet is fully overwritten (idempotent); exceptions Parquet is rebuilt from scratch then merged with human-override state |
| E6 | `matchbook_overrides.parquet` references a `match_id` that no longer exists in canonical `match` | The link row is written with that `match_id`; the dbt `relationships` test will surface the violation; the asset itself does not validate FK existence (dbt is the FK gate) |
| E7 | Matchbook event is for rugby union (sport-id 2), not football | The conform asset filters to football only (sport-id 15) before processing; rugby events are silently skipped (not written to exceptions) |
| E8 | Fuzzy matching produces a tie (two candidates with identical combined score) | Both are written to the candidates JSON in the exceptions row; neither is auto-linked; the human must decide |
| E9 | `data/manual_links/` directory does not exist | The Streamlit app and conform asset create it before writing; no error |
| E10 | Concurrent writes to `matchbook_overrides.parquet` from multiple Streamlit sessions | The overrides Parquet is written atomically (temp-file + rename, same pattern as bronze); last writer wins per event decision; concurrent multi-user editing is not a supported scenario |
| E11 | `matchbook_t60_enrichment.parquet` does not exist when dbt runs `match.sql` | The dbt model treats the join to T-60 enrichment as a LEFT JOIN; rows without T-60 data get `favourite_team_id = NULL` (no error, no fabrication) |
| E12 | A Matchbook event already in `matchbook_event_link` (from a prior run) is seen again | The conform asset produces the same `link_id = md5(matchbook_event_id)` (idempotent); dbt's full-rebuild materialisation overwrites with the same row; no duplicate |
| E13 | The resolved-links Parquet contains a row where `match_method = 'human_override'` and `action = 'merge'` | The conform asset writes the row with the surviving `match_id`; the `merge_source_match_id` is not written to `matchbook_event_link` — the merge is only a decision-routing hint |
| E14 | Matchbook event `start_utc` is not parseable as a UTC datetime | The event is quarantined to exceptions with `unresolved_reason = 'invalid_start_utc'`; no link row is produced |
| E15 | Multiple Matchbook bronze Parquet files for the same sport on the same date (multiple batch runs) | The conform asset reads all files via glob and deduplicates by `event_id` before matching; the latest `ingested_at` value wins on dedup |

---

## 7. Acceptance criteria

- [ ] AC1 — Given Matchbook bronze Parquet exists for football (sport-id 15), the `matchbook_conform` asset parses every event name on ` v ` and attempts fuzzy matching against the canonical `match` table.
- [ ] AC2 — A Matchbook event whose home AND away team names score ≥ 0.85 (rapidfuzz `token_sort_ratio`) against a canonical match's resolved team names, AND whose `start_utc` differs from `kickoff_time` by ≤ 90 min, receives a resolved link with `confidence = 0.95` (exact constant, not approximate), `review_status = 'auto_confirmed'`, `match_method = 'fuzzy_high'`. The value 0.95 is a constant assigned to all HIGH-strategy rows; it is not computed from the individual fuzzy scores.
- [ ] AC3 — A Matchbook event that satisfies the MEDIUM (≥ 0.70) threshold and uniquely resolves to exactly one canonical match receives `confidence = 0.75` (exact constant, not approximate), `review_status = 'needs_review'`, `match_method = 'fuzzy_medium'`. The value 0.75 is a constant assigned to all MEDIUM-strategy rows.
- [ ] AC4 — A Matchbook event that satisfies no fuzzy threshold (or resolves to multiple candidates at MEDIUM) is written to `data/exceptions/matchbook_unresolved.parquet` with a populated `candidates` JSON column and is absent from the resolved-links Parquet.
- [ ] AC5 — An event in `matchbook_overrides.parquet` (any action) is processed before fuzzy matching and produces a link row with `confidence = 1.0`, `review_status = 'human_confirmed'`, `match_method = 'human_override'`.
- [ ] AC6 — Running `matchbook_conform` twice over identical bronze input produces the same resolved-links Parquet and the same exceptions Parquet (idempotent).
- [ ] AC7 — The `matchbook_event_link` dbt model (replacing the empty scaffold) reads `data/silver/matchbook_resolved_links.parquet` and writes a DuckLake table with the specified columns; `not_null` and `unique` tests on `link_id` pass; `relationships` test on `match_id → ref('match')` passes for ALL rows including `new_canonical` rows, because `match.sql` includes a UNION of `data/silver/matchbook_canonical_additions.parquet` (written by the conform asset for `action = 'new_canonical'` events).
- [ ] AC8 — The `matchbook_t60_enrichment` asset identifies, for each linked event with a "Match Odds" tick in the window `[kickoff_ms − 4500000, kickoff_ms − 2700000]`, the runner with the lowest `best_back_price` and writes a row to `data/silver/matchbook_t60_enrichment.parquet`.
- [ ] AC9 — After `matchbook_t60_enrichment` runs and dbt rebuilds `match.sql`, `match.favourite_team_id` is non-NULL for at least one match that had T-60 data; matches without T-60 data retain `favourite_team_id = NULL`. The `matchbook_t60_enrichment` asset resolves runner-to-team by: (1) reading `raw_event["runners"]` from the Matchbook events bronze Parquet for the linked `event_id`; (2) fuzzy-matching each runner `name` against `home_team_name`/`away_team_name` from `canonical_match_export` Parquet using `rapidfuzz.fuzz.token_sort_ratio`; (3) assigning home/away runner IDs to the best match ≥ 0.70; if no runner reaches 0.70, `favourite_team_id` remains NULL for that match.
- [ ] AC10 — The Streamlit app starts without error when `matchbook_unresolved.parquet` is absent, and displays all unresolved events when the file is present.
- [ ] AC11 — A "Confirm" action in the Streamlit UI appends a row with `action = 'link'` to `matchbook_overrides.parquet`; a "New Canonical Record" action appends `action = 'new_canonical'`; a "Merge Duplicates" action appends `action = 'merge'` with `merge_source_match_id` populated.
- [ ] AC12 — Rugby-union events (sport-id 2) in the Matchbook bronze Parquet are not written to the exceptions Parquet and do not appear in resolved-links.
- [ ] AC13 — The `matchbook_conform_job` is registered in `definitions.py`; it is subtracted from `AssetSelection.all()` so `medallion_hello_world` does not run it.
- [ ] AC14 — The `matchbook_conform` asset depends on `AssetKey(["matchbook_events_bronze"])` and the dbt conform build step depends on the resolved-links Parquet (expressed via Dagster asset deps, not Python imports).
- [ ] AC15 — The Streamlit service is defined in `docker-compose.yml` (or an overlay), exposes port 8501, mounts `./data`, and restarts unless-stopped.
- [ ] AC16 — ESPN score enrichment: after `espn_ingestion` runs for a fixture that was previously pre-match, `match.ft_score` is non-NULL and `match_id` is unchanged.
- [ ] AC17 — No Dagster asset module uses `from __future__ import annotations`. Pure-Python engine modules (e.g. `matchbook/conform.py`, `matchbook/t60.py`) that contain no Dagster decorators may use `from __future__ import annotations`; the ban applies only to asset modules containing `@asset` decorators.
- [ ] AC18 — All new `Settings` fields required by new assets are added to `config.py` before the asset module is written.
- [ ] AC19 — Pure-Python fuzzy matching, event-name parsing, T-60 window logic, and override loading are unit-testable without a live DuckLake catalog or Matchbook API.
- [ ] AC20 — ERD.md is updated in the same commit that implements `matchbook_event_link` schema changes (adding `match_method`, `confidence`, `review_status` columns) to reflect the new schema.
- [ ] AC21 — ERD.md is updated in the same commit to state `favourite_team_id` is captured from the T-60 minute window (kickoff − 75 min to kickoff − 45 min) rather than the prior "T-45m" label.

---

## 8. Things to be aware of / constraints

### Repo-level constraints (from CLAUDE.md)

- **No `from __future__ import annotations` in Dagster asset modules** — Dagster
  introspects annotations at runtime; stringized annotations break it.
- **Config via `pydantic-settings` only** — all new paths and settings (`matchbook_conform_dir`,
  `matchbook_exceptions_dir`, `matchbook_overrides_dir`, `matchbook_t60_dir`,
  `matchbook_conform_canonical_dir`) must be declared as typed properties in `config.py`
  before the asset modules are written. `matchbook_conform_canonical_dir` is a `Path`
  pointing to `data/silver/canonical/` — the directory where dbt writes the
  `canonical_team_export` and `canonical_match_export` Parquet files.
- **`pathlib.Path` for all filesystem paths** — never bare string paths or `os.path`.
- **`AssetSelection.all()` must subtract new assets** — `matchbook_conform_job` assets
  must be subtracted in `definitions.py` from `medallion_hello_world`, same as
  `football_assets` and `espn_assets`.
- **dbt AssetKey is prefixed by schema folder only** — `matchbook_event_link` will have
  `AssetKey(["silver", "matchbook_event_link"])`, NOT `["silver", "canonical", "matchbook_event_link"]`.
  The dbt node selector for the model is `silver.canonical.matchbook_event_link`.
- **dbt single-writer constraint for DuckLake** — Python conform assets write Parquet
  files only; dbt writes to DuckLake. No Python asset opens DuckLake read-write.
- **Python conform assets read canonical entity Parquet exports produced by dbt** —
  two new dbt external Parquet export models (`canonical_team_export`,
  `canonical_match_export`, following the same pattern as `users_by_city_export.sql`)
  write `data/silver/canonical/team.parquet` and `data/silver/canonical/match.parquet`.
  The Python conform asset reads these via
  `pd.read_parquet(settings.matchbook_conform_canonical_dir / "team.parquet")` (and
  similarly for `match.parquet`). Python never connects to DuckLake or
  `warehouse.duckdb` — not even read-only.
- **Canonical `match_id` is always from the `canonical_match_id` macro logic** — the
  Python conform asset, when minting a new canonical id for `action = 'new_canonical'`,
  must compute `md5(concat_ws('|', league_id, season_id, date, home_team_id, away_team_id))`
  using the same field order as the SQL macro. Never use a provider event_id as an identity.
- **`BronzeAwareTranslator` in `assets/dbt.py`** — the resolved-links Parquet is
  registered as a new dbt source named `"matchbook_resolved_links"`. A mapping entry
  must be added to `_SOURCE_ASSET_KEYS`:
  `"matchbook_resolved_links": AssetKey(["matchbook_conform"])`.
  This wires the Dagster asset graph edge from the Python conform asset to the dbt
  `matchbook_event_link` model without a manual `deps=` declaration.
- **`dbt parse` exits 0 without a live catalog** — CI can parse manifests; the conform
  layer SQL that reads an external Parquet source will only execute at runtime.
- **Compose overlay pattern** — the Streamlit service should be added to the base
  `docker-compose.yml` (it reads only `./data`, has no telemetry dependency), mirroring
  the `jupyter` service pattern. If the Streamlit service needs SigNoz tracing in dev,
  it goes in the signoz overlay instead.

### Domain constraints

- **`event_name` format** — Matchbook football events use `"Home v Away"` format;
  split on the FIRST occurrence of ` v ` (space-v-space). Other sports may use
  different delimiters (rugby union in-scope bronze is not conform-processed by this spec).
- **T-60 window** — `kickoff_ms` in the odds lake is epoch milliseconds for the fixture
  kickoff. The T-60 window is `[kickoff_ms − 4500000, kickoff_ms − 2700000]`
  (75 min to 45 min before kickoff inclusive). `ingested_at` in the odds lake is also
  epoch milliseconds (per `MatchbookOddsRecord`).
- **"Match Odds" market identification** — filter on `market_type` column; the expected
  value is `'match_odds'` (lowercase, underscore-separated). Treat missing/empty
  `market_type` as non-Match-Odds and exclude from T-60 calculation.
- **Favourite = lowest `best_back_price`** — in a betting exchange, a lower back price
  means shorter odds = more likely to win = the favourite. Among all ticks in the T-60
  window for Match Odds, find the runner with the minimum `best_back_price` at any tick
  in the window. Where `best_back_price` is NULL for a tick, skip that tick for the
  minimum calculation.
- **Runner-to-team resolution** — the odds lake stores `runner_id` (Matchbook exchange
  runner id) and `event_participant_id`. The Matchbook events bronze `raw_event` JSON
  contains a `"runners"` list of objects with `{"id": ..., "name": "...", "prices": [...]}`.
  The `matchbook_t60_enrichment` asset extracts runner names from `raw_event["runners"]`,
  fuzzy-matches each name against `home_team_name`/`away_team_name` from
  `canonical_match_export` Parquet using `rapidfuzz.fuzz.token_sort_ratio`, and assigns
  home/away runner IDs based on best match ≥ 0.70. If no runner reaches 0.70,
  `favourite_team_id` is NULL for that match. No external catalogue lookup is required.
- **Exceptions Parquet rebuild strategy** — the exceptions Parquet is rebuilt on each
  conform run from the current unresolved set (i.e. events in bronze that are NOT in the
  resolved-links output and NOT resolved by an override). This avoids stale "ghost" rows.
- **`matchbook_event_link` schema extension** — the current empty scaffold has only
  `link_id`, `match_id`, `matchbook_event_id`. This spec adds `match_method`,
  `confidence`, `review_status` to mirror `espn_match_link`'s provenance columns.
  The `_schema.yml` test for `matchbook_event_link` must be updated accordingly.
- **`match.favourite_team_id` update strategy** — the current `match.sql` emits
  `cast(null as varchar) as favourite_team_id`. The simplest correct pattern is to LEFT
  JOIN the T-60 enrichment Parquet in `match.sql` on `match_id` and coalesce
  `favourite_team_id` from the Parquet. Alternatively, a new `match_enriched` model
  layered on `match` could carry it. The choice is deferred to the implementer; both
  are acceptable. The constraint is that `match.favourite_team_id` must be populated
  without opening DuckLake read-write from Python.
- **ERD.md must be updated in the same commit** — CLAUDE.md requires ERD.md to be
  updated whenever canonical table semantics change. ERD.md currently labels
  `favourite_team_id` as "captured at T-45m". This is incorrect: the T-60 window
  (kickoff − 75 min to kickoff − 45 min, midpoint = T-60) is the correct label.
  Update ERD.md to state `favourite_team_id` is captured from the T-60 minute window
  (kickoff − 75 min to kickoff − 45 min) in the same commit that implements this spec.

### Non-functional constraints

- **rapidfuzz** must be added to `pyproject.toml` dependencies before any conform
  asset is written.
- **streamlit** must be added to `pyproject.toml` dependencies before the UI module
  is written.
- The Streamlit service in Docker mounts `./data` read-write (needs to write
  `manual_links/matchbook_overrides.parquet`) and `./src` if live-reload is wanted
  in dev; in prod the baked image is used.
- The conform Python engine (matchbook-side matching, T-60 filtering, override loading)
  must be in a Dagster-free module (e.g. `src/data_platform/matchbook/conform.py`,
  `src/data_platform/matchbook/t60.py`) following the same pattern as
  `matchbook/ingest.py` and `espn/ingest.py`. The Dagster wrapper lives in `assets/`.
- Unit tests for the fuzzy matching engine, name parser, T-60 window logic, and override
  loader must be placed in `tests/matchbook/` following the existing test layout.

---

## 9. Assumptions

1. **Rapidfuzz `token_sort_ratio` is the comparison function** — the feature description
   specifies rapidfuzz but not the specific ratio function. `token_sort_ratio` is assumed
   because team names may appear in different token orders (e.g. "Man City" vs "City Man").
   If `ratio` or `partial_ratio` is more appropriate for a specific use case, the
   implementer may substitute; the thresholds (0.85 HIGH, 0.70 MEDIUM) are defined
   against `token_sort_ratio` and must be re-calibrated if the function changes.

2. **T-60 window expressed in epoch milliseconds** — `kickoff_ms` and `ingested_at`
   in the odds lake are both epoch milliseconds (per `MatchbookOddsRecord` in
   `schemas.py`). The window `[kickoff_ms − 4500000, kickoff_ms − 2700000]` (75–45 min
   before kickoff) is therefore computed in millisecond arithmetic.

3. **The `matchbook_t60_enrichment` asset reads from `data/silver/matchbook_resolved_links.parquet`
   (produced by `matchbook_conform`) to know which `event_id` links to which `match_id`.**
   It reads canonical entity data (home/away team names) from
   `data/silver/canonical/match.parquet` (produced by the `canonical_match_export` dbt
   model). The Dagster dependency ordering therefore is:
   `matchbook_events_bronze` → `matchbook_conform` (Python, writes resolved-links Parquet) →
   dbt build (`matchbook_event_link` table + `canonical_match_export`) →
   `matchbook_t60_enrichment` (Python, reads resolved-links Parquet + canonical Parquet +
   odds Parquet) → dbt build (`match.sql` with T-60 join).

4. **Only football events (sport-id 15) are conformed** — rugby-union events are in the
   Matchbook bronze Parquet but are silently skipped by the conform asset. This may be
   revisited when rugby-union canonical entities are defined.

5. **`match_method` allowed values in `matchbook_event_link._schema.yml`** will be
   extended to `['fuzzy_high', 'fuzzy_medium', 'human_override']` and `review_status` to
   `['auto_confirmed', 'needs_review', 'human_confirmed']`, mirroring the `espn_match_link`
   pattern but with different values.

6. **The Streamlit app writes to `data/manual_links/matchbook_overrides.parquet`
   atomically (temp-file + rename)** — consistent with all other Parquet writes in this
   codebase. If the overrides file exists, the app reads it, applies the new decision,
   and rewrites the full file.

7. **The `matchbook_conform_job` schedule offset** — suggested at `0 1,7,13,19 * * *`
   (1 hour after the top-of-the-6h cycle) to allow the `matchbook_events_ingestion` job
   (cron `0 */6 * * *`) to complete before conform runs. This is a soft assumption;
   the exact cron is deferred to the implementer.

8. **Python conform asset reads canonical entities from dbt-exported Parquet files** —
   the Python conform and T-60 enrichment assets never connect to DuckLake or
   `warehouse.duckdb`. Canonical `match` and `team` data is accessed via
   `pd.read_parquet(settings.matchbook_conform_canonical_dir / "match.parquet")` and
   `pd.read_parquet(settings.matchbook_conform_canonical_dir / "team.parquet")`,
   produced by the `canonical_match_export` and `canonical_team_export` dbt models
   (new models following the `users_by_city_export.sql` pattern).

9. **`favourite_team_id` in `match.sql` is populated via a LEFT JOIN** on the T-60
   enrichment Parquet registered as a new dbt external source (or via `read_parquet()`
   inline in `match.sql`). The exact dbt pattern is deferred to the implementer.

10. **The Streamlit service port** — 8501 (Streamlit default). If this conflicts with
    another service, the implementer may choose another port; expose it via
    `${STREAMLIT_PORT:-8501}` in docker-compose for configurability.

---

## 10. Open questions

| # | Question | Blocker? | Resolution |
|---|----------|----------|------------|
| ~~OQ1~~ | ~~How should new-canonical Matchbook entities be surfaced in `match.sql`?~~ | ~~BLOCKER~~ | **RESOLVED** — The Python conform asset writes `data/silver/matchbook_canonical_additions.parquet` for `action = 'new_canonical'` events. `match.sql` UNIONs this source (UNION ALL, only when the Parquet exists). The dbt `relationships` test on `matchbook_event_link.match_id → match.match_id` passes for all rows including `new_canonical`. See Scenario F1 note and AC7. |
| ~~OQ2~~ | ~~Runner-to-team resolution: can `runner_id` be resolved via `raw_event` JSON alone?~~ | ~~BLOCKER~~ | **RESOLVED** — The `matchbook_t60_enrichment` asset reads `raw_event["runners"]` from the events bronze Parquet, fuzzy-matches each runner `name` against `home_team_name`/`away_team_name` from `canonical_match_export` Parquet using `rapidfuzz.fuzz.token_sort_ratio` (threshold ≥ 0.70), and assigns home/away runner IDs. If no runner reaches 0.70, `favourite_team_id` is NULL. See Scenario H1 and AC9. |
| OQ3 | Should the T-60 enrichment asset depend on the `matchbook_event_link` DuckLake table (via a Dagster asset key for the dbt model) or on the resolved-links Parquet file directly? | Non-blocker | Prefer depending on the dbt-produced `AssetKey(["silver", "matchbook_event_link"])` to enforce the correct ordering in the asset graph. Reading the Parquet directly would bypass the dbt FK validation step. |
| OQ4 | Should the `matchbook_conform_job` include a dbt build step for all silver canonical models (full `espn_assets`-style) or only `matchbook_event_link`? | Non-blocker | Scope the dbt build to `matchbook_event_link` (and `match` for the T-60 enrichment final step) to avoid redundant work. Use `dbt build --select silver.canonical.matchbook_event_link silver.canonical.match` in the job's dbt invocation. |
| OQ5 | Should the Streamlit service be in the base `docker-compose.yml` or the signoz dev overlay? | Non-blocker | Base `docker-compose.yml`, mirroring `jupyter`. The Streamlit app has no telemetry dependency (it only reads/writes Parquet). |

---

## 11. Traceability

> **Note:** No ADO user stories exist for this feature; they were not pre-created before
> the feature was requested. Traceability is therefore to feature description sections
> (`FD-006-1` through `FD-006-5`) derived from the user's direct feature request
> (recorded as input `FD-006`). The `user_stories: []` field in the frontmatter reflects
> this. The table below maps each major requirement to its scenarios and acceptance
> criteria.

The table maps each major requirement from the feature description to its scenarios and
acceptance criteria.

| Feature description requirement | Scenarios | Spec acceptance criteria |
|---------------------------------|-----------|--------------------------|
| FD-006-1: Matchbook conform layer — link each event to canonical match | A1, A2, B1, B2, C1, C2, D1, D2, E1, E2, F1 | AC1, AC2, AC3, AC4, AC5, AC6, AC12, AC13, AC14 |
| FD-006-1a: HIGH CONFIDENCE auto-link (>0.85 fuzzy + ±90 min) | C1, C2 | AC2 |
| FD-006-1b: MEDIUM CONFIDENCE auto-link with flag (>0.7, unique resolve) | D1, D2 | AC3 |
| FD-006-1c: NO MATCH → exceptions queue | E1, E2 | AC4 |
| FD-006-1d: New canonical entity creation on human confirm | F1 | AC5 |
| FD-006-1e: dbt `matchbook_event_link` from resolved-links Parquet | G1, G2 | AC7 |
| FD-006-2: T-60 enrichment — favourite team from odds lake | H1, H2, H3 | AC8, AC9 |
| FD-006-3: ESPN score enrichment — already working, re-trigger dbt | I1 | AC16 |
| FD-006-4: Exceptions queue Parquet (`matchbook_unresolved.parquet`) | E1, E2, J1 | AC4, AC10 |
| FD-006-5: Streamlit exceptions UI — view, confirm, reject, merge | J1, J2, J3, J4, J5 | AC10, AC11, AC15 |
| FD-006-5a: Human decisions → `matchbook_overrides.parquet` | J2, J3, J4 | AC11 |
| FD-006-5b: Overrides read on next pipeline run as definitive | B1, B2 | AC5 |
| Repo contract: no `from __future__ import annotations` in asset modules | (all asset scenarios) | AC17 |
| Repo contract: config via `pydantic-settings` | (all asset scenarios) | AC18 |
| Repo contract: exclude new assets from `medallion_hello_world` | (Capability A, G, H) | AC13 |
| Repo contract: `canonical_match_id` macro logic for identity | F1, G1 | AC7 |
| Repo contract: Python never writes to DuckLake directly | (all conform + T-60 scenarios) | AC7, AC9 |
| Repo contract: dbt AssetKey prefixed by schema folder only | (Capability G, H) | AC14 |
| Non-functional: rapidfuzz in pyproject.toml | (Capability C, D) | AC19 |
| Non-functional: streamlit in pyproject.toml | (Capability J) | AC15 |
| Non-functional: pure-Python engines are unit-testable | (Capabilities A–E, H) | AC19 |
