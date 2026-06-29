---
id: 001-matchbook
title: Matchbook Ingestor Migration
status: draft
created: 2026-06-28
---

# Matchbook Ingestor Migration — Specification

## 1. Outcome Statement

When this work is complete, an operator can:

1. Start the full stack (`docker compose up`) and observe a `matchbook-ingestor` container consuming the `matchbook_odds_stream` Redis channel and writing ZSTD-compressed Parquet files to `data/bronze/matchbook_odds/year=YYYY/month=MM/day=DD/part-{timestamp}.parquet`.
2. Run `dbt build --select stg_matchbook_odds` and have a Silver view over all bronze Matchbook Parquet (including migrated historical data) build successfully, with dbt schema tests passing.
3. Run the one-off migration script to copy data from the `sports-gaming-engine` project's `lakehouse_data` Docker volume into this project's bronze location — with the result being indistinguishable from natively-produced bronze files.
4. Trust that each Parquet flush is validated by Pydantic (per-record) and Pandera (per-frame) before being written, so no unvalidated data ever lands in bronze.
5. Run `pytest` and see unit tests covering dedup logic and flush behaviour pass.

---

## 2. Scope

### In scope

| # | Item |
|---|------|
| 2.1 | Reroute `DirectParquetConsumer._write_parquet` output path from `silver/matchbook_odds/` to `bronze/matchbook_odds/` (Hive-partitioned by date) |
| 2.2 | Remove the hardcoded `/app/data/lake` root; derive the bronze path from `settings.bronze_dir` via two new config fields: `REDIS_HOST` / `REDIS_PORT` and `MATCHBOOK_BRONZE_DIR` (or inherited from `bronze_dir`) |
| 2.3 | Add `REDIS_HOST` and `REDIS_PORT` as typed fields in `config.py` (flush constants remain module-level; see resolved OQ-5) |
| 2.4 | Add Pydantic `MatchbookOddsRecord` model in `models/schemas.py` to validate each tick before it enters the buffer |
| 2.5 | Add a module-level `MATCHBOOK_ODDS_SCHEMA: pa.Schema` constant in the consumer; validate each flush via `table.cast(MATCHBOOK_ODDS_SCHEMA)` — no Pandera (see resolved OQ-4) |
| 2.6 | Add `matchbook-ingestor` as a Docker service in `docker-compose.yml` (base, environment-neutral); point it at Redis and `./data` |
| 2.7 | Update `docker-compose.prod.yml` to extend `matchbook-ingestor` with the OTLP endpoint env var (same pattern as the other three services) |
| 2.8 | Add dbt source entry for `matchbook_odds` in `dbt/data_platform/models/silver/_sources.yml` pointing at the bronze glob |
| 2.9 | Add `stg_matchbook_odds.sql` Silver staging model (view) under `dbt/data_platform/models/silver/` — a minimal faithful projection of bronze, no enrichment |
| 2.10 | Write a one-off migration script `scripts/migrate_matchbook_bronze.py` that copies Parquet files from the `sports-gaming-engine` `lakehouse_data` volume path to this project's bronze location |
| 2.11 | Leave `matchbook_event_link.sql` as an empty typed scaffold (no change); document the justification |
| 2.12 | Unit tests for dedup logic and buffer-flush behaviour under `tests/matchbook/` |

### Explicitly out of scope

- Silver enrichment from Postgres catalogue tables (market/runner names, team names from `matchbook_market_catalogue`, `matchbook_runner_catalogue`, `provider_match_cache`) — this is deferred; the staging model is a faithful projection only
- Canonical link population in `matchbook_event_link.sql` — no event-to-canonical-match mapping data exists yet
- Gold models or downstream publishing assets for Matchbook odds
- Any change to the Kotlin JSONL pipeline or the Redis publisher
- Dagster asset wrapping for the Matchbook daemon (it runs as a plain Docker service, not a Dagster asset)
- OTel tracing inside the daemon process (deferred; spans inside a long-lived non-Dagster process require a different setup)

---

## 3. BDD Scenarios

### Scenario 3.1 — Consumer writes to bronze (not silver)

