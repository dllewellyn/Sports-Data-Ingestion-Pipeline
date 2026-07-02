# ARCHITECTURE

This file is the **map of the codebase**: where code lives, what each package
owns, which way dependencies are allowed to point, and how to add new code
without breaking the layering. It is meant to orient a new contributor (human or
agent) before they touch a file.

It deliberately does **not** cover:

- **Component relationships / runtime topology** — see the C4 diagrams in
  [`architecture/`](architecture/).
- **The end-to-end data flow** (sources → bronze → canonical → conform →
  enrichment → gold) — see [`data flows.md`](data%20flows.md).
- **The relational data model** (canonical entities + provider link tables) — see
  [`ERD.md`](ERD.md).
- **Non-obvious runtime constraints and failure modes** (DuckDB single-writer,
  asset-key prefixing, `from __future__` bans, version pins) — see the
  "Non-obvious constraints" section of [`CLAUDE.md`](CLAUDE.md). Those are
  *operational gotchas*; this file is *structural*.
- **How to run things** — see [`README.md`](README.md) and `CLAUDE.md`.

---

## 1. System at a glance

A medallion (bronze → canonical → marts) data pipeline. Dagster orchestrates;
dbt-duckdb transforms and tests into a PostgreSQL-backed DuckLake catalog; bronze
is persisted as Parquet; work is traced with OpenTelemetry into a self-hosted
SigNoz.

Four bronze sources feed one canonical model:

```
ESPN API ─────────▶ bronze/espn ─────────────┐
Matchbook events ─▶ bronze/matchbook_events ──┤  dbt staging ─▶ dbt intermediate ─▶ dbt marts ─▶ Parquet exports
Matchbook odds ───▶ bronze/matchbook (Redis) ─┤  (views over    (canonical league/   (analytics,    (notebooks +
football-data ────▶ bronze/football_{main,    ┘   bronze)         season/team/match    e.g. completed  MCP read the
                                    extra})                       + provider links)    matches)        files)
```

**ESPN is the union base for match identity.** Non-ESPN providers are linked
onto (or mint) canonical matches by the **conform** layer — a symmetric,
cross-provider layer (see §4b); Matchbook odds drive **T-60** favourite
enrichment. The pipeline is one Dagster **code location**
(`src/data_platform`) plus one dbt **project** (`dbt/data_platform`), stitched
together so dbt models appear as Dagster assets.

---

## 2. Package & directory structure

```
src/data_platform/              # The Dagster code location (all orchestration Python)
├── definitions.py              # Composition root: assembles assets, jobs, schedules, resources
├── config.py                   # Typed settings (pydantic-settings) — the only config source
├── otel.py                     # Telemetry bootstrap + tracer accessor
├── models/                     # Data contracts (no orchestration, no I/O)
│   ├── schemas.py              #   Pydantic v2 — per-record edge validation
│   └── validation.py           #   Pandera — frame-level validation
├── football/                   # football-data.co.uk bronze source
│   ├── registry.py season.py           #   leaves: league whitelist, season classification
│   ├── discovery.py http_client.py     #   network edge: link discovery + throttled client
│   ├── ingest.py                       #   Dagster-free engine: fetch → validate → write
│   └── asset_results.py                #   result/report dataclasses for asset metadata
├── espn/                       # ESPN soccer bronze source (mirrors football/)
│   ├── registry.py season.py discovery.py http_client.py asset_results.py
│   └── ingest.py                       #   scoreboard JSON → bronze Parquet engine
├── matchbook/                  # Matchbook: events + odds + enrichment
│   ├── ingest.py                       #   events REST API → bronze engine
│   ├── t60.py                          #   T-60 favourite enrichment engine (§4b)
│   └── ingestor/                       #   real-time Redis odds → Parquet daemon
│       ├── direct_parquet_consumer.py  #     subscribe, dedup, buffer, flush
│       └── schema.py                   #     PyArrow schema for odds ticks
├── conform/                    # Symmetric cross-provider conform layer (§4b)
│   ├── resolve.py                      #   shared identity authority (season→league→team→match)
│   ├── matchbook.py                    #   Matchbook events → resolve/link/mint → additions Parquet
│   ├── football_data.py                #   football-data conform (scaffolded)
│   ├── matchbook_scoring.py            #   fuzzy score + kickoff tolerance
│   ├── matchbook_event_name.py         #   parse "Home vs Away"
│   └── matchbook_overrides.py          #   load human-review decisions
├── mcp/                        # MCP server: read-only lakehouse catalogue inspector
│   └── inspector.py server.py __main__.py
└── assets/                     # Dagster assets — thin wrappers over the engines above
    ├── dbt.py                  #   dbt_models + BronzeAwareTranslator (staging/intermediate/marts)
    ├── ingestion/              #   bronze: espn, matchbook_events, football_{main,extra}
    └── intermediate/           #   matchbook_conform, matchbook_t60 (write silver Parquet for dbt)

dbt/data_platform/              # The dbt project (all SQL transformation + warehouse tests)
├── dbt_project.yml profiles.yml       # DuckLake target; nodes routed with +database: lake
└── models/
    ├── staging/                #   views over bronze Parquet (stg_espn_events, stg_matchbook_odds)
    ├── intermediate/           #   canonical league/season/team/match + provider *_link tables
    └── marts/                  #   core/fct_completed_matches + exports/*_export (external Parquet)
```

