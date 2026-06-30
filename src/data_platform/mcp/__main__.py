"""Module entrypoint for stdio execution of Lakehouse MCP server."""

from data_platform.mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
