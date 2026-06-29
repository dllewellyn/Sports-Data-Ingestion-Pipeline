---
id: 001-matchbook
title: Matchbook Ingestor Migration — Implementation Plan
status: approved
spec: specs/001-matchbook-ingestor-migration-specification.md
created: 2026-06-28
---

# Matchbook Ingestor Migration — Implementation Plan

## Convention Audit

Before any task begins, confirm the governing convention for each artifact touched exists and has no gaps:

| Artifact type | Convention source | Status |
|---|---|---|
| Pydantic model (new field set) | CLAUDE.md "Validate at boundaries with Pydantic v2"; `models/schemas.py` existing pattern | OK — pattern established by `MainMatchRecord`/`ExtraMatchRecord` |
| `config.py` fields | CLAUDE.md "Config comes from pydantic-settings, never ad-hoc os.getenv" | OK — `Settings` class with `SettingsConfigDict` already in place |
| dbt external source | `_sources.yml` existing `users` table with `external_location` meta | OK — pattern established; `dbt-duckdb` reads the `meta.external_location` key |
| dbt view (silver staging) | `dbt_project.yml` `silver: +materialized: view` | OK — `stg_users` is the precedent; all silver models are views by project config |
| Docker service (base, env-neutral) | CLAUDE.md "docker-compose.yml is environment-NEUTRAL"; `docker-compose.yml` `x-app: &app` anchor | OK — three existing services consume the `*app` anchor |
| Docker prod overlay | CLAUDE.md "prod → docker-compose.prod.yml"; `x-prod-app: &prod-app` anchor already defined | OK — pattern is `<<: *prod-app` under each service |
| pytest unit tests | `pyproject.toml` `[tool.pytest.ini_options]`; `tests/football/` layout with `conftest.py` | OK — importlib mode, `pythonpath = ["src"]`, no `__init__.py` in test dirs |
| Migration script (CLI) | CLAUDE.md "Use pathlib.Path for filesystem paths"; "pydantic-settings only" (N/A for a one-off script) | OK — no config.py usage required in a one-off CLI script; `pathlib.Path` + `argparse` is the convention |
| Atomic Parquet write (temp+rename) | CLAUDE.md "Atomic temp-file + rename write (football per-file failure isolation)" | OK — same pattern required; `_write_parquet` will mirror the football ingestor |
| PyArrow schema cast as frame gate | spec §6.6 (replaces Pandera for this consumer); `schema.py` + `matchbook_odds_schema.json` | OK — SCHEMA already loaded from JSON; cast approach consistent with spec OQ-4 |

No gaps found. All conventions have an established precedent.

---

## BDD Scenario Coverage

Maps each BDD scenario from the specification (§3) to the plan task(s) that implement it.

| BDD Scenario | Tasks |
|---|---|
| 3.1 Consumer writes to bronze | TASK-01, TASK-03, TASK-08 (Test 4) |
| 3.2 Bronze write validated before landing | TASK-02, TASK-03, TASK-08 (Test 5, 8) |
| 3.3 Docker service starts and connects to Redis | TASK-01, TASK-04 |
| 3.4 dbt Silver model reads bronze Parquet | TASK-05, TASK-06 |
| 3.5 Migration script copies historical data | TASK-07 |
| 3.6 Dedup prevents duplicate ticks | TASK-08 (Tests 1, 2) |
| 3.7 SIGTERM flushes buffer before exit | TASK-08 (Test 6) |
| 3.8 Time-based flush fires below tick threshold | TASK-08 (Tests 3, 7) |

---

## Dependency Graph

```
TASK-01 (config.py)
    └── TASK-03 (consumer fix)
TASK-02 (MatchbookOddsRecord)
    └── TASK-03 (consumer fix)
TASK-03 (consumer fix)
    └── TASK-04 (Docker wiring)   [can start after TASK-01]
    └── TASK-08 (tests)
TASK-05 (dbt source)
    └── TASK-06 (stg_matchbook_odds.sql)
TASK-07 (migration script) — independent of all others
TASK-08 (tests) — after TASK-03
```

TASK-04, TASK-05, TASK-06, and TASK-07 are independent of each other once TASK-01–03 are done.

---

## Phase 1 — Config & Schema

### TASK-01 — Add Redis fields to `config.py`

**Files to change:** `src/data_platform/config.py`

**Exact changes:**

Add four new typed fields to the `Settings` class, after the `football_*` block and before `data_dir`:

```python
# Matchbook Redis ingestion
redis_host: str = "redis"
redis_port: int = 6379
matchbook_flush_tick_threshold: int = 5_000
matchbook_flush_interval_s: int = 60
```

