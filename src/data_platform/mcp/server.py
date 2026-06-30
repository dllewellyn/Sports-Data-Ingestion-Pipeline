"""FastMCP server definition for lakehouse data catalogue (Spec 007 S5)."""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from data_platform.mcp.inspector import LakehouseInspector

mcp = FastMCP("lakehouse")
inspector = LakehouseInspector()


def _format_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2)


@mcp.resource("lakehouse://catalog")
def catalog_resource() -> str:
    """Return structured JSON index of all landed Parquet datasets and dbt models."""
    return _format_json(inspector.get_catalog())


@mcp.resource("lakehouse://dataset/{layer}/{name}/schema")
def schema_resource(layer: str, name: str) -> str:
    """Return merged column schema and physical types for a dataset."""
    return _format_json(inspector.get_dataset_schema(layer, name))


@mcp.resource("lakehouse://dataset/{layer}/{name}/sample")
def sample_resource(layer: str, name: str) -> str:
    """Return up to 10 sample records from landed Parquet file."""
    return _format_json(inspector.get_dataset_sample(layer, name))


@mcp.tool("query_lakehouse_sql")
def query_lakehouse_sql(query: str) -> str:
    """Execute a read-only analytical SQL query over landed lakehouse datasets."""
    return _format_json(inspector.run_sql_query(query))