The two top-level code trees — `src/data_platform/` (Python/orchestration) and
`dbt/data_platform/` (SQL/transformation) — are the architectural spine.
Everything else (`architecture/` C4 diagrams, `data/` Parquet lake + DuckLake,
`signoz/` telemetry stack, `notebooks/`, `investigations/`) is config, output,
docs, or scratch.

---

## 3. Layering & dependency rules

The medallion layers are the primary structure. **Dependencies flow strictly
downstream; a layer never imports or reads from a layer above it.**

| Layer | Owned by | Reads | Writes | Validation gate |
| --- | --- | --- | --- | --- |
| **Bronze** | `assets/ingestion/*` (+ source helper packages `football/`, `espn/`, `matchbook/`) | Source APIs / websites / Redis stream | `data/bronze/**/*.parquet` | Pydantic (record) → Pandera (frame) |
| **Staging** | `dbt/.../models/staging` | bronze Parquet (external source) | DuckLake view (via dbt) | dbt tests |
| **Intermediate (canonical)** | `dbt/.../models/intermediate` **and** `assets/intermediate/*` (conform, T-60) | staging; canonical Parquet exports | DuckLake tables (dbt); `data/silver/*.parquet` (Python) | dbt tests |
| **Marts (gold)** | `dbt/.../models/marts` | intermediate | DuckLake table + `data/gold/*.parquet` (external export) | dbt tests |
| **Consume** | `notebooks/`, `mcp/` inspector | marts Parquet **files** | — | — |

Hard rules that define the architecture:

1. **The network edge lives only in the bronze layer.** The ingest assets under
   `assets/ingestion/` plus their source helper packages (`football/`, `espn/`,
   `matchbook/` — discovery, throttled HTTP clients, the Redis odds consumer) are
   the sole part of the system that touches the outside world. No module outside
   the bronze layer may make outbound HTTP/stream calls. New sources are new
   bronze assets, never network calls bolted onto downstream code.
2. **Validate at the boundary, before data lands.** Every record entering the
   system is parsed by a Pydantic model (`models/schemas.py`); the assembled frame
   is then checked by a Pandera schema (`models/validation.py`) before Parquet is
   written. Warehouse invariants are asserted by dbt tests. Three gates, in order.
3. **dbt owns the DuckLake catalog; Python reads and writes Parquet files, not
   catalog tables.** dbt materializes into DuckLake. Python assets (including the
   `assets/intermediate/*` conform + T-60 assets) read bronze/canonical Parquet
   and write their own Parquet; dbt then reads those files back in. No Python code
   opens a DuckLake connection, even read-only (see `CLAUDE.md`).
4. **`definitions.py` is the only composition root.** It is the single place that
   knows about all assets, jobs, schedules, and resources at once. Asset modules
   declare *what they are*; `definitions.py` decides *how they fit together*.
   Asset modules do not import each other — they express edges via
   `deps=[AssetKey(...)]`.