Wait — per spec OQ-5 (resolved), `MATCHBOOK_FLUSH_TICK_THRESHOLD` and `MATCHBOOK_FLUSH_INTERVAL_S` remain module-level constants in the consumer. Only `redis_host` and `redis_port` go into `config.py`. So add only:

```python
# Matchbook Redis ingestion
redis_host: str = "redis"
redis_port: int = 6379
```

No `@property` is needed for the matchbook bronze subdirectory — the consumer appends `matchbook_odds/` itself using `settings.bronze_dir / "matchbook_odds"`.

**Self-review checkpoint:**
- `from data_platform.config import settings; settings.redis_host` returns `"redis"` without error.
- `settings.redis_port` returns `6379` as `int`.
- `settings.bronze_dir` still works (existing property untouched).
- `ruff check src/data_platform/config.py` passes with no findings.

**Red test (before this task):**
```python
from data_platform.config import settings
settings.redis_host   # AttributeError: 'Settings' object has no attribute 'redis_host'
```

**Test facility:** Manual Python REPL import check; also asserted transitively by TASK-03 once the consumer reads from `settings`.

---

### TASK-02 — Add `MatchbookOddsRecord` to `models/schemas.py`

**Files to change:** `src/data_platform/models/schemas.py`

**Exact changes:**

Append a new Pydantic model at the end of the file (before `__all__`). The model mirrors the 28 fields from `matchbook_odds_schema.json`. Fields `event_id`, `market_id`, `runner_id`, and `ingested_at` are required (non-optional); all others are `int | None` or `float | None` or `str | None` or `bool | None` as appropriate. `ingested_at` is `int` in Pydantic (the consumer stores epoch-ms before Arrow casts it to `timestamp[ms, UTC]`).

```python
class MatchbookOddsRecord(BaseModel):
    """One Matchbook odds tick — validated at the Redis pub/sub boundary.

    Required fields (non-nullable in bronze): event_id, market_id, runner_id,
    ingested_at. All price/volume/depth fields are nullable (may be absent).
    ingested_at is epoch milliseconds (int); Arrow will cast to timestamp[ms, UTC].
    """

    model_config = ConfigDict(extra="ignore")

    event_id: int
    market_id: int
    runner_id: int
    ingested_at: int
    sport_id: int | None = None
    market_type: str | None = None
    market_status: str | None = None
    in_running: bool
    best_back_price: float | None = None
    best_back_available: float | None = None
    best_lay_price: float | None = None
    best_lay_available: float | None = None
    back_price_2: float | None = None
    back_available_2: float | None = None
    back_price_3: float | None = None
    back_available_3: float | None = None
    lay_price_2: float | None = None
    lay_available_2: float | None = None
    lay_price_3: float | None = None
    lay_available_3: float | None = None
    back_depth: float | None = None
    lay_depth: float | None = None
    wom: float | None = None
    market_volume: float | None = None
    runner_volume: float | None = None
    handicap_line: float | None = None
    event_participant_id: int | None = None
    kickoff_ms: int | None = None
```

Add `"MatchbookOddsRecord"` to the `__all__` list at the bottom.

Note: `in_running` is listed as `nullable: false` in the schema JSON but the consumer sets it as `bool(msg.get("in_running"))` — which defaults to `False` when absent. Keep it as `bool` (required) in the Pydantic model to mirror the non-nullable constraint; if the field is absent from a message, `_process_json_message` already coerces it to `False` before building the buffer dict. The consumer creates the buffer dict first, then validates it; the field will always be present when validated.

**Self-review checkpoint:**
- `from data_platform.models.schemas import MatchbookOddsRecord` imports without error.
- `MatchbookOddsRecord(event_id=1, market_id=2, runner_id=3, ingested_at=1000, in_running=False)` succeeds.
- `MatchbookOddsRecord(market_id=2, runner_id=3, ingested_at=1000, in_running=False)` raises `ValidationError` (missing `event_id`).
- `ruff check src/data_platform/models/schemas.py` passes.

**Red test (before this task):**
```python
from data_platform.models.schemas import MatchbookOddsRecord
# ImportError: cannot import name 'MatchbookOddsRecord' from 'data_platform.models.schemas'
```

**Test facility:** Direct pytest assertion in TASK-08; importable from day 1 for TASK-03 wiring.

---

## Phase 2 — Consumer Fix

### TASK-03 — Reroute and validate `direct_parquet_consumer.py`

**Files to change:** `src/data_platform/matchbook/ingestor/direct_parquet_consumer.py`

This task has five distinct sub-changes. Apply them in the order listed.

#### 3a — Remove the fallback import block and add a settings import

**Remove** the `try/except ImportError` block at the top:
```python
try:
    from .schema import DEDUP_FIELDS as _DEDUP_FIELDS
    from .schema import SCHEMA
except ImportError:
    # Fallback for direct execution: python -m ingestor.direct_parquet_consumer
    from schema import DEDUP_FIELDS as _DEDUP_FIELDS  # type: ignore[no-redef]
    from schema import SCHEMA  # type: ignore[no-redef]
```

