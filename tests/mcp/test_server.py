"""Integration tests for FastMCP server endpoints (Spec 007 S5)."""

import json

from data_platform.mcp.server import (
    catalog_resource,
    mcp,
    query_lakehouse_sql,
    sample_resource,
    schema_resource,
)


def test_fastmcp_server_setup():
    assert mcp.name == "lakehouse"


def test_catalog_resource_endpoint():
    res = catalog_resource()
    data = json.loads(res)
    assert "lakehouse_catalog" in data


def test_schema_resource_endpoint():
    res = schema_resource("bronze", "nonexistent")
    data = json.loads(res)
    assert "error" in data


def test_sample_resource_endpoint():
    res = sample_resource("bronze", "nonexistent")
    data = json.loads(res)
    assert data["status"] == "Sample unavailable"


def test_query_lakehouse_sql_tool():
    res = query_lakehouse_sql("DROP TABLE bronze")
    data = json.loads(res)
    assert "error" in data
    assert "Only read-only SELECT queries are permitted" in data["error"]
