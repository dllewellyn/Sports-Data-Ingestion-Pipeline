---
name: bronze-ingest-source
description: >
  Scaffold and implement a new REST API bronze ingest source following this
  repo's established pattern: pure-Python engine in `<provider>/ingest.py`,
  thin Dagster wrapper in `assets/<provider>.py`, Pydantic+Pandera boundary
  validation, atomic Parquet write, OTel span, dedicated job + schedule.
  USE WHEN adding a new external API data source to the bronze layer — "add
  a new bronze source", "ingest from <API>", "wire up a new data provider".
---

# bronze-ingest-source

Adds a new REST API bronze ingest source to the Sports-Data-Ingestion-Pipeline.
The pattern is confirmed by three implementations: `users/bronze.py` (simple),
`espn/ingest.py` (paginated, multi-league, no auth), and
`matchbook/ingest.py` (session-token auth, multi-sport, per-unit isolation).
Follow `espn/` or `matchbook/` depending on whether auth is required.

## When to use

- User says "add bronze ingestion for X", "wire up <API> as a bronze source",
  or "ingest raw <provider> events/fixtures/odds into the bronze layer".
- A new data provider is being onboarded for the first time.
- Do NOT use for silver/gold dbt work — this skill covers the Parquet bronze
  layer only.

## Files to create / change

```
src/data_platform/
  <provider>/
    __init__.py          # empty
    ingest.py            # pure-Python engine (Dagster-free)
  assets/
    <provider>.py        # thin Dagster asset wrapper — NO from __future__ import annotations
  config.py              # new Settings fields + bronze dir property
  models/
    schemas.py           # new Pydantic record model (<Provider>Record)
    models/validation.py # new Pandera frame schema (<provider>_bronze_schema)
  definitions.py         # register asset + job + schedule + AssetSelection subtraction

tests/
  <provider>/
    __init__.py          # empty (if not already present)
    conftest.py          # silence OTel tracer for this package
    test_contracts.py    # Pydantic + Pandera unit tests
    test_ingest.py       # ingest engine unit tests (no live HTTP, no Dagster)
    test_asset.py        # asset key/group, no __future__ annotation, result shape

.env.example             # placeholder credentials if auth is needed
```

## Step order (always this sequence)