**Replace with** a clean relative import (the module is now always run as `python -m data_platform.matchbook.ingestor.direct_parquet_consumer`):
```python
from .schema import DEDUP_FIELDS as _DEDUP_FIELDS
from .schema import SCHEMA
```

Also **add** these imports near the top of the file (after the stdlib/third-party block):
```python
from pathlib import Path

from data_platform.config import settings
from data_platform.models.schemas import MatchbookOddsRecord
```

Remove `import os` if it becomes unused after the path changes below (check — `os` is used in the old `_write_parquet`; after the rewrite, it will no longer be needed there, but it may still be needed in `__main__`. After the `__main__` changes in 3e, `os` should be fully removed).

#### 3b — Add Pydantic validation to `_process_json_message`

In `_process_json_message`, after the buffer dict is assembled and before `self._buffer.append(...)`, insert a Pydantic validation step. The buffer dict already has `ingested_at` computed and `in_running` coerced to `bool`, so the record is complete at this point.

The pattern mirrors the existing malformed-ID handling:
```python
try:
    MatchbookOddsRecord.model_validate(row)
except ValidationError:
    logger.warning("Dropping tick that failed schema validation: event_id=%s market_id=%s runner_id=%s", event_id, market_id, runner_id)
    return
```

Add `from pydantic import ValidationError` to the imports (pydantic is already a project dependency).

The buffer dict variable should be named `row` (or extracted to a local) so it can be passed to `model_validate` before the `self._buffer.append(row)` call. Currently the dict is passed directly to `append`; refactor to:
```python
row = { ... }  # existing dict literal
try:
    MatchbookOddsRecord.model_validate(row)
except ValidationError:
    logger.warning("Dropping tick that failed schema validation: ...")
    return
self._buffer.append(row)
```

#### 3c — Rewrite `_write_parquet` to use `bronze_dir` and `pathlib.Path`

**Replace** the entire `_write_parquet` standalone function:

```python
def _write_parquet(table: pa.Table, lake_root: str) -> None:
    now = datetime.now(tz=timezone.utc)
    dest_dir = os.path.join(
        lake_root, "silver", "matchbook_odds",
        f"year={now.year}",
        f"month={now.month:02d}",
        f"day={now.day:02d}",
    )
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, f"part-{int(time.time() * 1000)}.parquet")
    pq.write_table(table, path, compression="zstd")
```

**With:**
```python
def _write_parquet(table: pa.Table, bronze_dir: Path) -> None:
    now = datetime.now(tz=timezone.utc)
    dest_dir = (
        bronze_dir
        / "matchbook_odds"
        / f"year={now.year}"
        / f"month={now.month:02d}"
        / f"day={now.day:02d}"
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / f"part-{int(time.time() * 1000)}.parquet.tmp"
    try:
        table.cast(SCHEMA)
    except (pa.lib.ArrowInvalid, pa.lib.ArrowTypeError):
        logger.warning("Schema cast failed — dropping batch of %d rows", len(table))
        return
    pq.write_table(table, tmp, compression="zstd")
    tmp.rename(tmp.with_suffix(""))  # atomic: .parquet.tmp -> .parquet
```

Note: `tmp.with_suffix("")` removes the last suffix (`.tmp`), leaving `.parquet`. This is the correct atomic rename pattern.

#### 3d — Update `DirectParquetConsumer.__init__` and `_flush`

In `__init__`, replace the `lake_root` parameter with `bronze_dir`:

```python
def __init__(
    self,
    redis_host: str | None = None,
    redis_port: int | None = None,
    bronze_dir: Path | None = None,
) -> None:
    _host = redis_host if redis_host is not None else settings.redis_host
    _port = redis_port if redis_port is not None else settings.redis_port
    self._redis = redis.Redis(host=_host, port=_port, decode_responses=True)
    self._bronze_dir: Path = bronze_dir if bronze_dir is not None else settings.bronze_dir
    self._buffer: list[dict[str, Any]] = []
    self._dedup: dict[tuple[int, int, int], tuple] = {}
    self._last_flush = time.monotonic()
    self._running = True

    signal.signal(signal.SIGTERM, self._handle_signal)
    signal.signal(signal.SIGINT, self._handle_signal)
```

Keeping `redis_host`/`redis_port` as optional parameters (defaulting to `settings`) makes the class testable without patching global config.

Update `_flush` to pass `self._bronze_dir` instead of `self._lake_root`:
```python
_write_parquet(table, self._bronze_dir)
```