```
Given  DirectParquetConsumer is instantiated with settings.bronze_dir as its root
When   _flush() is called with a non-empty buffer
Then   the Parquet file is written to
         <bronze_dir>/matchbook_odds/year=YYYY/month=MM/day=DD/part-<timestamp_ms>.parquet
And    no file is created under any path containing "silver"
And    the file uses ZSTD compression
And    the file schema matches the 28-field PyArrow schema from matchbook_odds_schema.json
```

### Scenario 3.2 — Bronze write is validated before landing

```
Given  a batch of ticks has accumulated in the buffer
When   _flush() is called
Then   each tick is validated against MatchbookOddsRecord (Pydantic) before entering the buffer
And    the assembled pa.Table is cast against MATCHBOOK_ODDS_SCHEMA (PyArrow) before pq.write_table
And    if the schema cast fails, no Parquet file is written (atomic write: temp-rename pattern)
And    a validation failure raises an exception (not silent fallback)
```

### Scenario 3.3 — Docker service starts and connects to Redis

```
Given  docker-compose.yml defines a matchbook-ingestor service
And    a Redis service is reachable on the Docker network at redis:6379
When   docker compose up matchbook-ingestor is run
Then   the container starts without error
And    the consumer subscribes to the matchbook_odds_stream channel
And    the service restarts automatically if it crashes (restart: unless-stopped)
And    it writes to /app/data/bronze/matchbook_odds/ (the ./data bind-mount)
```

### Scenario 3.4 — dbt Silver model reads bronze Parquet

```
Given  at least one Parquet file exists under data/bronze/matchbook_odds/**/*.parquet
And    the dbt source matchbook_odds is registered in _sources.yml pointing at that glob
When   dbt build --select stg_matchbook_odds is run
Then   the model builds without error
And    the resulting relation contains all 28 columns from the bronze schema
And    dbt schema tests (not_null on event_id, market_id, runner_id, ingested_at) pass
And    union_by_name=true is used in the source read so old files lacking kickoff_ms are tolerated
```

### Scenario 3.5 — Migration script copies historical data to bronze

```
Given  the sports-gaming-engine lakehouse_data Docker volume is mounted or its path is accessible
And    Parquet files exist at <source_root>/silver/matchbook_odds/**/*.parquet
When   python scripts/migrate_matchbook_bronze.py --source <source_root> --dest data/bronze is run
Then   every source Parquet file is copied to
         data/bronze/matchbook_odds/year=YYYY/month=MM/day=DD/part-<original_filename>
         (preserving the existing date-partition structure where present, or deriving date from ingested_at otherwise)
And    no Parquet file is rewritten or schema-converted (copy-only; the 28-field schema is already bronze-compatible)
And    already-present destination files are skipped (idempotent)
And    the script prints a summary: N files copied, M skipped
And    a dry-run flag (--dry-run) prints what would be copied without writing
```

### Scenario 3.6 — Dedup logic prevents duplicate ticks

```
Given  the consumer has processed a tick for (event_id=1, market_id=10, runner_id=100)
And    the tick had best_back_price=2.0, best_lay_price=2.1 (and other dedup fields)
When   an identical tick arrives (all 12 dedup fields unchanged)
Then   the tick is NOT added to the buffer
And    the dedup dict is NOT updated

When   a tick arrives with best_back_price changed to 2.05 (any dedup field changed)
Then   the tick IS added to the buffer
And    the dedup dict is updated to the new state
```

### Scenario 3.7 — Graceful shutdown flushes buffer

```
Given  the consumer is running and the buffer contains N > 0 ticks
When   a SIGTERM or SIGINT signal is received
Then   _running is set to False
And    the main loop exits after the current iteration
And    pubsub.close() is called
And    _flush() is called and writes the remaining N ticks to a Parquet file
And    the process exits cleanly (no ticks lost)
```

### Scenario 3.8 — Time-based flush fires when buffer is below threshold

```
Given  the consumer buffer contains fewer than MATCHBOOK_FLUSH_TICK_THRESHOLD ticks
And    MATCHBOOK_FLUSH_INTERVAL_S seconds have elapsed since the last flush
When   the main loop evaluates flush conditions
Then   _flush() is called
And    the buffer is drained to a Parquet file

Given  the buffer is empty
And    MATCHBOOK_FLUSH_INTERVAL_S seconds have elapsed
When   the main loop evaluates flush conditions
Then   _flush() is NOT called (no empty Parquet files are written)
```

