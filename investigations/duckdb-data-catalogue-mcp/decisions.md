# Decisions

## Made
- **D1: Zero-Lock Hybrid Introspection (2026-06-30)** — The MCP server must combine static `manifest.json` metadata parsing with dynamic in-memory DuckDB (`:memory:`) views over Parquet files rather than opening `data/warehouse.duckdb`. *Rationale:* Avoids single-writer file concurrency exceptions with running Dagster/dbt pipelines.
- **D2: Resource-First Lakehouse Hierarchy (2026-06-30)** — Expose data discovery primarily via MCP Resources using parameterized URI routing (`lakehouse://catalog`, `lakehouse://dataset/{layer}/{name}/schema`, `lakehouse://dataset/{layer}/{name}/sample`). *Rationale:* Allows AI agents to read context directly as resources rather than relying solely on tool function invocations.
- **D3: Guardrailed SQL Execution Tool (2026-06-30)** — Include `run_sql_query` as an MCP Tool with SQL mutation stripping. *Rationale:* AI agents performing exploratory analysis need arbitrary ad-hoc aggregations across joins that standard sample resources cannot answer.

## Open questions
- Q1: Should the MCP server be integrated into the Dagster webserver environment or distributed as an independent CLI entrypoint (`uv run python -m data_platform.mcp`)?
- Q2: Should row-level data sampling be configurable via query parameters on resource URIs?