Update `run()` log line from `lake_root` to `bronze_dir`:
```python
logger.info("Starting Parquet consumer", extra={"bronze_dir": str(self._bronze_dir)})
```

#### 3e — Update the `__main__` block

Replace the argparse-based `__main__` block with a lean block that reads from `settings`:

```python
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    DirectParquetConsumer().run()
```

The Docker `command` uses `python -m data_platform.matchbook.ingestor.direct_parquet_consumer` which triggers `__main__`. `settings` reads `REDIS_HOST`/`REDIS_PORT` from the environment (set by Docker compose), and `settings.bronze_dir` resolves via `DATA_DIR` (also set by compose). No argparse needed.

**Self-review checkpoint:**
- `grep -r "silver" src/data_platform/matchbook/` finds no output path references to `"silver"`.
- `grep -r "lake_root\|LAKE_ROOT\|/app/data/lake" src/data_platform/matchbook/` finds nothing.
- `grep -r "os.path.join\|os.makedirs" src/data_platform/matchbook/ingestor/direct_parquet_consumer.py` finds nothing (all replaced by `pathlib`).
- `grep -r "os.getenv" src/data_platform/matchbook/ingestor/direct_parquet_consumer.py` finds nothing.
- `ruff check src/data_platform/matchbook/` passes with no findings.
- `ruff format src/data_platform/matchbook/` produces no diff.
- Unit tests from TASK-08 pass.

**Red test (before this task):**
AC-01: `DirectParquetConsumer(bronze_dir=tmp_path)._flush()` after buffering a tick — the Parquet file lands under a path containing `"silver"` instead of the bronze partition.
AC-02: `grep -r "silver" src/data_platform/matchbook/ingestor/direct_parquet_consumer.py` returns a match.
AC-08: `DirectParquetConsumer()` calls `os.getenv("REDIS_HOST")` instead of `settings.redis_host`.

**Test facility:** pytest TASK-08; `ruff check`; manual grep.

---

## Phase 3 — Docker Wiring

### TASK-04 — Add `matchbook-ingestor` to Docker Compose files

**Files to change:** `docker-compose.yml`, `docker-compose.prod.yml`

#### 4a — `docker-compose.yml` base

**Add** a new service after `jupyter:` and before `volumes:`:

```yaml
  matchbook-ingestor:
    <<: *app
    command: python -m data_platform.matchbook.ingestor.direct_parquet_consumer
    environment:
      REDIS_HOST: ${REDIS_HOST:-redis}
      REDIS_PORT: ${REDIS_PORT:-6379}
    networks:
      - sports-quant
    restart: unless-stopped
```

Note: The `*app` anchor already includes `restart: unless-stopped`, but the service-level key overrides the anchor cleanly; leave it explicit for clarity.

The `*app` anchor does NOT set a `networks:` key, so adding `networks: [sports-quant]` here is an addition, not an override. The other three services (`dagster-webserver`, `dagster-daemon`, `jupyter`) gain no network change — they do not need to reach Redis.

**Add** to the top-level `networks:` block (currently absent in the base compose — the existing file has only a `volumes:` block at the bottom):

```yaml
networks:
  sports-quant:
    external: true
```

The `volumes:` block already exists; no change needed there. The base `*app` anchor mounts `./data:/app/data` which covers bronze output — no additional volume mount is required.

#### 4b — `docker-compose.prod.yml` overlay

**Add** `matchbook-ingestor` to the `services:` block in the prod overlay, following the exact same pattern as the other three services:

```yaml
  matchbook-ingestor:
    <<: *prod-app
```

This extends the service with `OTEL_EXPORTER_OTLP_ENDPOINT` from the `*prod-app` anchor. No other prod-specific overrides are needed.

