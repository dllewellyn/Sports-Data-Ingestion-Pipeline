---
id: 007
title: DuckDB Lakehouse Data Catalogue MCP Server Plan
slug: duckdb-lakehouse-catalogue-mcp
status: draft
created: 2026-06-30
specification: 007-duckdb-lakehouse-catalogue-mcp-specification.md
user_stories: []
---

# DuckDB Lakehouse Data Catalogue MCP Server Plan

## 1. Summary
We will implement a standard stdio Model Context Protocol (MCP) server for the Medallion lakehouse data catalogue under `src/data_platform/mcp/`. Built on `fastmcp`, the server exposes structured resources (`lakehouse://catalog`, `lakehouse://dataset/{layer}/{name}/schema`, `lakehouse://dataset/{layer}/{name}/sample`) and a read-only SQL tool (`run_sql_query`). To guarantee sub-second discovery without file lock contention against active Dagster or dbt workflows, the implementation uses **Zero-Lock Hybrid Introspection**: static parsing of `dbt/data_platform/target/manifest.json` combined with ephemeral in-memory DuckDB connections (`duckdb.connect(":memory:")`) over materialized Parquet files in `data/`.

## 2. Skills to use

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| FastMCP server & MCP entrypoint implementation | — | MISSING — proceed using standard Python/FastMCP patterns; capture learnings via `self-learn` |
| Static dbt manifest & Parquet inspection logic | — | MISSING — proceed using repository Parquet read rules; capture learnings via `self-learn` |
| Pure-Python unit & integration testing (`tests/mcp/`) | `plan`, `implementor` | available (workflow governance); missing specific MCP test mocking skill |
| Architecture & structural conformance review | `code-architecture-review` | available |
| Post-build learning codification | `self-learn` | available |

## 3. Convention & rule audit (resolved before implementation)

| Artifact type | Governing convention | Status |
|---------------|----------------------|--------|
| Python MCP module (`src/data_platform/mcp/*.py`) | CLAUDE.md *Python conventions* + zero-lock DuckDB `:memory:` rule + ARCHITECTURE.md rule 3 (Python reads Parquet files, not catalog tables) | exists |
| Runtime settings (`src/data_platform/config.py`) | CLAUDE.md *Configuration & telemetry* (`pydantic-settings`, typed `Settings` fields preceding consumers) | exists |
| Pytest test files (`tests/mcp/test_*.py`) | CLAUDE.md *Commands* (`PYTHONPATH=src uv run pytest`) + `pyproject.toml` `[tool.pytest.ini_options]` (importlib mode, unique basenames) | exists |

## 4. Testable units (BDD → tests)

| Unit | Spec trace (scenario / AC) | Test facility | Failing-first assertion |
|------|----------------------------|---------------|-------------------------|
| `Settings.dbt_manifest_path` configuration property | Section 8 Constraints / AC1 | pytest | `test_config_mcp.py` fails asserting `settings.dbt_manifest_path` exists as a `Path` object |
| `LakehouseInspector.get_catalog()` with valid dbt manifest | Catalogue Discovery Scenario 1 / AC1, AC2 | pytest | `test_catalog.py` fails asserting `get_catalog()` parses manifest JSON and enumerates bronze, silver, and gold entries with resource URIs |
| `LakehouseInspector.get_catalog()` fallback without manifest | Catalogue Discovery Scenario 2 / AC2, Edge Case E1 | pytest | `test_catalog.py` fails asserting missing manifest triggers Parquet scan in `data/bronze/` and returns structured `dbt parse` warning note |
| `LakehouseInspector.get_dataset_schema()` materialized | Schema Inspection Scenario 1 / AC3 | pytest | `test_schema.py` fails asserting in-memory DuckDB inspection merges physical Parquet types with manifest column descriptions |
| `LakehouseInspector.get_dataset_schema()` unmaterialized / missing | Schema Inspection Scenario 2, Edge Case E2 / AC3 | pytest | `test_schema.py` fails asserting missing Parquet returns manifest columns with availability note or clean `{"error": ...}` dict |
| `LakehouseInspector.get_dataset_sample()` | Dataset Sampling Scenarios / AC4 | pytest | `test_sample.py` fails asserting `LIMIT 10` sample records returned from Parquet file or clean `Sample unavailable` dict |
| `LakehouseInspector.run_sql_query()` read-only query & truncation | Guardrailed SQL Scenarios 1, Edge Case E5 / AC5 | pytest | `test_sql.py` fails asserting valid `SELECT` returns `row_count` and max 50 rows via `:memory:` DuckDB |
| `LakehouseInspector.run_sql_query()` mutation keyword rejection | Guardrailed SQL Scenario 2 / AC6 | pytest | `test_sql.py` fails asserting DDL/DML queries (`DROP`, `INSERT`, `UPDATE`, etc.) are rejected before DuckDB execution |
| FastMCP stdio server registration & zero-lock integration | All capabilities / AC1, AC7 | pytest | `test_server.py` fails asserting `FastMCP("lakehouse")` initializes resources/tools and delegates cleanly without file locks |

