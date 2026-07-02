---
id: 004
title: Platform foundation & deployment / observability topology
slug: platform-foundation-and-deployment-topology
status: implemented
created: 2026-06-29
user_stories: []
source_commits: [6b82373, 92fbb47, 0ec9a2b, 0a49ed1]
investigation: null
related_specs: [001, 002]
---

# Platform foundation & deployment / observability topology

## 1. Summary

The data platform ships as a Dagster-orchestrated **medallion pipeline** with an
end-to-end "hello-world" flow (`raw_users → silver/stg_users →
gold/dim_users_by_city → gold/users_by_city_export → publish_gold_parquet`):
records are pulled from a source API at the system's only network edge, validated
record-by-record (Pydantic) and frame-wide (Pandera), landed as bronze Parquet, then
transformed and tested by dbt on DuckDB, with the gold aggregate written out as
Parquet and re-read by a publish asset. Every stage is traced via OpenTelemetry. The
whole stack runs under Docker Compose as an **environment-neutral base plus exactly
one overlay** chosen by `COMPOSE_FILE`: a vendored, pinned self-hosted SigNoz stack
for local dev, an external-collector wiring for prod, and a remote overlay that joins
the shared `sports-quant` infrastructure on the home server. The outcome is a
runnable, observable, reproducible medallion platform that a developer can `docker
compose up` locally and ship to a remote host without changing application code.

## 2. Background & context

This is a **retrospective specification reconstructed from commits
`6b82373..0a49ed1`** (in build order: `6b82373`, `92fbb47`, `0ec9a2b`, `0a49ed1`),
written after the fact to document already-shipped behaviour. No user stories existed
at the time; the source of truth is the committed code and the current state of the
files those commits introduced.

It documents two joined outcomes that together form the platform's foundation:

1. **The medallion data platform itself** (`6b82373`) — the Dagster + dbt-on-DuckDB +
   Parquet + layered-validation + OTel scaffold and the hello-world flow that
   exercises it end to end.
2. **The deployment & observability topology** (`92fbb47`, `0ec9a2b`, `0a49ed1`) — the
   Docker Compose split into a neutral base and one selectable overlay (dev SigNoz /
   prod external collector / remote shared-infra), the vendored pinned SigNoz stack,
   and the remote overlay's port-inheritance fix.

This spec is the substrate that the data-source specs build on. The football bronze
ingestion (spec **001**) and the ESPN ingestion + canonical conform (spec **002**)
add new bronze sources and dbt models on top of exactly this foundation (the same
bronze→silver→gold validation layering, the same DuckDB single-writer rule, the same
compose topology). It is therefore declared `related_specs: [001, 002]`.

Note on later evolution: since these commits, the warehouse backing store was
migrated from a plain DuckDB file to a **DuckLake** (Postgres-catalogued) profile,
and the base compose gained DuckLake, a DuckDB-UI browser service (since **removed
on 2026-07-02** — see `specs/002-ducklake-ui-specification.md`), and a Matchbook
ingestor service. Those are out of scope for this spec's source commits; where they
touch behaviour described here they are flagged in §9 / §10. This spec describes the
medallion foundation's *behaviour* (single-writer warehouse owned by dbt, Parquet at
every layer, layered validation, OTel tracing, base+overlay compose) at outcome
altitude, which remains true today.

## 3. Goals & non-goals

**Goals**
- A runnable end-to-end medallion flow: ingest → silver → gold → published Parquet,
  triggerable as one Dagster job (`medallion_hello_world`).
- Validation layered at three gates: Pydantic per record, Pandera on the assembled
  frame, dbt tests in the warehouse — bad data fails before it propagates.
- Bronze, gold (and the warehouse-derived export) persisted as Parquet so any layer's
  artifact is consumable as a file without re-running upstream.
- A single DuckDB writer owned by dbt; Python consumers read files, never the live
  warehouse, so there are no cross-process catalog races.
