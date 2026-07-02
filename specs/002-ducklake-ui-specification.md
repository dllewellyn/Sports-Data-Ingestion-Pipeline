# Spec 002 — DuckLake + DuckDB UI Integration

**Status:** DuckLake — Delivered · DuckDB UI — **Removed (2026-07-02)**
**Date:** 2026-06-29
**Feature request:** Add DuckDB UI and DuckLake to all docker compose files. Integrate correctly so the project starts to become a fully fledged DuckDB data lake.

> **⚠️ The DuckDB UI half of this spec was removed on 2026-07-02.** The `duckdb-ui`
> compose service and `scripts/start_duckdb_ui.py` were deleted. The DuckDB Local
> UI is a MotherDuck-hosted SPA that would not initialise reliably in a headless
> container behind a reverse proxy (`Failed to resolve app state with user —
> RangeError: Offset is outside the bounds of the DataView`), and it depends on a
> third-party remote (`ui.duckdb.org`). Interactive querying of the DuckLake
> catalog is served instead by the **JupyterLab** and **Streamlit** services and
> the **DuckDB MCP inspector** (`investigations/duckdb-data-catalogue-mcp/`). The
> **DuckLake** half of this spec (Postgres-backed catalog, `ducklake-catalog`
> service) remains in place and is unaffected. The requirements below are retained
> as the historical record of what was built.

---

## 1. Overview

This specification adds two capabilities to the platform:

1. **DuckDB UI** — a browser-accessible SQL interface into the data warehouse, surfacing the existing `warehouse.duckdb` and (once the catalog is running) the DuckLake catalog. Implemented as a dedicated Docker service using the official `duckdb/duckdb` image. The UI opens the warehouse in READ_ONLY mode to respect the single-writer constraint.

2. **DuckLake foundation** — a PostgreSQL-backed DuckLake catalog service added to the base compose stack, with the `ducklake` DuckDB extension pre-loaded in dbt. This is an incremental step: the catalog is wired and available but silver/gold dbt models are not migrated to DuckLake in this spec. Migration of existing models is a follow-up. The goal is that the plumbing is in place so a follow-up spec can move individual dbt models to DuckLake with no infrastructure change.

Together these make the project a multi-reader data lake: operators can browse data in the UI while ingestion runs, and the DuckLake catalog provides the foundation for future multi-writer concurrency.

---

## 2. Goals and Non-Goals

### Goals

- Add a `duckdb-ui` service to all four compose files (base, signoz dev, prod, remote) so `docker compose up` always brings up a browser-accessible SQL UI on port **4213**.
- Add a `ducklake-catalog` PostgreSQL service to the base compose file so all overlays inherit it.
- Install and load the `ducklake` DuckDB extension in `dbt/data_platform/profiles.yml` so dbt can reference DuckLake-managed tables in future models without any profiles change.
- Attach the DuckLake catalog in the dbt `profiles.yml` `attach` stanza so queries across catalog + warehouse work from day one.
- Bump the `duckdb` Python dependency to `>=1.2.0` and document that DuckLake 1.0 requires `>=1.5.2` (the Dockerfile base image must supply this at build time).
- Add `POSTGRES_CATALOG_URL`, `DUCKLAKE_DATA_PATH` settings to `config.py` and `.env.example`.
- The DuckDB UI container attaches `warehouse.duckdb` READ_ONLY and the DuckLake catalog for browsing.

### Non-Goals

- **Migrating existing silver/gold dbt models to DuckLake** — that is Spec 003.
- **Making Dagster assets write directly to DuckLake** — not in scope; assets still write Parquet to the bronze layer and dbt owns the warehouse.
- **Replacing `warehouse.duckdb`** — the warehouse file continues to be the live dbt target. DuckLake tables will co-exist until the migration spec.
- **Multi-writer Dagster runs** — the single-writer DuckDB constraint on `warehouse.duckdb` is not lifted by this spec; only the DuckLake catalog tables gain concurrent-write capability.
- **Authentication / TLS on the DuckDB UI** — the UI runs without auth (same as JupyterLab in dev mode).
- **Upgrading the SigNoz pinned snapshot** — unrelated to this feature.