## 5. Guardrail register

| Guardrail | How verified in place | Covered by step |
|-----------|------------------------|-----------------|
| ruff check + format (pre-commit) | `uv run pre-commit run --all-files` clean | S0–S5 |
| Pytest unit & integration suite | `PYTHONPATH=src uv run pytest tests/mcp/` passes cleanly | S0–S5 |
| Zero-lock DuckDB concurrency safety | All DuckDB access uses `duckdb.connect(":memory:")` reading Parquet files directly; verified by concurrent execution test in `test_server.py` | S1–S5 |
| Typed runtime configuration | All file paths (`data_dir`, `dbt_manifest_path`) read from `config.settings` via `pathlib.Path` | S0–S5 |
| Repo non-obvious constraints respected | No `from __future__ import annotations` in asset modules; Python pinned `>=3.12,<3.13` | all |

## 6. Implementation steps

### Step S0 — Configuration & MCP Package Scaffold
- **Goal:** Add `dbt_manifest_path: Path = Path("dbt/data_platform/target/manifest.json")` to `Settings` in `src/data_platform/config.py` and scaffold `src/data_platform/mcp/__init__.py`.
- **Spec trace:** Section 8 Constraints / AC1.
- **Red (failing test first):** Write `tests/mcp/test_config_mcp.py` asserting `settings.dbt_manifest_path` exists as a `pathlib.Path` object pointing to the manifest file. Run `PYTHONPATH=src uv run pytest tests/mcp/test_config_mcp.py` and watch it fail with `AttributeError`.
- **Implementation:** Add `dbt_manifest_path: Path = Path("dbt/data_platform/target/manifest.json")` to `Settings` in `src/data_platform/config.py` and create empty package `src/data_platform/mcp/__init__.py`.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/mcp/test_config_mcp.py` passes.
- **Guardrails to satisfy:** ruff check + format clean (`uv run ruff check --fix src tests/mcp` + `uv run ruff format src tests/mcp`).
- **Self-review checkpoint:** Reviewer confirms `dbt_manifest_path` is typed `Path` in `config.py`, test genuinely fails before implementation, no reward-hacking.

### Step S1 — Catalogue Discovery Logic (`LakehouseInspector.get_catalog`)
- **Goal:** Implement static dbt manifest parsing and local Parquet discovery fallback in `src/data_platform/mcp/inspector.py`.
- **Spec trace:** Catalogue Discovery Scenarios 1 & 2 / AC1, AC2, Edge Case E1.
- **Red (failing test first):** Write `tests/mcp/test_catalog.py` asserting `LakehouseInspector().get_catalog()` returns structured dictionary containing lakehouse dataset entries with resource URIs (`lakehouse://dataset/{layer}/{name}/schema` and `sample`), and verifies fallback note when manifest JSON is missing. Watch test fail.
- **Implementation:** Create `src/data_platform/mcp/inspector.py` defining `LakehouseInspector`. Read `settings.dbt_manifest_path`; if present, extract nodes where `resource_type == "model"` or `source`, mapping layer, description, column counts, and URIs. If absent, scan `settings.data_dir / "bronze"` for `.parquet` files and return items with a structured warning note.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/mcp/test_catalog.py` passes.
- **Guardrails to satisfy:** Zero-lock requirement (no database connections opened during discovery); ruff clean.
- **Self-review checkpoint:** Reviewer verifies both manifest and fallback paths are covered by tests, output matches exact JSON schema required by BDD scenarios, no mock data hardcoded in production module.

### Step S2 — Dataset Schema & Metadata Inspection (`LakehouseInspector.get_dataset_schema`)
- **Goal:** Implement zero-lock schema inspection merging dbt manifest column descriptions with physical Parquet column data types.
- **Spec trace:** Dataset Schema Inspection Scenarios 1 & 2, Edge Cases E2 & E3 / AC3.
- **Red (failing test first):** Write `tests/mcp/test_schema.py` asserting `get_dataset_schema(layer, name)` returns exact physical types from Parquet merged with manifest descriptions when materialized, returns manifest types with unmaterialized note when file is absent, and returns clean `{"error": ...}` dictionary for non-existent datasets. Watch test fail.
- **Implementation:** Add `get_dataset_schema` to `LakehouseInspector`. Resolve Parquet artifact path from `settings.data_dir / layer / f"{name}.parquet"`. If file exists, open `duckdb.connect(":memory:")` and execute `DESCRIBE SELECT * FROM read_parquet(...)` to get physical column names and SQL types, merging descriptions from manifest. If file missing, return manifest metadata with note.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/mcp/test_schema.py` passes.
- **Guardrails to satisfy:** Single-writer DuckDB rule (`:memory:` connection only); clean error handling without raising unhandled exceptions.
- **Self-review checkpoint:** Reviewer verifies DuckDB connection is strictly ephemeral `:memory:`, proper path resolution via `pathlib.Path`, edge cases E2/E3 handled cleanly.

