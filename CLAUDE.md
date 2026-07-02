# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install deps (creates .venv; respects uv.lock and .python-version)
uv sync

# Run the Dagster UI locally (auto-runs `dbt parse` to build the manifest)
PYTHONPATH=src DATA_DIR="$PWD/data" DUCKDB_PATH="$PWD/data/warehouse.duckdb" \
  DAGSTER_HOME="$PWD/.dagster" uv run dagster dev -m data_platform.definitions

# Run a source flow headless. `job execute` does NOT build the dbt
# manifest, so parse first or the import fails at @dbt_assets decoration time:
( cd dbt/data_platform && uv run --project ../.. dbt parse --profiles-dir . )
PYTHONPATH=src DATA_DIR="$PWD/data" DUCKDB_PATH="$PWD/data/warehouse.duckdb" \
  DAGSTER_HOME="$PWD/.dagster" \
  uv run dagster job execute -m data_platform.definitions -j espn_ingestion

# dbt directly (run a single model / test from the dbt project dir)
cd dbt/data_platform
uv run --project ../.. dbt build --select stg_espn_events     # one model + its tests
uv run --project ../.. dbt test  --select int_match           # tests only

# Run dbt WITHOUT the live catalog, via a scratch file-backed DuckLake. When the
# Docker `ducklake-catalog` (Postgres) is unreachable, point --profiles-dir at a
# scratch profile whose `path:` is `ducklake:<dir>/catalog.ducklake` (a local FILE,
# not Postgres) plus a schema-correct bronze fixture — this runs real materializations
# and tests locally. Use `--threads 1` (threads>1 triggers a nondeterministic
# `__dbt_tmp` catalog-qualification race on file-backed DuckLake) and keep it off
# `warehouse.duckdb` (single-writer lock).

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
>
> The relational **data model** (canonical entities + provider linking tables) is
> documented in [`ERD.md`](ERD.md) — it is living documentation: when you add or
> change a canonical/link table (or a dbt model under `models/intermediate/int_*`),
> update `ERD.md` in the same commit. Note `ERD.md` was ported from the upstream
> Postgres gaming-engine; this repo materializes that model in DuckLake (see the
> storage-engine note in `ERD.md` and the constraint below).

Medallion pipeline orchestrated by Dagster, transformed/tested by dbt on DuckDB,
every layer persisted as Parquet, traced via OpenTelemetry → SigNoz.

```
sources ──▶ bronze Parquet ──▶ silver/staging (dbt) ──▶ intermediate/canonical (dbt + Python) ──▶ marts/gold (dbt)
(ESPN,       assets/ingestion/*  stg_espn_events,         int_{league,season,team,match},          fct_completed_matches
 Matchbook,  requests+Pydantic   stg_matchbook_odds       int_*_link, matchbook_conform + t60      + *_export (external Parquet)
 football)   +Pandera                                     [dbt tests + relationships]              [dbt tests]
```

- **Edge of the system is `assets/ingestion/*`** — the only assets that touch the
  network. Validation is layered: Pydantic (`models/schemas.py`) per record →
  Pandera (`models/validation.py`) on the frame → dbt tests in the warehouse.
- **dbt lineage surfaces as Dagster assets** via `@dbt_assets` in `assets/dbt.py`.
  The dbt project lives under `dbt/data_platform/`; staging reads the bronze Parquet
  as an external source, intermediate/marts build the canonical model on top.

### Non-obvious constraints (these caused real bugs — preserve them)