- In-app OpenTelemetry tracing that produces a coherent trace across the flow
  (ingest span with a child HTTP span; gold publish span), with `requests`
  auto-instrumented.
- All runtime configuration sourced from typed `pydantic-settings` so Docker, dbt
  (`env_var`) and Python agree on the same values.
- One environment-neutral Compose base plus exactly one overlay selected by
  `COMPOSE_FILE`, covering dev (self-hosted SigNoz), prod (external collector) and
  remote (shared `sports-quant` infra) without touching application code.
- A vendored, pinned, reproducible self-hosted SigNoz observability backend for local
  dev.

**Non-goals (explicitly out of scope)**
- The specific data sources beyond the hello-world `users` flow (football is spec 001;
  ESPN/canonical conform is spec 002).
- The DuckLake migration of the warehouse backing store and the DuckDB-UI service
  (later work; see §9/§10).
- Production secret management / TLS / auth hardening beyond "set a real JWT secret
  / token before exposing beyond localhost".
- Auto-upgrading the SigNoz stack (it is a deliberately pinned snapshot).
- A scheduled production run cadence for the hello-world flow (a daily schedule exists
  but ships **off** by default).

## 4. Actors & triggers

- **Developer / operator** — runs `dagster dev` or `docker compose up`, launches the
  `medallion_hello_world` job from the Dagster UI or CLI, and selects the deployment
  mode via `COMPOSE_FILE` in `.env`.
- **Dagster daemon / scheduler** — `medallion_daily` (cron `0 6 * * *`) can trigger
  the flow, but is **disabled by default** (toggled on in the UI).
- **Source API** — `${API_BASE_URL}/users` (default `jsonplaceholder.typicode.com`),
  the upstream system the bronze asset pulls from.
- **OTLP collector** — the SigNoz in-stack collector (dev), an external collector
  (prod), or the shared `signoz-otel-collector` (remote) receives the exported spans.
- **The `deploy` skill / remote host** — `git pull` + `docker compose up -d --build`
  on `192.168.1.166`, joining the pre-existing `sports-quant` network.

## 5. Behaviour specification (BDD)

### Capability: End-to-end medallion hello-world flow

**Scenario: Ingest, transform, test, and publish users end to end**
- **Given** the source API returns a list of user records and a DuckDB warehouse dbt
  can write
- **When** the `medallion_hello_world` job runs
- **Then** the `raw_users` bronze asset fetches `${API_BASE_URL}/users`, validates and
  lands `data/bronze/users.parquet`
- **And** the dbt assets build `silver/stg_users` (a view over the bronze Parquet) and
  `gold/dim_users_by_city` (a per-city user-count table) and run their tests inline
- **And** the `gold/users_by_city_export` external model writes
  `data/gold/users_by_city.parquet`
- **And** `publish_gold_parquet` reads that Parquet file (ordered by `user_count`
  desc) and emits run metadata, completing the flow

**Scenario: The job scope excludes heavy standalone sources**
- **Given** football and ESPN bronze assets are also registered in the code location
- **When** `medallion_hello_world` (whose selection is `AssetSelection.all()` minus the
  football and ESPN assets) runs
- **Then** only the hello-world chain materializes
- **And** the football / ESPN backfills are NOT swept in (they have their own jobs)

**Scenario: The daily schedule is defined but off by default**
- **Given** `medallion_daily` is registered with cron `0 6 * * *`
- **When** the code location loads
- **Then** the schedule exists but is stopped until toggled on in the UI, so no
  unattended run fires by default

### Capability: Layered validation at ingest

**Scenario: A malformed source record is rejected at the edge**
- **Given** the source API returns a record missing a required field or with an
  out-of-range `id` (`< 1`)
- **When** `raw_users` validates each record against the `User` Pydantic model
- **Then** validation raises immediately and no bronze Parquet is written from that
  run, rather than letting the bad record reach silver

