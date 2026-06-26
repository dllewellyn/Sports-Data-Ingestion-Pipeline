# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install deps (creates .venv; respects uv.lock and .python-version)
uv sync

# Run the Dagster UI locally (auto-runs `dbt parse` to build the manifest)
PYTHONPATH=src DATA_DIR="$PWD/data" DUCKDB_PATH="$PWD/data/warehouse.duckdb" \
  DAGSTER_HOME="$PWD/.dagster" uv run dagster dev -m data_platform.definitions

# Run the whole medallion flow headless. `job execute` does NOT build the dbt
# manifest, so parse first or the import fails at @dbt_assets decoration time:
( cd dbt/data_platform && uv run --project ../.. dbt parse --profiles-dir . )
PYTHONPATH=src DATA_DIR="$PWD/data" DUCKDB_PATH="$PWD/data/warehouse.duckdb" \
  DAGSTER_HOME="$PWD/.dagster" \
  uv run dagster job execute -m data_platform.definitions -j medallion_hello_world

# dbt directly (run a single model / test from the dbt project dir)
cd dbt/data_platform
uv run --project ../.. dbt build --select stg_users          # one model + its tests
uv run --project ../.. dbt test  --select dim_users_by_city  # tests only

# Lint + format (PEP 8). Both run automatically on commit via pre-commit.
uv run ruff check --fix src
uv run ruff format src

# Enable the git pre-commit hook (once per clone) and run it across everything
uv run pre-commit install
uv run pre-commit run --all-files

# Full containerised stack (Dagster :3000, JupyterLab :8888, OTel collector :4317/:4318)
cp .env.example .env && docker compose up --build
```

There is no Python unit-test suite; data correctness is asserted by **dbt tests**
(run inline via `dbt build`) plus Pydantic/Pandera validation at ingest.

## Architecture

Medallion pipeline orchestrated by Dagster, transformed/tested by dbt on DuckDB,
every layer persisted as Parquet, traced via OpenTelemetry → SigNoz.

```
raw_users ──▶ silver/stg_users ──▶ gold/dim_users_by_city ──▶ gold/users_by_city_export ──▶ publish_gold_parquet
(Dagster:     (dbt view)            (dbt table)                (dbt external → Parquet)        (Dagster: reads Parquet)
 requests+Pydantic+Pandera                                                                      emits OTel span)
 → bronze Parquet)
```

- **Edge of the system is `assets/bronze.py`** — the only asset that touches the
  network. Validation is layered: Pydantic (`models/schemas.py`) per record →
  Pandera (`models/validation.py`) on the frame → dbt tests in the warehouse.
- **dbt lineage surfaces as Dagster assets** via `@dbt_assets` in `assets/dbt.py`.
  The dbt project lives under `dbt/data_platform/`; silver reads the bronze Parquet
  as an external source, gold aggregates silver.

### Non-obvious constraints (these caused real bugs — preserve them)

- **DuckDB is single-writer; dbt owns the warehouse file.** Do NOT add a second
  process/Dagster step that opens `warehouse.duckdb` read-write during a run — a
  separate process cannot see dbt's un-checkpointed WAL writes and gets phantom
  "schema does not exist" catalog errors. Produce derived Parquet *inside dbt*
  (the `external` materialization in `gold/users_by_city_export.sql`) and have
  Python read the resulting **file**, not the warehouse table.
- **dbt model asset keys are prefixed by their model subfolder**, e.g.
  `AssetKey(["gold", "users_by_city_export"])`, not `["users_by_city_export"]`.
  Cross-asset `deps=[...]` in Python assets must use the prefixed key or the
  dependency edge silently won't form (the step then runs out of order).
- **The bronze→silver edge is wired by `BronzeAwareTranslator`** in `assets/dbt.py`,
  which maps the dbt source `users` to `AssetKey(["raw_users"])`. Renaming the
  bronze asset or the dbt source breaks the lineage link.
- **Do not add `from __future__ import annotations` to asset modules.** Dagster
  introspects `context`/return annotations at runtime; stringized annotations make
  it raise `DagsterInvalidDefinitionError`.
- **Python is pinned to `>=3.12,<3.13`** (`.python-version` + `pyproject.toml`).
  dbt/mashumaro fails to build serializers on 3.14.
- **`[tool.uv] package = false`** — the project is not built as a wheel; code is
  imported from `src/` via `PYTHONPATH=src`. In Docker the venv lives at
  `/opt/venv` (not `/app`) so the `./src` bind-mount for live reload doesn't
  shadow installed dependencies.

### Configuration & telemetry

- All runtime config flows through `config.py` (`pydantic-settings`, env-driven):
  `DATA_DIR`, `DUCKDB_PATH`, `API_BASE_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`.
  The dbt `profiles.yml` and the gold `external` model read `DUCKDB_PATH`/`DATA_DIR`
  via `env_var(...)`, so all components must agree on these.
- `otel.py` installs the tracer provider once and auto-instruments `requests`.
  Without a collector reachable at `OTEL_EXPORTER_OTLP_ENDPOINT` you get harmless
  `Connection refused` retries; spans are dropped. The collector forwards to SigNoz
  per `otel-collector-config.yaml` (endpoint/key set in `.env`).

## Python conventions

PEP 8 layout and import order are **enforced by ruff** (config in `pyproject.toml`,
run via pre-commit) — don't hand-format; let `ruff format` decide. Lint set is
`E,W,F,I,UP,B,C4,SIM`; fix findings rather than suppressing them (no blanket
`# noqa`). Beyond what ruff checks, follow the patterns this codebase already uses:

- **Validate at boundaries with Pydantic v2, not dataclasses.** Any data entering
  the system (API payloads, external config) gets a Pydantic model; dataclasses do
  no validation/coercion. DataFrame contracts go through Pandera. See
  `models/schemas.py` and `models/validation.py`.
- **Config comes from `pydantic-settings`** (`config.py`), never ad-hoc `os.getenv`.
  Add new settings as typed fields there so Docker, dbt (`env_var`), and Python
  stay in sync.
- **Type-annotate public functions and assets.** `pyupgrade` (UP) keeps syntax
  modern (e.g. `str | None`, not `Optional[str]`) — but remember the documented
  exception: **no `from __future__ import annotations` in Dagster asset modules**.
- **Use `pathlib.Path`** for filesystem paths (settings expose `Path` objects), and
  prefer context managers for DuckDB connections / spans (`with ... as`).
- Keep functions side-effect-honest: an asset either produces its artifact or
  raises — no silent fallbacks, defaults-on-failure, or stubbed data.

## Maintaining this file

Treat CLAUDE.md as living documentation. **When you discover something a future
instance would otherwise have to rediscover the hard way — a non-obvious
constraint, a tool/version gotcha, a failure mode and its fix, a new command or
convention — add it here in the same commit.** Keep additions concise and put
hard-won constraints under "Non-obvious constraints". Remove guidance that becomes
stale. Do not restate what's discoverable from the file tree or generic Python advice.