---

## 3. Scenarios

### Scenario 1: Developer starts the stack and browses data in the UI

```
Given the developer has run `cp .env.example .env` and set COMPOSE_FILE to the dev (signoz) overlay
When they run `docker compose up -d`
Then a `duckdb-ui` container starts alongside the existing services
And the DuckDB UI is reachable at http://localhost:4213 in a browser
And the UI session has the warehouse tables visible under an `warehouse` attachment (READ_ONLY)
And the UI session has the DuckLake catalog visible under a `lake` attachment
And no write error is raised because the warehouse attachment is read-only
```

### Scenario 2: Developer queries the warehouse from the UI while ingestion is running

```
Given a Dagster run is actively writing to warehouse.duckdb via dbt
When the developer runs a SELECT query in the DuckDB UI against the warehouse attachment
Then the query returns results without blocking or corrupting the dbt write
Because the UI connection is READ_ONLY
```

### Scenario 3: Developer uses the UI on the prod overlay

```
Given the developer sets COMPOSE_FILE to include docker-compose.prod.yml
When they run `docker compose up -d`
Then the `duckdb-ui` service starts with the same port and read-only warehouse attach
And the UI works without any SigNoz dependency
```

### Scenario 4: Developer uses the UI on the remote overlay

```
Given the developer sets COMPOSE_FILE to include docker-compose.remote.yml
When they run `docker compose up -d`
Then the `duckdb-ui` service starts and joins the sports-quant external network
And the DuckDB UI is reachable on port 4213
```

### Scenario 5: dbt connects to the DuckLake catalog

```
Given the DuckLake catalog Postgres service is running
And profiles.yml includes the ducklake extension and attach stanza
When a developer runs `dbt parse` or `dbt build`
Then dbt connects to warehouse.duckdb and loads the ducklake extension without error
And the DuckLake catalog is attached as `lake` in the same DuckDB session
And existing silver/gold models build successfully (no behavioural change)
```

### Scenario 6: New config settings are available at runtime

```
Given POSTGRES_CATALOG_URL and DUCKLAKE_DATA_PATH are set in .env
When the application starts (Dagster services, Jupyter, etc.)
Then settings.postgres_catalog_url and settings.ducklake_data_path are populated
And the settings are available for future asset code that creates DuckLake-managed tables
```

### Scenario 7: DuckDB version constraint is satisfied

```
Given the pyproject.toml pins duckdb>=1.2.0
And the Dockerfile base image provides a DuckDB runtime >= 1.5.2
When the ducklake extension is loaded inside dbt or the UI container
Then the extension installs without a version compatibility error
```

---

## 4. Acceptance Criteria

**Infrastructure — Docker Compose**

1. `docker-compose.yml` (base) defines a `ducklake-catalog` service using the official `postgres:16` image, with a named volume for persistence and a `POSTGRES_DB=ducklake` (configurable).
2. `docker-compose.yml` (base) defines a `duckdb-ui` service using `duckdb/duckdb:latest`, binding port `4213:4213`, with `./data` mounted at `/app/data` read-only where possible.
3. The `duckdb-ui` service startup command loads the `ui` extension, ATTACHes `warehouse.duckdb` as READ_ONLY, ATTACHes the DuckLake catalog, and calls `start_ui()`.
4. `duckdb-ui` depends on `ducklake-catalog` being healthy before starting.
5. `docker-compose.signoz.yml` applies a `duckdb-ui` service extension that joins `signoz-net` (so it resolves `ducklake-catalog` hostname).
6. `docker-compose.prod.yml` applies a `duckdb-ui` service entry (no SigNoz net join needed unless catalog is on signoz-net).
7. `docker-compose.remote.yml` applies a `duckdb-ui` service entry that joins `sports-quant` network.
8. Running `docker compose up -d` with any overlay brings up a `duckdb-ui` container that reaches port 4213.