**Scenario: The assembled frame is validated before it lands**
- **Given** the per-record Pydantic check passed and the records are flattened into a
  DataFrame
- **When** `bronze_users_schema` (Pandera, `strict=True`, `coerce=True`) validates the
  frame
- **Then** column presence, dtypes, nullability, `id` uniqueness/`>=1`, and `email`
  containing `@` are enforced before `to_parquet`
- **And** only a frame that passes all checks is written to bronze

**Scenario: Warehouse-level data assertions run inside the build**
- **Given** silver/gold models have dbt tests (`not_null`/`unique` on `user_id`,
  `city`, `user_count`; the singular `assert_positive_user_count`)
- **When** the dbt assets run `dbt build` (run + test)
- **Then** the tests execute inline and a failing assertion fails the asset, so data
  correctness is gated in the warehouse as well as at ingest

### Capability: Parquet-persisted medallion layers with a single DuckDB writer

**Scenario: dbt owns the warehouse; Python reads files, not the warehouse**
- **Given** dbt is the only process that opens the warehouse read-write during a run
- **When** the gold aggregate must be published to downstream consumers
- **Then** dbt's `external` materialization writes `gold/users_by_city.parquet` as part
  of the build (single writer)
- **And** `publish_gold_parquet` reads that **file** via DuckDB `read_parquet`, never
  the live warehouse table, so there is no second-writer catalog race

**Scenario: Silver reads bronze as an external Parquet source**
- **Given** bronze landed `data/bronze/users.parquet`
- **When** dbt builds `stg_users`
- **Then** it reads the bronze Parquet directly via the dbt `bronze.users` source
  (`external_location` pointing at the file), not a warehouse-loaded copy

**Scenario: Bronze→silver lineage is drawn in the Dagster asset graph**
- **Given** the dbt `users` source maps to the Dagster `raw_users` asset key
- **When** the code location loads with `BronzeAwareTranslator`
- **Then** Dagster draws the `raw_users → silver/stg_users → gold/... → publish`
  lineage edges so the medallion flow is a connected graph

### Capability: In-app OpenTelemetry tracing

**Scenario: Spans are produced across the flow with HTTP auto-instrumentation**
- **Given** telemetry is configured once when the code location is imported
- **When** the flow runs
- **Then** the ingest produces an `ingest.raw_users` span with a child `requests` HTTP
  span (auto-instrumented), and the publish produces a `publish.gold_users_by_city`
  span, all under service `data-platform`

**Scenario: Startup never depends on a reachable collector**
- **Given** no OTLP collector is reachable at `OTEL_EXPORTER_OTLP_ENDPOINT`
- **When** the app starts and runs
- **Then** the exporter emits harmless `Connection refused` retries and spans are
  dropped, but the application still starts and the flow still completes (no
  `depends_on` edge on a collector in compose)

### Capability: Typed, single-source runtime configuration

**Scenario: All components read the same env-driven config**
- **Given** `config.py` exposes typed `pydantic-settings` fields (`api_base_url`,
  `data_dir`, `duckdb_path`, `otel_exporter_otlp_endpoint`, `otel_service_name`,
  `deployment_environment`, …) with `.env` support
- **When** Python, dbt (`env_var('DATA_DIR')` / `env_var('DUCKDB_PATH')`), and the
  containers read configuration
- **Then** they resolve from the same environment values, so paths and endpoints stay
  in sync across the stack

### Capability: Base-plus-one-overlay Compose topology

**Scenario: The base is environment-neutral**
- **Given** `docker-compose.yml` defines only the app services and sets no OTLP
  endpoint and no telemetry network
- **When** it is brought up alone
- **Then** it carries no environment-specific wiring; an overlay must supply where
  telemetry goes and any live-reload/network behaviour

