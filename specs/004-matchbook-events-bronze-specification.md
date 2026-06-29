---
id: "004"
title: Matchbook Events Bronze Ingestion
slug: matchbook-events-bronze-ingestion
status: draft
created: 2026-06-29
user_stories: []
investigation: null
related_specs: ["001", "002", "003"]
---

# Matchbook Events Bronze Ingestion

## 1. Summary

On a 6-hourly schedule, the platform fetches all currently-open Matchbook events for football (sport-id 15) and rugby union (sport-id 2) and writes them as raw, faithful-to-source Parquet files into the bronze layer. Each run produces one file per sport, partitioned by sport and ingestion date, with the full raw API event JSON stored verbatim alongside key extracted fields. This gives downstream silver/gold conform layers an auditable, re-processable snapshot of the Matchbook event catalogue without needing to re-fetch from the API.

## 2. Background & context

The sports-gaming-engine project (`transformer/dagster_project/ingestion.py`) already ingests Matchbook events into a Postgres bronze schema. This spec ports that ingestion to this pipeline's Parquet-based bronze layer using the established patterns (Dagster asset, Pydantic+Pandera boundary validation, atomic write, `raw_event` JSON column). Future specs will perform deconfliction of Matchbook events onto the canonical `match`, `team`, and `competition` tables already defined in the silver layer (Spec 001/003).

Credentials (`MATCHBOOK_USERNAME`, `MATCHBOOK_PASSWORD`) are already present in the sports-gaming-engine `.env` and must be declared in this project's `config.py` and `.env.example`.

## 3. Goals & non-goals

**Goals**
- Fetch all open Matchbook events for football and rugby union every 6 hours.
- Write one bronze Parquet file per sport per run, partitioned as `data/bronze/matchbook_events/<sport>/<YYYY-MM-DD>/<batch-timestamp>.parquet`.
- Store the full raw API event JSON verbatim in a `raw_event` column so any field omitted from the structured columns can be recovered without a re-fetch.
- Validate each event record at the bronze boundary: Pydantic per-record, Pandera per-frame.
- Expose the Dagster asset and a dedicated `matchbook_events_ingestion` job and `matchbook_events_schedule` schedule (cron `0 */6 * * *`).
- Credentials and connection settings flow through `pydantic-settings` (`config.py`).

**Non-goals (explicitly out of scope)**
- Deconfliction of Matchbook events onto canonical `match`/`team`/`competition` tables — that is future work.
- Silver or gold dbt models reading this bronze layer — future work.
- Ingesting any Matchbook sport other than football (15) and rugby union (2).
- Ingesting markets, runners, or odds as separate Parquet files (they ride inside `raw_event`; structured extraction is future work).
- Replacing or migrating the existing sports-gaming-engine Postgres ingestion — both can coexist.
- Any real-time or streaming path — only the scheduled 6-hourly batch.

## 4. Actors & triggers

| Actor | Trigger |
|-------|---------|
| Dagster scheduler | Cron `0 */6 * * *` (every 6 hours, at :00) — fires `matchbook_events_schedule` |
| Engineer | Manual `matchbook_events_ingestion` job launch via Dagster UI |
| CI / test suite | Direct call to the pure-Python ingest function (no Dagster) |

The asset has no upstream Dagster asset dependencies — it is a network-edge leaf.

## 5. Behaviour specification (BDD)

### Capability: Authentication

**Scenario: Successful session token acquisition**
- **Given** `MATCHBOOK_USERNAME` and `MATCHBOOK_PASSWORD` are present in config
- **When** the asset executes
- **Then** the asset POSTs to `https://api.matchbook.com/bpapi/rest/security/session` with the credentials as a JSON body
- **And** extracts the `session-token` field from the response
- **And** uses that token as the `session-token` request header on all subsequent event-fetch calls

**Scenario: Missing credentials**
- **Given** `MATCHBOOK_USERNAME` or `MATCHBOOK_PASSWORD` is absent from config
- **When** the asset executes
- **Then** the asset raises immediately with a descriptive error before making any network call
- **And** no Parquet file is written

**Scenario: Auth endpoint returns error or no token**
- **Given** valid credentials are configured
- **When** the auth POST returns a non-2xx status or a 2xx response with no `session-token` field
- **Then** the asset raises, propagating the HTTP or value error
- **And** no Parquet file is written

---

### Capability: Event fetching

**Scenario: Paginated fetch of open events for one sport**
- **Given** a valid session token
- **When** the asset fetches events for a sport-id
- **Then** it GETs `https://api.matchbook.com/edge/rest/events` with params `sport-ids=<id>`, `status=open`, `include-markets=true`, `include-runners=true`, `per-page=20`, `offset=0`
- **And** if the response `total` exceeds the first page, issues subsequent GETs incrementing `offset` by the batch count until all events are retrieved
- **And** accumulates all event dicts across pages