### Module dependency direction

```
definitions.py ──imports──▶ assets/*  ──imports──▶ football/ espn/ matchbook/ conform/ mcp/,
                                                    models/*, config, otel  (leaf-ward)
```

- `config.py` and `models/*` are **leaves**: they import nothing from `assets/`
  or `definitions.py`. `otel.py` depends only on `config.py`.
- Source packages (`football/`, `espn/`, `matchbook/`, `mcp/`) and the
  cross-provider `conform/` package hold the Dagster-free engines and helpers.
  They import `config`/`models`/`otel`, never `assets/` or `definitions.py`, and
  never each other (per-provider conform modules share only `conform/resolve.py`).
- `assets/*` modules are thin wrappers that read `settings`, call an engine, and
  emit Dagster metadata. Bronze→canonical→marts ordering is expressed through
  Dagster asset keys (and `BronzeAwareTranslator`), not Python imports.

---

## 4. Module responsibilities

| Module | Responsibility | May depend on | Must NOT |
| --- | --- | --- | --- |
| `definitions.py` | Compose the code location (assets, jobs, schedules, resources) | everything below | contain business/ingest logic |
| `config.py` | All typed runtime settings, env-driven | (stdlib, pydantic-settings) | call `os.getenv` ad hoc elsewhere |
| `otel.py` | Install tracer provider once; expose `get_tracer()` | `config` | own any pipeline logic |
| `models/schemas.py` | Pydantic contracts for incoming payloads + flattening | (pydantic) | do I/O or orchestration |
| `models/validation.py` | Pandera frame contracts | (pandera) | do I/O or orchestration |
| `football/`, `espn/` | A bronze source's engine + helpers: registry/season (leaves), discovery/http_client (network edge), `ingest.py` (fetch→validate→write engine) | `config`, `models`, `otel` | depend on `assets/` or another source |
| `matchbook/ingest.py` | Matchbook events REST → bronze engine (auth, paginate, flatten, validate, write) | `models`, `otel` | open a DuckLake connection |
| `matchbook/ingestor/` | Real-time Redis odds → Parquet daemon (subscribe, dedup, buffer, flush) | `config` | do transformation/joining |
| `conform/` | Symmetric cross-provider conform: per-provider modules (`matchbook.py`, `football_data.py`) resolve/link/mint via the shared `resolve.py` identity authority → four `<provider>_canonical_*_additions.parquet` + link/exception Parquet | `models`, `config` | write to DuckLake (§4b) |
| `conform/resolve.py` | Shared identity authority: season→league→team→match id resolution (seed-first) reused by every provider | `config` | open a DuckLake connection |
| `matchbook/t60.py` | Identify the pre-match favourite from odds ticks → Parquet | `config` | write to DuckLake |
| `mcp/` | Read-only lakehouse catalogue inspector (parses the dbt manifest) | `config` | mutate the warehouse |
| `assets/ingestion/*` | Thin Dagster wrappers over the bronze engines | source packages, `models`, `config`, `otel` | depend on other assets |
| `assets/intermediate/*` | Thin Dagster wrappers over conform + T-60 | `conform`, `matchbook`, `config` | reimplement transformation in Python |
| `assets/dbt.py` | Run/test dbt; map dbt source → bronze asset key for lineage | (dagster-dbt) | reimplement transformations in Python |

Transformation logic belongs in **dbt SQL**, not Python. Python assets handle
ingest (the edge), linking/enrichment that dbt can't (fuzzy matching, favourite
detection), and consumption; everything else is dbt.

## 4b. Concepts (names not obvious from the file tree)

