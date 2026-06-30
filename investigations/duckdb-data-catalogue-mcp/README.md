# Investigation: Exposing DuckDB Lakehouse Data Catalogue via MCP Server

**Status:** concluded
**Owner:** AI Agent & dllewellyn
**Started:** 2026-06-30

## Question
What is the best approach to build an stdio-based MCP server that exposes the entire DuckDB/Parquet lakehouse data catalogue to AI agents primarily via MCP Resources, while supporting read-only SQL queries if required?

## Why now
AI agents need standardized, low-latency visibility into what datasets exist across the Medallion lakehouse (bronze, silver, gold layers and DuckDB tables/views) so they can autonomously explore, understand, and query data without hardcoding schema details or risking concurrent write locks.

## Hypotheses / options
- **H1 (Live DuckDB Read-Only Introspection):** Connect to DuckDB (`warehouse.duckdb` or directly inspecting Parquet layers) with read-only access and expose catalogs, schemas, and sample data via MCP Resources (`lakehouse://...`).
- **H2 (dbt Manifest & Parquet Header Parsing):** Parse metadata statically from `dbt/data_platform/target/manifest.json` and Parquet file metadata to avoid DuckDB database file locking entirely.
- **H3 (Hybrid + SQL Tool):** Combine metadata inspection (H1/H2) with an MCP Resource hierarchy (`lakehouse://resources/tables`, `lakehouse://resources/table/{name}/schema`) and an optional MCP Tool (`execute_sql_query`) for custom read-only SQL analysis.

## Done criteria
A working prototype stdio MCP server under `code/` that runs via stdio and exposes lakehouse datasets as MCP resources, verified with test queries/resource reads, and backed by findings on concurrency, lock safety, and schema presentation.

## Scope & constraints
- **In scope:** Python stdio MCP server implementation, exposing lakehouse datasets as MCP resources, optional SQL query tool.
- **Out of scope:** Writing or modifying data in the lakehouse, production deployment, UI components.
- **Constraints:** Must not lock out Dagster/dbt pipelines from writing to the DuckDB database or Parquet files.
