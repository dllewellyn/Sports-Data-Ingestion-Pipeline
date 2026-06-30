---
id: 007
title: DuckDB Lakehouse Data Catalogue MCP Server
slug: duckdb-lakehouse-catalogue-mcp
status: draft
created: 2026-06-30
user_stories: []
investigation: duckdb-data-catalogue-mcp
related_specs: [002, 003]
---

# DuckDB Lakehouse Data Catalogue MCP Server

## 1. Summary
Exposes the entire Medallion lakehouse data catalogue (bronze sources, silver models, and gold models) as a standard stdio Model Context Protocol (MCP) server. AI agents connecting via stdio can discover available datasets, inspect detailed schema and column metadata, preview sample rows, and execute guardrailed read-only SQL queries against landed Parquet files. By using a zero-lock hybrid architecture that combines static dbt manifest parsing with in-memory DuckDB inspection over Parquet files, AI coding assistants gain low-latency visibility into available sports data without causing file lock contention with running Dagster ingestion or dbt transformation pipelines.

## 2. Background & context
As autonomous AI agents and coding assistants (e.g., Claude Code, Cursor, Antigravity) are increasingly utilized to develop analytics features, dbt transformations, and data quality tests in this repository, they require accurate, real-time visibility into the database structure and data catalogue. Previously, AI agents had to either inspect raw SQL definition files manually or attempt to open `data/warehouse.duckdb` directly. Opening `warehouse.duckdb` creates single-writer database file lock exceptions that crash concurrent Dagster ingestion runs or dbt builds.

Investigation `duckdb-data-catalogue-mcp` proved that a lightweight Python stdio MCP server built with FastMCP (`fastmcp`) can solve this completely through **Zero-Lock Hybrid Introspection** (Decision D1). By statically parsing `dbt/data_platform/target/manifest.json` for hierarchy and documentation, and attaching an in-memory DuckDB connection (`duckdb.connect(":memory:")`) to register read-only views over landed Parquet files, the MCP server provides sub-second catalogue discovery and data inspection without ever opening or locking any DuckDB catalog database files.

## 3. Goals & non-goals
**Goals**
- Provide a standard stdio MCP server exposing the lakehouse dataset hierarchy via structured MCP Resources (`lakehouse://catalog`, `lakehouse://dataset/{layer}/{name}/schema`, `lakehouse://dataset/{layer}/{name}/sample`).
- Combine static dbt manifest metadata (descriptions, data types, layer classification) with dynamic Parquet introspection (real-time column data types and sample rows).
- Provide a guardrailed read-only MCP Tool (`run_sql_query`) allowing AI agents to run exploratory `SELECT` queries and joins across medallion layers.
- Guarantee zero file locking or concurrency contention with active Dagster workflows or dbt builds.