**dbt profiles**

9. `dbt/data_platform/profiles.yml` adds `ducklake` to the `extensions` list alongside `parquet`.
10. `profiles.yml` adds an `attach` stanza that attaches the DuckLake Postgres catalog as `lake` using `POSTGRES_CATALOG_URL` env var, with `DATA_PATH` pointing to `/app/data/lake/`.
11. `dbt parse` succeeds with the new profiles on a fresh checkout (catalog Postgres does not need to be reachable for parse; only for runtime queries against DuckLake-managed tables).

**Python config**

12. `src/data_platform/config.py` adds `postgres_catalog_url: str` with a default of `postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake`.
13. `src/data_platform/config.py` adds `ducklake_data_path: Path` with a default of `Path("data/lake")`.
14. `.env.example` documents both new settings under a `# --- DuckLake catalog ---` comment block.

**Dependency version**

15. `pyproject.toml` bumps `duckdb>=1.2.0` (from `>=1.1`).
16. A comment in `pyproject.toml` notes that DuckLake 1.0 requires `duckdb>=1.5.2` and that the Docker image must satisfy this (the Python client version does not need to match exactly, but the DuckDB runtime called by dbt must be `>=1.5.2`).

**Single-writer constraint preserved**

17. The `duckdb-ui` service opens `warehouse.duckdb` with `(READ_ONLY)` — confirmed by the startup command in the compose service definition.
18. No new Python asset or compose service opens `warehouse.duckdb` in read-write mode.

**`.env.example` documentation**

19. `.env.example` is updated to include the DuckLake section and a note about the `DUCKLAKE_DATA_PATH` host-side path.

---

## 5. Architectural Decisions

### 5.1 Incremental DuckLake adoption: catalog first, model migration later

**Decision:** This spec adds the DuckLake catalog (Postgres service) and wires the `ducklake` extension into dbt, but does NOT migrate any existing dbt models to use DuckLake as their target. `profiles.yml` continues pointing `path` at `warehouse.duckdb`; the DuckLake catalog is available as a secondary `attach`.

**Rationale:** A big-bang migration of all silver/gold tables carries significant risk and is unrelated to the stated goal of "adding the UI." The incremental approach lets us prove the infrastructure works (catalog reachable, extension loads, UI shows data) before committing to a schema migration. Spec 003 will migrate specific model groups to DuckLake.

### 5.2 PostgreSQL as DuckLake catalog

**Decision:** Use `postgres:16` as the DuckLake catalog database, added as a base-compose service named `ducklake-catalog`.

**Rationale:** DuckLake 1.0 requires a catalog database; PostgreSQL is the primary supported backend and is already familiar to the team. Adding it to the base compose means all overlays (dev, prod, remote) inherit it without overlay-specific duplication. A named Docker volume (`ducklake_catalog`) provides persistence across restarts.

**Alternative considered:** SQLite catalog — supported by DuckLake but offers no concurrent-write benefit. Rejected: the whole point of DuckLake is multi-process writes, which requires Postgres.

### 5.3 DuckDB UI as a separate container, warehouse attached READ_ONLY

**Decision:** The `duckdb-ui` service is a separate container running `duckdb/duckdb:latest`. It mounts `./data` read-only (or at minimum opens the warehouse file with `READ_ONLY`). It does NOT run `dbt`, Dagster, or any Python code.

**Rationale:** The existing single-writer constraint on `warehouse.duckdb` (CLAUDE.md) means any container that opens the file read-write while dbt is running will get phantom catalog errors. Read-only attach is explicitly supported by DuckDB and is the correct solution. The UI container is ephemeral and stateless — it holds no data of its own.

### 5.4 DuckDB version bump to >=1.2.0 in pyproject.toml; >=1.5.2 at runtime

**Decision:** Bump `duckdb>=1.2.0` in `pyproject.toml`. Document that the runtime DuckDB (used by dbt via `dbt-duckdb` inside the app containers and the `duckdb-ui` container) must be `>=1.5.2` for DuckLake 1.0.