---

## 4. Acceptance Criteria

| ID | Criterion | Pass condition |
|----|-----------|----------------|
| AC-01 | Bronze output path | `_write_parquet` produces files under `{bronze_dir}/matchbook_odds/year=…/month=…/day=…/` — verified by unit test asserting the path and by absence of any `silver/` path in the output |
| AC-02 | No silver path | Grep of the ingestor package finds no hardcoded `silver` in the Parquet output path after the change |
| AC-03 | ZSTD compression | Written Parquet metadata reports `ZSTD` compression (checkable via `pq.read_metadata(path).row_group(0).column(0).compression`) |
| AC-04 | Schema fidelity | Every Parquet file produced by the consumer passes `pa.Schema.equals(SCHEMA)` on its schema |
| AC-05 | Pydantic validation | A tick with a missing `event_id`, `market_id`, or `runner_id` is dropped with a warning log, not written |
| AC-06 | Pandera validation | A frame with a non-nullable column forced to None causes the flush to raise before `pq.write_table` is called; no partial Parquet file is left on disk |
| AC-07 | Atomic write | Files are written to a temp path then renamed; a killed flush leaves no zero-byte or partial Parquet at the final path |
| AC-08 | Config fields | `config.py` exposes `redis_host: str`, `redis_port: int`, and the consumer reads these; no ad-hoc `os.getenv` in the daemon |
| AC-09 | Docker service | `docker compose config` shows a `matchbook-ingestor` service; `docker compose up matchbook-ingestor` starts without error when Redis is available |
| AC-10 | dbt source registered | `dbt/data_platform/models/silver/_sources.yml` contains a `matchbook_odds` table entry with `external_location` pointing at the bronze glob |
| AC-11 | Silver model builds | `dbt build --select stg_matchbook_odds` exits 0 when at least one bronze file exists |
| AC-12 | Silver schema tests | `not_null` tests on `event_id`, `market_id`, `runner_id`, `ingested_at` pass |
| AC-13 | Migration idempotent | Running `migrate_matchbook_bronze.py` twice copies no files on the second run |
| AC-14 | Migration dry-run | `--dry-run` prints a plan and exits 0; no files are written |
| AC-15 | Dedup correctness | Unit test: sending the same tick twice results in buffer length 1; sending an updated tick results in buffer length 2 |
| AC-16 | Flush on SIGTERM | Unit test: consumer with 3 buffered ticks, `_handle_signal` called, then `run()` exits — exactly one Parquet file is written containing 3 rows |
| AC-17 | No empty flush | Unit test: `_flush()` called on empty buffer writes nothing (no file created) |
| AC-18 | Time-based flush | Unit test: mock `time.monotonic` to advance by `flush_interval + 1`; verify `_flush()` is called even when buffer is below the tick threshold |
| AC-19 | `matchbook_event_link.sql` unchanged | The scaffold remains an empty typed select; no data is populated (no `event_id` → canonical `match_id` mapping exists) |
| AC-20 | No second DuckDB writer | The daemon and migration script never open `warehouse.duckdb`; they write only Parquet files to `data/bronze/` |

---

## 5. Constraints

These constraints are inherited from the project architecture and MUST NOT be violated:

