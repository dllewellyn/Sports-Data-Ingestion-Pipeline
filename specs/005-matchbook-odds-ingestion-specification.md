---
id: 005
title: Matchbook Odds Ingestion (Redis stream → bronze Parquet → silver staging)
slug: matchbook-odds-ingestion
status: implemented
created: 2026-06-29
user_stories: []
source_commits: [2f77945, a67a9a6, 93f44d1, cb09e53, 8aeccac, eba8f84, 5147116, 08ba04a, ff5f87f, ee6cd94, 37aa9c6]
investigation: null
related_specs: [003, 004]   # 004 = platform foundation (the medallion platform this source plugs into); 003 = DuckLake model migration (stg_matchbook_odds is now DuckLake-managed)
---

# Matchbook Odds Ingestion (Redis stream → bronze Parquet → silver staging)

## 1. Summary

A new betting-exchange data source is ingested into the medallion warehouse:
Matchbook odds ticks. A long-lived daemon (`matchbook-ingestor`) subscribes to the
`matchbook_odds_stream` Redis channel published by the external sports-gaming-engine
stack, deduplicates state-change ticks in memory, validates each tick against a
Pydantic contract, and writes ZSTD-compressed, Hive-partitioned bronze Parquet using
an atomic temp-file-and-rename write. dbt then exposes that Parquet as a `bronze`
source and a faithful `stg_matchbook_odds` silver staging view. A one-off migration
script back-fills historical Matchbook Parquet from the upstream lakehouse into the
same bronze location. The result is Matchbook odds available as a first-class,
queryable layer in the warehouse alongside the football and ESPN sources.

## 2. Background & context

This is a **retrospective specification reconstructed from commits
`2f77945..37aa9c6`** (in build order:
`2f77945, a67a9a6, 93f44d1, cb09e53, 8aeccac, eba8f84, 5147116, 08ba04a, ff5f87f,
ee6cd94, 37aa9c6`). It was written after the fact to document already-shipped
behaviour; there were no user stories. Commits `4d057e5` and `2bda834` in the same
arc are ruff-style-only and non-substantive, so they are not listed as source
commits. Commit `ee6cd94` is a combined/merge commit that overlaps the granular
commits (the same work arrived both as granular commits and as a squashed commit via
branch merges); this spec describes the **end-state behaviour**, not the commit
mechanics.

The ingestor, schema, and odds JSON schema were **migrated from the upstream
sports-gaming-engine** project and reworked to fit this repository's conventions:
config via `pydantic-settings` (not `os.getenv`), validation at the boundary via
Pydantic, bronze Parquet as the landing layer (not silver), and dbt as the
transform/test layer. It relates to **spec 003** (DuckLake silver/gold migration) in
that `stg_matchbook_odds` is a silver dbt model under the same project, but it does
not itself depend on the DuckLake catalog — it reads the bronze Parquet glob
directly.

## 3. Goals & non-goals

**Goals**
- Continuously capture Matchbook odds ticks from the `matchbook_odds_stream` Redis
  channel into the bronze layer without data loss during the parallel-run phase
  (a separate upstream JSONL consumer subscribes to the same channel).
- Suppress redundant ticks: only persist a tick when a tracked price/volume/depth/
  status field actually changes for a `(event_id, market_id, runner_id)` runner.
- Validate every tick at the ingest boundary; drop malformed/invalid ticks rather
  than corrupting bronze.
- Write bronze as ZSTD-compressed Parquet, Hive-partitioned by capture date, with
  an atomic write so no partial or empty file is ever visible.
- Expose the bronze Parquet to dbt as a `bronze` source and a faithful, untransformed
  `stg_matchbook_odds` silver staging view, with not-null tests on the identity
  columns.
- Run the consumer as a containerised service wired to the external network where
  Redis lives, in both dev and prod compose overlays.
- Provide an idempotent one-off script to migrate historical Matchbook Parquet from
  the upstream lakehouse into this project's bronze location.

**Non-goals (explicitly out of scope)**
- Enrichment of odds data — market/runner/team names from the upstream Postgres
  catalogue are deferred to a future model; silver staging is a faithful projection.
- Any gold-layer aggregation, dimensional model, or canonical-match linkage for
  Matchbook (no `matchbook_match_link` population — that remains an empty scaffold
  per repo constraints).
- Orchestrating the consumer as a Dagster asset/job — it runs as a standalone daemon
  process, not in the Dagster asset graph.
- Starting or managing the Redis broker itself (it belongs to the external
  sports-gaming-engine stack).
- Schema evolution beyond additive columns handled by `union_by_name` (e.g. the
  late-added `kickoff_ms` column).

