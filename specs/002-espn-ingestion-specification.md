---
id: 002
title: ESPN soccer ingestion (bronze fixtures + canonical match/league/season/team population)
slug: espn-ingestion
status: draft
created: 2026-06-28
user_stories: [espn-data-flow]
investigation: espn-api-discovery
related_specs: [001]
---

# ESPN soccer ingestion (bronze fixtures + canonical match/league/season/team population)

## 1. Summary

A data platform engineer can ingest association-football (soccer) fixtures from
ESPN's public JSON API into the medallion platform, on a recurring **6-hourly**
schedule, such that the canonical `league`, `season`, `team` and `match` tables are
populated and each ESPN event is linked to its canonical match via `espn_match_link`.
The flow is **idempotent / upsert, not append-only**: a fixture seen pre-match is
re-ingested post-match to fill in results (kickoff, half-time and full-time scores),
landing on the *same* canonical `match_id` every time. Bronze stores the **full ESPN
event payload verbatim** (faithful-to-source) so future fields can be promoted without
re-fetching. Canonical match identity is computed from a **provider-independent natural
fixture key** (competition + season + kickoff date + resolved home/away teams) so that
a future provider (e.g. Matchbook) ingesting the same real-world fixture resolves to the
same `match_id` and its link table points at that same canonical match.

## 2. Background & context

This spec realises the **ESPN data flow** feature. There is no synced Azure DevOps work
item for it yet; the authoritative requirement is the feature description carried in the
frontmatter as `user_stories: [espn-data-flow]` (clauses a–d below), traced in §11.

Feature requirement clauses (source of record):
- **(a)** The flow **re-runs**, and once a match has been played it must populate **all
  the data it has at that time** — the same fixture is ingested pre-match and re-ingested
  post-match to fill in results. The flow is idempotent / upsert, not append-only.
- **(b)** The **full post-match data must be stored in bronze verbatim**, in case extra
  fields are wanted in future (faithful-to-source bronze, like the football ingestor's
  wide ride-along columns).
- **(c)** It must **de-duplicate against existing matches**: when a future Matchbook
  ingestor adds pre-match odds, the ESPN and Matchbook link tables must resolve to the
  **same canonical `match_id`**. ESPN populates/links the canonical match; a future
  provider linking to the same real-world fixture must land on the same `match_id`.
- **(d)** It must run on a **schedule every 6 hours**.

This spec draws directly on **investigation `espn-api-discovery`**
(`investigations/espn-api-discovery/findings.md` + `evidence/api_endpoints.md`), which
proved the ingestion feasible against the live API and recommended moving to
specification. Findings carried in here:

- **League discovery is self-contained** via `sports.core.api.espn.com/v2/sports/soccer/leagues`
  (239 soccer leagues, string slugs e.g. `eng.1`, `uefa.champions`), so no pre-seeded
  competition-id table is needed; the dead `provider_entity_cache` is replaced by a small
  configured **league allowlist** (curated subset, not all 239 — depth-vs-breadth is config).
- **Seasons expose exact date windows** via `/leagues/{id}/seasons` → per-season
  `year`, `startDate`, `endDate` (EPL: 26 seasons back to 2001-02).
- **Scoreboard** `site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates={YYYYMMDD}-{YYYYMMDD}&limit=1000`
  returns every event in a window (EPL full season = 380 events), each event carrying
  `id`, `date` (kickoff), `status.type` (`name`, `state`, `completed`), `season`
  (`year`, `displayName`), and per-competitor `homeAway` / `team` (`id`, `displayName`,
  `name`, `shortDisplayName`) / `score`. Pre-match events show `STATUS_SCHEDULED`;
  played events show `STATUS_FINAL` / `completed: true` with scores.
- **No auth / no API key**; a browser `User-Agent` suffices; not aggressively
  rate-limited (a ~0.1 s courtesy pace per call is sufficient).

This spec mirrors the patterns established by **spec 001 / the football-data.co.uk
ingestor** (`src/data_platform/football/`, `src/data_platform/assets/football_*.py`):
typed source registry/allowlist, single throttled cache-aware HTTP resource, faithful
bronze with per-source-unit Parquet, Pydantic-per-record + open Pandera frame, per-unit
failure isolation with atomic temp-file+rename writes. It introduces the **first conform
layer** that populates the canonical `silver/canonical/` tables (which are currently
empty typed scaffolds).