**Scenario: Dev overlay brings up self-hosted SigNoz and live reload**
- **Given** `COMPOSE_FILE=docker-compose.yml:docker-compose.signoz.yml`
- **When** `docker compose up -d` runs
- **Then** the full vendored SigNoz stack starts (ClickHouse, Zookeeper, the SigNoz
  UI/query service on `:8080`, its OTLP collector on `:4317/:4318`, a one-shot schema
  migrator)
- **And** the app services export OTLP to `signoz-otel-collector:4317`, join
  `signoz-net`, and bind-mount `./src` `./dbt` `./notebooks` over the baked image for
  live reload

**Scenario: Prod overlay exports to an external collector and fails fast if unset**
- **Given** `COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml`
- **When** compose is brought up
- **Then** no SigNoz is started and the apps export to
  `${OTEL_EXPORTER_OTLP_ENDPOINT}`
- **And** if `OTEL_EXPORTER_OTLP_ENDPOINT` is unset compose **fails fast** (the `:?`
  variable form) with a message telling the operator to set it
- **And** there are no source bind-mounts, so prod runs the code baked into the image

**Scenario: Remote overlay joins shared sports-quant infrastructure**
- **Given** `COMPOSE_FILE=docker-compose.yml:docker-compose.remote.yml` on the home
  server
- **When** the stack is deployed (`docker compose up -d --build`)
- **Then** the app services join the external `sports-quant` network, export to the
  shared `signoz-otel-collector:4317` over gRPC, point at the shared `redis:6379`, and
  run with `DEPLOYMENT_ENVIRONMENT=remote` and per-service `OTEL_SERVICE_NAME`s
  (`ingestion-dagster-webserver`, `ingestion-dagster-daemon`, `ingestion-jupyter`)
- **And** the Dagster UI is published on the host port from `${DAGSTER_UI_PORT:-3000}`
  (set to `3002` on the remote host) to avoid colliding with other services

**Scenario: Remote port mapping is inherited from the base, not redefined**
- **Given** the base maps the Dagster UI port via `${DAGSTER_UI_PORT:-3000}:3000`
- **When** the remote overlay is layered on (after `0a49ed1`)
- **Then** the remote overlay does NOT re-declare a `ports:` block for
  `dagster-webserver` (the earlier `ports: !reset` was removed), so the host port
  comes solely from the base's `${DAGSTER_UI_PORT}` mapping

### Capability: Vendored, pinned SigNoz backend

**Scenario: The SigNoz stack is a reproducible pinned snapshot**
- **Given** the SigNoz config is vendored under `signoz/` and image tags are pinned via
  `VERSION` / `OTELCOL_TAG` in `.env`
- **When** the dev stack runs
- **Then** it uses the pinned versions (default `v0.116.1` / `v0.144.2`) and writes
  traces/metrics/logs into ClickHouse, queryable in the UI on `:8080`
- **And** it does not auto-update (upstream deprecated Compose); upgrading means
  bumping the tags and re-pulling `signoz/**` from the matching git tag

