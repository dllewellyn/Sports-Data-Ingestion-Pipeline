# ARCHITECTURE

This file is the **map of the codebase**: where code lives, what each package
owns, which way dependencies are allowed to point, and how to add new code
without breaking the layering. It is meant to orient a new contributor (human or
agent) before they touch a file.

It deliberately does **not** cover:

- **Component relationships / runtime topology** — see the C4 diagrams in
  [`architecture/`](architecture/) (`c3_data_platform_components.md` is the
  current component view).
- **Non-obvious runtime constraints and failure modes** (DuckDB single-writer,
  asset-key prefixing, `from __future__` bans, version pins) — see the
  "Non-obvious constraints" section of [`CLAUDE.md`](CLAUDE.md). Those are
  *operational gotchas*; this file is *structural*. Where a structural rule
  exists only because of a runtime constraint, it links there rather than
  restating it.
- **How to run things** — see [`README.md`](README.md) and `CLAUDE.md`.

---

## 1. System at a glance

A medallion (bronze → silver → gold) data pipeline. Dagster orchestrates;
dbt-duckdb transforms and tests; every layer is persisted as Parquet; work is
traced with OpenTelemetry into a self-hosted SigNoz.

```
raw_users ──▶ silver/stg_users ──▶ gold/dim_users_by_city ──▶ gold/users_by_city_export ──▶ publish_gold_parquet
 (Python asset)   (dbt view)          (dbt table)               (dbt external → Parquet)        (Python asset)
```

The pipeline is one Dagster **code location** (`src/data_platform`) plus one dbt
**project** (`dbt/data_platform`). The two are stitched together so that dbt
models appear as Dagster assets.

---

## 2. Package & directory structure

```
.
├── src/data_platform/          # The Dagster code location (all orchestration Python)
│   ├── definitions.py          # Composition root: assembles assets, jobs, schedules, resources
│   ├── config.py               # Typed settings (pydantic-settings) — the only config source
│   ├── otel.py                 # Telemetry bootstrap + tracer accessor
│   ├── models/                 # Data contracts (no orchestration, no I/O)
│   │   ├── schemas.py          #   Pydantic v2 — per-record edge validation
│   │   └── validation.py       #   Pandera — frame-level validation
│   ├── football/               # football-data.co.uk bronze source (Epic #1)
│   │   ├── registry.py         #   typed league whitelist (main + extra families)
│   │   ├── discovery.py        #   requests + regex whitelist-driven link discovery
│   │   ├── http_client.py      #   throttled, cache-aware HTTP client resource
│   │   └── season.py           #   current-season vs historical classification
│   └── assets/                 # Dagster assets, one module per medallion layer / source
│       ├── bronze.py           #   raw_users: a network edge (bronze layer)
│       ├── football_main.py    #   main family (mmz4281/<season>/<div>) bronze ingestor
│       ├── football_extra.py   #   extra family (new/<CODE>) bronze ingestor
│       ├── dbt.py              #   dbt_models + BronzeAwareTranslator (silver + gold)
│       └── gold.py             #   publish_gold_parquet: consumes the gold Parquet
│
├── dbt/data_platform/          # The dbt project (all SQL transformation + warehouse tests)
│   ├── dbt_project.yml         #   silver = view, gold = table (+ external Parquet export)
│   ├── profiles.yml            #   DuckLake target; reads POSTGRES_CATALOG_URL/DATA_DIR via env_var
│   ├── models/
│   │   ├── silver/             #   staging views over the bronze Parquet source
│   │   └── gold/               #   aggregates + the external (Parquet) export model
│   └── tests/                  #   singular data tests
│
├── architecture/               # C4 diagrams (Mermaid) — component/topology view
├── data/                       # Parquet lake + warehouse.duckdb (gitignored output)
├── signoz/                     # Vendored, pinned SigNoz stack config (telemetry backend)
├── notebooks/                  # Exploratory JupyterLab work (not part of the pipeline)
├── investigations/             # Time-boxed spikes feeding future work
└── user_stories/               # Backlog (synced with Azure DevOps via the .agents skills)
```

The two top-level code trees — `src/data_platform/` (Python/orchestration) and
`dbt/data_platform/` (SQL/transformation) — are the architectural spine.
Everything else is config, output, docs, or scratch.

