# Investigation Code: DuckDB Data Catalogue MCP Server Prototype

This directory contains disposable spikes and a working prototype of the stdio MCP server exposing the DuckDB lakehouse data catalogue.

## Files
- `server.py`: Prototype stdio MCP server built using FastMCP / Python MCP SDK.

## How to run
Run the stdio server using `uv run` or python within the project virtual environment:
```bash
uv run python investigations/duckdb-data-catalogue-mcp/code/server.py
```