**Scenario: Empty result for a sport**
- **Given** a valid session token
- **When** Matchbook returns zero open events for a sport (e.g. rugby union off-season)
- **Then** no Parquet file is written for that sport
- **And** the asset logs the empty result and continues to the next sport without error

**Scenario: Both sports fetched per run**
- **Given** a valid session token
- **When** the asset executes
- **Then** it fetches football (sport-id 15) and rugby union (sport-id 2) in sequence
- **And** writes a separate Parquet file for each sport that returned events

---

### Capability: Record validation

**Scenario: Well-formed events pass validation**
- **Given** the API returns events with the expected fields (`id`, `name`, `status`, `volume`, `start`, `sport-id`, `markets`)
- **When** validation runs at the bronze boundary
- **Then** each event passes the Pydantic record schema
- **And** the assembled DataFrame passes the Pandera frame schema
- **And** the Parquet file is written

**Scenario: Individual malformed record skipped, valid records continue**
- **Given** the API returns a mix of well-formed and malformed event dicts (e.g. missing `id`, wrong type on `start`)
- **When** Pydantic validation runs per record
- **Then** each failing record is logged with its event id (or position) and the validation error
- **And** valid records are accumulated and written to Parquet
- **And** if any records failed, the asset surfaces the count of failures in its MaterializeResult metadata
- **And** the asset re-raises at the end of the full run (after all sports are processed) so the run status is marked failed while the valid Parquet files are still persisted
- **And** if zero valid records remain for a sport after skipping, that sport is treated as E7 (no file written; no re-raise for that sport alone)

**Scenario: Frame fails Pandera schema**
- **Given** the assembled DataFrame for a sport violates the Pandera frame schema (e.g. wrong column types across the frame)
- **When** Pandera validation runs on the assembled DataFrame
- **Then** the asset raises, no Parquet is written for that sport
- **And** the error is surfaced in the run log

---

### Capability: Parquet write

**Scenario: Successful atomic write**
- **Given** at least one valid event has been validated for a sport
- **When** the asset writes the Parquet file
- **Then** it writes to a temporary file first, then atomically renames it to the final path `data/bronze/matchbook_events/<sport>/<YYYY-MM-DD>/<batch-timestamp>.parquet`
- **And** no partial Parquet file is left behind if the write fails mid-stream

**Scenario: Output path is created on first run**
- **Given** the partition directory does not yet exist
- **When** the asset writes the Parquet file
- **Then** all required parent directories are created before the write

**Scenario: `raw_event` column carries the complete original event dict**
- **Given** a valid event dict fetched from the API
- **When** the Parquet row is written
- **Then** the `raw_event` column contains the full serialised JSON of the original event dict (including `markets`, `runners`, any fields not projected into the structured columns)
- **And** a reader can deserialise `raw_event` and recover any field present in the original API response without calling the API again

---

### Capability: Scheduling

**Scenario: 6-hourly schedule fires the asset**
- **Given** the Dagster daemon is running
- **When** the cron expression `0 */6 * * *` fires
- **Then** the `matchbook_events_schedule` triggers a run of `matchbook_events_ingestion` job
- **And** the job materialises the `matchbook_events_bronze` asset

**Scenario: Manual job launch**
- **Given** the Dagster UI is running
- **When** an engineer launches `matchbook_events_ingestion` manually
- **Then** the `matchbook_events_bronze` asset is materialised on demand

## 6. Edge cases & error handling

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | Auth endpoint unreachable (network timeout) | Asset raises; no Parquet written; run marked failed |
| E2 | `MATCHBOOK_USERNAME` or `MATCHBOOK_PASSWORD` not set | Asset raises immediately with descriptive config error before any HTTP call |
| E3 | Auth response has no `session-token` field | Asset raises with a ValueError naming the missing field |
| E4 | Events endpoint returns non-2xx | Asset raises; no Parquet written for that sport |
| E5 | Single event record fails Pydantic validation | Record skipped and logged; remaining valid records proceed; failure count surfaced in metadata; asset re-raises at end |
| E6 | Assembled DataFrame fails Pandera schema | Asset raises for that sport; no Parquet written for that sport |
| E7 | Zero events returned for a sport | No Parquet written for that sport; logged; continues to next sport |
| E8 | Zero events for ALL sports | Asset completes without writing any Parquet; logs the empty result; run succeeds (no data is a valid state) |
| E9 | Parquet write fails mid-stream | Atomic write (temp + rename) ensures no partial file; error propagates |
| E10 | Run executes while a previous run's Parquet for the same partition already exists | New batch-timestamp ensures a new file; existing files are not deleted (append-partition behaviour) |
| E11 | `sport-id` field missing from event | Pydantic validation fails that record; see E5 |
| E12 | `start` field absent or unparseable | Pydantic validation fails that record; see E5 |
| E13 | Paginated fetch: `total` field absent from API response | Treat as single page (no further pages); log warning |