---

## 3. Layering & dependency rules

The medallion layers are the primary structure. **Dependencies flow strictly
downstream; a layer never imports or reads from a layer above it.**

| Layer | Owned by | Reads | Writes | Validation gate |
| --- | --- | --- | --- | --- |
| **Bronze** | `assets/bronze.py`, `assets/football_*.py` (+ `football/` helpers) | Source API / website (HTTP) | `data/bronze/**/*.parquet` | Pydantic (record) → Pandera (frame) |
| **Silver** | `dbt/.../models/silver` | bronze Parquet (external source) | DuckLake view (via dbt) | dbt tests |
| **Gold** | `dbt/.../models/gold` | silver | DuckLake table + `data/gold/*.parquet` (via dbt) | dbt tests |
| **Publish** | `assets/gold.py` | gold Parquet **file** | run metadata + OTel span | — |

Hard rules that define the architecture:

1. **The network edge lives only in the bronze layer.** The bronze layer is the
   sole part of the system that touches the outside world: the ingest assets
   under `assets/` (`bronze.py`, `football_main.py`, `football_extra.py`) plus
   their discovery/HTTP helpers (the `football/` package — link discovery and the
   shared throttled HTTP client). No module outside the bronze layer may make
   outbound HTTP calls. New ingest sources are new bronze assets (and, if needed,
   their own source helper package), never network calls bolted onto silver/gold/
   publish code.
2. **Validate at the boundary, before data lands.** Every record entering the
   system is parsed by a Pydantic model (`models/schemas.py`); the assembled
   frame is then checked by a Pandera schema (`models/validation.py`) before it
   is written to Parquet. Warehouse-level invariants are asserted by dbt tests.
   Three complementary gates, in that order.
3. **dbt owns the DuckLake catalog; Python reads Parquet files, not catalog tables.** Cross-process
   readers (the publish asset, notebooks) read the **Parquet artifacts** dbt
   produces, never catalog tables directly. (This is a structural expression
   of the single-writer constraint documented in `CLAUDE.md`.)
4. **`definitions.py` is the only composition root.** It is the single place
   that knows about all assets, jobs, schedules, and resources at once. Asset
   modules declare *what they are*; `definitions.py` decides *how they fit
   together*. Asset modules do not import each other to wire dependencies — they
   express edges via `deps=[AssetKey(...)]`.

### Module dependency direction

```
definitions.py  ──imports──▶  assets/*  ──imports──▶  models/*, config, otel
                                                          (leaf modules)
```

- `config.py` and `models/*` are **leaves**: they import nothing from
  `assets/` or `definitions.py`. They are pure contracts/config and must stay
  that way so they are trivially reusable and testable.
- `otel.py` depends only on `config.py`.
- `assets/*` modules depend on `models/`, `config`, `otel`, and source helper
  packages like `football/` — **never on each other**. The bronze→silver→gold
  ordering is expressed through Dagster asset keys (and the `BronzeAwareTranslator`),
  not through Python imports.
- `football/` is a bronze-layer **source helper package**: `registry`/`season` are
  leaves (no I/O); `discovery` and `http_client` own this source's network edge.
  It imports `config` (and `season`), never `assets/` or `definitions.py`.

---

## 4. Module responsibilities