The canonical model is documented in `ERD.md`: `league (1)──(N) season (1)──(N) match`;
`match.season_id` FK → `season.season_id`; the league is reached via `season.league_id`.
`team.similar_names` exists for alias-based entity resolution; `league` and `season` have
no aliases column. `espn_match_link(link_id, match_id, espn_event_id)` is the provider
link for ESPN.

### Decisions taken (this revision)

The scope is **"build ESPN now, with a seam for future cross-provider linkage."** The
following are **decided**, not open assumptions:

- **D1 — match identity is deterministic, computed by a provider-agnostic resolver.**
  Match identity = (canonical league, canonical season, **kickoff calendar date (UTC)**,
  canonical home team, canonical away team). ESPN is the sole canonical writer now, so its
  own events de-dup deterministically across re-runs. The identity resolution is a
  **provider-agnostic, separately-testable unit** — a shared dbt macro/model (or a pure
  Python function if the resolver is Python-side) taking `(league, season, date, home,
  away) → match_id` — so a non-ESPN fixture can be fed through the exact same path. This
  resolver is the **canonical identity authority for ALL current and future soccer
  providers, including football-data.co.uk** (its eventual `football_data_match_link`
  population must resolve through the same function and the same `match_id` scheme).
- **D2 — team alias resolution is SEED-only.** `team.similar_names` is **pre-seeded** for
  the allowlisted leagues; incoming ESPN team names are matched against
  `team.name`/`team.similar_names`. The conform step does **not** auto-write newly-seen
  spellings (auto-learn is deferred).
- **Linkage seam (forward-compatible scaffolding):** provider link records carry match
  provenance — `match_method`, `confidence`, `review_status`. For ESPN every link is
  `match_method = deterministic`, `confidence = 1.0`, `review_status = auto_confirmed` —
  truthful values for an exact within-provider match, **not** stubs. These columns are the
  only forward-compatible scaffolding added; no engine, queue table, or UI is built here.

The **probabilistic cross-provider record-linkage epic** (fuzzy team-name matching,
kickoff-time signal weighting, multi-signal confidence scoring, transitive reinforcement,
and a human-in-the-loop escalation/review UI) is **explicitly out of scope** (see §3
Non-goals and the forward-looking note there). It is triggered only when a *second*
provider arrives (nothing to fuzzy-match against while ESPN is sole writer).

## 3. Goals & non-goals

**Goals**

- Land **bronze ESPN event Parquet, faithful-to-source** (the full event payload
  preserved), partitioned per fetched unit (per league per season), on each run.
- Populate the canonical `league`, `season`, `team` and `match` tables from ESPN bronze
  via a conform/silver-canonical step.
- Maintain `espn_match_link` mapping each ESPN `event_id` to its canonical `match_id`.
- **Idempotent upsert behaviour**: a fixture re-ingested after kickoff updates the same
  canonical `match` row in place (scores, kickoff corrections) — the run is not
  append-only and does not duplicate matches across runs.
- **Provider-agnostic match identity (D1)**: a deterministic, separately-testable
  resolver `(canonical league, canonical season, kickoff calendar date (UTC), canonical
  home team, canonical away team) → match_id` drives match-id assignment, so a different
  provider ingesting the same fixture later resolves to the same `match_id` through the
  same resolver.
- **Linkage-seam provenance columns** on the provider link table (`match_method`,
  `confidence`, `review_status`), populated truthfully by ESPN (`deterministic` / `1.0` /
  `auto_confirmed`) — the only forward-compatible scaffolding for a future linkage epic.
- A Dagster **schedule firing every 6 hours** that runs the ESPN flow end-to-end.
- ESPN runs as its **own job**, excluded from `AssetSelection.all()`-based jobs so it does
  not get swept into the hello-world demo job / its daily schedule (mirrors the football
  exclusion).

**Non-goals (explicitly out of scope)**

- The **Matchbook ingestor** itself. This spec only guarantees the canonical match
  identity and `match_id` assignment are designed so Matchbook can later link to the same
  match; it does not build `matchbook_event_link` population.