| Constraint | Source | Implication for this feature |
|-----------|--------|------------------------------|
| **DuckDB is single-writer** | CLAUDE.md | The daemon and migration script write Parquet only; they never open `warehouse.duckdb` |
| **No `from __future__ import annotations` in Dagster asset modules** | CLAUDE.md | Not applicable here (daemon is not a Dagster asset), but if any shim Dagster asset is ever added, this rule applies |
| **Config via pydantic-settings only** | ARCHITECTURE.md §5 | All new settings (`redis_host`, `redis_port`, flush thresholds) go in `config.py` as typed fields; no `os.getenv` scattered in daemon code |
| **`pathlib.Path` for filesystem paths** | CLAUDE.md (Python conventions) | `_write_parquet` must use `Path` objects from `settings.bronze_dir`, not string concatenation with `os.path.join` |
| **Validate at the boundary** | ARCHITECTURE.md §3 rule 2 | Pydantic (record) → Pandera (frame) validation must happen before `pq.write_table`, matching the pattern in `assets/bronze.py` |
| **Atomic temp-file + rename write** | CLAUDE.md (per-file failure isolation) | `_write_parquet` writes to a `.tmp` file then renames; no partial file is left if the process is killed during write |
| **Bronze layer is the only network edge** | ARCHITECTURE.md §3 rule 1 | The daemon reads Redis (a network edge); it is therefore correctly positioned as a bronze-layer process |
| **`docker-compose.yml` is environment-neutral** | CLAUDE.md (Compose overlay design) | `matchbook-ingestor` in the base file must set no OTLP endpoint and join no SigNoz network; those come from the overlay |
| **No Postgres catalogue joins in the staging model** | Scope | `stg_matchbook_odds.sql` is a faithful projection of bronze only; enrichment from `matchbook_market_catalogue` etc. is deferred |
| **`AssetSelection.all()` exclusion** | CLAUDE.md | If a Dagster asset for Matchbook is ever added, it must be excluded from `medallion_job` (not applicable in this feature; daemon is a Docker service) |

---

## 6. Implementation Notes

### 6.1 Path change in `direct_parquet_consumer.py`

Current `_write_parquet`:
```python
dest_dir = os.path.join(lake_root, "silver", "matchbook_odds", ...)
```

Target:
```python
dest_dir = settings.bronze_dir / "matchbook_odds" / f"year={now.year}" / f"month={now.month:02d}" / f"day={now.day:02d}"
```

The `lake_root` constructor parameter should be replaced with a `bronze_dir: Path` parameter (defaulting to `settings.bronze_dir`). The entrypoint `__main__` block should read from `settings` instead of argparse env fallbacks.

### 6.2 New `config.py` fields

```python
redis_host: str = "redis"
redis_port: int = 6379
matchbook_flush_tick_threshold: int = 5_000
matchbook_flush_interval_s: int = 60
```

`bronze_dir` already exists as a property (`data_dir / "bronze"`); no new path field is needed for the Matchbook subdirectory — the consumer appends `matchbook_odds/` itself.

### 6.3 `matchbook-ingestor` Docker service

Add to `docker-compose.yml` under `services:`, inheriting the `*app` anchor:

```yaml
matchbook-ingestor:
  <<: *app
  command: python -m data_platform.matchbook.ingestor.direct_parquet_consumer
  environment:
    REDIS_HOST: redis
    REDIS_PORT: 6379
  networks:
    - sports-quant
```

Redis is provided by the external `sports-gaming-engine` stack. Do NOT add a `redis` service to this project. The `sports-quant` network must be declared as external at the top-level `networks:` key:

```yaml
networks:
  sports-quant:
    external: true
```

The prod overlay needs to extend `matchbook-ingestor` with the OTLP endpoint:
```yaml
# docker-compose.prod.yml
services:
  matchbook-ingestor:
    <<: *prod-app
```

### 6.4 dbt source + Silver staging model

`_sources.yml` addition:
```yaml
- name: matchbook_odds
  description: "Matchbook odds tick data (bronze Parquet, Hive-partitioned by date)"
  meta:
    external_location: "read_parquet('{{ env_var('DATA_DIR', '/app/data') }}/bronze/matchbook_odds/**/*.parquet', union_by_name=true)"
```

`stg_matchbook_odds.sql` (view, faithful projection only):
```sql
select
    event_id,
    market_id,
    runner_id,
    ingested_at,
    sport_id,
    market_type,
    market_status,
    in_running,
    best_back_price,
    best_back_available,
    best_lay_price,
    best_lay_available,
    back_price_2,
    back_available_2,
    back_price_3,
    back_available_3,
    lay_price_2,
    lay_available_2,
    lay_price_3,
    lay_available_3,
    back_depth,
    lay_depth,
    wom,
    market_volume,
    runner_volume,
    handicap_line,
    event_participant_id,
    kickoff_ms
from {{ source('bronze', 'matchbook_odds') }}
```

### 6.5 Pydantic model in `models/schemas.py`