**Rationale:** The Python client version (`pyproject.toml`) and the DuckDB engine version called by `dbt-duckdb` are the same library, so bumping the Python dependency is sufficient for the Dagster/dbt path. The `duckdb/duckdb:latest` Docker image ships a recent DuckDB CLI that should already satisfy `>=1.5.2`; the implementation should verify the pinned tag.

**Note:** The project currently pins `duckdb>=1.1`. The bump to `>=1.2.0` in `pyproject.toml` is conservative (keeps `uv.lock` stable). Bumping further to `>=1.5.2` is acceptable if `uv lock` resolves cleanly — the implementor should check and go to `>=1.5.2` directly if the resolution is clean.

### 5.5 dbt profiles.yml: ducklake extension + attach stanza

**Decision:** Add `ducklake` to the dbt `extensions` list (so dbt installs/loads it at connection time) and add an `attach` stanza pointing at the Postgres catalog as `lake`.

**Rationale:** This is the minimal change that makes DuckLake tables queryable from dbt models without touching existing model SQL. The `path` remains `warehouse.duckdb` so all current models run unchanged. When Spec 003 migrates a model, it can reference `lake.<schema>.<table>` or the `profiles.yml` `path` can be switched per-environment.

### 5.6 Compose overlay merge semantics respected

**Decision:** The `ducklake-catalog` and `duckdb-ui` services are defined in the base `docker-compose.yml`. Overlays add only what differs for their environment (network membership, env var overrides). No service definition is duplicated across overlay files.

**Rationale:** CLAUDE.md documents that the base is environment-NEUTRAL and overlays add only env-specific concerns. Adding both new services to the base ensures no overlay is broken by forgetting to add them.

---

## 6. Constraints (non-negotiable)

These come directly from CLAUDE.md and must not be violated in the implementation:

- **Single-writer DuckDB:** The `duckdb-ui` container MUST open `warehouse.duckdb` with `(READ_ONLY)`. No new service or asset may open it read-write.
- **No `from __future__ import annotations` in Dagster asset modules.** The new `config.py` fields are additions to an existing file that already has `from __future__ import annotations` — this is acceptable because `config.py` is not a Dagster asset module.
- **All config via pydantic-settings.** `POSTGRES_CATALOG_URL` and `DUCKLAKE_DATA_PATH` must be typed fields on `Settings`, not ad-hoc `os.getenv()` calls.
- **Compose overlay merge semantics.** The base file is environment-neutral. Do not add SigNoz-net or sports-quant network memberships to the base service definitions.
- **`dbt build` is not green from a clean checkout** (pre-existing constraint, unchanged). The new DuckLake attach does not change this — `dbt parse` should still succeed without data, but `dbt build` requires bronze Parquet first.
- **DuckDB single-writer on `warehouse.duckdb` during dbt runs.** The `ducklake-catalog` Postgres service does not touch the DuckDB file; it is independent. The single-writer constraint only affects processes that open the `.duckdb` file directly.

---

## 7. Implementation Checklist (for the implementor)

These are the discrete file changes required, in dependency order:

1. **`pyproject.toml`** — bump `duckdb>=1.2.0` (or `>=1.5.2` if `uv lock` resolves cleanly). Add a comment about the runtime `>=1.5.2` requirement for DuckLake.
2. **`src/data_platform/config.py`** — add `postgres_catalog_url` and `ducklake_data_path` fields.
3. **`.env.example`** — add DuckLake section with both new vars.
4. **`docker-compose.yml`** — add `ducklake-catalog` (Postgres 16) and `duckdb-ui` services; add `ducklake_catalog` named volume.
5. **`docker-compose.signoz.yml`** — add `duckdb-ui` service extension to join `signoz-net`.
6. **`docker-compose.prod.yml`** — add `duckdb-ui` service entry (minimal; no extra network).
7. **`docker-compose.remote.yml`** — add `duckdb-ui` service entry joining `sports-quant`.
8. **`dbt/data_platform/profiles.yml`** — add `ducklake` to extensions; add `attach` stanza for the DuckLake catalog.
9. **`CLAUDE.md`** — add a note under "Non-obvious constraints" about the DuckDB UI READ_ONLY pattern and the DuckLake incremental migration approach.