- The **probabilistic cross-provider record-linkage epic**: fuzzy team-name matching,
  kickoff-time signal weighting, multi-signal **confidence scoring**, transitive /
  "circular" reinforcement (a weak fuzzy match corroborated by other already-linked
  entities becoming high-confidence), and a **human-in-the-loop escalation UI** with a
  persisted manual-decision / review-queue store. None of this is built here — ESPN is the
  sole canonical writer, so there is nothing to fuzzy-match against yet. The only seam left
  for it is the `match_method`/`confidence`/`review_status` columns (above).
  **Forward-looking note:** when a *second* soccer provider (Matchbook / football-data)
  lands, this epic should **start with an `investigation`** (architecture fit under the
  DuckDB single-writer / dbt-owned conform model; where human-curated decisions are
  persisted; the UI surface the repo currently lacks) before any build.
- **Auto-learning of team aliases** (writing newly-seen spellings back to
  `team.similar_names` during conform) — deferred to the linkage epic; this spec seeds
  aliases and matches against the seed only (D2).
- **Rugby** (and any non-soccer sport). The investigation proved the same pattern works
  for rugby, but the canonical model and this repo are soccer; rugby is a later source.
- A **full historic backfill** of all seasons. The schedule keeps current/near-window
  fixtures fresh; deep multi-season backfill is a separate concern (the same code path can
  do it, but it is not part of this spec's "done").
- Gold marts / analytics over the canonical matches, and any external redistribution.
- `favourite_team_id` population (captured T-45m before kickoff from market data, not
  available from ESPN) — left null by ESPN ingestion.
- Odds of any kind (ESPN scores only; odds are Matchbook/football-data concerns).

## 4. Actors & triggers

- **Actor:** the platform itself (an unattended scheduled run), or a data platform
  engineer running the job on demand.
- **Primary trigger:** a Dagster **schedule that fires every 6 hours** (cron
  `0 */6 * * *`), running the dedicated ESPN job.
- **Secondary trigger:** manual materialization of the ESPN job (same code path), for
  ad-hoc refresh or a bounded backfill.
- **Internal order:** discovery/season-window resolution → scoreboard fetch (the only
  network edge) → bronze Parquet write → conform step populates `league` / `season` /
  `team` / `match` and `espn_match_link`.

## 5. Behaviour specification (BDD)

### Capability: League & season discovery (clause d enabling the recurring fetch)

**Scenario: League allowlist drives discovery (no pre-seeded id table)**
- **Given** a configured allowlist of ESPN soccer league slugs (e.g. `eng.1`, `esp.1`,
  `uefa.champions`)
- **When** the flow runs
- **Then** only the allowlisted leagues are queried (the dead `provider_entity_cache` is
  not used), and each league's metadata (`id`/slug, display name) is resolved from the
  ESPN league endpoint.

**Scenario: Season windows resolved from ESPN, not guessed**
- **Given** an allowlisted league
- **When** the flow resolves which seasons to fetch
- **Then** it reads the league's `/seasons` endpoint for per-season `year`, `startDate`,
  `endDate`, and selects the season window(s) overlapping the run's target date range
  (e.g. today ± a configured horizon) rather than hard-coding date ranges.

### Capability: Faithful-to-source bronze (clause b)

**Scenario: Full ESPN event payload is preserved verbatim in bronze**
- **Given** a scoreboard response for an allowlisted league/season window
- **When** the flow writes bronze
- **Then** the **complete event payload is preserved** (a mandatory core is enforced per
  record, and all additional ESPN fields ride along) so that fields not yet promoted to
  canonical can be recovered later from bronze without re-fetching.

**Scenario: One bronze Parquet per fetched unit, partitioned**
- **Given** a successfully fetched league/season scoreboard
- **When** the artifact is materialized
- **Then** exactly one bronze Parquet is written under an ESPN partitioning keyed by
  league (and season), with deterministic path/naming across runs of the same unit.

**Scenario: Post-match re-fetch captures the richer payload**
- **Given** a fixture that was `STATUS_SCHEDULED` at a prior run and is now `STATUS_FINAL`
  with scores
- **When** the flow re-fetches and re-writes that league/season unit
- **Then** bronze now carries the post-match payload (scores, completed status, any extra
  fields) for that event, verbatim.

### Capability: Canonical population & idempotent upsert (clause a)

**Scenario: Pre-match fixture creates canonical rows**
- **Given** a `STATUS_SCHEDULED` ESPN event for an allowlisted league/season
- **When** the conform step runs
- **Then** a `league` row (if new), a `season` row (if new, with `start_date`/`end_date`
  from ESPN), home/away `team` rows (if new), and a `match` row are present, with
  `match.season_id` → the season, `match.home_team_id`/`away_team_id` → the teams,
  `match.kickoff_time` set, and `ht_score`/`ft_score` null (not yet played);
  `favourite_team_id` is null.
- **And** an `espn_match_link` row maps that ESPN `event_id` to the new `match_id`,
  carrying provenance `match_method = deterministic`, `confidence = 1.0`,
  `review_status = auto_confirmed`.

**Scenario: Post-match re-run fills in results on the SAME match (idempotent upsert)**
- **Given** a `match` already created pre-match (with its `espn_match_link`)
- **When** the same fixture is re-ingested after kickoff with `STATUS_FINAL` and scores
- **Then** the **same** `match_id` is updated in place — `ht_score` and `ft_score` are
  populated (and `kickoff_time` corrected if ESPN revised it) — and **no new `match` row
  or duplicate `espn_match_link` row is created**.

**Scenario: Re-running with no changes is a no-op for canonical state**
- **Given** a fixture whose ESPN payload is unchanged since the last run
- **When** the flow runs again
- **Then** the canonical `match` row and its `espn_match_link` are unchanged (re-runs are
  idempotent; counts of matches/links do not grow on identical input).

### Capability: Provider-agnostic match identity & de-duplication (clause c)

**Scenario: Match identity is computed by a provider-agnostic resolver**
- **Given** a fixture's `(canonical league, canonical season, kickoff calendar date,
  canonical home team, canonical away team)`
- **When** the shared identity resolver is invoked
- **Then** it returns a deterministic `match_id` derived from that natural key — **not**
  from any provider id (the raw ESPN `event_id` is never an identity input) — and the
  resolver is a **single separately-testable unit** (a shared dbt macro/model, or a pure
  function) reused by every provider, with no ESPN-specific logic.

**Scenario: Date component uses the UTC calendar date of kickoff**
- **Given** a fixture whose stored `kickoff_time` is a timestamp
- **When** the resolver computes the date component of the natural key
- **Then** it uses `cast(kickoff_time as date)` interpreted in **UTC** (ESPN `date`
  truncated to its UTC calendar date), so the identity date cannot drift from the stored
  timestamp across timezone representations, and an intra-day kickoff-time revision does
  not change the `match_id`.

**Scenario: Team alias resolution maps provider names to one canonical team (seeded)**
- **Given** `team.similar_names` is pre-seeded for the allowlisted leagues, and ESPN names
  a team by a seeded alias (e.g. "Wolves" for "Wolverhampton Wanderers")
- **When** the conform step resolves the team
- **Then** the name is matched against `team.name` / `team.similar_names` so the seeded
  spelling resolves to the existing canonical `team_id`, and the conform step **does not**
  write the spelling back as a new alias (no auto-learn).

**Scenario: A second provider for the same fixture resolves to the same match_id**
- **Given** a canonical `match` already created by ESPN for a real-world fixture
- **When** a second-provider-shaped fixture for the same real-world fixture (same
  `(league, season, kickoff calendar date, home, away)`) is fed through the **same shared
  resolver**
- **Then** it returns the **same** existing `match_id` (it does not create a second
  canonical match), demonstrating the resolver is genuinely provider-agnostic rather than
  ESPN-against-itself — and a future provider's link table would point at that `match_id`.

### Capability: Scheduled, isolated execution (clause d)

**Scenario: The flow runs every 6 hours**
- **Given** the ESPN schedule is enabled
- **When** the scheduler ticks
- **Then** the ESPN job is launched on a 6-hourly cadence (cron `0 */6 * * *`).

**Scenario: ESPN is its own job, excluded from all()-based jobs**
- **Given** the hello-world `medallion_hello_world` job and its daily schedule select
  `AssetSelection.all()` (minus heavy standalone sources)
- **When** that demo job or schedule runs
- **Then** the ESPN assets are **not** included (they are subtracted, like the football
  assets), and ESPN runs only via its dedicated job/schedule.

## 6. Edge cases & error handling

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | A league/season scoreboard fetch fails (network/non-200) after polite retries | That unit fails and is surfaced (logged + reflected in run status); **no partial/empty bronze Parquet is written** for it (atomic temp-file + rename); other units continue; the asset re-raises at the end so the run reflects failures. |
| E2 | A scoreboard returns zero events for the window | No bronze artifact is silently written as if successful; the empty result is recorded (logged/metadata); not treated as a hard failure for the run. |
| E3 | An event is missing a mandatory core field (event id, kickoff date, or a home/away competitor) | That record is dropped by row-level (Pydantic) validation, counted, and excluded from bronze/canonical; valid events in the same unit continue. |
| E4 | Post-match re-ingest of an already-canonical fixture | Idempotent upsert: same `match_id` updated in place (scores filled); no duplicate `match` or `espn_match_link` row (clause a/c). |
| E5 | ESPN names a team by a **seeded** alias (e.g. "Wolves") | Resolved via `team.name` / `team.similar_names` (pre-seeded) to the existing canonical `team_id`; the conform step does **not** auto-write the spelling (auto-learn deferred); no duplicate team, no split match identity. |
| E5b | ESPN names a team **not in the seed list** (genuine first encounter) | Treated as a genuinely new team → new `team_id` (and thus a new match identity). **Residual risk:** an *existing* team appearing under an un-seeded alias would fork into a second team and fork the match. **Mitigation in this spec:** curated seed lists for the allowlisted leagues; auto-learn / fuzzy reconciliation is deferred to the linkage epic. |
| E6 | Two distinct real fixtures share the same teams + competition but different kickoff dates (e.g. home and away legs) | They are **different** matches — the natural key includes the UTC kickoff calendar date, so each leg gets its own `match_id`. |
| E7 | A fixture's kickoff is rescheduled to a different calendar date by ESPN between runs | **Decided (D1):** the date component is the UTC calendar date of kickoff, so an intra-day time revision keeps the same `match_id`; a fixture moved to a *different day* becomes a new `match_id` (the prior day's match is left as-is). Frequent re-runs keep this current; deep reconciliation of moved fixtures is a linkage-epic concern. |
| E8 | ESPN season window overlaps a calendar split (Aug→May) | Season selection uses ESPN's own `startDate`/`endDate`, so the correct season window is fetched without a hand-coded rollover rule. |
| E9 | Re-run over an unchanged fixture | No-op for canonical state; match/link counts do not grow (idempotency). |
| E10 | DuckDB single-writer constraint during conform | The conform/canonical population happens **inside dbt** (dbt owns the warehouse file); Python does not open `warehouse.duckdb` read-write in a separate step (see §8). |
| E11 | An event has no scores yet but `STATUS_FINAL`/abandoned/postponed status | `ht_score`/`ft_score` remain null until ESPN provides them; status handling must not fabricate scores; abandoned/postponed handling recorded (left null). |

## 7. Acceptance criteria

Bronze (clause b):
- [ ] AC1 — On each run, the ESPN flow writes bronze Parquet preserving the **full event
  payload verbatim** (mandatory core enforced per record; all other ESPN fields ride
  along), one Parquet per league/season unit, under a deterministic ESPN partitioning.
- [ ] AC2 — A fixture fetched post-match has its richer payload (scores, completed status)
  present in bronze, recoverable without re-fetching.

Canonical population & idempotent upsert (clause a):
- [ ] AC3 — After a run, `league`, `season`, `team` and `match` are populated for
  ingested fixtures, with `match.season_id`/`home_team_id`/`away_team_id`/`kickoff_time`
  set and the season reachable via `season.league_id`; canonical dbt tests
  (`match_id` not-null/unique, etc.) pass.
- [ ] AC4 — Re-ingesting a played fixture updates the **same** `match_id` in place
  (`ht_score`/`ft_score` filled), creating **no** duplicate `match` or `espn_match_link`
  row — verified by stable match/link counts and updated score columns across two runs.
- [ ] AC5 — Each ingested ESPN event has exactly one `espn_match_link` row mapping its
  `event_id` to the canonical `match_id`, carrying provenance `match_method =
  deterministic`, `confidence = 1.0`, `review_status = auto_confirmed`.

Provider-agnostic identity / de-dup (clause c):
- [ ] AC6 — `match_id` is produced by a **single, separately-testable, provider-agnostic
  resolver** taking `(canonical league, canonical season, kickoff calendar date,
  canonical home/away team) → match_id`, with no provider-specific logic and the raw ESPN
  `event_id` never an identity input. The resolver is the canonical identity authority for
  all current/future soccer providers (including football-data.co.uk).
- [ ] AC6b — The resolver's date component is the **UTC calendar date** of `kickoff_time`
  (`cast(kickoff_time as date)` in UTC), so the identity date does not drift from the
  stored timestamp and an intra-day time revision does not change `match_id`.
- [ ] AC7 — ESPN team names that match a **pre-seeded** `team.name`/`team.similar_names`
  resolve to the existing canonical `team_id` (no duplicate team), and the conform step
  does **not** auto-write newly-seen spellings.
- [ ] AC7b — An ESPN team name **not** present in the seed list is treated as a new team
  (new `team_id`); no fuzzy/auto-learn matching is performed.
- [ ] AC8 — A test feeds a **second-provider-shaped** fixture (same natural key, non-ESPN
  origin) through the **same shared resolver** and asserts it returns the **same**
  `match_id` the ESPN path produced (proving provider-agnostic identity, not
  ESPN-against-itself).

Scheduling & isolation (clause d):
- [ ] AC9 — A Dagster schedule runs the ESPN job on a 6-hourly cadence (cron `0 */6 * * *`).
- [ ] AC10 — ESPN assets are excluded from `AssetSelection.all()`-based jobs (the
  hello-world job/daily schedule) and run only via the dedicated ESPN job/schedule.

Robustness:
- [ ] AC11 — A failed league/season unit is isolated (surfaced, no partial Parquet, other
  units continue, run reflects the failure); a zero-event window writes no spurious
  artifact.

## 8. Things to be aware of / constraints

**Domain vocabulary is the requirement here**
- Bronze is **faithful-to-source**: enforce a small mandatory ESPN event core (event id,
  kickoff date, home/away competitors with team id/name, status) per record (Pydantic v2)
  and let all other ESPN fields ride along (open Pandera frame, `strict=False`), mirroring
  the football ingestor's wide ride-along columns.
- Canonical chain is `league (1)──(N) season (1)──(N) match`; `match.season_id` FK →
  `season.season_id`; league reached via `season.league_id`. `match` has no direct
  `league_id`. `favourite_team_id` stays null for ESPN.
- **The natural-key resolver is the canonical identity authority for ALL soccer providers
  (F6/D1).** Match identity = (canonical league, canonical season, **UTC kickoff calendar
  date**, canonical home team, canonical away team), computed by one shared,
  separately-testable resolver (dbt macro/model, or pure function). football-data.co.uk's
  eventual `football_data_match_link` population — and every future provider — must resolve
  through this **same** resolver and the **same** `match_id` scheme; no provider may mint
  its own identity. The date component is `cast(kickoff_time as date)` in UTC so identity
  cannot drift across timezone representations (F4/D1).
- **Team resolution is seed-only (D2).** `team.similar_names` is pre-seeded for the
  allowlisted leagues; incoming names match against `team.name`/`team.similar_names`; the
  conform step does not auto-write new spellings. An unseen name is a new team (residual
  fork risk documented at E5b). `league`/`season` have no aliases column; alias resolution
  for them is deferred (Q2, non-blocking — ESPN slugs are stable).
- **Link provenance columns (the only linkage seam).** Provider link rows carry
  `match_method`, `confidence`, `review_status`; ESPN writes `deterministic` / `1.0` /
  `auto_confirmed` (truthful for an exact within-provider match). No review-queue table,
  no fuzzy/confidence engine, no UI is built here (those are the deferred linkage epic).

**Repo / platform constraints (from `CLAUDE.md` & `ARCHITECTURE.md`)**
- **DuckDB is single-writer; dbt owns the warehouse file.** The conform layer that
  populates `league`/`season`/`team`/`match`/`espn_match_link` must be **dbt models**
  (the canonical tables are already dbt models under `models/silver/canonical/`), not a
  second Python process opening `warehouse.duckdb` read-write during a run. Python reads
  the bronze **Parquet files**; dbt reads bronze as an external source and performs the
  upsert/merge into the canonical tables. The idempotent upsert is therefore expressed in
  dbt (e.g. an incremental/merge or a full rebuild keyed on the natural key), not raw DDL.
- The canonical tables are currently **empty typed scaffolds** (`select cast(null …) …
  limit 0`, `+materialized: table`). This feature replaces those scaffolds with populated
  conform models for the ESPN path; keep them as dbt models (don't create/alter with a raw
  DuckDB connection).
- **dbt model asset keys are prefixed by their model subfolder — do NOT guess the prefix
  (F5).** The canonical models live under `models/silver/canonical/`, so the key may be
  e.g. `["silver", "canonical", "match"]`. This is a documented real-bug source in
  `CLAUDE.md` (a wrong key silently fails to form the dependency edge). The plan /
  implementation must **resolve the ACTUAL key from the dbt manifest** rather than assume
  it, and both `BronzeAwareTranslator` (in `assets/dbt.py`, which must register the new
  ESPN bronze source and map it to the ESPN bronze `AssetKey`) and any cross-asset
  `deps=[...]` must use that exact key.
- **No `from __future__ import annotations`** in Dagster asset modules.
- The bronze asset is the **only network edge**; wrap fetches in an OTel span via
  `get_tracer()`; an asset either produces its artifact or raises — no silent fallbacks /
  defaults-on-failure / stubbed data. Per-unit failure isolation with **atomic temp-file +
  rename** writes (mirror the football assets).
- **Importing `definitions` reads the dbt manifest**, so `dbt parse` must run before the
  import (and before pytest that imports defs). New canonical/conform models change the
  manifest — re-parse.
- New config goes in `config.py` as typed `pydantic-settings` fields (ESPN base URLs,
  league allowlist, fetch horizon, throttle/timeout/retries, user-agent) — no ad-hoc
  `os.getenv`. A shared throttled, cache-aware HTTP resource modelled on
  `ThrottledHttpClient` is registered in `Definitions(...)`.
- `AssetSelection.all()`-based jobs (the hello-world job + `medallion_daily`) must subtract
  the ESPN assets, exactly as they subtract `football_assets`. Give ESPN its own job +
  6-hourly schedule.
- **ERD.md is living documentation:** populating the canonical tables / adding conform
  models under `models/silver/canonical/` must update `ERD.md` in the same commit.
- Ruff-enforced PEP 8 (`E,W,F,I,UP,B,C4,SIM`); `pathlib.Path`; context managers for
  connections/spans.

**ESPN API realities (from investigation + live check)**
- No auth/API key; browser `User-Agent` required; not aggressively rate-limited (~0.1 s
  courtesy pace; a polite throttle is still applied via the shared client).
- Endpoints: leagues list + league detail + `/seasons` (`sports.core.api.espn.com`);
  scoreboard with a `dates={YYYYMMDD}-{YYYYMMDD}` window (`site.api.espn.com`). Events
  carry `id`, `date`, `status.type` (`name`/`state`/`completed`), `season` (`year`/
  `displayName`), and per-competitor `homeAway`/`team`(`id`,`displayName`,`name`,
  `shortDisplayName`)/`score`.

## 9. Assumptions

- **A1 (sport scope)** — Scope is **association football (soccer)** only. The canonical
  model (`ht_score`/`ft_score`, home/away) and the whole repo are soccer; ESPN is
  multi-sport but this flow targets soccer. Rugby and other sports are out of scope
  (Non-goal), even though the investigation proved the same pattern works for rugby.
- **A2 (league allowlist)** — Discovery is driven by a configured **allowlist of soccer
  league slugs** (a curated subset of the 239 ESPN soccer leagues), held in a typed
  registry mirroring `football/registry.py`. The exact list is agreed at build time; this
  spec governs behaviour, not the membership. This replaces the dead `provider_entity_cache`.
- **A3 (fetch horizon, not full backfill)** — Each scheduled run keeps current / near-window
  fixtures fresh by fetching the season window(s) overlapping today ± a configured horizon,
  so pre-match fixtures are captured and re-fetched post-match. Deep multi-season historic
  backfill is out of scope (Non-goal) though the same code path supports it.
- **A4 (natural fixture key) — now DECIDED, see §2 D1.** The key and its UTC-calendar-date
  granularity and seed-based team resolution are no longer assumptions; they are decided
  (D1/D2) and specified in §2, §5, §7 (AC6/AC6b/AC7) and §8. Retained here only as a
  pointer.
- **A5 (conform in dbt)** — The canonical upsert is performed **inside dbt** (dbt owns the
  warehouse), expressed as a merge/incremental keyed on the natural key, satisfying both
  the single-writer constraint and the idempotent-upsert requirement.
- **A6 (idempotency mechanism)** — "Same `match_id` on re-run" is achieved because
  `match_id` is a deterministic function of the natural key (D1); a re-fetch of the same
  fixture maps to the same key → same row.
- **A7 ("all the data it has at that time", clause a)** — interpreted as: populate every
  canonical field ESPN currently exposes (kickoff, status, ht/ft scores once available);
  fields ESPN doesn't provide (e.g. `favourite_team_id`) stay null; the full raw payload
  is in bronze regardless (clause b).
- **A8 (consistency)** — "Deterministic path/naming across runs" means a stable output
  path and stable column/dtype contract per source unit, not byte-identical Parquet.

## 10. Open questions

No blockers remain. The previously-open Q1 is resolved and Q2/Q3 are accepted:

- **Q1 — RESOLVED (D1).** The match-identity key and rescheduling behaviour are decided:
  key = (canonical league, canonical season, **UTC kickoff calendar date**, canonical home
  team, canonical away team), computed by a shared provider-agnostic resolver; an intra-day
  time revision keeps the same `match_id`, a move to a different calendar day mints a new
  one. See §2 D1, §5 (identity scenarios), E7, AC6/AC6b.
- **Q2 — DEFERRED / ACCEPTED (non-blocking).** `team` has `similar_names`; `league` and
  `season` do not. ESPN slugs are stable, so no league/season alias mechanism is needed for
  ESPN-only population. When a second provider lands, add a league alias column (an
  `ERD.md` + canonical-model change) as part of the linkage epic. Not built here.
- **Q3 — ACCEPTED (ratified).** Bronze is **one Parquet per league per season** (mirrors
  `football_main`) — faithful, stable, re-writable units. No longer open.

## 11. Traceability

| Requirement clause | Requirement summary | Scenarios | Spec acceptance criteria |
|--------------------|---------------------|-----------|--------------------------|
| **(a)** idempotent re-run; post-match fills all available data on the same fixture (upsert, not append) | Pre-match fixture creates canonical rows; Post-match re-run fills results on the SAME match; Re-running unchanged is a no-op; Post-match re-fetch captures richer payload | Pre-match fixture creates canonical rows; Post-match re-run fills in results on the SAME match (idempotent upsert); Re-running with no changes is a no-op; Post-match re-fetch captures the richer payload | AC2, AC3, AC4, AC5 |
| **(b)** full post-match data stored in bronze verbatim (faithful-to-source) | Full ESPN event payload preserved verbatim; one Parquet per unit; richer post-match payload present | Full ESPN event payload is preserved verbatim in bronze; One bronze Parquet per fetched unit; Post-match re-fetch captures the richer payload | AC1, AC2 |
| **(c)** de-dup against existing matches; ESPN & future providers resolve to the same `match_id` | Match identity via a provider-agnostic resolver; UTC calendar-date key; seeded alias resolution; unknown-name handling; a second provider resolves to the same match_id via the same resolver | Match identity is computed by a provider-agnostic resolver; Date component uses the UTC calendar date of kickoff; Team alias resolution maps provider names to one canonical team (seeded); A second provider for the same fixture resolves to the same match_id | AC6, AC6b, AC7, AC7b, AC8 |
| **(d)** run on a schedule every 6 hours | 6-hourly schedule; ESPN is its own job excluded from all()-based jobs | The flow runs every 6 hours; ESPN is its own job, excluded from all()-based jobs | AC9, AC10 |
| (cross-cutting robustness, implied by a/b/d) | per-unit failure isolation; empty-window handling; canonical tests pass | League/season fetch failure (E1); zero-event window (E2); invalid event dropped (E3) | AC11 |