**Non-goals (explicitly out of scope)**
- Performing data mutations, writes, or schema alterations (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`) via the MCP server.
- Exposing SSE/HTTP network transport endpoints (only stdio transport is supported).
- Triggering or orchestrating Dagster ingestion jobs or dbt transformation builds from within the MCP server.
- Building graphical user interface components (visual browsing is handled by the DuckLake UI or external tools).

## 4. Actors & triggers
- **AI Coding Agents & Assistants:** Client software (e.g., Claude Code, Antigravity, IDE extensions) that spawns the MCP server process via stdio (`uv run python -m data_platform.mcp` or standalone entrypoint script) upon initialization or when an agent requests context about available database tables.
- **MCP Client Protocol Triggers:** Protocol requests (`resources/list`, `resources/read`, `tools/list`, `tools/call`) initiated by the agent during exploratory discovery or query execution.

## 5. Behaviour specification (BDD)

### Capability: Lakehouse Catalogue Discovery

**Scenario: Agent discovers all lakehouse datasets**
- **Given** the MCP server is launched via stdio and a valid `dbt/data_platform/target/manifest.json` exists
- **When** the AI agent reads the resource `lakehouse://catalog`
- **Then** the server returns a JSON object containing `lakehouse_catalog` with an entry for each bronze source, silver model, and gold model
- **And** each entry includes the dataset's medallion `layer` (`bronze`, `silver`, or `gold`), fully qualified `name`, `description`, `columns_count`, and direct URI links to its `schema_resource` and `sample_resource`

**Scenario: Catalogue discovery when dbt manifest has not been generated**
- **Given** `dbt/data_platform/target/manifest.json` does not exist on the local filesystem (e.g., fresh repository checkout before `dbt parse`)
- **When** the AI agent reads the resource `lakehouse://catalog`
- **Then** the server returns any locally landed sample Parquet files discovered in `data/bronze/`
- **And** includes a structured status message explaining that `dbt parse` should be run to populate full model lineage and descriptions

### Capability: Dataset Schema & Metadata Inspection

**Scenario: Agent inspects schema for a materialized dataset**
- **Given** a dataset (e.g., `silver.stg_users` or `bronze.users`) exists in the dbt manifest and its corresponding Parquet artifact exists on disk
- **When** the AI agent reads the resource `lakehouse://dataset/{layer}/{name}/schema`
- **Then** the server creates an in-memory DuckDB view over the Parquet file and extracts physical column types
- **And** returns a JSON response merging the dbt manifest column descriptions with exact physical data types for every column

**Scenario: Agent inspects schema for an unmaterialized dataset**
- **Given** a dataset is defined in the dbt manifest but its Parquet artifact has not yet been written to disk
- **When** the AI agent reads `lakehouse://dataset/{layer}/{name}/schema`
- **Then** the server returns column names and types defined in the dbt manifest
- **And** notes in the response that physical Parquet introspection is currently unavailable because the file has not been materialized locally

### Capability: Dataset Sampling

**Scenario: Agent requests sample rows from a landed dataset**
- **Given** the landed Parquet file for `dataset/{layer}/{name}` exists on disk
- **When** the AI agent reads the resource `lakehouse://dataset/{layer}/{name}/sample`
- **Then** the server queries the Parquet file via an in-memory DuckDB connection (`duckdb.connect(":memory:")`)
- **And** returns the first 10 rows formatted as a JSON array of record dictionaries

**Scenario: Agent requests sample rows from an unlanded dataset**
- **Given** the Parquet file for the requested dataset does not exist on disk
- **When** the AI agent reads `lakehouse://dataset/{layer}/{name}/sample`
- **Then** the server returns a structured JSON response indicating status `Sample unavailable` with clear details explaining that the Parquet file has not been materialized

### Capability: Guardrailed Ad-Hoc SQL Querying

**Scenario: Agent executes a valid read-only analytical query**
- **Given** the agent needs to join or filter data across multiple landed Parquet files
- **When** the agent invokes the `run_sql_query` tool with a valid `SELECT` statement querying registered dataset views
- **Then** the server executes the query within its isolated in-memory DuckDB connection
- **And** returns the query string, total `row_count`, and up to 50 result records in JSON format

**Scenario: Agent attempts to execute a data mutation query**
- **Given** an agent or prompt injection attempts to modify data or schema
- **When** the agent invokes `run_sql_query` with SQL containing mutating keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `ATTACH`)
- **Then** the server rejects the request before execution and returns an error message stating that only read-only SELECT queries are permitted

## 6. Edge cases & error handling

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | `manifest.json` is missing or corrupted | Return any discoverable Parquet files and a structured warning instructing the user/agent to run `dbt parse`. Do not crash on startup. |
| E2 | Requested dataset name or layer does not match any known resource | Return a structured JSON error `{"error": "Dataset <name> in layer <layer> not found"}` with suggestions or list of available layers. |
| E3 | Parquet file exists but is corrupted or unreadable by DuckDB | Catch DuckDB `IOException` or execution errors during schema/sample reads and return structured JSON indicating the file cannot be read. |
| E4 | SQL query executed via `run_sql_query` has syntax error or references non-existent table | Catch DuckDB catalog/syntax exceptions and return `{"error": "<exact DuckDB error message>"}` so the agent can self-correct. |
| E5 | SQL query returns excessive result rows (>50 rows) | Automatically truncate the returned records list to the first 50 rows while reporting the total `row_count` so context windows are not flooded. |
| E6 | Concurrent Dagster job rewrites a Parquet file while MCP server is reading | Because DuckDB in-memory queries over Parquet files open read handles briefly during query execution, OS file replacement works cleanly or returns a standard read retry without corrupting catalog state. |