## 7. Acceptance criteria

- [ ] AC1 — A Parquet file is present under `data/bronze/matchbook_events/football/<YYYY-MM-DD>/` after a successful run that returned football events.
- [ ] AC2 — A Parquet file is present under `data/bronze/matchbook_events/rugby_union/<YYYY-MM-DD>/` after a successful run that returned rugby union events.
- [ ] AC3 — Each row in the Parquet has a `raw_event` column containing valid JSON that round-trips to the original API event dict, including the `markets` array.
- [ ] AC4 — Each row has structured columns: `event_id` (string), `event_name` (string), `sport_id` (int), `status` (string), `start_utc` (string/timestamp), `volume` (float), `ingested_at` (timestamp), `raw_event` (string JSON).
- [ ] AC5 — When a run is replayed (same date), a new file with a distinct batch timestamp is written; previously written files are not overwritten or deleted.
- [ ] AC6 — When credentials are missing, the asset raises before making any HTTP call and no Parquet is written.
- [ ] AC7 — When a single record fails Pydantic validation, the remaining valid records are written and the run is marked failed (not silently swallowed).
- [ ] AC8 — No partial Parquet file is left on disk after a write-time failure.
- [ ] AC9 — `matchbook_events_bronze` asset is NOT included in the `medallion_hello_world` job or the daily medallion schedule.
- [ ] AC10 — A dedicated `matchbook_events_ingestion` job and `matchbook_events_schedule` (cron `0 */6 * * *`) are registered in `definitions.py`.
- [ ] AC11 — `MATCHBOOK_USERNAME` and `MATCHBOOK_PASSWORD` are declared as fields in `config.py` (pydantic-settings) and documented in `.env.example`.
- [ ] AC12 — A `matchbook_events_bronze_dir` property exists on `Settings` returning `settings.bronze_dir / "matchbook_events"` (distinct from the existing `matchbook_bronze_dir` property which returns `bronze_dir / "matchbook_odds"` for the Redis-based odds ingestor).
- [ ] AC13 — The asset module does NOT contain `from __future__ import annotations`.
- [ ] AC14 — The pure-Python ingest logic (auth, fetch, validate, write) lives in `src/data_platform/matchbook/ingest.py` (matching the `espn/ingest.py` / `football/ingest.py` pattern). A thin Dagster wrapper in `assets/matchbook_events.py` calls it. Unit tests covering the ingest function exist under `tests/matchbook/` (no Dagster, no live HTTP).
- [ ] AC15 — Running `dagster definitions validate` with the updated `definitions.py` exits 0.
- [ ] AC16 — When the auth endpoint returns a non-2xx status or a 2xx response with no `session-token` field, the asset raises before writing any Parquet file.

## 8. Things to be aware of / constraints

**Medallion-layer rules (CLAUDE.md)**
- All HTTP calls MUST remain in the bronze asset — no network access in silver or gold.
- Atomic write: always write to a temp file then rename; never leave a partial Parquet.
- Config via `pydantic-settings` only — no ad-hoc `os.getenv`.
- No `from __future__ import annotations` in Dagster asset modules — Dagster introspects annotations at runtime.
- `AssetSelection.all()` sweeps all assets; `matchbook_events_bronze` MUST be excluded from `medallion_hello_world` and its daily schedule. Give it a dedicated job.

**Faithful-to-source bronze**
- The `raw_event` JSON column must contain the complete original event dict (all fields, including `markets` and `runners`). This is the same pattern as ESPN bronze (`espn/ingest.py`). A future field must be recoverable from bronze without a re-fetch; prove it with a test that reads a non-projected field from `raw_event`.

**Partitioning**
- Path: `data/bronze/matchbook_events/<sport>/<YYYY-MM-DD>/<batch-timestamp>.parquet`
- `<sport>` is `football` or `rugby_union` (snake_case, matching the reference implementation).
- `<batch-timestamp>` is a UTC ISO-8601 timestamp (e.g. `20260629T120000Z`) — ensures multiple runs on the same date produce distinct files.

**Credentials**
- `MATCHBOOK_USERNAME` and `MATCHBOOK_PASSWORD` come from the sports-gaming-engine `.env`. They must be added to this project's `.env.example` with placeholder values and documented as required for Matchbook ingestion. Do NOT commit real credentials.
- `config.py` already contains `matchbook_redis_host` and `matchbook_redis_port` fields (for the existing Redis-based odds ingestor). The new `matchbook_username` and `matchbook_password` fields must be added alongside them — do not rename or remove the existing Redis fields.