## 4. Actors & triggers

- **External Matchbook publisher (sports-gaming-engine)** — publishes JSON odds-tick
  messages onto the `matchbook_odds_stream` Redis pub/sub channel. This is the
  upstream trigger for continuous ingestion.
- **`matchbook-ingestor` daemon** — the long-lived consumer process (a Docker
  service or `python -m data_platform.matchbook.ingestor.direct_parquet_consumer`).
  Triggered at startup; runs until SIGTERM/SIGINT.
- **dbt** (`dbt build`/`dbt run`) — invoked by an operator or scheduler to materialise
  `stg_matchbook_odds` and run its tests over the accumulated bronze Parquet.
- **Operator running the migration script** — a human invoking
  `scripts/migrate_matchbook_bronze.py` once to back-fill historical data.

## 5. Behaviour specification (BDD)

### Capability: Tick deduplication

**Scenario: Identical consecutive tick is suppressed**
- **Given** the consumer has already buffered a tick for runner
  `(event_id, market_id, runner_id)`
- **When** a second message arrives for the same runner with identical values for all
  tracked dedup fields (best back/lay price, best back/lay available, queue depth at
  levels 2/3, market volume, runner volume, in_running, market_status)
- **Then** the second message is not added to the buffer
- **And** the buffer length is unchanged.

**Scenario: Tick with a changed tracked field is buffered**
- **Given** the consumer has already buffered a tick for a runner
- **When** a later message for the same runner changes any tracked dedup field
  (e.g. `best_back_price`)
- **Then** the new tick is appended to the buffer and recorded as the runner's latest
  state.

### Capability: Boundary validation (Pydantic gate)

**Scenario: Message missing a required identity field is dropped**
- **Given** a message that omits `event_id` (or has a non-integer `event_id`,
  `market_id`, or `runner_id`)
- **When** the consumer processes it
- **Then** the message is dropped with a warning and the buffer is unchanged, with no
  exception propagated.

**Scenario: Message failing the Pydantic contract is dropped**
- **Given** a candidate bronze row that fails `MatchbookOddsRecord` validation
- **When** the consumer validates it before buffering
- **Then** the row is dropped with a warning identifying `event_id/market_id/runner_id`
  and is never written to bronze.

**Scenario: Missing optional/derivable fields are tolerated**
- **Given** a message missing `in_running`
- **When** the consumer processes it
- **Then** `in_running` is coerced to `False` (via `bool(None)`), the record is still
  valid, and the tick is buffered (only the five required fields — `event_id`,
  `market_id`, `runner_id`, `ingested_at`, `in_running` — are mandatory; all price/
  volume/depth fields are nullable).

### Capability: Buffer flush to bronze Parquet

**Scenario: Buffer flush writes one ZSTD Parquet file to the bronze date partition**
- **Given** a non-empty buffer of validated ticks
- **When** the buffer is flushed
- **Then** exactly one Parquet file is written under
  `<bronze_dir>/matchbook_odds/year=YYYY/month=MM/day=DD/part-<epoch_ms>.parquet`
- **And** the file is ZSTD-compressed
- **And** the path contains `matchbook_odds`, `year=`, `month=`, `day=` and never
  `silver` (bronze, not silver).

**Scenario: Flush is triggered by size or time**
- **Given** the consumer is running
- **When** 5 000 state-change ticks have accumulated **or** 60 seconds have elapsed
  since the last flush and the buffer is non-empty
- **Then** the buffer is flushed and the flush timer is reset.

**Scenario: Empty buffer flush writes nothing**
- **Given** an empty buffer
- **When** a flush is attempted
- **Then** no file (and no empty/partial file) is written.

**Scenario: Graceful shutdown flushes the buffer**
- **Given** the consumer is running with buffered ticks
- **When** it receives SIGTERM or SIGINT
- **Then** the run loop exits cleanly, the pub/sub connection is closed, and a final
  flush writes the remaining buffered ticks before the process stops (no ticks lost).

### Capability: Atomic, schema-gated write

**Scenario: Each Parquet file appears atomically**
- **Given** a batch being written
- **When** the file is written
- **Then** it is written to a `part-<epoch_ms>.parquet.tmp` temp file and renamed to
  the final `.parquet` name, so a reader never observes a half-written file.

**Scenario: A batch that fails the Arrow schema cast is dropped, not written**
- **Given** a buffered batch whose Arrow table cannot be cast to the canonical
  `matchbook_odds` schema
- **When** the write is attempted
- **Then** the cast gate fails, the batch is dropped with a warning, and no file is
  written.

### Capability: dbt bronze source & silver staging

