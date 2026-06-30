"""Lakehouse catalogue inspection engine for MCP server (Spec 007)."""

import json
import re
from pathlib import Path
from typing import Any

import duckdb

from data_platform.config import settings as default_settings


class LakehouseInspector:
    """Zero-lock hybrid inspector for Medallion Parquet files and dbt manifest."""

    def __init__(
        self,
        dbt_manifest_path: Path | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.dbt_manifest_path = (
            dbt_manifest_path
            if dbt_manifest_path is not None
            else default_settings.dbt_manifest_path
        )
        self.data_dir = data_dir if data_dir is not None else default_settings.data_dir

    def get_catalog(self) -> dict[str, Any]:
        """Discover all lakehouse datasets from dbt manifest or local bronze fallback."""
        if self.dbt_manifest_path.exists():
            return self._parse_manifest()
        return self._fallback_discovery()

    def _parse_manifest(self) -> dict[str, Any]:
        try:
            with open(self.dbt_manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            return {
                "lakehouse_catalog": [],
                "error": f"Failed to read dbt manifest at {self.dbt_manifest_path}: {e}",
            }

        catalog: list[dict[str, Any]] = []

        # Process sources (bronze layer)
        for src in manifest.get("sources", {}).values():
            layer = "bronze"
            name = f"{src.get('source_name')}.{src.get('name')}"
            desc = src.get("description", "")
            cols = src.get("columns", {})
            catalog.append(
                {
                    "layer": layer,
                    "name": name,
                    "description": desc,
                    "columns_count": len(cols),
                    "schema_resource": f"lakehouse://dataset/{layer}/{name}/schema",
                    "sample_resource": f"lakehouse://dataset/{layer}/{name}/sample",
                }
            )

        # Process models (silver/gold layers)
        for node in manifest.get("nodes", {}).values():
            if node.get("resource_type") == "model":
                fqn = node.get("fqn", [])
                layer = fqn[1] if len(fqn) > 1 else "silver"
                name = node.get("name", "")
                desc = node.get("description", "")
                cols = node.get("columns", {})
                catalog.append(
                    {
                        "layer": layer,
                        "name": name,
                        "description": desc,
                        "columns_count": len(cols),
                        "schema_resource": f"lakehouse://dataset/{layer}/{name}/schema",
                        "sample_resource": f"lakehouse://dataset/{layer}/{name}/sample",
                    }
                )

        return {"lakehouse_catalog": catalog}

    def _fallback_discovery(self) -> dict[str, Any]:
        catalog: list[dict[str, Any]] = []
        bronze_dir = self.data_dir / "bronze"
        if bronze_dir.exists():
            for file_path in sorted(bronze_dir.glob("*.parquet")):
                name = file_path.stem
                catalog.append(
                    {
                        "layer": "bronze",
                        "name": name,
                        "description": f"Discovered Parquet file at {file_path}",
                        "columns_count": 0,
                        "schema_resource": f"lakehouse://dataset/bronze/{name}/schema",
                        "sample_resource": f"lakehouse://dataset/bronze/{name}/sample",
                    }
                )

        status_msg = (
            f"dbt manifest not found at {self.dbt_manifest_path}. "
            "Run `dbt parse` to populate full model lineage and column descriptions."
        )
        return {
            "lakehouse_catalog": catalog,
            "status": status_msg,
        }

    def get_dataset_schema(self, layer: str, name: str) -> dict[str, Any]:
        """Inspect column schema merging dbt manifest metadata with physical Parquet types."""
        manifest_cols, found_in_manifest = self._get_manifest_columns(layer, name)
        parquet_path = self.data_dir / layer / f"{name}.parquet"

        if not parquet_path.exists():
            if not found_in_manifest:
                return {"error": f"Dataset {name} in layer {layer} not found"}
            columns = {
                cname: {
                    "manifest_type": cdata.get("data_type", "UNKNOWN"),
                    "description": cdata.get("description", ""),
                }
                for cname, cdata in manifest_cols.items()
            }
            return {
                "dataset": f"{layer}.{name}",
                "materialized": False,
                "status": f"Parquet file not yet materialized at {parquet_path}",
                "columns": columns,
            }

        # Materialized: inspect via ephemeral in-memory DuckDB connection
        physical_cols: dict[str, str] = {}
        try:
            conn = duckdb.connect(":memory:")
            res = conn.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(parquet_path)]
            ).fetchall()
            for row in res:
                col_name, col_type = row[0], row[1]
                physical_cols[col_name] = col_type
            conn.close()
        except Exception as e:
            return {"error": f"Failed to inspect Parquet file at {parquet_path}: {e}"}

        columns = {}
        all_col_names = list(physical_cols.keys()) + [
            k for k in manifest_cols if k not in physical_cols
        ]
        for cname in all_col_names:
            mcol = manifest_cols.get(cname, {})
            columns[cname] = {
                "physical_type": physical_cols.get(cname, "N/A"),
                "description": mcol.get("description", ""),
            }
            if "data_type" in mcol:
                columns[cname]["manifest_type"] = mcol.get("data_type", "")

        return {
            "dataset": f"{layer}.{name}",
            "materialized": True,
            "columns": columns,
        }

    def get_dataset_sample(self, layer: str, name: str) -> dict[str, Any]:
        """Fetch up to 10 sample records from landed Parquet file."""
        parquet_path = self.data_dir / layer / f"{name}.parquet"
        if not parquet_path.exists():
            return {
                "status": "Sample unavailable",
                "details": f"Parquet file not found at {parquet_path}",
            }

        try:
            conn = duckdb.connect(":memory:")
            rel = conn.execute("SELECT * FROM read_parquet(?) LIMIT 10", [str(parquet_path)])
            col_names = [desc[0] for desc in rel.description]
            raw_rows = rel.fetchall()
            conn.close()

            sample_rows = []
            for row in raw_rows:
                row_dict = {}
                for idx, col in enumerate(col_names):
                    row_dict[col] = row[idx]
                sample_rows.append(row_dict)

            return {
                "dataset": f"{layer}.{name}",
                "sample_count": len(sample_rows),
                "sample_rows": sample_rows,
            }
        except Exception as e:
            return {
                "status": "Sample unavailable",
                "details": f"Failed to read Parquet sample at {parquet_path}: {e}",
            }

    def run_sql_query(self, query: str) -> dict[str, Any]:
        """Execute a guardrailed read-only analytical SQL query over landed Parquet files."""
        mutating_pattern = re.compile(
            r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|COPY|EXPORT)\b",
            re.IGNORECASE,
        )
        if mutating_pattern.search(query):
            return {"error": "Only read-only SELECT queries are permitted"}

        try:
            conn = duckdb.connect(":memory:")
            for layer in ("bronze", "silver", "gold"):
                layer_dir = self.data_dir / layer
                if layer_dir.exists():
                    for p in sorted(layer_dir.glob("*.parquet")):
                        view_name = f"{layer}_{p.stem}"
                        conn.execute(
                            f"CREATE VIEW {view_name} AS SELECT * FROM read_parquet('{p}')"
                        )

            rel = conn.execute(query)
            col_names = [desc[0] for desc in rel.description] if rel.description else []
            raw_rows = rel.fetchall()
            conn.close()

            records = []
            for row in raw_rows[:50]:
                row_dict = {col: row[idx] for idx, col in enumerate(col_names)}
                records.append(row_dict)

            return {
                "query": query,
                "row_count": len(raw_rows),
                "records": records,
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_manifest_columns(self, layer: str, name: str) -> tuple[dict[str, Any], bool]:
        if not self.dbt_manifest_path.exists():
            return {}, False

        try:
            with open(self.dbt_manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            return {}, False

        if layer == "bronze":
            for src in manifest.get("sources", {}).values():
                s_name = f"{src.get('source_name')}.{src.get('name')}"
                if s_name == name or src.get("name") == name:
                    return src.get("columns", {}), True
        else:
            for node in manifest.get("nodes", {}).values():
                if node.get("resource_type") == "model" and node.get("name") == name:
                    return node.get("columns", {}), True

        return {}, False