1. **Contracts** — `models/schemas.py` + `models/validation.py` + tests.
2. **Ingest engine** — `<provider>/ingest.py` + tests.
3. **Config** — `config.py` fields + property + `.env.example` + tests.
   Config MUST precede the asset wrapper (see CLAUDE.md: "Config fields must
   precede the asset wrapper in sequencing").
4. **Asset wrapper** — `assets/<provider>.py` + tests.
5. **Definitions wiring** — `definitions.py` ALWAYS LAST.

## Ingest engine conventions (`<provider>/ingest.py`)

### Required functions

```python
# If auth is needed (session-token pattern):
def authenticate(username, password, *, base_url, timeout) -> str:
    """See CLAUDE.md: Matchbook session-token auth pattern."""

# Paginated or single-page fetch:
def fetch_<units>(session_token_or_key, <filter_params>, *, base_url, per_page, timeout) -> list[dict]:
    ...

# Flatten one raw dict to structured columns + raw_event:
def flatten_<unit>(raw: dict, *, ingested_at: str) -> dict:
    return {
        # structured projected columns ...
        "raw_event": json.dumps(raw, separators=(",", ":"), sort_keys=True),  # FULL original dict
    }

# Ingest one unit (sport / league / division) — returns, does NOT raise on per-record failures:
def ingest_<unit>(...) -> tuple[Path | None, int]:  # (out_path_or_None, failure_count)
    ...
    # Atomic write:
    tmp = out_path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(out_path)
    return out_path, failure_count

# Outer loop — re-raises at end if any failures (AC pattern):
def run_<provider>_ingest(...) -> IngestionReport:
    token = authenticate(...)  # raises before any Parquet write (CLAUDE.md)
    for unit in UNITS:
        try:
            path, failures = ingest_<unit>(...)
            total_failures += failures
            ...
        except Exception:  # noqa: BLE001 — per-unit isolation
            report.failed.append(...)
    if total_failures > 0:
        raise RuntimeError(f"... {total_failures} failures")
    return report
```

### Key rules

- **`raw_event` must contain the full original dict** — including nested arrays
  like `markets`, `runners`, `venue`. A future field must be recoverable from
  bronze without re-fetching. Prove it with a test that reads a non-projected
  field from `raw_event`.
- **`ingest_<unit>` returns failure count, does NOT re-raise** on per-record
  Pydantic failures — `run_*_ingest` re-raises after all units complete.
  Raising in the unit function aborts the remaining units. (CLAUDE.md)
- **Atomic write:** `tmp = out.with_suffix(".tmp")` → `df.to_parquet(tmp)` →
  `tmp.replace(out)`. No partial Parquet on failure.
- **`from __future__ import annotations` is allowed** in the engine module
  (pure Python, not a Dagster asset module). It is FORBIDDEN in
  `assets/<provider>.py`.
- No `os.getenv` — config via `pydantic-settings` (`config.py`).
- No Dagster imports in the engine.
- OTel span: `with get_tracer().start_as_current_span("ingest.<provider>"):`.

## Config conventions (`config.py`)

Add alongside any existing provider fields (check for name collisions first —
see CLAUDE.md: "Config property name collision for new providers"):

```python
# New fields:
<provider>_username: str = ""          # if auth needed
<provider>_password: str = ""          # if auth needed
<provider>_events_base_url: str = "https://api.<provider>.com"
<provider>_throttle_seconds: float = 0.0

# New property:
@property
def <provider>_bronze_dir(self) -> Path:
    return self.bronze_dir / "<provider>"
```

Check that `<provider>_bronze_dir` doesn't collide with an existing property
on the same provider (e.g. Matchbook already has `matchbook_bronze_dir` for
the odds ingestor → the events property is `matchbook_events_bronze_dir`).

## Dagster asset wrapper (`assets/<provider>.py`)

```python
# NO: from __future__ import annotations   ← Dagster introspects annotations at runtime

from dagster import AssetKey, MaterializeResult, asset
from ..config import settings
from ..<provider>.ingest import run_<provider>_ingest, IngestionReport
from ..models.validation import <provider>_bronze_schema

@asset(
    key=AssetKey(["<provider>_bronze"]),
    group_name="bronze",
    compute_kind="python",
    description="...",
)
def <provider>_bronze(context) -> MaterializeResult:
    report = run_<provider>_ingest(
        username=settings.<provider>_username,
        ...
        out_dir=settings.<provider>_bronze_dir,
        log=context.log,
        schema=<provider>_bronze_schema,
    )
    return MaterializeResult(metadata={...})
```

## Definitions wiring (`definitions.py`) — ALWAYS LAST

```python
from .assets.<provider> import <provider>_bronze

<provider>_assets = AssetSelection.assets(<provider>_bronze)

medallion_job = define_asset_job(
    selection=AssetSelection.all() - football_assets - espn_assets - <provider>_assets,
    ...
)

<provider>_job = define_asset_job(name="<provider>_ingestion", selection=<provider>_assets)
<provider>_schedule = ScheduleDefinition(job=<provider>_job, cron_schedule="0 */6 * * *")

defs = Definitions(
    assets=[..., <provider>_bronze],
    jobs=[..., <provider>_job],
    schedules=[..., <provider>_schedule],
)
```

## Key tests to write

| Test | What to assert |
|------|---------------|
| `test_contracts.py` | Valid dict validates; missing required field raises; frame missing `raw_event` raises SchemaError |
| `test_ingest.py` | `authenticate` happy path; ValueError on missing token; 401 raises; empty creds raises before HTTP; pagination accumulates; zero events returns None; `raw_event` round-trip recovers non-projected field (e.g. `markets`); atomic write (no partial on failure); replay appends new file; per-record failures counted + NOT raised; `run_*_ingest` re-raises at end |
| `test_asset.py` | Asset key/group correct; `from __future__` absent (via `inspect.getsource`); success returns `MaterializeResult`; failure re-raises |
| `tests/test_definitions.py` | Asset + resource registered; dedicated job registered with an **exact** `AssetSelection.assets(...)` key set (assert `job_keys == EXPECTED_KEYS`, not just membership); schedule cron correct and targeting the job |

## Output path pattern

```
data/bronze/<provider>/<unit_name>/<YYYY-MM-DD>/<batch_ts>.parquet
```

`batch_ts` format: `%Y%m%dT%H%M%SZ` (e.g. `20260629T120000Z`).
Multiple runs on the same date append new files (do not overwrite).

## Reference implementations

- Auth + multi-sport: `src/data_platform/matchbook/ingest.py` + `assets/matchbook_events.py`
- No auth + multi-league: `src/data_platform/espn/ingest.py` + `assets/espn.py`
- Tests: `tests/matchbook/test_ingest.py`, `tests/espn/`