**Scenario: Bronze Parquet is exposed as a dbt source**
- **Given** Matchbook bronze Parquet has been written under
  `<DATA_DIR>/bronze/matchbook_odds/`
- **When** dbt resolves the `bronze.matchbook_odds` source
- **Then** it reads the Hive-partitioned glob `matchbook_odds/**/*.parquet` with
  `union_by_name=true`, so files written before the `kickoff_ms` column existed are
  read with that column as NULL.

**Scenario: Silver staging is a faithful projection**
- **Given** the `bronze.matchbook_odds` source
- **When** `stg_matchbook_odds` is materialised (a view, inherited from
  `dbt_project.yml`)
- **Then** it selects all 28 bronze columns with no enrichment or transformation
- **And** dbt tests assert `event_id`, `market_id`, `runner_id`, and `ingested_at`
  are non-null.

### Capability: Containerised service

**Scenario: Consumer runs as a compose service on the external Redis network**
- **Given** the base compose stack
- **When** the `matchbook-ingestor` service starts
- **Then** it runs `python -m data_platform.matchbook.ingestor.direct_parquet_consumer`,
  reads `MATCHBOOK_REDIS_HOST`/`MATCHBOOK_REDIS_PORT` (defaulting to `redis:6379`),
  joins the external `sports-quant` network where Redis lives, writes to the shared
  `./data` bronze volume, and restarts unless stopped.
- **And** the prod overlay extends the same service with the prod app wiring
  (external OTLP endpoint); the service is environment-neutral in the base.

### Capability: Historical bronze migration

**Scenario: Migrate historical Parquet from the upstream lakehouse**
- **Given** a locally accessible directory of upstream Matchbook Parquet files laid
  out as `year=YYYY/month=MM/day=DD/<file>.parquet`
- **When** `scripts/migrate_matchbook_bronze.py --source-dir <dir>` runs
- **Then** each `.parquet` file is copied to
  `<dest-dir>/matchbook_odds/year=YYYY/month=MM/day=DD/<file>.parquet` (dest-dir
  defaults to `data/bronze`; the script appends `matchbook_odds/`), preserving the
  original filename.

**Scenario: Migration derives the date when no Hive partition is present**
- **Given** a source file whose path has no `year=/month=/day=` tokens
- **When** the script processes it
- **Then** it derives the date from the minimum `ingested_at` value in the Parquet,
  and skips-and-counts the file only if the date cannot be determined.

**Scenario: Migration is idempotent and supports dry-run**
- **Given** a destination file that already exists
- **When** the script runs
- **Then** that file is skipped (re-running copies nothing new); and `--dry-run`
  prints intended copies without writing any file.

## 6. Edge cases & error handling

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | Unparseable Redis message (bad JSON / missing `data`) | Logged and dropped; loop continues. |
| E2 | Message missing/invalid `event_id`/`market_id`/`runner_id` | Dropped with "missing IDs" warning; buffer unchanged. |
| E3 | Candidate row fails `MatchbookOddsRecord` validation | Dropped with a warning naming the IDs; never written. |
| E4 | Duplicate consecutive tick (no tracked field changed) | Suppressed; not buffered. |
| E5 | Empty buffer at flush time | No file written (no empty/partial Parquet). |
| E6 | Batch fails the Arrow schema cast | Whole batch dropped with a warning; no file written. |
| E7 | Process killed (SIGTERM/SIGINT) with buffered ticks | Final flush persists remaining ticks before exit. |
| E8 | `timestamp_ns` absent on a message | `ingested_at` falls back to current wall-clock epoch ms. |
| E9 | Bronze files pre-dating the `kickoff_ms` column | dbt `union_by_name=true` fills `kickoff_ms` with NULL on read. |
| E10 | Migration: destination file already exists | Skipped-and-counted (idempotent re-runs). |
| E11 | Migration: no Hive partition tokens in path | Date derived from `ingested_at`; file skipped only if undeterminable. |
| E12 | Migration: source-dir missing or contains no `.parquet` | Script exits with a non-zero status and an error message. |

## 7. Acceptance criteria

- [ ] AC1 — A non-empty buffer flush writes exactly one Parquet file under
  `<bronze_dir>/matchbook_odds/year=YYYY/month=MM/day=DD/part-<epoch_ms>.parquet`.
- [ ] AC2 — The written file is ZSTD-compressed and its path contains `matchbook_odds`
  and never `silver`.
- [ ] AC3 — Files are written via a `.parquet.tmp` → `.parquet` rename (atomic write).
- [ ] AC4 — A batch that fails the Arrow schema cast to the canonical `matchbook_odds`
  schema is dropped without writing any file.
