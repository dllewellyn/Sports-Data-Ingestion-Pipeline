"""Tests for LakehouseInspector catalogue discovery (Spec 007 S1)."""

import json
from pathlib import Path
from typing import Any

from data_platform.mcp.inspector import LakehouseInspector


def test_get_catalog_with_manifest(tmp_path: Path, monkeypatch: Any):
    manifest_path = tmp_path / "manifest.json"
    manifest_data = {
        "sources": {
            "source.data_platform.football_data.matches": {
                "source_name": "football_data",
                "name": "matches",
                "description": "Raw matches",
                "columns": {"id": {}, "home_team": {}},
            }
        },
        "nodes": {
            "model.data_platform.stg_matches": {
                "resource_type": "model",
                "fqn": ["data_platform", "silver", "stg_matches"],
                "name": "stg_matches",
                "description": "Staging matches",
                "columns": {"id": {}},
            }
        },
    }
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    inspector = LakehouseInspector(dbt_manifest_path=manifest_path, data_dir=tmp_path / "data")
    result = inspector.get_catalog()

    assert "lakehouse_catalog" in result
    catalog = result["lakehouse_catalog"]
    assert len(catalog) == 2

    bronze_item = next(item for item in catalog if item["name"] == "football_data.matches")
    assert bronze_item["layer"] == "bronze"
    assert bronze_item["description"] == "Raw matches"
    assert bronze_item["columns_count"] == 2
    assert (
        bronze_item["schema_resource"] == "lakehouse://dataset/bronze/football_data.matches/schema"
    )
    assert (
        bronze_item["sample_resource"] == "lakehouse://dataset/bronze/football_data.matches/sample"
    )

    silver_item = next(item for item in catalog if item["name"] == "stg_matches")
    assert silver_item["layer"] == "silver"
    assert silver_item["columns_count"] == 1
    assert silver_item["schema_resource"] == "lakehouse://dataset/silver/stg_matches/schema"


def test_get_catalog_fallback_without_manifest(tmp_path: Path):
    manifest_path = tmp_path / "missing_manifest.json"
    data_dir = tmp_path / "data"
    bronze_dir = data_dir / "bronze"
    bronze_dir.mkdir(parents=True)
    (bronze_dir / "sample_matches.parquet").write_bytes(b"dummy")

    inspector = LakehouseInspector(dbt_manifest_path=manifest_path, data_dir=data_dir)
    result = inspector.get_catalog()

    assert "lakehouse_catalog" in result
    assert "status" in result
    assert "dbt parse" in result["status"]
    catalog = result["lakehouse_catalog"]
    assert len(catalog) == 1
    assert catalog[0]["name"] == "sample_matches"
    assert catalog[0]["layer"] == "bronze"