### Step S3 — Dataset Sampling (`LakehouseInspector.get_dataset_sample`)
- **Goal:** Implement zero-lock 10-row Parquet sampling.
- **Spec trace:** Dataset Sampling Scenarios 1 & 2 / AC4.
- **Red (failing test first):** Write `tests/mcp/test_sample.py` asserting `get_dataset_sample(layer, name)` returns a list of up to 10 row dictionaries from materialized Parquet file, and returns `{"status": "Sample unavailable", "details": ...}` when file is missing. Watch test fail.
- **Implementation:** Add `get_dataset_sample` to `LakehouseInspector`. If Parquet file exists, run `SELECT * FROM read_parquet(?) LIMIT 10` inside `duckdb.connect(":memory:")`, fetch arrow/dicts or pandas rows converted to clean JSON dicts. If missing, return structured unavailable dictionary.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/mcp/test_sample.py` passes.
- **Guardrails to satisfy:** Ephemeral `:memory:` DuckDB connection; exact 10-row limit.
- **Self-review checkpoint:** Reviewer confirms sample rows match Parquet contents, no lock contention, clean dictionary output.

### Step S4 — Guardrailed Ad-Hoc SQL Querying (`LakehouseInspector.run_sql_query`)
- **Goal:** Implement read-only SQL execution tool logic with regex/keyword mutation validation and 50-row truncation.
- **Spec trace:** Guardrailed Ad-Hoc SQL Querying Scenarios 1 & 2, Edge Cases E4 & E5 / AC5, AC6.
- **Red (failing test first):** Write `tests/mcp/test_sql.py` asserting valid `SELECT` queries across registered layer views return `query`, `row_count`, and max 50 records; asserting queries containing `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `ATTACH` return `{"error": "Only read-only SELECT queries are permitted"}` before database execution; asserting syntax errors return DuckDB error messages. Watch test fail.
- **Implementation:** Add `run_sql_query(query)` to `LakehouseInspector`. Validate `query` string against mutating SQL tokens. Instantiate `duckdb.connect(":memory:")`, scan `settings.data_dir` to register read-only views (`CREATE VIEW bronze_users AS SELECT * FROM read_parquet(...)`), execute query, count total rows, slice first 50 records as dicts, and return structured response.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/mcp/test_sql.py` passes.
- **Guardrails to satisfy:** Strict rejection of all mutation statements; max 50 row truncation to protect agent context window.
- **Self-review checkpoint:** Reviewer tests regex/keyword validator against SQL injection/subqueries, confirms views read Parquet files directly.

### Step S5 — FastMCP Server Integration (`src/data_platform/mcp/server.py` & entrypoint)
- **Goal:** Wire `FastMCP("lakehouse")` resources and tool to `LakehouseInspector` and expose runnable module entrypoint.
- **Spec trace:** All capabilities / AC1, AC7.
- **Red (failing test first):** Write integration test `tests/mcp/test_server.py` asserting `mcp = FastMCP("lakehouse")` registers resources (`lakehouse://catalog`, `lakehouse://dataset/{layer}/{name}/schema`, `lakehouse://dataset/{layer}/{name}/sample`) and tool (`run_sql_query`), and tests simulated concurrent reading without locking. Watch test fail.
- **Implementation:** Create `src/data_platform/mcp/server.py` initializing `mcp = FastMCP("lakehouse")` and defining resource/tool wrappers around a singleton or instantiated `LakehouseInspector`. Create `src/data_platform/mcp/__main__.py` invoking `mcp.run(transport="stdio")`.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/mcp/test_server.py` passes and full pre-commit runs cleanly (`uv run pre-commit run --all-files`).
- **Guardrails to satisfy:** Full suite pass; zero lock interference; ruff format and lint compliance.
- **Self-review checkpoint:** Reviewer verifies stdio transport wiring, confirms endpoints match exact URI templates from Spec 007, verifies all acceptance criteria AC1–AC7 pass.

## 7. Sequencing & dependencies
```
[Step S0: Config & Scaffold]
             │
             ▼