- [ ] AC5 — A message missing `event_id` (or otherwise failing `MatchbookOddsRecord`)
  is dropped with no crash and no buffering.
- [ ] AC6 — `MatchbookOddsRecord` requires exactly `event_id`, `market_id`,
  `runner_id`, `ingested_at`, `in_running`; all other (price/volume/depth) fields are
  nullable; unknown fields are ignored (`extra="ignore"`).
- [ ] AC7 — An identical consecutive tick for the same runner is not buffered; a tick
  changing any tracked dedup field is buffered.
- [ ] AC8 — Flush fires at 5 000 buffered ticks or 60 seconds since last flush (when
  the buffer is non-empty); an empty buffer flush writes nothing.
- [ ] AC9 — SIGTERM/SIGINT causes a clean exit with a final flush of the buffer.
- [ ] AC10 — `bronze.matchbook_odds` is registered as a dbt source reading
  `matchbook_odds/**/*.parquet` with `union_by_name=true`.
- [ ] AC11 — `stg_matchbook_odds` is a view projecting all 28 bronze columns with no
  enrichment, with not-null tests on `event_id`, `market_id`, `runner_id`,
  `ingested_at`.
- [ ] AC12 — A `matchbook-ingestor` compose service runs the consumer module, reads
  `MATCHBOOK_REDIS_HOST`/`MATCHBOOK_REDIS_PORT`, joins the external `sports-quant`
  network, and is present in both base and prod overlays.
- [ ] AC13 — Redis host/port are configured through `pydantic-settings`
  (`matchbook_redis_host`, `matchbook_redis_port`), not ad-hoc `os.getenv`.
- [ ] AC14 — `scripts/migrate_matchbook_bronze.py` copies each source `.parquet` to
  `<dest>/matchbook_odds/year=…/month=…/day=…/<original-name>`, preserving filename,
  skipping existing destinations, supporting `--dry-run`, and deriving the date from
  `ingested_at` when Hive tokens are absent.

## 8. Things to be aware of / constraints

