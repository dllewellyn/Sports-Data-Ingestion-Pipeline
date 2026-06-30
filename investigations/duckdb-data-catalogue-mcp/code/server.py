"""DuckDB Lakehouse Data Catalogue MCP Server Prototype (stdio).

Exposes the Medallion data pipeline (bronze -> silver -> gold) via MCP Resources and Tools:
- Resources:
  - `lakehouse://catalog`: Complete index of all datasets across medallion layers.
  - `lakehouse://dataset/{layer}/{name}/schema`: Detailed schema & metadata for a dataset.
  - `lakehouse://dataset/{layer}/{name}/sample`: Sample rows (first 10 rows) from a dataset.
- Tools:
  - `run_sql_query(query: str)`: Execute custom read-only DuckDB SQL queries across datasets.
"""

import json
from pathlib import Path
from typing import Any
import duckdb
from fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("DuckDB Lakehouse Catalogue")

# Root directory resolution
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DBT_MANIFEST_PATH = PROJECT_ROOT / "dbt" / "data_platform" / "target" / "manifest.json"
DATA_DIR = PROJECT_ROOT / "data"


def _load_catalog_metadata() -> dict[str, dict[str, Any]]:
    """Index all datasets from dbt manifest and local parquet discoveries."""
    datasets = {}

    # 1. Parse dbt manifest if available
    if DBT_MANIFEST_PATH.exists():
        try:
            with open(DBT_MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            # Process sources (bronze layer)
            for src in manifest.get("sources", {}).values():
                layer = "bronze"
                name = src.get("name", "")
                full_name = f"{src.get('source_name')}.{name}"
                desc = src.get("description", "")
                ext_loc = src.get("meta", {}).get("external_location")
                columns = {
                    col_name: {"type": col_info.get("data_type", "UNKNOWN"), "description": col_info.get("description", "")}
                    for col_name, col_info in src.get("columns", {}).items()
                }
                datasets[full_name] = {
                    "layer": layer,
                    "name": full_name,
                    "description": desc,
                    "external_location": ext_loc,
                    "columns": columns,
                    "resource_type": "source",
                }

            # Process nodes (silver/gold models)
            for node in manifest.get("nodes", {}).values():
                if node.get("resource_type") == "model":
                    layer_path = node.get("fqn", [])
                    layer = layer_path[1] if len(layer_path) > 1 else "silver"
                    name = node.get("name", "")
                    desc = node.get("description", "")
                    mat = node.get("config", {}).get("materialized", "table")
                    columns = {
                        col_name: {"type": col_info.get("data_type", "UNKNOWN"), "description": col_info.get("description", "")}
                        for col_name, col_info in node.get("columns", {}).items()
                    }
                    datasets[name] = {
                        "layer": layer,
                        "name": name,
                        "description": desc,
                        "materialization": mat,
                        "columns": columns,
                        "resource_type": "model",
                    }
        except Exception as e:
            datasets["_error"] = {"error": f"Failed to parse manifest: {e}"}

    # Also register our spike sample parquet if available for real querying
    sample_parquet = PROJECT_ROOT / "investigations" / "football-data-co-uk-ingestion" / "evidence" / "spike2_bronze_sample.parquet"
    if sample_parquet.exists():
        datasets["bronze.football_sample"] = {
            "layer": "bronze",
            "name": "bronze.football_sample",
            "description": "Sample landed bronze Parquet from football-data.co.uk investigation.",
            "external_location": str(sample_parquet),
            "columns": {},
            "resource_type": "source",
        }

    return datasets


def _get_duckdb_conn() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection and register views for local parquet files."""
    con = duckdb.connect(":memory:")
    datasets = _load_catalog_metadata()
    for ds in datasets.values():
        ext = ds.get("external_location")
        if ext and isinstance(ext, str) and ext.endswith(".parquet"):
            path = Path(ext)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            if path.exists():
                view_name = ds["name"].replace(".", "_")
                try:
                    con.execute(f"CREATE VIEW {view_name} AS SELECT * FROM read_parquet('{path}')")
                except Exception:
                    pass
    return con


@mcp.resource("lakehouse://catalog")
def get_catalog() -> str:
    """Return complete index of all datasets available in the Medallion lakehouse."""
    datasets = _load_catalog_metadata()
    summary = []
    for name, ds in datasets.items():
        summary.append({
            "layer": ds.get("layer"),
            "name": ds.get("name"),
            "description": ds.get("description"),
            "columns_count": len(ds.get("columns", {})),
            "schema_resource": f"lakehouse://dataset/{ds.get('layer')}/{ds.get('name')}/schema",
            "sample_resource": f"lakehouse://dataset/{ds.get('layer')}/{ds.get('name')}/sample",
        })
    return json.dumps({"lakehouse_catalog": summary}, indent=2)


@mcp.resource("lakehouse://dataset/{layer}/{name}/schema")
def get_dataset_schema(layer: str, name: str) -> str:
    """Return detailed column definitions and statistics for a specific dataset."""
    datasets = _load_catalog_metadata()
    ds = datasets.get(name)
    if not ds:
        # Try finding by matching suffix if needed
        for k, v in datasets.items():
            if v.get("layer") == layer and v.get("name").endswith(name):
                ds = v
                break
    if not ds:
        return json.dumps({"error": f"Dataset {name} in layer {layer} not found"}, indent=2)

    # Introspect with DuckDB if external location parquet exists
    con = _get_duckdb_conn()
    view_name = ds["name"].replace(".", "_")
    duckdb_cols = {}
    try:
        df = con.execute(f"DESCRIBE {view_name}").df()
        for _, row in df.iterrows():
            duckdb_cols[row["column_name"]] = row["column_type"]
    except Exception:
        pass

    columns_output = {}
    all_col_names = set(ds.get("columns", {}).keys()) | set(duckdb_cols.keys())
    for col in sorted(all_col_names):
        col_meta = ds.get("columns", {}).get(col, {})
        columns_output[col] = {
            "data_type": duckdb_cols.get(col, col_meta.get("type", "UNKNOWN")),
            "description": col_meta.get("description", ""),
        }

    return json.dumps({
        "dataset": ds.get("name"),
        "layer": ds.get("layer"),
        "description": ds.get("description"),
        "columns": columns_output,
    }, indent=2)


@mcp.resource("lakehouse://dataset/{layer}/{name}/sample")
def get_dataset_sample(layer: str, name: str) -> str:
    """Return first 10 sample rows from the dataset if readable."""
    datasets = _load_catalog_metadata()
    ds = datasets.get(name)
    if not ds:
        return json.dumps({"error": f"Dataset {name} not found"}, indent=2)

    con = _get_duckdb_conn()
    view_name = ds["name"].replace(".", "_")
    try:
        sample_rows = con.execute(f"SELECT * FROM {view_name} LIMIT 10").df().to_dict(orient="records")
        return json.dumps({"dataset": ds.get("name"), "sample_rows": sample_rows}, indent=2, default=str)
    except Exception as e:
        return json.dumps({
            "dataset": ds.get("name"),
            "status": "Sample unavailable (raw Parquet file not currently landed locally or view not materialized)",
            "detail": str(e),
        }, indent=2)


@mcp.tool()
def run_sql_query(query: str) -> str:
    """Execute a read-only DuckDB SQL query against the lakehouse views/parquet files."""
    con = _get_duckdb_conn()
    try:
        # Restrict mutations basic check
        upper_query = query.strip().upper()
        if any(upper_query.startswith(cmd) for cmd in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER"]):
            return json.dumps({"error": "Only read-only SELECT queries are permitted."}, indent=2)
        df = con.execute(query).df()
        return json.dumps({
            "query": query,
            "row_count": len(df),
            "results": df.head(50).to_dict(orient="records"),
        }, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


if __name__ == "__main__":
    mcp.run("stdio")
