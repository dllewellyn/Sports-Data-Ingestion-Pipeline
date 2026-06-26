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

# Unit-test pure-Python logic with pytest. Tests live under tests/ mirroring the
# src/data_platform/ layout (e.g. tests/football/). pyproject puts src/ on the
# import path (importlib mode, no __init__.py in tests/ — keep test basenames
# unique). pytest is a local/CI gate, NOT part of the ruff pre-commit hook.
PYTHONPATH=src uv run pytest

# Enable the git pre-commit hook (once per clone) and run it across everything
uv run pre-commit install
uv run pre-commit run --all-files

# Full containerised stack (Dagster :3000, JupyterLab :8888, OTel collector :4317/:4318)
cp .env.example .env && docker compose up --build
```

Data correctness in the warehouse is asserted by **dbt tests** (run inline via
`dbt build`) plus Pydantic/Pandera validation at ingest. Pure-Python logic
(discovery, throttling, season detection, contracts, ingestor wiring) is covered
by **pytest** under `tests/` (see the `pytest` command above).

## Architecture

> Code/package structure, layering & dependency rules, and the "add a new data
> source" guide live in [`ARCHITECTURE.md`](ARCHITECTURE.md). The notes below are
> the *runtime gotchas*; keep structural facts in ARCHITECTURE.md, not here.

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

#### football-data.co.uk bronze ingestion (`football/` + `assets/football_*.py`)

- **The two families need different mandated encodings — this is load-bearing.**
  Main (`mmz4281/<season>/<div>.csv`) is **latin-1**; extra (`new/<CODE>.csv`) is
  **utf-8-sig** (UTF-8 with BOM). Reading an extra file as latin-1 mojibakes the
  first header into `ï»¿Country`; reading it as plain `utf-8` leaves a BOM on
  `Country`. utf-8-sig strips the BOM. Don't "simplify" both families to one
  encoding.
- **Skip-existing is keyed purely on bronze-artifact presence**, and only for
  **historical** files. "Current season" is derived from the season token with a
  **July rollover** (`football/season.py`): a run in months Jan–Jun belongs to the
  prior calendar year's season. Current-season + all extra files are *always*
  re-fetched (extra packs every season in one file). No ETag/Last-Modified/hash.
- **One Parquet per source file, partitioned by family** —
  `football_main/<league>/<season>/<div>.parquet`, `football_extra/<code>.parquet`.
  Bronze is faithful-to-source: the mandatory core is enforced (Pydantic record +
  open Pandera `strict=False` frame) and the wide optional-odds columns ride along
  (a main E0 file is 7 cols in 1993/94 → 106 in 2023/24).
- **The live registry exposes 11 main + 16 extra leagues** (the spec estimated
  ~19 extra). The registry in `football/registry.py` is the single source of
  truth — discovery holds no hard-coded league URLs.
- **Per-file failure isolation:** a fetch error, zero-valid-rows file, or schema
  failure is recorded and the backfill continues; **no partial/empty Parquet is
  written** for it (atomic temp-file + rename write). The asset re-raises at the
  end so the run status reflects failures while successful files persist.
- **Importing `definitions` (incl. in pytest) reads the dbt manifest**, so run
  `dbt parse` first or the import fails with an orjson/manifest error. The one
  test that imports `defs` skips gracefully when the manifest is absent.
- **The daemon and webserver must load the SAME `workspace.yaml`.** They are
  separate processes; if the webserver loads the location via `-m
  data_platform.definitions` (a process-local workspace) while `dagster-daemon run`
  has no workspace, the daemon's workspace is empty and any **queued** run (UI
  launch → `QueuedRunCoordinator`) fails at launch with
  `DagsterCodeLocationNotFoundError: Location data_platform.definitions does not
  exist in workspace`. Both compose services load `workspace.yaml`; keep it that
  way. (Validation: `dagster definitions validate` only loads the location in one
  process — it does NOT catch this; you must actually launch a queued run, or at
  least `dagster definitions validate -w workspace.yaml`.)
- **`AssetSelection.all()` sweeps in every registered asset**, so `medallion_job`
  explicitly subtracts the football assets (`AssetSelection.all() -
  football_assets`). Without that, the hello-world demo job *and the daily
  schedule* would trigger the ~705-file football backfill. Run football only via
  the dedicated `football_backfill` job. When adding a new heavy/standalone source,
  give it its own job and exclude it from `all()`-based jobs.

### Configuration & telemetry

- All runtime config flows through `config.py` (`pydantic-settings`, env-driven):
  `DATA_DIR`, `DUCKDB_PATH`, `API_BASE_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`.
  The dbt `profiles.yml` and the gold `external` model read `DUCKDB_PATH`/`DATA_DIR`
  via `env_var(...)`, so all components must agree on these.
- `otel.py` installs the tracer provider once and auto-instruments `requests`.
  Without a collector reachable at `OTEL_EXPORTER_OTLP_ENDPOINT` you get harmless
  `Connection refused` retries; spans are dropped (so app startup never depends on
  the collector — no `depends_on` edge in compose).
- **Compose is base + one overlay, selected by `COMPOSE_FILE` in `.env`.**
  `docker-compose.yml` is environment-NEUTRAL (app services only; it sets no OTLP
  endpoint and no network, and bind-mounts only `./data` + the `dagster_home`
  volume). Exactly one overlay is layered on top:
    - **dev** → `docker-compose.signoz.yml`: the full self-hosted SigNoz stack
      *plus* the app-service dev wiring (endpoint → `signoz-otel-collector:4317`,
      join `signoz-net`, bind-mount `./src` `./dbt` `./notebooks` over the baked
      image for live reload).
    - **prod** → `docker-compose.prod.yml`: no SigNoz; points apps at an external
      collector via `${OTEL_EXPORTER_OTLP_ENDPOINT:?...}` (compose fails fast if it
      is unset). No source bind-mounts — prod runs the code baked into the image
      (`COPY . .` in the Dockerfile), so rebuild/ship the image to deploy.
  Overlay merge relies on Compose semantics: `environment` merges by key (overlay
  sets the endpoint), service `volumes` concatenate (dev adds the three live-reload
  mounts to the base two), and `networks` is set by the overlay. Don't put
  env-specific values (endpoint, signoz-net, live-reload mounts) back into the base.
- **Telemetry backend is self-hosted SigNoz, vendored into the repo (dev only).**
  The full stack (ClickHouse + Zookeeper + SigNoz UI + its own OTLP collector + a
  one-shot schema migrator) lives in `docker-compose.signoz.yml`, with pinned config
  under `signoz/` (`common/clickhouse/*.xml`, `common/signoz/`,
  `docker/otel-collector-config.yaml`). It writes traces/metrics/logs into
  ClickHouse; UI on `:8080`. The `signoz-net` network is defined here.
- **The SigNoz stack is a PINNED v0.116.1 snapshot.** Upstream deprecated Compose
  in favour of their "Foundry" installer, so it won't auto-update. To upgrade, bump
  `VERSION`/`OTELCOL_TAG` in `.env` and re-pull `signoz/**` from the matching SigNoz
  git tag (`deploy/docker` + `deploy/common`); the bind-mount paths were rewritten
  from upstream's `../common/...` to repo-root-relative `./signoz/...`.

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

# Do not overengieer this project

Code should be simple and easy to understand. Avoid unnecessary abstractions, patterns, or frameworks that do not add clear value.

Prioritize clarity and maintainability over cleverness. Same goes for architecture - split modules by logical boundaries, but avoid overcomplicating the structure.

Follow the KISS principle: Keep It Simple, Stupid. If a solution can be implemented in a straightforward way, do so. Avoid premature optimization or overengineering.

Implement good levels of abstraction, at the top level it should read like prose; with files having a clear purpose and a single responsibility. Avoid deep inheritance hierarchies or complex design patterns unless they are clearly justified.