## 6. Edge cases & error handling

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | Source API returns a record failing the Pydantic `User` contract | Validation raises in `raw_users`; the run fails and no bronze Parquet is written for that run (no silent drop, no defaults). |
| E2 | Assembled frame violates the Pandera `bronze_users_schema` (missing column, bad dtype, dup `id`, `email` without `@`) | `strict=True` frame validation raises before `to_parquet`; nothing lands. |
| E3 | A gold city row has `user_count < 1`, or a `not_null`/`unique` test fails | The inline dbt test fails the `dbt build`, failing the Dagster asset. |
| E4 | `dbt build` from a clean checkout before any ingest | `stg_users` errors with `IO Error: No files found … users.parquet` because bronze hasn't materialized — environmental, not a regression; run the ingest first. |
| E5 | No OTLP collector reachable at the configured endpoint | App starts and the flow completes; the exporter logs harmless `Connection refused` retries and drops spans (startup never depends on the collector). |
| E6 | Prod overlay with `OTEL_EXPORTER_OTLP_ENDPOINT` unset | Compose fails fast at parse/up time with the `:?` error message instructing the operator to set the endpoint. |
| E7 | A second process opens `warehouse.duckdb` read-write during a dbt run | Forbidden — it cannot see dbt's un-checkpointed WAL writes and gets phantom "schema does not exist" catalog errors. Derived data must be produced inside dbt (the `external` model) and read as a file. |
| E8 | Dagster daemon and webserver load different workspaces | A queued run launches into an empty workspace and fails with `DagsterCodeLocationNotFoundError`. Both services must load the same `workspace.yaml`. |
| E9 | Host port `3000` already taken on the remote host (e.g. another Dagster / Grafana) | Set `DAGSTER_UI_PORT` (e.g. `3002`) so the base port mapping publishes a non-conflicting host port. |
| E10 | `requests` already instrumented in a re-imported subprocess | `RequestsInstrumentor().instrument()` is wrapped in a try/except that logs and continues; configuration is idempotent (`_configured` guard). |
| E11 | SigNoz `init-clickhouse` cannot reach GitHub on first boot | It downloads the histogram-quantile UDF binary on first run and needs internet; without it the one-shot init fails (operator concern, documented in compose). |

## 7. Acceptance criteria

- [ ] AC1 — `medallion_hello_world` runs end to end producing `data/bronze/users.parquet`,
      the dbt silver view, the dbt gold table, `data/gold/users_by_city.parquet`, and a
      successful `publish_gold_parquet` materialization.
- [ ] AC2 — Every source record is validated by the `User` Pydantic model and the
      assembled frame by the `bronze_users_schema` Pandera schema (`strict=True`)
      before any bronze Parquet is written.
- [ ] AC3 — dbt models carry tests that run inline via `dbt build` (the silver/gold
      `not_null`/`unique` tests and `assert_positive_user_count`).
- [ ] AC4 — The gold aggregate is published by dbt's `external` materialization to
      `gold/users_by_city.parquet`, and `publish_gold_parquet` reads that **file** via
      DuckDB `read_parquet`, never the live warehouse table.
- [ ] AC5 — Each medallion layer is persisted as Parquet (bronze users; gold export).
- [ ] AC6 — `BronzeAwareTranslator` maps the dbt `users` source to `AssetKey(["raw_users"])`
      so Dagster draws the bronze→silver→gold lineage.
- [ ] AC7 — Tracing produces an `ingest.raw_users` span with a child `requests` HTTP
      span and a `publish.gold_users_by_city` span under service `data-platform`, and
      the app starts/runs even with no collector reachable.
- [ ] AC8 — All runtime config is typed `pydantic-settings` in `config.py`, and dbt
      reads `DATA_DIR`/`DUCKDB_PATH` via `env_var(...)`.
- [ ] AC9 — `docker-compose.yml` is environment-neutral (no OTLP endpoint, no telemetry
      network in the app config); telemetry wiring is supplied only by an overlay.
- [ ] AC10 — `COMPOSE_FILE` selects exactly one of: dev (`docker-compose.signoz.yml`),
      prod (`docker-compose.prod.yml`), remote (`docker-compose.remote.yml`).
- [ ] AC11 — The dev overlay starts the full pinned self-hosted SigNoz stack (UI on
      `:8080`, collector on `:4317/:4318`) and wires apps to it with live-reload
      bind-mounts on `signoz-net`.
- [ ] AC12 — The prod overlay starts no SigNoz, exports to
      `${OTEL_EXPORTER_OTLP_ENDPOINT}`, and fails fast if it is unset.
- [ ] AC13 — The remote overlay joins the external `sports-quant` network, exports to
      the shared `signoz-otel-collector:4317`, and publishes the Dagster UI on
      `${DAGSTER_UI_PORT:-3000}`; it does NOT re-declare a `ports:` block for
      `dagster-webserver` (port mapping is inherited from the base).
