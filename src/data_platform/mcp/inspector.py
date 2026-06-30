"""Lakehouse catalogue inspection engine for MCP server (Spec 007)."""

import json
from pathlib import Path
from typing import Any

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