## 7. Acceptance criteria

- [ ] AC1 — The MCP server starts cleanly via stdio protocol and successfully registers `lakehouse://catalog`, `lakehouse://dataset/{layer}/{name}/schema`, `lakehouse://dataset/{layer}/{name}/sample`, and `run_sql_query`.
- [ ] AC2 — Reading `lakehouse://catalog` returns JSON enumerating all bronze sources and silver/gold models discovered from `dbt/data_platform/target/manifest.json`.
- [ ] AC3 — Reading `lakehouse://dataset/{layer}/{name}/schema` returns merged descriptions from dbt manifest and physical column types from Parquet inspection.
- [ ] AC4 — Reading `lakehouse://dataset/{layer}/{name}/sample` returns up to 10 sample records from the landed Parquet file without opening `data/warehouse.duckdb`.
- [ ] AC5 — Invoking `run_sql_query` with a `SELECT` query returns up to 50 rows formatted as JSON dictionaries.
- [ ] AC6 — Invoking `run_sql_query` with DDL or DML statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`) immediately fails with a read-only restriction error.
- [ ] AC7 — Unit and integration tests under `tests/mcp/` pass cleanly with pytest and verify zero lock interference when run alongside simulated concurrent DuckDB operations.

## 8. Things to be aware of / constraints
- **DuckDB Single-Writer Constraint & Zero-Lock Requirement:** Per repo `CLAUDE.md` and `ARCHITECTURE.md`, `data/warehouse.duckdb` and DuckLake catalog files must NEVER be opened by secondary Python processes. The MCP server MUST instantiate DuckDB exclusively via `duckdb.connect(":memory:")` and query Parquet files directly using `read_parquet(...)` or views over Parquet files.
- **Python Version & Dependency:** Must run on Python `>=3.12,<3.13` per repository constraints. Utilizes `fastmcp` (verified in investigation spikes).
- **No `from __future__ import annotations`:** Do not use stringized annotations in module definitions that interface with runtime introspection (matching Dagster asset module conventions).
- **Path Resolution:** File paths (`DATA_DIR`, `DBT_MANIFEST_PATH`) must use `pathlib.Path` and resolve relative to `PROJECT_ROOT` or `config.Settings` so the server operates reliably across local dev and container environments.

## 9. Assumptions
- **Entrypoint:** Assumed the MCP server code will reside under `src/data_platform/mcp/` (e.g., `src/data_platform/mcp/server.py`) and be invocable via `uv run python -m data_platform.mcp.server`.
- **Sample Limit:** Assumed a fixed limit of 10 rows for `lakehouse://dataset/{layer}/{name}/sample` is optimal for agent context windows; deeper exploration is performed via `run_sql_query`.

## 10. Open questions
None. (All technical risks and design decisions were answered during investigation `duckdb-data-catalogue-mcp`).

## 11. Traceability

| User story / Source | Story acceptance criteria covered | Scenarios | Spec acceptance criteria |
|---------------------|-----------------------------------|-----------|--------------------------|
| Investigation `duckdb-data-catalogue-mcp` (New Feature) | Expose lakehouse catalogue via stdio MCP Resources (`catalog`, `schema`, `sample`) and optional SQL Tool (`run_sql_query`) with zero database file locking. | All scenarios across all 4 capabilities | AC1, AC2, AC3, AC4, AC5, AC6, AC7 |