- [ ] AC14 — The SigNoz stack is a pinned snapshot (`VERSION`/`OTELCOL_TAG`), vendored
      under `signoz/`, and does not auto-update.

## 8. Things to be aware of / constraints

- **DuckDB is single-writer; dbt owns the warehouse file.** Do not add a second
  process that opens the warehouse read-write during a run (phantom catalog errors
  from un-checkpointed WAL). Produce derived data inside dbt and read the resulting
  **file** in Python (CLAUDE.md "Non-obvious constraints"; E7).
- **`dbt build` is not green from a clean checkout** — silver reads the bronze Parquet
  that the Dagster ingest must materialize first (E4).
- **dbt model Dagster asset keys are prefixed by their schema folder only** (e.g.
  `gold/dim_users_by_city` → `AssetKey(["gold", "dim_users_by_city"])`); deeper
  subfolders are dropped, and the dbt node *selector* differs from the asset key.
  Resolve keys from the manifest, not by guessing.
- **The bronze→silver edge is wired by `BronzeAwareTranslator`** mapping the dbt
  `users` source to `AssetKey(["raw_users"])`; renaming the bronze asset or the dbt
  source breaks lineage.
- **Do not add `from __future__ import annotations` to Dagster asset modules** —
  Dagster introspects `context`/return annotations at runtime; stringized annotations
  raise `DagsterInvalidDefinitionError`. (Note `config.py` / `otel.py` / `schemas.py`
  are non-asset modules and legitimately do use it.)
- **OTel collector is optional at startup** — never make the app depend on a reachable
  collector (E5); no `depends_on` collector edge in compose.
- **Compose is base + exactly one overlay, selected by `COMPOSE_FILE`.** Overlay merge
  relies on Compose semantics: `environment` merges by key, `volumes` concatenate,
  `networks` is set by the overlay. Keep env-specific values (endpoint, networks,
  live-reload mounts) out of the base.
- **The daemon and webserver must load the same `workspace.yaml`** or queued runs fail
  with `DagsterCodeLocationNotFoundError` (E8).
- **Python is pinned `>=3.12,<3.13`** and the venv lives at `/opt/venv` in Docker so
  the `./src` bind-mount does not shadow installed deps.
- **The SigNoz stack is a deliberately pinned snapshot** (`VERSION`/`OTELCOL_TAG`); it
  is heavy (ClickHouse + Zookeeper ~2–3 GB RAM) and `init-clickhouse` needs internet
  on first boot (E11).
- **Secrets** — `JUPYTER_TOKEN` and `SIGNOZ_JWT_SECRET` default to placeholders;
  change them before exposing anything beyond localhost.
- **Heavy/standalone sources get their own jobs** and are subtracted from
  `AssetSelection.all()` so the hello-world job and daily schedule never trigger them.

## 9. Assumptions

- The hello-world `users` flow against `jsonplaceholder.typicode.com` is intended as a
  reference/demonstration of the medallion mechanics, not a production data product —
  inferred from the source default and the "hello-world" naming.
- The three-gate validation layering (Pydantic → Pandera → dbt tests) is a deliberate
  defense-in-depth choice, inferred from the consistent pattern and module docstrings.
- "Single DuckDB writer owned by dbt" is a hard design rule, not a coincidence — the
  `external` materialization + file-read publish pattern was chosen specifically to
  avoid cross-process races (stated in `gold.py` and CLAUDE.md).
- The base compose was made environment-neutral specifically so the same application
  image runs unchanged across dev/prod/remote, with only telemetry/network wiring
  varying by overlay (inferred from the overlay structure and comments).
- The current warehouse profile uses **DuckLake** (Postgres-catalogued) rather than the
  plain DuckDB file present at these source commits; the single-writer-owned-by-dbt and
  Parquet-export behaviours this spec describes still hold. The DuckLake migration is a
  later, separately-specified change (see §10).