- **DuckDB single-writer constraint applies to `warehouse.duckdb` only (applies to warehouse.duckdb only; DuckLake-managed tables support concurrent access).** Do NOT open `warehouse.duckdb` read-write from a second process/Dagster step — a separate process cannot see dbt's un-checkpointed WAL writes and gets phantom "schema does not exist" catalog errors. After Spec 003, `profiles.yml` `path:` points at the DuckLake catalog. Silver and gold dbt models now write to DuckLake (the PostgreSQL-backed catalog), which supports concurrent readers. The gold external Parquet exports (`marts/exports/*_export.sql`) still write files — have Python read the resulting **file**, not any catalog table.
- **dbt's `profiles.yml` primary connection is `path: ":memory:"` — do NOT point it back at `warehouse.duckdb`.** Every model/seed/test is routed to `+database: lake` (the DuckLake/Postgres catalog) and every source is external Parquet, so dbt stores no data in a warehouse file. Pointing `path:` at a real `.duckdb` file only bought DuckDB's single-writer *file lock*, which made any overlap between dbt runs (scheduled + manual, a retry launched while the prior run's process lingers, or a hard-crashed process from a previous attempt) fail with `IO Error: Could not set lock on file "…/warehouse.duckdb": Conflicting lock is held … (PID …)`. `:memory:` removes the lock; shared state lives in DuckLake (concurrency-safe). Keep the `attach: lake` stanza — with a non-ducklake `path:` there is no double-attach (contrast the "remove `attach:` when switching `path:` to DuckLake" constraint above). Note: the compose `DUCKDB_PATH` env var is now vestigial for dbt (nothing else opens the warehouse file read-write — the MCP inspector uses `:memory:`).
- **`dbt build` OOMs ("Out of Memory Error: Allocation failure") without a `settings:` cap in `profiles.yml`.** DuckDB defaults `memory_limit` to 80% of the *host* RAM it detects — not the container's share. On the shared home server (192.168.1.166, which also runs the SigNoz/ClickHouse stack) the OS can't actually hand over that much, so a big sort/aggregation/table-write (e.g. `stg_espn_events`' `qualify row_number()` window, or the intermediate table writes) gets its allocation *refused* before DuckDB ever decides to spill. Fix (in place): the dev output carries a `settings:` block bounding `memory_limit` (env `DUCKDB_MEMORY_LIMIT`, default 4GB) below what the host guarantees, a `temp_directory` (`$DATA_DIR/.duckdb_tmp`) + `max_temp_directory_size` so it spills to disk, and `preserve_insertion_order: false` to cut peak memory on writes. If it still OOMs, lower `DUCKDB_MEMORY_LIMIT`; on a bigger box raise it. This is NOT a query-shape bug — the ESPN bronze is ~44MB and the intermediate models are linear scans, no cartesian self-join.
- **Python assets must NOT open a DuckLake connection — even read-only.** ARCHITECTURE.md rule 3 ("dbt owns the DuckLake catalog; Python reads Parquet files, not catalog tables") applies to ALL Python connections to DuckLake, not just read-write ones. When a conform or enrichment asset needs canonical data (e.g. the `team` or `match` tables), add a dbt external Parquet export for those tables and have Python read the resulting files. A read-only `duckdb.connect(...)` on the DuckLake catalog from a Python Dagster asset violates the architectural boundary.
- **`DATA_PATH` in the DuckLake `attach` stanza must match across all consumers.** The `profiles.yml` `attach:` entry specifies a `DATA_PATH`. Always ensure consistent data path specifications so catalog attachments succeed cleanly.
- **Remove the `attach:` stanza when switching `profiles.yml` `path:` to DuckLake.** During incremental adoption (Spec 002), DuckLake was introduced via `attach:` (alias `lake`) while `path:` still pointed at `warehouse.duckdb`. After switching `path:` to the DuckLake catalog URI, the `attach:` entry must be deleted — keeping both causes a double-attach of the same catalog, which raises a cryptic error on startup.
- **DuckDB postgres extension requires DSN string format (`postgres:dbname=...`) for automatic URI detection.** Passing a standard `postgresql://...` URI inside `ducklake:` paths causes DuckDB to misinterpret it as a local file path unless `(TYPE POSTGRES)` is explicitly appended. Always format `POSTGRES_CATALOG_URL` as a libpq DSN string starting with `postgres:dbname=...` so DuckLake's internal attach succeeds cleanly.
- **All dbt models, seeds, and tests must specify `+database: lake` in `dbt_project.yml`.** When attaching DuckLake as a secondary catalog (`lake`), dbt nodes default to DuckDB's primary database unless explicitly routed. Setting `+database: lake` globally ensures materializations are written into DuckLake.
- **`dbt-duckdb` does NOT need `is_ducklake: true` for a PostgreSQL-backed DuckLake path.** `path: "ducklake:postgres:dbname=..."` is sufficient for `dbt-duckdb 1.10.1`+; `is_ducklake: true` is only needed for MotherDuck paths.
- **`dbt parse` exits 0 even without a live Postgres catalog connection.** Parse only reads model SQL to generate the manifest; it does not connect to the catalog. Safe to run in CI without the DuckLake catalog service standing up.
- **DuckDB runtime >=1.5.2 required for the DuckLake 1.0 extension.** The Python package in `pyproject.toml` is pinned `>=1.5.2`.
- **The canonical domain schema lives as dbt models, not raw DDL.** `int_team`,
  `int_league`, `int_season`, `int_match`, and the `int_*_match_link`/`int_*_event_link`
  tables are dbt models under `dbt/data_platform/models/intermediate/int_*.sql`.
  **Conform is symmetric and cross-provider:** ESPN conforms in **SQL** and is the
  **union base**; each `int_<entity>` is `ESPN base CTE UNION ALL
  read_parquet(<provider>_canonical_<entity>_additions.parquet)`, keep-one on the id.
  Non-ESPN providers conform in **Python** (`src/data_platform/conform/<provider>.py`,
  sharing `conform/resolve.py`) and contribute rows additively via those additions
  files; Matchbook is live, football-data is a scaffold. Don't create/alter these
  with a raw DuckDB connection — that reintroduces the second-writer problem above.
  (`ERD.md` is the Postgres-flavoured source spec; this repo realises it in DuckLake.)
- **`dbt build` is NOT green from a clean checkout.** The staging models
  (`stg_espn_events`, `stg_matchbook_odds`) read bronze Parquet under `data/bronze/**`,
  which the Dagster ingestion assets must materialize first; without it dbt fails with
  `IO Error: No files found …`. This is environmental (no data yet), not a regression —
  run the relevant bronze ingest before `dbt build`, or expect those models to error
  while the rest pass.
- **dbt model Dagster asset keys are prefixed by their *schema* folder only — NOT
  every subfolder.** A model under `models/intermediate/int_match.sql` gets
  `AssetKey(["intermediate", "int_match"])`; a deeper subfolder (were one to exist)
  is dropped from the key. Likewise `marts/…` → `["marts", "<model>"]`. Resolve the
  real key from the dbt manifest (or `dbt_models.keys`) rather than guessing — a
  wrong key makes `BronzeAwareTranslator` and cross-asset `deps=[...]` silently not
  form the edge. **Separately, the dbt *node selector* DOES include the subfolder** —
  e.g. `dbt build --select intermediate.int_match` (the fully-qualified path); a bare
  wrong prefix selects nothing and gives a vacuous green. So: Dagster
  `AssetKey(["intermediate","int_match"])` vs the dbt selector path — both
  load-bearing. Note: switching
  `profiles.yml` `path:` to DuckLake changes the manifest `database` field from
  `warehouse` to `ducklake`; this does NOT affect AssetKey derivation (which uses
  schema prefix only) — confirmed via `dagster definitions validate`. When you
  `--select` a subgraph whose `relationships` tests point at UNSELECTED tables, add
  `--indirect-selection=empty` so dbt builds exactly the selected nodes — otherwise the
  pulled-in neighbour test errors with `Table … does not exist`. This is graph-scoping,
  NOT a gate bypass.
- **Canonical match identity goes through the `canonical_match_id` dbt macro — never
  a provider event id.** `match_id` is `md5` over the *canonical resolved* natural
  key (canonical league_id, season_id, UTC kickoff date, seed-resolved home/away
  `team_id`), computed by `macros/canonical_match_id.sql`. ALWAYS derive `match_id`
  (and link tables' `match_id`) via that macro over canonical resolved values; NEVER
  mint identity from a raw provider id (ESPN `event_id`, etc.). This is what lets a
  future provider (Matchbook/football-data) de-dup onto the same fixture. The ESPN
  resolution is inlined in `int_match.sql`/`int_team.sql`/`int_espn_match_link.sql`;
  the Python providers share the `conform/resolve.py` identity authority (a replica
  of the same macro) — both are guarded by a `relationships` test.
- **A Python provider that mints canonical rows writes FOUR additions Parquet files, not one.**
  `data/silver/<provider>_canonical_{match,team,league,season}_additions.parquet` — one per
  canonical entity a minted match references. Minting a match MUST emit (or reuse) its whole
  `season → league → team` chain: a team-addition per unresolved `home_team_id`/`away_team_id`,
  a season-addition for its `season_id`, a league-addition for that season's `league_id`, and the
  match-addition itself. Identity is **seed-first**: team ids resolve through the `team_aliases`
  seed (`coalesce(seed.team_id, md5(lower(name)))`), league ids through the `league_aliases` seed
  (`coalesce(seed.league_id, mint_provider_scoped(provider, provider_key))`), `season_id =
  md5(league_id || '|' || year)`, and `match_id` via the `canonical_match_id` macro's replica —
  never a raw provider id or a provider-private constant. Each of the four files is
  **bootstrap-written empty** (correct columns, zero rows — via `conform.bootstrap_additions_files`)
  **before any `dbt build`**, because the `int_*` models read them with `read_parquet`, which
  ERRORS on a missing file (it does NOT silently return zero rows for an absent file — the
  bootstrap-empty discipline is the only thing keeping the union green). The Python conform modules **never open
  a DuckLake connection** (even read-only): they read bronze Parquet + the `canonical_*`
  external-Parquet exports and write the additions files; dbt owns the catalog and unions the files
  via `read_parquet` + `UNION ALL`, keep-one on the id. ESPN is exempt — it conforms in SQL and is
  the union base. Do NOT write directly to DuckLake or create a separate canonical table (the
  link-table `relationships` test on `match_id → match.match_id` must stay passable, and direct
  DuckLake writes reintroduce the second-writer problem). This four-file bootstrap
  applies to **still-scaffolded providers that mint nothing** too (e.g. football-data):
  because `read_parquet` errors on a missing path, EVERY provider the `int_*` models
  union must have its four files bootstrapped, not just providers with a live conform
  body — so `matchbook_conform` bootstraps BOTH matchbook and football-data via
  `bootstrap_additions_files` (the T038 fix; a scaffold provider still needs its empties).
- **`league_aliases` seed maps each provider's league key onto the ESPN-anchored canonical `league_id`.**
  `dbt/data_platform/seeds/league_aliases.csv` — columns `league_id, canonical_name, provider,
  provider_key`. The natural key is the composite **`(provider, provider_key)`** and MUST be
  `unique` (one canonical mapping per provider key), enforced by a zero-dependency SINGULAR test
  under `dbt/data_platform/tests/` (`... group by provider, provider_key having count(*) > 1`
  returns zero rows — no `dbt_utils`). `league_id` and `provider_key` are `not_null`; `provider` is
  `not_null` + `accepted_values(espn|matchbook|football_data)`. `league_id` is intentionally **NOT
  `unique`** — several providers deliberately map onto one ESPN-anchored `league_id` (mirroring how
  `team_aliases` allows many `alias` rows per `team_id`). The seed is **ESPN-anchor additive**: it
  RECORDS ESPN's own mapping (`provider=espn, provider_key=<league_slug>, league_id=md5(<slug>)`)
  and maps OTHER providers' keys onto that SAME id — it does NOT redefine ESPN identity, so ESPN's
  `int_league`/`int_match`/`int_espn_*_link` stay byte-for-byte unchanged. `provider_key` encoding:
  ESPN = `league_slug` (e.g. `eng.1`); Matchbook = `"<sport_id>|<category_id>"`; football_data =
  its `<family|division>` key. **Seed-only, no auto-learn** (no write-back of provider spellings).
  Registered in `dbt/data_platform/seeds/_seeds.yml` (the first `_seeds.yml` in the repo).
- **The bronze→silver edge is wired by `BronzeAwareTranslator`** in `assets/dbt.py`,
  which maps each dbt bronze source (e.g. `espn_events` → `AssetKey(["espn_bronze"])`,
  `matchbook_events` → `AssetKey(["matchbook_events_bronze"])`) to its upstream Dagster
  ingest asset. Renaming a bronze asset or dbt source breaks the lineage link. **Every
  dbt bronze source a model reads must have an entry in `_SOURCE_ASSET_KEYS` pointing at its producer,
  or the asset-graph edge silently doesn't form** (the source becomes a dangling
  external key). This is easy to miss — `dagster definitions validate` stays green
  either way; verify with `defs.resolve_asset_graph()` and check the staging model's
  `parent_keys`.
- **A continuously-running producer (e.g. the `matchbook-ingestor` Redis daemon) is
  modelled as an `@observable_source_asset`, NOT a materializing `@asset`.** A
  materialization run must terminate, and micro-batching a fire-and-forget pub/sub
  stream would drop ticks. `matchbook_odds_bronze` (`assets/ingestion/matchbook_odds.py`)
  observes the daemon's bronze Parquet: it gives `stg_matchbook_odds` a real upstream
  node and records freshness (newest-file age) + a WARN-severity `odds_stream_fresh`
  check, run by the `matchbook_odds_observe` job/schedule. The freshness check is WARN
  (not ERROR) on purpose — odds only stream during live markets, so a hard SLA would
  false-alarm overnight. To schedule a source-asset observation + its check, select by
  key: `AssetSelection.assets(<AssetKey>) | AssetSelection.checks_for_assets(<AssetKey>)`
  — pass the **`AssetKey`**, not the `SourceAsset` object (`AssetSelection.assets(<SourceAsset>)`
  raises `CheckError: Unexpected type for AssetKey`).
- **Do not add `from __future__ import annotations` to asset modules.** Dagster
  introspects `context`/return annotations at runtime; stringized annotations make
  it raise `DagsterInvalidDefinitionError`.
- **Python is pinned to `>=3.12,<3.13`** (`.python-version` + `pyproject.toml`).
  dbt/mashumaro fails to build serializers on 3.14.
- **`[tool.uv] package = false`** — the project is not built as a wheel; code is
  imported from `src/` via `PYTHONPATH=src`. In Docker the venv lives at
  `/opt/venv` (not `/app`) so the `./src` bind-mount for live reload doesn't
  shadow installed dependencies.

#### ESPN soccer bronze ingestion (`espn/` + `assets/espn.py`)

- **`/seasons` API returns `$ref` link references, not inline objects.** ESPN's `/v2/sports/soccer/leagues/{slug}/seasons` endpoint returns a list of items containing only `{"$ref": "..."}` URLs. Discovery must extract the year or follow `$ref` links rather than expecting inline `year`/`startDate`/`endDate` fields. To avoid slow network scans across decades of historical seasons during discovery, filter `$ref` URLs by year before fetching reference details.
- **ESPN soccer season windows span ~365 days across calendar years.** The discovery fetch horizon (`espn_fetch_horizon_days`) must be large enough (or clamped appropriately) so that historical/active season date windows cover multi-year leagues (e.g. Aug–May). A short window causes filtering to return zero matches and empty parquet directories.

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
- **Faithful bronze of a *nested* source needs a verbatim raw column — an open
  Pandera frame is not enough.** `strict=False` only proves columns already *in the
  frame* survive validation; it does NOT protect against a lossy flatten/projection
  *upstream*. For a flat CSV (football) `pd.read_csv` keeps every column, so the frame
  is faithful. For nested JSON (ESPN), hand-projecting a core set drops the rest of
  the payload (e.g. `venue`, `team.shortDisplayName`) — so the ESPN bronze also
  stores the **complete original event dict verbatim** in a `raw_event` JSON column
  (`espn/ingest.py`). Faithful-to-source means a future field can be recovered from
  bronze **without a re-fetch**; prove it with a test that recovers a *non-projected*
  field, not just that an extra column rides along.
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
- **Every job uses an explicit `AssetSelection.assets(...)` selection — no
  `AssetSelection.all()`-based job exists.** Each source is scoped to its own job
  (`espn_ingestion`, `matchbook_events_ingestion`, `matchbook_conform_job`,
  `matchbook_odds_observe`, `football_backfill`), so a heavy source like the ~705-file
  football backfill only runs via its dedicated `football_backfill` job. When adding a
  new source, give it its own explicit-selection job rather than reintroducing an
  `all()`-based sweep (which would pull every registered asset — including the heavy
  backfills — into one run).

### Configuration & telemetry

- All runtime config flows through `config.py` (`pydantic-settings`, env-driven):
  `DATA_DIR`, `DUCKDB_PATH`, `POSTGRES_CATALOG_URL`, `API_BASE_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`.
  The dbt `profiles.yml` reads `POSTGRES_CATALOG_URL` (DuckLake catalog URI) and the gold
  `external` model reads `DATA_DIR` via `env_var(...)`.
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
- **Matchbook session-token auth:** Auth lives in a standalone `authenticate(username, password, *, base_url, timeout) -> str` function in the ingest module so it is unit-testable without Dagster. POST credentials to the auth endpoint; call `response.raise_for_status()` before inspecting the body; raise `ValueError("session-token not present in auth response")` if the key is absent. Acquire exactly one token per asset run — do not refresh mid-run. Auth failure raises before any Parquet write is attempted.
- **Config property name collision for new providers:** When adding a new bronze source for a provider that already has config fields (e.g. Matchbook has `matchbook_bronze_dir` for the Redis odds ingestor), check `config.py` for existing property names before adding a new one. Silently overwriting a live property breaks the existing ingestor.
- **Config fields must precede the asset wrapper in sequencing:** The asset module reads `settings.<field>` at the top of its body — if the config field doesn't exist yet, importing the asset raises `AttributeError` at test time. Always add new `Settings` fields (and the provider's `base_url` config field) before writing the Dagster asset wrapper.
- **Per-sport ingest isolation: ingest unit returns, outer loop re-raises.** The unit-level ingest function (e.g. `ingest_sport`) must return a failure count rather than raising on per-record Pydantic failures — raising aborts remaining units. The outer `run_*_ingest` function accumulates failures and re-raises at the end so all units are attempted and valid Parquet files persist. Pattern: `matchbook/ingest.py`, mirrors `espn/ingest.py`.
- **Run ruff on the files you changed, not the whole tree.** `ruff format src` (or a
  task that lints `src` wholesale) reformats unrelated, pre-existing files and drags
  them into your change set. Scope ruff to your own files; the pre-commit hook
  already runs on staged files only. Note `pre-commit run --all-files` is the full
  repo gate — keep it green (it surfaces *any* file's lint debt, not just yours).
- **`pre-commit run --all-files` currently fails on a pre-existing `SIM105` in `investigations/duckdb-data-catalogue-mcp/code/server.py:120`** (`try/except/pass` instead of `contextlib.suppress`). This is not a regression from recent spec work. When landing a feature, verify your changes don't introduce *new* SIM findings; if all-files still fails after your changes are clean, the break is pre-existing debt and can be fixed in a follow-up lint sprint.
- **Enrichment Parquet files may write join-key columns as INT32/INT64 even when the canonical target is VARCHAR.** The T-60 enrichment asset writes `favourite_team_id` as INT32 (pandas default for numeric-looking hex strings stored as integers), but `team.team_id` is VARCHAR in DuckLake. Any gold LEFT JOIN on an enrichment-sourced ID column must use `cast(... as varchar)` explicitly — the join silently errors without it. Discovered and fixed in spec 008 commit `16802b6`.
- **Gold layer convention: two-file pattern (table + export).** Each gold analytics model follows the `marts/core/fct_completed_matches.sql` + `marts/exports/completed_matches_export.sql` template: one SQL file for the logic (inherits `+materialized: table` from `dbt_project.yml`), one `<model>_export.sql` wrapping it with `materialized='external'` to write `$DATA_DIR/gold/<model>.parquet`. Notebooks read the exported Parquet file; they never connect to the DuckLake catalog.
- **Production Parquet `ingested_at` is `datetime64[ms, UTC]` not `datetime64[ns]`.** The Redis Matchbook odds ingestor writes `ingested_at` as `datetime64[ms, UTC]`. Converting this to `int64` gives epoch-milliseconds directly; dividing by 1_000_000 (as you would for `datetime64[ns]`) produces epoch-seconds and makes every tick appear outside the T-60 window. The safe normalisation is: `if tz is not None: localize(None); then astype("datetime64[ms]").astype("int64")` — this produces epoch-ms regardless of the original unit. See `filter_t60_ticks` in `t60.py`.
- **Matchbook live-ingest events nest runners inside `markets[i]['runners']`, not at the top level.** The live `/v2/events` API response has `raw_event['markets'][i]['runners']` (each runner has `'id'` and `'name'`). Historic Postgres-migrated events (`_migration_source` in raw_event; the migration asset itself is retired) have no runner data. When resolving runner-to-team, first try top-level `runners`, then fall back to searching `markets` for the one_x_two market. (`t60.py` run_t60_enrichment.)
- **Migration `ingested_at` is the migration timestamp (overrides live-ingest rows in recency dedup).** The (now-removed) Postgres migration stamped each event's `ingested_at` with the time the migration ran (~June 30), more recent than live events ingested on June 29. Any such rows still in the bronze lake (with no runner data) would win the dedup over live rows (with runner data) for shared event IDs, so `t60.py` prefers rows with `markets` in `raw_event` before sorting by `ingested_at`. This defensive dedup remains even though the migration asset is gone — remove it only if the historic migrated bronze data is also purged. (`t60.py` events dedup logic.)

## Maintaining this file

Treat CLAUDE.md as living documentation. **When you discover something a future
instance would otherwise have to rediscover the hard way — a non-obvious
constraint, a tool/version gotcha, a failure mode and its fix, a new command or
convention — add it here in the same commit.** Keep additions concise and put
hard-won constraints under "Non-obvious constraints". Remove guidance that becomes
stale. Do not restate what's discoverable from the file tree or generic Python advice.

**`data flows.md`** is the companion document describing the end-to-end data flow
(sources → bronze → silver canonical → conform → enrichment → gold). **Keep it
current in the same commit whenever you:**
- Add or remove a data source (new bronze asset)
- Add a dbt silver or gold model that changes the flow
- Change the conform or T-60 enrichment logic materially
- Build a new gold analytics model joining the linked data
- Run a bulk migration that significantly changes table row counts

# Do not overengieer this project

Code should be simple and easy to understand. Avoid unnecessary abstractions, patterns, or frameworks that do not add clear value.

Prioritize clarity and maintainability over cleverness. Same goes for architecture - split modules by logical boundaries, but avoid overcomplicating the structure.

Follow the KISS principle: Keep It Simple, Stupid. If a solution can be implemented in a straightforward way, do so. Avoid premature optimization or overengineering.

Implement good levels of abstraction, at the top level it should read like prose; with files having a clear purpose and a single responsibility. Avoid deep inheritance hierarchies or complex design patterns unless they are clearly justified.