---

## 8. Open Questions

| # | Question | Status | Notes |
|---|----------|--------|-------|
| 1 | Which `duckdb/duckdb` Docker image tag to pin? `latest` is acceptable for dev but prod should pin a specific version. Does the current `latest` ship DuckDB `>=1.5.2`? | **NON-BLOCKER** | Implementation should check at build time; if `latest` < 1.5.2 then pin `duckdb/duckdb:v1.5.2` or higher. |
| 2 | Does `uv lock` resolve cleanly with `duckdb>=1.5.2`? It may conflict with `dbt-duckdb>=1.9` or `dagster`'s transitive pins. | **BLOCKER** | Must be verified before bumping past `>=1.2.0`. If there is a conflict, stay at `>=1.2.0` and document that the DuckLake 1.0 extension requires manually ensuring the installed DuckDB runtime is 1.5.2+. |
| 3 | Does the `attach` stanza in `dbt-duckdb` profiles accept a `ducklake:postgresql://...` URI without setting `is_ducklake: true`? The research notes say `is_ducklake` may be needed for MotherDuck paths specifically — local Postgres may not need it. | **NON-BLOCKER** | The implementor should test; if `is_ducklake: true` is needed, add it to the attach stanza. |
| 4 | Should the DuckLake catalog Postgres credentials be hardcoded dev defaults or use env vars in base compose? | **NON-BLOCKER** | Recommendation: use env vars with dev defaults in base compose (e.g., `DUCKLAKE_POSTGRES_USER=ducklake`, `DUCKLAKE_POSTGRES_PASSWORD=ducklake`) and document them in `.env.example`. The `POSTGRES_CATALOG_URL` setting assembles from these. |
| 5 | Should `./data` be mounted read-only (`ro`) in the `duckdb-ui` container? DuckLake-managed Parquet under `data/lake/` will be written by dbt; read-only mount would prevent the UI container from corrupting them but also block any future UI-initiated writes. | **NON-BLOCKER** | For this spec, mount `./data:/app/data:ro`. The UI is a read/browse tool only. |
| 6 | The DuckDB UI `start_ui()` call blocks the container process. What healthcheck is appropriate for the `duckdb-ui` service? | **NON-BLOCKER** | `wget --spider http://localhost:4213` or `curl -sf http://localhost:4213`. Implement a basic healthcheck so `depends_on: condition: service_healthy` works for any future service that needs the UI to be ready. |
| 7 | Does `dbt parse` (run inside `dagster-webserver` and `dagster-daemon` startup commands) fail if the DuckLake catalog Postgres is not yet healthy? | **BLOCKER** | `dbt parse` only reads the manifest and does not open a DB connection, so it should be fine. But `dbt build` connects at model execution time. Verify that loading the `ducklake` extension in the profiles does NOT require a live Postgres connection at parse time. If it does, the `attach` stanza must be conditional or deferred. |

---

## 9. Traceability

| User request | Scenario | Acceptance Criteria |
|---|---|---|
| Add DuckDB UI to all docker compose files | S1, S2, S3, S4 | AC 1–8 |
| UI shows warehouse data while ingestion is running (safe read) | S2 | AC 17, 18 |
| Integrate DuckLake so project becomes a data lake | S5, S6, S7 | AC 9–16 |
| DuckLake catalog available as Postgres service | S5 | AC 1, 4, 12, 13 |
| dbt can use DuckLake tables in future models | S5 | AC 9, 10, 11 |
| Config settings for new infrastructure | S6 | AC 12, 13, 14, 19 |
| DuckDB version supports DuckLake 1.0 | S7 | AC 15, 16 |

---

*End of Spec 002*