**Self-review checkpoint:**
- `docker compose config` (from the repo root with a valid `.env`) shows a `matchbook-ingestor` service.
- `docker compose config` shows `networks: sports-quant: external: true` in the networks section.
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` shows `matchbook-ingestor` with the `OTEL_EXPORTER_OTLP_ENDPOINT` environment var.
- The `dagster-webserver`, `dagster-daemon`, and `jupyter` services remain unchanged (no `networks:` key added to them).

**Red test (before this task):**
```bash
docker compose config | grep matchbook-ingestor
# (no output — service doesn't exist yet)
```

**Test facility:** `docker compose config` (dry-run, no containers started); AC-09.

---

## Phase 4 — dbt Silver

### TASK-05 — Add `matchbook_odds` source to `_sources.yml`

**Files to change:** `dbt/data_platform/models/silver/_sources.yml`

**Exact changes:**

Append a new table entry under the existing `bronze` source. The file currently has only `users`. Add after the `users` table:

```yaml
      - name: matchbook_odds
        description: "Matchbook odds tick data (bronze Parquet, Hive-partitioned by date). Written by the matchbook-ingestor Docker service."
        meta:
          external_location: "read_parquet('{{ env_var(''DATA_DIR'', ''/app/data'') }}/bronze/matchbook_odds/**/*.parquet', union_by_name=true)"
        columns:
          - name: event_id
            description: "Matchbook exchange event ID"
          - name: market_id
            description: "Matchbook market ID"
          - name: runner_id
            description: "Matchbook runner/selection ID"
          - name: ingested_at
            description: "Tick capture time (epoch ms, cast to timestamp[ms, UTC] by Arrow)"
          - name: sport_id
          - name: market_type
          - name: market_status
          - name: in_running
          - name: best_back_price
          - name: best_back_available
          - name: best_lay_price
          - name: best_lay_available
          - name: back_price_2
          - name: back_available_2
          - name: back_price_3
          - name: back_available_3
          - name: lay_price_2
          - name: lay_available_2
          - name: lay_price_3
          - name: lay_available_3
          - name: back_depth
          - name: lay_depth
          - name: wom
          - name: market_volume
          - name: runner_volume
          - name: handicap_line
          - name: event_participant_id
          - name: kickoff_ms
```

**Important YAML quoting note:** The `env_var()` call inside the `external_location` string must use single-quoted arguments inside the double-quoted YAML string. The dbt `external_location` meta key is evaluated as a Jinja expression by `dbt-duckdb`'s external source plugin. Use the form shown above (single-quoted inner strings).

**Self-review checkpoint:**
- `cd dbt/data_platform && dbt parse --profiles-dir .` succeeds without YAML parse errors.
- `dbt source freshness --select source:bronze.matchbook_odds` does not crash (even if no files exist yet).
- The `external_location` glob path correctly points to `bronze/matchbook_odds/**/*.parquet`.

**Red test (before this task):**
```bash
cd dbt/data_platform && dbt build --select stg_matchbook_odds
# Compilation Error: source 'bronze.matchbook_odds' is not defined
```

**Test facility:** `dbt parse` (catches YAML errors); `dbt build --select stg_matchbook_odds` (needs at least one Parquet file to pass fully — see AC-11 note in spec).

---

### TASK-06 — Create `stg_matchbook_odds.sql`

**Files to change:** `dbt/data_platform/models/silver/stg_matchbook_odds.sql` (new file)

**Exact content:**

```sql
-- Faithful projection of Matchbook bronze Parquet. No enrichment here —
-- market/runner/team names from the Postgres catalogue are out of scope
-- for this staging layer (deferred to a future enrichment model).
--
-- union_by_name=true (in the source definition) handles old files that
-- pre-date the kickoff_ms column: DuckDB fills the absent column with NULL.

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

**Also create** `dbt/data_platform/models/silver/stg_matchbook_odds.yml` for schema tests:

```yaml
version: 2

models:
  - name: stg_matchbook_odds
    description: "Silver staging view over Matchbook bronze Parquet — faithful projection, no enrichment."
    columns:
      - name: event_id
        tests:
          - not_null
      - name: market_id
        tests:
          - not_null
      - name: runner_id
        tests:
          - not_null
      - name: ingested_at
        tests:
          - not_null
```

The model inherits `+materialized: view` and `+schema: silver` from `dbt_project.yml` — no `{{ config(...) }}` block needed.