[Step S1: Catalogue Discovery]
             │
             ▼
[Step S2: Schema Inspection] ──▶ [Step S3: Dataset Sampling]
             │                               │
             └───────────────┬───────────────┘
                             ▼
              [Step S4: Guardrailed SQL Tool]
                             │
                             ▼
             [Step S5: FastMCP Server Integration]
```
- **Ordering rationale:** Configuration (`S0`) must precede all inspector code so paths resolve correctly. Discovery (`S1`), Schema (`S2`), and Sampling (`S3`) build foundational Parquet inspection routines. The SQL Tool (`S4`) reuses Parquet discovery to register views. Finally, FastMCP wiring (`S5`) exposes all implemented inspector capabilities over the stdio protocol.

## 8. Assumptions
- **Entrypoint:** Assumed the server will reside under `src/data_platform/mcp/server.py` with entrypoint module `src/data_platform/mcp/__main__.py` invocable via `uv run python -m data_platform.mcp`.
- **Sample Limit:** Fixed 10-row limit for dataset sampling and 50-row limit for SQL query execution protect agent context windows.
- **Test Harness:** Uses existing pytest setup (`PYTHONPATH=src uv run pytest`) established for pure-Python modules under `tests/`.

## 9. Open questions
None.

## 10. Traceability

| Spec scenario / AC | Unit(s) | Step(s) | Guardrail(s) |
|--------------------|---------|---------|--------------|
| Section 8 Constraints / AC1 | Config `dbt_manifest_path` property | S0 | ruff check, pytest |
| Catalogue Discovery Scenarios 1 & 2 / AC1, AC2, E1 | `LakehouseInspector.get_catalog()` | S1 | pytest, zero-lock DuckDB |
| Dataset Schema Inspection Scenarios 1 & 2 / AC3, E2, E3 | `LakehouseInspector.get_dataset_schema()` | S2 | pytest, zero-lock DuckDB |
| Dataset Sampling Scenarios 1 & 2 / AC4 | `LakehouseInspector.get_dataset_sample()` | S3 | pytest, zero-lock DuckDB |
| Guardrailed SQL Scenarios 1 & 2 / AC5, AC6, E4, E5 | `LakehouseInspector.run_sql_query()` | S4 | pytest, read-only SQL validation |
| Server Initialization & Concurrency / AC1, AC7 | FastMCP stdio server & entrypoint | S5 | pre-commit run --all-files, pytest |