**Session-token lifecycle**
- The reference implementation acquires one session token per asset run and reuses it for all paginated event fetches in that run. There is no token refresh mid-run — if the token expires during a long paginated fetch (unlikely for typical event counts), the run will fail with a 401 and must be retried.

**API pagination**
- Events endpoint: `offset` + `per-page` style. The reference uses `per-page=20`. Continue until `len(batch) < per_page` or `len(events) >= total`.

**Dependency isolation**
- The asset has no upstream Dagster asset deps. It does not depend on dbt, DuckLake, or any other asset in the medallion flow.

**No DuckDB / DuckLake writes**
- Bronze writes Parquet only. No DuckDB or DuckLake writes in this spec.

**`definitions.py` is the sole composition root**
- Register the new asset, job, schedule, and any new resources in `definitions.py`. Do not create a parallel entry point.

## 9. Assumptions

- A1: The Matchbook credentials (`MATCHBOOK_USERNAME`, `MATCHBOOK_PASSWORD`) that work in the sports-gaming-engine project will work against the same Matchbook API endpoint from this pipeline (same account, no IP allowlisting).
- A2: `per-page=20` is an appropriate page size (same as the reference implementation). If Matchbook imposes rate limits, the throttle should be configurable via `matchbook_throttle_seconds` in `config.py`; assumed to start at 0.0 (no sleep) and can be tuned.
- A3: "Every 6 hours" means UTC-aligned at :00 (cron `0 */6 * * *`), not relative to last run.
- A4: Rugby union and football are the only sports for now; sport-id list is hardcoded (not config-driven), matching the reference implementation. If additional sports are needed, a follow-up spec covers it.
- A5: The `status=open` filter is the correct production filter — it matches what the reference implementation uses. No historical/closed events are needed for bronze at this time.
- A6: The batch-timestamp in the filename is sufficient to avoid overwrite collisions between concurrent runs. No file-locking or distributed coordination is needed.
- A7: Matchbook's `session-token` remains valid for at least the duration of a single paginated fetch (typically seconds to a few minutes). No mid-run token refresh is required.
- A8: The Parquet files produced here will NOT be read directly by any existing dbt model — they are inert bronze until a future silver conform layer is specified.

## 10. Open questions

**Q1 (non-blocking, best-guess pick: no throttle for now):** Should `matchbook_throttle_seconds` be added to `config.py` now for future use, or added when/if rate limiting is encountered? *Best guess: add it as an optional field defaulting to 0.0 so it's easy to tune without a code change.*

**Q2 (non-blocking, best-guess pick: fail-fast on all-sport failure):** If ALL sports return zero events (e.g. during an outage or off-peak window), should the run succeed (no data is valid) or fail? *Best guess: succeed with a warning log, since zero events during off-season is a legitimate state, not an error.*

**Q3 (non-blocking, best-guess pick: 20):** Is `per-page=20` acceptable, or should it be configurable? *Best guess: hardcode 20 matching the reference; add `matchbook_per_page` config field only if needed.*

**Q4 (resolved — append):** Each run appends a new file per partition date (multiple files per day). Rationale: the 6-hourly cadence is intended to capture successive point-in-time snapshots of the open event catalogue; a 6h-old snapshot has forensic/audit value (events open and close between runs). ESPN overwrites because it fetches the current state of a fixed scoreboard — replacement is correct there. Matchbook events accumulate. The batch-timestamp path scheme encodes this decision.

## 11. Traceability

This spec was written from a direct user description (no user story JSON files exist for this feature). The user description maps to the spec as follows:

| Source | User requirement | Scenarios | Spec acceptance criteria |
|--------|-----------------|-----------|--------------------------|
| User description | "implement the matchbook raw events similar to from here: ../sports-gaming-engine/transformer" | Auth scenarios, Event fetching scenarios, Parquet write scenarios | AC1–AC4, AC11–AC12 |
| User description | "put them into a new bronze layer only" | Parquet write — successful atomic write, `raw_event` column | AC1–AC4, AC8, AC9 |
| User description | "future work will deconflict these into our match/team/competition table(s)" | Non-goals section | — (explicit non-goal) |
| User description | "ingest every 6 hours" | Scheduling scenarios | AC10 |
| CLAUDE.md constraint | `AssetSelection.all()` exclusion | Scheduling scenarios | AC9 |
| User description | "get the credentials from the .env file in the other project" | Auth scenarios, Missing credentials | AC6, AC11 |
| CLAUDE.md constraint | Atomic write, faithful-to-source, no `__future__`, pydantic-settings, AssetSelection exclusion | All validation & write scenarios, constraints section | AC7, AC8, AC9, AC10, AC13 |
| Reference implementation | Pagination, sport-id list, session-token pattern, `parse_matchbook_event` field set | Event fetching scenarios | AC1–AC4 |
