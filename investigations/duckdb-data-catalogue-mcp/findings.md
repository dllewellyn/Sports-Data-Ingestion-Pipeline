# Findings

## Conclusion (top — fill in once concluded)
- **Answer to the question:** The best approach to expose the entire DuckDB/Parquet lakehouse data catalogue to AI agents via an stdio MCP server is a **Hybrid Metadata + In-Memory DuckDB Engine** approach using FastMCP (`fastmcp`). By statically parsing `dbt/data_platform/target/manifest.json` for medallion structure and descriptions, and using an in-memory DuckDB connection (`duckdb.connect(":memory:")`) to register read-only views over landed Parquet files, the MCP server avoids DuckDB single-writer file concurrency locks completely while providing real-time schema introspection and data sampling.
- **Recommendation:** Implement a lightweight Python stdio MCP server (`data_platform_mcp`) that exposes the lakehouse hierarchy through parameterized MCP Resources (`lakehouse://catalog`, `lakehouse://dataset/{layer}/{name}/schema`, `lakehouse://dataset/{layer}/{name}/sample`) and provides a restricted read-only SQL query tool (`run_sql_query`).
- **Confidence:** **High** — verified with working spikes (`spike1_manifest_parser.py`, `spike2_duckdb_reader.py`, `server.py`) and automated integration tests (`test_server.py`) demonstrating sub-second discovery and query execution without database file locks.

## Log
### 2026-06-30 — Spike 1: Static dbt Manifest Discovery (`spike1_manifest_parser.py`)
- **What I did:** Wrote a Python script to inspect `dbt/data_platform/target/manifest.json` and extract metadata for sources (bronze layer) and models (silver/gold layers).
- **What I observed:** Successfully discovered 6 bronze sources (`users`, `espn_events`, `matchbook_odds`, etc.) and 13 silver/gold models (`stg_users`, `match`, `dim_users_by_city`, etc.) along with rich markdown descriptions and external parquet paths.
- **What it tells us:** dbt's manifest acts as an authoritative, zero-lock catalog index for the lakehouse structure. However, models/sources without full YAML schema definitions lack complete column enumerations, necessitating dynamic Parquet inspection.

### 2026-06-30 — Spike 2: In-Memory DuckDB Parquet Introspection (`spike2_duckdb_reader.py`)
- **What I did:** Tested connecting DuckDB via `:memory:` and dynamically registering views over landed Parquet files (`evidence/spike2_bronze_sample.parquet`).
- **What I observed:** DuckDB instantly reads schema (`DESCRIBE`), computes exact row counts (`2,762` rows), and returns sample records (`LIMIT 3`) directly from Parquet files without requiring lock access to `warehouse.duckdb`.
- **What it tells us:** We do not need or want our MCP server to open `data/warehouse.duckdb` directly. Querying Parquet files via an in-memory DuckDB instance provides complete isolation from running Dagster/dbt write jobs.

### 2026-06-30 — Spike 3: Prototype Stdio MCP Server (`server.py` & `test_server.py`)
- **What I did:** Implemented a full stdio MCP server prototype using `fastmcp` combining dbt manifest discovery with DuckDB Parquet views, exposing 3 resource templates and 1 SQL execution tool.
- **What I observed:** The test suite (`test_server.py`) verified all resources (`lakehouse://catalog`, schema, sample) and successfully executed SQL queries across layers.
- **What it tells us:** Parameterized MCP Resources (`lakehouse://dataset/{layer}/{name}/schema`) provide a clean, REST-like discovery surface for AI agents.