**Self-review checkpoint:**
- After writing at least one Parquet file to `data/bronze/matchbook_odds/year=2026/month=06/day=28/part-*.parquet` (either via the consumer or by copying a test file), `dbt build --select stg_matchbook_odds` exits 0.
- The `not_null` tests pass (all four required columns have values in the test file).
- `stg_matchbook_odds` does not appear in the Dagster asset graph (it is a dbt asset registered via `@dbt_assets`, but it joins the lineage graph naturally — no explicit exclusion needed since it's not a Dagster-orchestrated job asset in the medallion flow. Verify it does not break `dagster definitions validate`).

**Red test (before this task — TASK-05 must be complete first):**
```bash
cd dbt/data_platform && dbt build --select stg_matchbook_odds
# Compilation Error: When searching for a node 'stg_matchbook_odds', dbt found no nodes
```

**Test facility:** `dbt build --select stg_matchbook_odds` (with a sample Parquet); dbt schema tests (AC-11, AC-12).

---

## Phase 5 — Migration Script

### TASK-07 — Create `scripts/migrate_matchbook_bronze.py`

**Files to change:** Create `scripts/migrate_matchbook_bronze.py` (new file; `scripts/` directory does not yet exist — create it).

**Exact content outline (implement this precisely):**

```python
#!/usr/bin/env python3
"""
Migrate Matchbook bronze Parquet from sports-gaming-engine lakehouse to this project.

Usage
-----
    python scripts/migrate_matchbook_bronze.py \\
        --source-dir /path/to/extracted/lakehouse_data \\
        --dest-dir data/bronze \\
        [--dry-run]

macOS / Docker Desktop — volume extraction prerequisite
-------------------------------------------------------
The lakehouse_data Docker volume is not directly accessible on the macOS host.
Extract it first:

    docker run --rm \\
        -v lakehouse_data:/data \\
        -v $(pwd):/out \\
        alpine tar cf /out/lake.tar -C /data .
    mkdir -p /tmp/lake && tar xf lake.tar -C /tmp/lake

Then run this script with --source-dir /tmp/lake/silver/matchbook_odds.

Source layout expected
----------------------
    <source-dir>/year=YYYY/month=MM/day=DD/<filename>.parquet

Destination layout produced
---------------------------
    <dest-dir>/matchbook_odds/year=YYYY/month=MM/day=DD/part-<filename>.parquet
"""
```

The script should:

1. Parse `--source-dir` (required), `--dest-dir` (default: `"data/bronze"`), `--dry-run` (flag) via `argparse`.
2. Glob `Path(args.source_dir).rglob("*.parquet")` to find all source files.
3. For each source file:
   a. Extract Hive partition tokens from the path by walking ancestors looking for `year=`, `month=`, `day=` directory components. If all three are found, reconstruct the partition path. If any are absent, read the Parquet file's `ingested_at` column minimum to derive the date (use `pyarrow.parquet.read_table(path, columns=["ingested_at"])` and extract the date from the first row).
   b. Construct `dest = Path(args.dest_dir) / "matchbook_odds" / f"year={y}" / f"month={m:02d}" / f"day={d:02d}" / f"part-{source.stem}.parquet"`.
   c. If `dest.exists()`: print `SKIP {dest}`, increment skip counter, continue.
   d. In `--dry-run`: print `WOULD COPY {source} → {dest}`, increment copy counter, continue.
   e. Otherwise: `dest.parent.mkdir(parents=True, exist_ok=True)` then `shutil.copy2(source, dest)`, print `COPY {source} → {dest}`, increment copy counter.
4. Print summary: `Copied: {N}  Skipped: {M}`.
5. Exit 0 in all non-error cases (including dry-run).

**Implementation note on partition token extraction:** Walk `source.parts` from the end toward the root, collecting `year=`, `month=`, `day=` components. This handles paths like `…/silver/matchbook_odds/year=2026/month=06/day=28/part-xxx.parquet` correctly. Parse the integer from each token (e.g., `int("2026")` from `"year=2026"`).

**Self-review checkpoint:**
- `python scripts/migrate_matchbook_bronze.py --help` prints the extraction prerequisite note.
- `python scripts/migrate_matchbook_bronze.py --source-dir /nonexistent --dry-run` exits with a clear error (no files found).
- Run twice on a real source dir: first run prints "Copied: N, Skipped: 0"; second run prints "Copied: 0, Skipped: N" (idempotency).
- No `warehouse.duckdb` is opened or created by the script.
- `ruff check scripts/migrate_matchbook_bronze.py` passes.

**Red test (before this task):**
```bash
python scripts/migrate_matchbook_bronze.py --help
# zsh: no such file or directory: scripts/migrate_matchbook_bronze.py
```

**Test facility:** Manual invocation with `--dry-run` against a real or synthetic source directory (AC-13, AC-14).

---

## Phase 6 — Tests

### TASK-08 — Create `tests/matchbook/test_consumer.py`

**Files to change:** Create `tests/matchbook/test_consumer.py` (new file). The `tests/matchbook/` directory does not exist — create it. No `__init__.py` needed (importlib mode).

**Design notes:**
- Mock `redis.Redis` entirely — the consumer holds a `self._redis` attribute; inject a mock at construction time.
- Use `tmp_path` (pytest built-in) as the `bronze_dir` so no real filesystem side effects persist.
- Mock `time.monotonic` where needed (flush timing tests).
- The consumer registers `signal.signal` in `__init__`; this is safe in test context.
- Test the `_process_json_message` method and `_flush` method directly (unit tests), plus the `run()` loop with a mock pubsub for integration-style tests.

**Test functions to implement:**

#### Test 1 — Dedup: same tick not buffered (AC-15)
```python
def test_dedup_same_tick_not_buffered(tmp_path):
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    tick = _valid_tick()
    consumer._process_json_message(tick)
    consumer._process_json_message(tick)  # identical
    assert len(consumer._buffer) == 1
```

#### Test 2 — Dedup: changed tick is buffered (AC-15)
```python
def test_dedup_changed_tick_buffered(tmp_path):
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    tick = _valid_tick()
    consumer._process_json_message(tick)
    tick2 = {**tick, "best_back_price": tick["best_back_price"] + 0.05}
    consumer._process_json_message(tick2)
    assert len(consumer._buffer) == 2
```

#### Test 3 — Empty buffer: `_flush` writes nothing (AC-17)
```python
def test_flush_empty_buffer_writes_nothing(tmp_path):
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    consumer._flush()
    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert parquet_files == []
```

#### Test 4 — Non-empty buffer: `_flush` writes one Parquet file (AC-01, AC-03, AC-04)
```python
def test_flush_writes_parquet(tmp_path):
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    consumer._process_json_message(_valid_tick())
    consumer._flush()
    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert len(parquet_files) == 1
    # Verify path structure
    path_str = str(parquet_files[0])
    assert "matchbook_odds" in path_str
    assert "year=" in path_str
    assert "month=" in path_str
    assert "day=" in path_str
    assert "silver" not in path_str
    # Verify compression
    meta = pq.read_metadata(parquet_files[0])
    assert meta.row_group(0).column(0).compression == "ZSTD"
```

#### Test 5 — Schema cast gate: bad type drops batch (AC-06)
```python
def test_flush_bad_schema_writes_nothing(tmp_path):
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    # Inject a row with event_id as string (violates int64 non-nullable schema)
    consumer._buffer.append({**_valid_tick_dict(), "event_id": "not-an-int"})
    consumer._flush()  # _rows_to_arrow will produce a type error on cast
    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert parquet_files == []
```

Note: The schema cast gate catches `pa.lib.ArrowInvalid`/`pa.lib.ArrowTypeError`. The test must inject a value that passes `_rows_to_arrow` (which calls `pa.array(col, type=field.type)`) but fails `table.cast(SCHEMA)`. The easiest approach: inject a row with `event_id=None` (which violates the non-nullable `int64` field). The `pa.array([None], type=pa.int64())` call will build a null array, and `table.cast(SCHEMA)` should reject null in a non-nullable field. Test this in isolation to confirm the exact failure mode before writing the assertion.

#### Test 6 — SIGTERM flushes buffer (AC-16)
```python
def test_sigterm_flushes_buffer(tmp_path, monkeypatch):
    mock_pubsub = MagicMock()
    mock_pubsub.get_message.return_value = None  # no messages
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub

    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    consumer._redis = mock_redis
    # Pre-load buffer with 3 ticks
    for _ in range(3):
        consumer._process_json_message(_valid_tick())
    assert len(consumer._buffer) == 1  # dedup: all identical → only 1

    # Actually add 3 distinct ticks to test the flush count
    consumer._buffer.clear()
    consumer._buffer.append(_valid_tick_dict(event_id=1))
    consumer._buffer.append(_valid_tick_dict(event_id=2))
    consumer._buffer.append(_valid_tick_dict(event_id=3))

    # Simulate SIGTERM: set _running=False, then run() exits and flushes
    consumer._running = False
    consumer.run()

    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert len(parquet_files) == 1
    table = pq.read_table(parquet_files[0])
    assert len(table) == 3
```

#### Test 7 — Time-based flush fires on interval (AC-18)
```python
def test_time_based_flush(tmp_path, monkeypatch):
    # Mock time.monotonic to simulate 61 seconds elapsed
    call_count = [0]
    def fake_monotonic():
        call_count[0] += 1
        if call_count[0] == 1:
            return 0.0   # initial _last_flush
        return 61.0      # elapsed > FLUSH_INTERVAL_S
    monkeypatch.setattr("data_platform.matchbook.ingestor.direct_parquet_consumer.time.monotonic", fake_monotonic)

    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    consumer._last_flush = 0.0
    consumer._buffer.append(_valid_tick_dict())
    # Manually evaluate the flush condition (mirrors the run() loop logic)
    elapsed = time.monotonic() - consumer._last_flush
    if elapsed >= FLUSH_INTERVAL_S and consumer._buffer:
        consumer._flush()
    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert len(parquet_files) == 1
```

#### Test 8 — Pydantic validation drops invalid record (AC-05)
```python
def test_pydantic_validation_drops_missing_event_id(tmp_path):
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    bad_tick = _valid_tick()
    del bad_tick["event_id"]
    consumer._process_json_message(bad_tick)
    assert len(consumer._buffer) == 0
```

Note: The existing `_process_json_message` already catches missing `event_id` with the `KeyError/ValueError` guard. After TASK-03b adds the Pydantic validation step, this test confirms the behaviour is preserved (whether caught by the existing guard or the Pydantic step).

**Helper fixtures to add at the top of the test file:**

```python
def _valid_tick(event_id: int = 1, market_id: int = 10, runner_id: int = 100) -> dict:
    return {
        "event_id": event_id,
        "market_id": market_id,
        "runner_id": runner_id,
        "timestamp_ns": str(int(time.time() * 1_000_000_000)),
        "in_running": True,
        "market_status": "open",
        "best_back_price": 2.0,
        "best_lay_price": 2.1,
        "best_back_available": 100.0,
        "best_lay_available": 80.0,
        # All other fields intentionally absent (nullable)
    }

def _valid_tick_dict(event_id: int = 1, market_id: int = 10, runner_id: int = 100) -> dict:
    """Returns a pre-processed buffer dict (post-_process_json_message format)."""
    return {
        "event_id": event_id, "market_id": market_id, "runner_id": runner_id,
        "ingested_at": int(time.time() * 1000),
        "sport_id": None, "market_type": None, "market_status": "open",
        "in_running": True,
        "best_back_price": 2.0, "best_back_available": 100.0,
        "best_lay_price": 2.1, "best_lay_available": 80.0,
        "back_price_2": None, "back_available_2": None,
        "back_price_3": None, "back_available_3": None,
        "lay_price_2": None, "lay_available_2": None,
        "lay_price_3": None, "lay_available_3": None,
        "back_depth": None, "lay_depth": None, "wom": None,
        "market_volume": None, "runner_volume": None,
        "handicap_line": None, "event_participant_id": None, "kickoff_ms": None,
    }
```

**Imports for the test file:**
```python
import time
from pathlib import Path
from unittest.mock import MagicMock

import pyarrow.parquet as pq
import pytest

from data_platform.matchbook.ingestor.direct_parquet_consumer import (
    FLUSH_INTERVAL_S,
    DirectParquetConsumer,
)
```

**Self-review checkpoint:**
- `PYTHONPATH=src uv run pytest tests/matchbook/ -v` — all 8 tests pass.
- No test requires a live Redis connection (mock everywhere).
- No test opens `warehouse.duckdb`.
- `ruff check tests/matchbook/test_consumer.py` passes.

**Red test (before TASK-03 is complete):**
Tests 4, 5, 6 fail because `_write_parquet` writes to `"silver/matchbook_odds/..."` instead of the bronze partition path.

**Test facility:** `PYTHONPATH=src uv run pytest tests/matchbook/ -v`

---

## Execution Order Summary

| Order | Task | Depends on | Parallelisable with |
|---|---|---|---|
| 1 | TASK-01: Config fields | — | TASK-02 |
| 1 | TASK-02: MatchbookOddsRecord | — | TASK-01 |
| 2 | TASK-03: Consumer fix | TASK-01, TASK-02 | — |
| 3 | TASK-04: Docker wiring | TASK-01 (for env var names) | TASK-05, TASK-06, TASK-07 |
| 3 | TASK-05: dbt source | — | TASK-04, TASK-06, TASK-07 |
| 3 | TASK-06: stg_matchbook_odds | TASK-05 | TASK-04, TASK-07 |
| 3 | TASK-07: Migration script | — | TASK-04, TASK-05 |
| 3 | TASK-08: Tests | TASK-03 | TASK-04, TASK-05, TASK-06, TASK-07 |

---

## Red Tests Summary

| Task | What fails before this task is done |
|---|---|
| TASK-01 | `settings.redis_host` → `AttributeError` |
| TASK-02 | `from data_platform.models.schemas import MatchbookOddsRecord` → `ImportError` |
| TASK-03 | `grep silver src/.../direct_parquet_consumer.py` returns a match; `_flush()` writes to silver path |
| TASK-04 | `docker compose config \| grep matchbook-ingestor` returns nothing |
| TASK-05 | `dbt build --select stg_matchbook_odds` fails with "source 'bronze.matchbook_odds' is not defined" |
| TASK-06 | `dbt build --select stg_matchbook_odds` fails with "no nodes named stg_matchbook_odds" |
| TASK-07 | `python scripts/migrate_matchbook_bronze.py --help` fails with "no such file" |
| TASK-08 | `pytest tests/matchbook/` fails with "no such directory" or tests fail on wrong output path |

---

## Frozen Artifacts

**AC-19 — `matchbook_event_link.sql` scaffold: no action required.**
Spec §2.11 explicitly scopes this out: the canonical link table remains an empty typed scaffold (`select cast(null as ...) limit 0`) until a conforming layer is built. No task modifies this file. Self-review checkpoint for TASK-06: after creating `stg_matchbook_odds.sql`, confirm `dbt/data_platform/models/silver/canonical/matchbook_event_link.sql` is unchanged (`git diff -- dbt/data_platform/models/silver/canonical/matchbook_event_link.sql` returns nothing).

---

## Open Questions

None. All open questions in the specification are resolved (OQ-1 through OQ-7). Resolutions are incorporated into this plan.