- **Conform** (`conform/`) — a **symmetric, cross-provider** layer. ESPN conforms
  in SQL and is the **union base** of the canonical `int_*` models; every other
  provider conforms in Python here (per-provider module — `matchbook.py`,
  `football_data.py`) and contributes canonical rows *additively*. A provider
  resolves each source event's whole `season → league → team` chain through the
  shared `resolve.py` identity authority (seed-first: `team_aliases`,
  `league_aliases`, then the `canonical_match_id` macro replica), fuzzy-matches
  team names + kickoff time (three confidence tiers) with human overrides, and
  **mints new canonical rows** when it knows a fixture ESPN doesn't. Each provider
  writes **four** `data/silver/<provider>_canonical_{match,team,league,season}_additions.parquet`
  files (bootstrap-written empty so the `int_*` `read_parquet` unions stay green
  before a provider mints anything) plus its resolved-links and unresolved-exception
  Parquet. dbt reads those files: `int_team`/`int_league`/`int_season`/`int_match`
  are each `ESPN base CTE UNION ALL read_parquet(<provider>_additions)`, keep-one
  on the id; the `int_*_link` tables read the resolved links. The Python conform
  modules **never open a DuckLake connection** — dbt owns the catalog.
- **T-60 enrichment** (`matchbook/t60.py`) — for each linked event, find the
  market favourite from the odds ticks in the window 45–75 min before kickoff
  (lowest back price = shortest odds), resolve that runner to a team, and write
  `favourite_team_id` per match. `int_match` left-joins the result.

---

## 5. Cross-cutting concerns

- **Configuration** — one `Settings` object in `config.py` (pydantic-settings),
  imported as `settings`. dbt reads the same values via `env_var(...)` in
  `profiles.yml` and the marts external export models. All components must agree on
  `DATA_DIR` / `DUCKDB_PATH` / `POSTGRES_CATALOG_URL`. Add new config as a typed
  field here, never as a scattered `os.getenv`.
- **Telemetry** — `otel.py` installs the tracer provider idempotently on import of
  the code location and auto-instruments `requests`. Engines open spans via
  `get_tracer()`. Telemetry is best-effort: a missing collector never blocks the
  pipeline.

---

## 6. How to add a new data source (extension guide)

Adding a dataset means adding a new medallion slice, layer by layer. Worked
references: the `football/` and `espn/` source packages.

1. **Contracts first (`models/`)** — add a Pydantic model for the incoming records
   and a Pandera schema for the assembled frame. Keep these leaf modules pure.
2. **Source package + engine** — add a `<provider>/` package with the Dagster-free
   ingest engine (fetch → validate with the step-1 contracts → atomic Parquet
   write) plus any discovery/HTTP helpers. This is the only place the new network
   call may live. Wrap the fetch in a span via `get_tracer()`.
3. **Bronze asset (`assets/ingestion/`)** — add a thin wrapper that reads
   `settings`, calls the engine, and emits Dagster metadata.
4. **dbt staging + intermediate** — register the new bronze Parquet as a dbt
   `source`, add a `stg_<name>` view under `models/staging/`, and (if it links to
   the canonical model) an `int_<name>_*_link` model under `models/intermediate/`.
   To get Dagster lineage from the bronze asset into dbt, extend the translator in
   `assets/dbt.py` to map the source name to the bronze `AssetKey`.
5. **Marts (optional)** — add analytics under `models/marts/`. If a consumer needs
   the result as a file, add an `external` export model so Python/notebooks read
   the file, not the catalog.
6. **Register in `definitions.py`** — add the new Python assets to `Definitions`,
   give heavy/standalone sources their own job (and exclude them from broad
   `AssetSelection`s), and add a schedule if it runs on a cadence.
7. **New settings** — add any new config (base URLs, paths) as typed fields in
   `config.py`.

If a step introduces a non-obvious runtime constraint or failure mode, record it
in `CLAUDE.md` (Non-obvious constraints) in the same change — not here. If it
changes the data flow, update `data flows.md`; if it changes the data model,
update `ERD.md`.

---

## 7. Keeping this file current

Update ARCHITECTURE.md when the **structure** changes: a new top-level package, a
new layer, a change to the dependency-direction rules, or a new module
responsibility. Routine model/asset additions that follow §6 do not need an edit.
Structural facts live here; runtime gotchas live in `CLAUDE.md`; component diagrams
live in `architecture/`; the data flow lives in `data flows.md`; the data model
lives in `ERD.md`.
