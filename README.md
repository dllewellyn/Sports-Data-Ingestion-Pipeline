# Data Ingestion Platform

A medallion-architecture data platform you can run with one command. Orchestrated
by **Dagster**, transformed and tested by **dbt** on **DuckDB**, with every layer
persisted as **Apache Parquet** and full **OpenTelemetry** tracing wired for
**SigNoz**.

## Stack & why

| Concern | Choice | Notes |
| --- | --- | --- |
| Packaging / envs | **uv** | Fast, lockfile-based (`uv.lock` committed). |
| HTTP ingest | **requests** | Auto-instrumented for OTel traces. |
| Record validation | **Pydantic v2** | The modern answer to "are dataclasses still a thing?" — dataclasses exist but do no validation/coercion. Pydantic validates each record at the API boundary. |
| DataFrame validation | **Pandera** | Validates the assembled frame (dtypes, nullability, ranges) before it lands. |
| Warehouse validation | **dbt tests** | `not_null` / `unique` / singular tests run inline with `dbt build`. |
| Orchestration + UI | **Dagster** (webserver + daemon) | Asset graph, runs, schedules at `:3000`. |
| Transformation | **dbt-core + dbt-duckdb** | Silver/gold models, lineage surfaced as Dagster assets. |
| Engine / storage | **DuckDB + Parquet** | DuckDB is the warehouse; each layer also persists as Parquet. |
| Notebooks | **JupyterLab** | Remote-accessible at `:8888`. |
| Observability | **OpenTelemetry → SigNoz** | OTLP traces via a local collector that forwards to SigNoz. |

## Medallion flow (hello-world)

```
                 raw_users (Dagster asset)              dbt build (Dagster: dbt_assets)            publish_gold_parquet
 source API ───▶ requests + Pydantic + Pandera ──▶  bronze ──▶ silver (view) ──▶ gold (table)  ──▶ gold Parquet ──▶ (Dagster asset)
                 data/bronze/users.parquet            stg_users      dim_users_by_city            data/gold/users_by_city.parquet
                 [OTel span]                          [dbt tests on silver + gold]                 [OTel span]
```

- **Bronze** — `raw_users` pulls users from the source API, validates every record
  (Pydantic) and the whole frame (Pandera), and writes `data/bronze/users.parquet`.
- **Silver** — dbt view `stg_users` cleans/conforms the bronze Parquet (read directly
  by dbt-duckdb as an external source). Tested: `user_id` not-null + unique, `email`/`city` not-null.
- **Gold** — dbt table `dim_users_by_city` aggregates users per city (tested), and the
  dbt `external` model `users_by_city_export` writes `data/gold/users_by_city.parquet`.
- **Publish** — `publish_gold_parquet` reads the gold Parquet and emits a gold-layer span.

> **Single-writer note:** DuckDB is single-writer. dbt owns the warehouse file; the
> gold Parquet is produced *by dbt* (external materialization) rather than by a second
> process reopening the warehouse, which avoids cross-process catalog races.

## Quick start

```bash
cp .env.example .env          # set JUPYTER_TOKEN and your SigNoz endpoint
docker compose up --build     # builds the image, starts all services
```

Then, from any machine on your network:

| Service | URL | Auth |
| --- | --- | --- |
| Dagster UI | `http://<host>:3000` | none |
| JupyterLab | `http://<host>:8888` | `JUPYTER_TOKEN` from `.env` |
| OTLP collector | `<host>:4317` (gRPC) / `:4318` (HTTP) | — |

**Run the hello-world flow:** open the Dagster UI → **Jobs → `medallion_hello_world`
→ Materialize all** (or **Assets → Materialize all**). Watch bronze → silver → gold
build, dbt tests pass, and the gold Parquet appear. A daily schedule
(`medallion_daily`, 06:00) ships disabled — toggle it on in the UI.

Then open `notebooks/explore.ipynb` in JupyterLab to query the layers with DuckDB.

## Local development (no Docker)

```bash
uv sync
export PYTHONPATH=src DATA_DIR="$PWD/data" DUCKDB_PATH="$PWD/data/warehouse.duckdb" \
       DAGSTER_HOME="$PWD/.dagster" OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
uv run dagster dev -m data_platform.definitions          # UI at http://localhost:3000

# or run the whole flow headless (parse dbt first to build the manifest;
# `dagster dev` does this automatically, `job execute` does not):
( cd dbt/data_platform && uv run --project ../.. dbt parse --profiles-dir . )
uv run dagster job execute -m data_platform.definitions -j medallion_hello_world
```

> Without a collector running, you'll see harmless `Connection refused` retries from
> the OTLP exporter — spans are simply dropped. Start the collector (`docker compose up
> otel-collector`) or point `OTEL_EXPORTER_OTLP_ENDPOINT` at a live endpoint to see traces.

## SigNoz

The `otel-collector` service receives OTLP from the apps and forwards to SigNoz.
Set these in `.env`:

- **Self-hosted SigNoz on the same host:** `SIGNOZ_OTLP_ENDPOINT=host.docker.internal:4317`, `SIGNOZ_OTLP_INSECURE=true`.
- **SigNoz Cloud:** `SIGNOZ_OTLP_ENDPOINT=ingest.<region>.signoz.cloud:443`, `SIGNOZ_OTLP_INSECURE=false`, `SIGNOZ_INGESTION_KEY=<key>`.

Traces appear under service `data-platform`. Each run produces an `ingest.raw_users`
span (with a child `requests` HTTP span) and a `publish.gold_users_by_city` span.

## Layout

```
├── docker-compose.yml          # dagster-webserver, dagster-daemon, jupyter, otel-collector
├── Dockerfile                  # uv-based image; venv at /opt/venv (not shadowed by bind mount)
├── otel-collector-config.yaml  # OTLP in -> SigNoz out
├── pyproject.toml / uv.lock     # deps (uv, package=false, src/ on PYTHONPATH)
├── src/data_platform/
│   ├── config.py               # pydantic-settings (env-driven)
│   ├── otel.py                 # tracer provider + OTLP exporter + requests instrumentation
│   ├── definitions.py          # Dagster code location: assets, job, schedule, dbt resource
│   ├── models/
│   │   ├── schemas.py          # Pydantic record models
│   │   └── validation.py       # Pandera DataFrame schema
│   └── assets/
│       ├── bronze.py           # raw_users ingest asset
│       ├── dbt.py              # @dbt_assets (silver + gold) + source->bronze lineage
│       └── gold.py             # publish_gold_parquet asset
├── dbt/data_platform/          # dbt project (profiles target DuckDB)
│   ├── models/silver/          # stg_users + sources + tests
│   └── models/gold/            # dim_users_by_city (table) + users_by_city_export (Parquet) + tests
├── notebooks/explore.ipynb     # DuckDB exploration of all layers
└── data/{bronze,silver,gold}/  # Parquet lake + warehouse.duckdb
```