- **Bronze, not silver.** The consumer writes to the bronze layer
  (`<bronze_dir>/matchbook_odds/...`), reversing the upstream project's silver-grade
  intent (the migrated JSON schema's `description` still reads "Silver-grade …"). The
  tests explicitly assert `silver` does not appear in the output path.
- **No second DuckDB writer.** Consistent with the repo's single-writer DuckDB
  constraint, the consumer writes Parquet **files**; dbt is the only thing that opens
  the warehouse. Do not have the consumer write into `warehouse.duckdb`.
- **Canonical schema is JSON-file-driven.** `matchbook_odds_schema.json` is the single
  source of truth; `schema.py` derives the PyArrow `SCHEMA` and dedup field list from
  it, and `MatchbookOddsRecord` (in `models/schemas.py`) mirrors it. Keep all three in
  sync when the field set changes.
- **Additive schema evolution only.** New columns (e.g. `kickoff_ms`) are tolerated by
  `union_by_name=true` in the dbt source; older files read the new column as NULL.
  Removing/retyping a column would break the read.
- **`ingested_at` units.** Stored as epoch milliseconds (int) in the bronze row;
  Arrow casts it to `timestamp[ms, UTC]`. Derived from `timestamp_ns // 1_000_000`
  when present, else wall-clock at receipt.
- **Date partition uses receipt time, not event/kickoff time.** `_write_parquet`
  partitions by the current UTC date at flush time, independent of the tick's own
  timestamp.
- **External Redis dependency.** The consumer depends on the external
  sports-gaming-engine Redis on the `sports-quant` network; this repo does not start
  Redis. If the channel is unreachable the daemon polls without producing data.
- **Standalone daemon, excluded from Dagster jobs.** The consumer is not a Dagster
  asset; it must not be swept into `AssetSelection.all()`-based jobs (it isn't one).
- **dbt asset/selector naming.** `stg_matchbook_odds` lives directly under
  `models/silver/`, so its Dagster asset key is `["silver", "stg_matchbook_odds"]`
  and its dbt selector is `silver.stg_matchbook_odds` (no extra subfolder here, unlike
  `silver/canonical/*`).
- **Migration prerequisite (macOS/Docker).** The upstream `lakehouse_data` volume is
  not directly host-accessible on macOS; extract it via a one-shot `tar` container
  before running the migration script (documented in the script docstring).

## 9. Assumptions

- The upstream publisher emits each odds tick as a single JSON object on the
  `matchbook_odds_stream` channel, with native JSON types (numbers, booleans, null) —
  matching the `_process_json_message` path the run loop uses.
- The dedup field set in `matchbook_odds_schema.json` (`dedup_fields`) is intended to
  capture every economically meaningful state change (price, size, queue depth,
  volume, status); ticks differing only in untracked fields are intentionally
  discarded as redundant.
- 5 000 ticks / 60 seconds are deliberate throughput/latency batching parameters
  rather than incidental constants.
- The "parallel-run phase" (a separate upstream JSONL consumer on the same channel)
  is a transitional state; this Parquet consumer is meant to coexist without
  coordinating with it.
- Partitioning bronze by receipt date (not event date) is acceptable for the bronze
  layer's faithful-capture purpose.

## 10. Open questions

All items are **unverified intent** for a human to confirm; none block implementation
(the feature already ships).

- **Redis source actually wired end-to-end?** Only the bronze/Parquet path is covered
  by tests — `tests/matchbook/test_consumer.py` mocks Redis entirely and exercises
  `_process_json_message`, dedup, flush, schema-cast, SIGTERM, and the validation
  gate. There is no test (and, in this repo, no evidence) that a live
  `matchbook_odds_stream` subscription has been exercised. The live consumption path
  is therefore asserted by construction, not verified.
- **Pub/sub vs streams mismatch.** The run loop uses Redis **pub/sub**
  (`pubsub.subscribe("matchbook_odds_stream")`), but the module docstring and dedup
  notes refer to Redis **streams** (XREAD/XADD) and "channel". A second, unused
  `_process_message`/`_build_dedup_state` code path (expecting string values, the
  XREAD wire format) survives the migration but is not called anywhere. Intended
  transport (pub/sub vs streams) and whether the dead `_process_message` path should
  be removed are unresolved.
- **`matchbook_bronze_dir` setting is unused.** `config.py` exposes a
  `matchbook_bronze_dir` property, but the consumer uses `settings.bronze_dir` and
  appends `matchbook_odds/` itself in `_write_parquet`. Whether the property was meant
  to be the single source of the partition root (and the consumer should use it) is
  unverified.
- **Migration script docstring drift.** The script's docstring still describes the
  destination as `part-<filename>.parquet`, but the code (after the `37aa9c6` fix)
  preserves `src.name` verbatim. The docstring is stale, not the behaviour.
- **Schema `description` mismatch.** `matchbook_odds_schema.json` still labels itself
  "Silver-grade Parquet schema", but the data lands in bronze. Whether the label
  should be corrected is unconfirmed.
- **Retention / compaction.** Whether the many small per-flush Parquet files are meant
  to be compacted, expired, or retained indefinitely is not expressed anywhere.

## 11. Traceability

| Source commit(s) | Behaviour introduced (scenarios) | Spec acceptance criteria |
|------------------|----------------------------------|--------------------------|
| `2f77945` | Migrate ingestor/schema/JSON schema from upstream (foundation for all consumer scenarios) | AC6 (schema shape), foundation for AC1–AC9 |
| `a67a9a6` | Redis host/port + bronze-dir config via pydantic-settings | AC13 |
| `93f44d1` | `MatchbookOddsRecord` Pydantic contract (boundary validation) | AC5, AC6 |
| `cb09e53` | Reroute to bronze path, Pydantic gate, atomic temp-rename write, schema-cast gate, settings-driven entrypoint (Tick dedup, Boundary validation, Buffer flush, Atomic schema-gated write) | AC1, AC2, AC3, AC4, AC5, AC7, AC8 |
| `8aeccac` | `matchbook-ingestor` compose service on external network (base + prod) | AC12 |
| `eba8f84` | `bronze.matchbook_odds` dbt source over Hive glob with `union_by_name` | AC10 |
| `5147116` | `stg_matchbook_odds` silver staging view + not-null tests | AC11 |
| `08ba04a` | One-off bronze migration script (dry-run, idempotent skip, date derivation) | AC14 |
| `ff5f87f` | Consumer unit tests (dedup, flush, empty-buffer, ZSTD path, schema-cast gate, SIGTERM, time-based flush, validation drop) | AC1, AC2, AC4, AC5, AC7, AC8, AC9 |
| `ee6cd94` | Combined/merge commit delivering the end-state of the above (no new behaviour beyond the granular commits) | AC1–AC14 (end-state) |
| `37aa9c6` | Migration script filename/dest-dir bug fixes (preserve `src.name`; dest-dir defaults to `data/bronze`) | AC14 |

> Coverage runs both ways: every source commit's behaviour lands in a scenario/AC
> above, and every AC traces to at least one commit. (Ruff-style commits `4d057e5`,
> `2bda834` carry no behaviour and are intentionally omitted.)