## 10. Open questions

All items below are **unverified intent** — the code is already implemented, so none
block implementation; they are flagged for a human to confirm or correct.

- **Daily schedule cadence (`0 6 * * *`)** — the specific 06:00 time and the
  ship-it-off-by-default decision: intent not recoverable from the history beyond the
  inline comment "stopped by default; toggle on in the UI".
- **Choice of SigNoz over other OTel backends** — why self-hosted SigNoz specifically
  (vs Jaeger/Tempo/Grafana stack or SigNoz Cloud) is not recorded; the cloud option
  was present in earlier `.env` and removed in `92fbb47`.
- **Pinned versions `v0.116.1` / `v0.144.2`** — the rationale for these exact versions
  (vs latest-at-the-time) is not stated beyond "upstream deprecated Compose".
- **Remote host specifics** — the hard-coded `192.168.1.166`, `sports-quant` network
  name, and `3002` UI port live in the `deploy` skill; whether these are meant to be
  the canonical deployment target or one example environment is not stated.
- **Dangling/aspirational overlay env vars** — two cases where the compose overlay sets
  an env var no code currently reads: (1) `OTEL_EXPORTER_OTLP_PROTOCOL: grpc` on the
  remote overlay (the exporter is hard-wired to OTLP/gRPC in `otel.py`, choosing
  `insecure` from the URL scheme); (2) `REDIS_HOST`/`REDIS_PORT` on the remote overlay
  (the only Redis consumer, the Matchbook ingestor, reads `MATCHBOOK_REDIS_HOST`/
  `MATCHBOOK_REDIS_PORT` instead — see spec 005). Whether these are aspirational or for
  a future switch is unverified.
- **Whether the DuckLake migration supersedes the single-DuckDB-file detail of this
  spec intentionally** — confirmed in code that the profile changed; the *behavioural*
  invariant (dbt-owned single writer, Parquet export, file-read publish) is assumed
  preserved on purpose but should be confirmed against specs `002-ducklake-ui` and
  `003-ducklake-model-migration` (which together wired and then switched to DuckLake).

## 11. Traceability

| Source commit(s) | Behaviour introduced | Scenarios | Spec acceptance criteria |
|------------------|----------------------|-----------|--------------------------|
| `6b82373` (scaffold medallion platform) | End-to-end hello-world flow; layered Pydantic/Pandera/dbt-test validation; Parquet at every layer; single-writer DuckDB owned by dbt with file-read publish; bronze→silver lineage via `BronzeAwareTranslator`; in-app OTel tracing; typed `pydantic-settings` config | All "medallion flow", "layered validation", "Parquet-persisted layers", "OTel tracing", "typed config" scenarios | AC1–AC8 |
| `92fbb47` (split compose into neutral base + dev/prod overlays; vendor pinned SigNoz) | Environment-neutral base; `COMPOSE_FILE` overlay selection; dev SigNoz overlay (full pinned stack + live reload); prod external-collector overlay (fails fast if endpoint unset) | "The base is environment-neutral", "Dev overlay brings up self-hosted SigNoz and live reload", "Prod overlay exports to an external collector and fails fast", "The SigNoz stack is a reproducible pinned snapshot" | AC9, AC10, AC11, AC12, AC14 |
| `0ec9a2b` (remote deployment overlay + deploy skill) | Remote overlay joining `sports-quant`, exporting to shared `signoz-otel-collector`, per-service OTEL names, configurable `DAGSTER_UI_PORT`; base port mappings made env-var-driven | "Remote overlay joins shared sports-quant infrastructure" | AC10, AC13 |
| `0a49ed1` (fix remote compose ports inheritance) | Removed the remote overlay's `ports: !reset` so the host port is inherited from the base's `${DAGSTER_UI_PORT}` mapping | "Remote port mapping is inherited from the base, not redefined" | AC13 |