A `MatchbookOddsRecord` model should mirror the 28 JSON schema fields, with `event_id`, `market_id`, `runner_id` as required `int` fields and all others optional/nullable. The consumer calls `MatchbookOddsRecord.model_validate(msg)` (or equivalent) before building the buffer dict; a `ValidationError` causes the tick to be dropped with a warning log (matching the existing malformed-ID handling pattern).

### 6.6 PyArrow schema validation (replaces Pandera for Matchbook)

A module-level `MATCHBOOK_ODDS_SCHEMA: pa.Schema` constant in `direct_parquet_consumer.py` defines the 28-column Arrow schema (types and nullability). Before each flush, `table.cast(MATCHBOOK_ODDS_SCHEMA)` is called on the assembled `pa.Table`. If it raises `pa.lib.ArrowInvalid` or `pa.lib.ArrowTypeError`, the flush aborts and no Parquet file is written. No Pandera dependency is added for this consumer and `models/validation.py` is not modified. Key nullability constraints enforced by the schema:
- `event_id`, `market_id`, `runner_id`, `in_running`, `ingested_at`: non-nullable
- All price/volume columns: nullable `float64`

### 6.7 Migration script `scripts/migrate_matchbook_bronze.py`

- Accepts `--source-dir` (path to the locally accessible `sports-gaming-engine` lake root) and `--dest` (this project's `data/` directory). On macOS the volume is not host-accessible; the `--help` output documents the required extraction step: `docker run --rm -v lakehouse_data:/data -v $(pwd):/out alpine tar cf /out/lake.tar -C /data .` followed by local extraction before running this script.
- Globs `<source>/silver/matchbook_odds/**/*.parquet`
- For each file, reads the Hive partition tokens from the path (`year=`, `month=`, `day=`); if absent, reads `ingested_at` from the Parquet metadata min to derive the date
- Writes to `<dest>/bronze/matchbook_odds/year=.../month=.../day=.../part-<original_stem>.parquet`
- Skips if destination already exists
- Uses `shutil.copy2` (preserve timestamps); does NOT re-encode or rewrite the Parquet (the 28-field schema is already bronze-compatible)
- Supports `--dry-run`

**Schema compatibility note**: The source files at `sports-gaming-engine/lakehouse_data/.../silver/matchbook_odds/` were written by the same `DirectParquetConsumer` with the same PyArrow schema. They are physically identical in format to what the rerouted consumer will produce in bronze. No schema conversion is needed. Older files pre-dating the `kickoff_ms` field will have that column absent, which `union_by_name=true` in dbt handles via NULL fill.

### 6.8 `matchbook_event_link.sql` — stays as empty scaffold

**Justification**: The link from a Matchbook `event_id` to a canonical `match_id` requires either a manual mapping table or an automated fuzzy-match process (comparing event names / kickoff times from `provider_match_cache` with `canonical.match`). Neither data source (the catalogue Postgres tables) nor the matching logic is within scope of this feature. The scaffold remains:
```sql
select
    cast(null as varchar) as link_id,
    cast(null as varchar) as match_id,
    cast(null as varchar) as matchbook_event_id
limit 0
```
Population is deferred to a future canonical-linking feature.

---

## 7. Traceability Table

| BDD Scenario | Acceptance Criteria |
|---|---|
| 3.1 Consumer writes to bronze | AC-01, AC-02, AC-03, AC-04 |
| 3.2 Bronze write is validated | AC-05, AC-06, AC-07 |
| 3.3 Docker service starts | AC-08, AC-09 |
| 3.4 dbt Silver model reads bronze | AC-10, AC-11, AC-12 |
| 3.5 Migration script | AC-13, AC-14, AC-20 |
| 3.6 Dedup logic | AC-15 |
| 3.7 Graceful shutdown flushes | AC-16 |
| 3.8 Time-based flush | AC-17, AC-18 |
| (implicit) Scaffold unchanged | AC-19 |
| (implicit) No DuckDB writes | AC-20 |

---

## 8. Open Questions

All questions are resolved. Resolutions are incorporated into the relevant sections above and summarised here for traceability.

---

**OQ-1 — Redis service in `docker-compose.yml`** ✅ RESOLVED

**Resolution:** Redis comes from the external `sports-gaming-engine` stack. Do NOT add a `redis` service to this project's `docker-compose.yml`. The `matchbook-ingestor` service connects to Redis over the external `sports-quant` Docker network (already defined in `sports-gaming-engine`). The compose service must declare `networks: [sports-quant]` and the network must be declared as `external: true` at the top-level `networks:` key.

_Implications for §6.3:_ Remove the `depends_on: [redis]` entry and the inline `redis` service stub. Add `networks: [sports-quant]` to the `matchbook-ingestor` service block and add the following to the top-level `networks:` section:
```yaml
networks:
  sports-quant:
    external: true
```

---

**OQ-2 — `__main__` entrypoint vs. a dedicated script** ✅ RESOLVED

**Resolution:** Use `python -m data_platform.matchbook.ingestor.direct_parquet_consumer` as the Docker `command:`. This matches the existing pattern from `sports-gaming-engine` (`python -m ingestor.direct_parquet_consumer`), adapted to this project's module path. No dedicated wrapper script or `[project.scripts]` entry is needed.

---

**OQ-3 — Migration script source path access** ✅ RESOLVED

**Resolution:** The migration script accepts a `--source-dir` CLI argument pointing to a locally accessible directory. On macOS (Docker Desktop), the `lakehouse_data` volume is not directly accessible on the host filesystem. The operator must first extract files using:
```bash
docker run --rm \
  -v lakehouse_data:/data \
  -v $(pwd):/out \
  alpine tar cf /out/lake.tar -C /data .
```
then extract the archive locally before running the script. The migration script's `--help` output must document this extraction step.

---

**OQ-4 — Pandera/PyArrow validation approach** ✅ RESOLVED

**Resolution:** Use PyArrow schema validation — no Pandas roundtrip. Pandera is NOT used for the Matchbook consumer; it is not a DataFrame workflow. The bronze write gate is: `table.cast(SCHEMA)` succeeds (which validates column types and nullability); if it raises, the batch is dropped and no Parquet file is written. This is implemented directly in `_flush()` before the atomic temp-file write.

_Implication:_ Scope item 2.5 (Pandera schema in `validation.py`) is replaced by a PyArrow schema cast check inline in the consumer. No new entry in `models/validation.py` is added for Matchbook. The `matchbook_odds_bronze_schema` referenced in §6.6 is a `pa.schema(...)` object, not a Pandera schema.

_Update §6.6:_ Replace the Pandera description with: "A module-level `MATCHBOOK_ODDS_SCHEMA: pa.Schema` constant defines the 28-column Arrow schema. Before each flush, `pa.Table.cast(MATCHBOOK_ODDS_SCHEMA)` is called; a `pa.lib.ArrowInvalid` or `pa.lib.ArrowTypeError` causes the flush to abort without writing."

---

**OQ-5 — Flush constants: config.py vs. module-level constants** ✅ RESOLVED

**Resolution:** Leave `FLUSH_TICK_THRESHOLD = 5_000` and `FLUSH_INTERVAL_S = 60` as module-level constants in `direct_parquet_consumer.py`. They are not added to `config.py`. Operator-level tuning via env vars is not a real requirement for these values.

_Implication:_ Scope item 2.3 should not include `MATCHBOOK_FLUSH_TICK_THRESHOLD` / `MATCHBOOK_FLUSH_INTERVAL_S`; only `REDIS_HOST` and `REDIS_PORT` are added to `config.py`.

---

**OQ-6 — `stg_matchbook_odds` materialization** ✅ RESOLVED

**Resolution:** Use `view` — consistent with all other staging models in this project. This is the correct choice for a faithful bronze projection at the staging layer.

---

**OQ-7 — `ingested_at` type: int in Pydantic, timestamp in Arrow** ✅ RESOLVED

**Resolution:** The consumer sets `ingested_at = int(time.time() * 1000)` (Unix epoch milliseconds). The Pydantic model (`MatchbookOddsRecord`) accepts `int` for `ingested_at`. The PyArrow table is built by casting the integer column to `pa.timestamp("ms", tz="UTC")` in `_rows_to_arrow`. This is the intended behaviour; no change to this flow is required.