| Module | Responsibility | May depend on | Must NOT |
| --- | --- | --- | --- |
| `definitions.py` | Compose the code location (assets, jobs, schedules, resources) | everything below | contain business/ingest logic |
| `config.py` | All typed runtime settings, env-driven | (stdlib, pydantic-settings) | call `os.getenv` ad hoc elsewhere |
| `otel.py` | Install tracer provider once; expose `get_tracer()` | `config` | own any pipeline logic |
| `models/schemas.py` | Pydantic contracts for incoming payloads + flattening | (pydantic) | do I/O or orchestration |
| `models/validation.py` | Pandera frame contracts | (pandera) | do I/O or orchestration |
| `assets/bronze.py` | Ingest + validate + land bronze Parquet | `models`, `config`, `otel` | depend on other assets |
| `football/registry.py` | Typed league whitelist (11 main + 16 extra), family-tagged; single source of truth for discovery | (stdlib) | do I/O, network, or hold ad-hoc URLs elsewhere |
| `football/discovery.py` | Whitelist-driven `requests`+regex link discovery → deterministic, de-duped, family-tagged CSV URLs | `registry`, `http_client`, `config` | use BeautifulSoup; emit off-list/noise links |
| `football/http_client.py` | Shared `ConfigurableResource`: 0.4 s pacing, within-run cache (historical only), artifact-presence skip-existing, bounded polite retry | `config`, `season` | be used by any non-bronze code |
| `football/season.py` | Classify a file current-season vs historical from its season token + injected run date | (stdlib) | read a hidden global clock |
| `assets/football_main.py` | Main-family (latin-1) bronze ingestor; one Parquet per `mmz4281` file | `football`, `models`, `config`, `otel` | depend on other assets |
| `assets/football_extra.py` | Extra-family (utf-8-sig) bronze ingestor; one Parquet per `new/<CODE>` file | `football`, `models`, `config`, `otel` | depend on other assets |
| `assets/dbt.py` | Run/test dbt; map dbt source→bronze asset key for lineage | (dagster-dbt) | reimplement transformations in Python |
| `assets/gold.py` | Read published gold Parquet; attach metadata + span | `config`, `otel` | open the warehouse read-write |

Transformation logic belongs in **dbt SQL**, not Python. Python assets handle
ingest (the edge) and publish (the consumer); everything in between is dbt.

---

## 5. Cross-cutting concerns

- **Configuration** — one `Settings` object in `config.py` (pydantic-settings),
  imported as `settings`. dbt reads the same values via `env_var(...)` in
  `profiles.yml` and the gold external model. All components must agree on
  `DATA_DIR` / `DUCKDB_PATH`. Add new config as a typed field here, never as a
  scattered `os.getenv`.
- **Telemetry** — `otel.py` installs the tracer provider idempotently on import
  of the code location and auto-instruments `requests`. Assets open spans via
  `get_tracer()`. Telemetry is best-effort: a missing collector never blocks the
  pipeline.

---

## 6. How to add a new data source (extension guide)

Adding a dataset means adding a new medallion slice, layer by layer, respecting
the rules above. Worked reference: the in-flight football-data.co.uk ingestion
(`investigations/` + `architecture/football-data-ingestion.md`).

1. **Contracts first (`models/`)** — add a Pydantic model for the incoming
   records and a Pandera schema for the assembled frame. Keep these leaf modules
   pure (no I/O).
2. **Bronze asset (`assets/`)** — add a new asset module (or a new asset in an
   existing bronze module) that fetches, validates with the contracts from step
   1, and writes `data/bronze/<name>.parquet`. This is the only place the new
   network call may live. Wrap the fetch in a span via `get_tracer()`.
3. **dbt source + silver model** — register the new bronze Parquet as a dbt
   `source`, add a `stg_<name>` view under `models/silver/`, and add schema
   tests. If you want Dagster lineage from the bronze asset into dbt, extend the
   translator in `assets/dbt.py` to map the new source name to the bronze
   `AssetKey` (mirroring how `users` maps to `raw_users`).
4. **Gold model(s)** — add aggregates under `models/gold/`. If a downstream
   consumer needs the result as a file, add an `external` (Parquet) export model
   so Python reads the file, not the warehouse.
5. **Publish asset (optional)** — if Python must consume the gold output, add an
   asset that `deps` on the gold model's **prefixed** asset key
   (`AssetKey(["gold", "<model>"])`) and reads the exported Parquet.
6. **Register in `definitions.py`** — add the new Python assets to
   `Definitions(...)`. dbt models are picked up automatically via `@dbt_assets`.
7. **New settings** — add any new config (base URLs, paths) as typed fields in
   `config.py`.

If a step introduces a non-obvious runtime constraint or failure mode, record it
in `CLAUDE.md` (Non-obvious constraints) in the same change — not here.

---

## 7. Keeping this file current

Update ARCHITECTURE.md when the **structure** changes: a new top-level package,
a new layer, a change to the dependency-direction rules, or a new module
responsibility. Routine model/asset additions that follow §6 do not need an edit.
Structural facts live here; runtime gotchas live in `CLAUDE.md`; component
diagrams live in `architecture/`.
