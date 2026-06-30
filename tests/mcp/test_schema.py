"""Tests for LakehouseInspector schema inspection (Spec 007 S2)."""

import json
from pathlib import Path

import duckdb

from data_platform.mcp.inspector import LakehouseInspector


def test_get_dataset_schema_materialized(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_data = {
        "nodes": {
            "model.data_platform.stg_users": {
                "resource_type": "model",
                "fqn": ["data_platform", "silver", "stg_users"],
                "name": "stg_users",
                "description": "Staging users",
                "columns": {
                    "user_id": {"description": "Primary key"},
                    "email": {"description": "User email address"},
                },
            }
        }
    }
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    silver_dir = tmp_path / "data" / "silver"
    silver_dir.mkdir(parents=True)
    parquet_path = silver_dir / "stg_users.parquet"

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE stg_users (user_id BIGINT, email VARCHAR, created_at TIMESTAMP)")
    conn.execute(f"COPY stg_users TO '{parquet_path}' (FORMAT PARQUET)")
    conn.close()

    inspector = LakehouseInspector(dbt_manifest_path=manifest_path, data_dir=tmp_path / "data")
    result = inspector.get_dataset_schema("silver", "stg_users")

    assert result["dataset"] == "silver.stg_users"
    assert result["materialized"] is True
    cols = result["columns"]
    assert cols["user_id"]["physical_type"] == "BIGINT"
    assert cols["user_id"]["description"] == "Primary key"
    assert cols["email"]["physical_type"] == "VARCHAR"
    assert cols["email"]["description"] == "User email address"
    assert cols["created_at"]["physical_type"] == "TIMESTAMP"


def test_get_dataset_schema_unmaterialized(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_data = {
        "nodes": {
            "model.data_platform.dim_users": {
                "resource_type": "model",
                "fqn": ["data_platform", "gold", "dim_users"],
                "name": "dim_users",
                "description": "Dimension users",
                "columns": {
                    "id": {"data_type": "INTEGER", "description": "ID"},
                },
            }
        }
    }
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    inspector = LakehouseInspector(dbt_manifest_path=manifest_path, data_dir=tmp_path / "data")
    result = inspector.get_dataset_schema("gold", "dim_users")

    assert result["dataset"] == "gold.dim_users"
    assert result["materialized"] is False
    assert "status" in result
    assert "Parquet file not yet materialized" in result["status"]
    assert result["columns"]["id"]["manifest_type"] == "INTEGER"


def test_get_dataset_schema_not_found(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")

    inspector = LakehouseInspector(dbt_manifest_path=manifest_path, data_dir=tmp_path / "data")
    result = inspector.get_dataset_schema("silver", "nonexistent")

    assert "error" in result
    assert "Dataset nonexistent in layer silver not found" in result["error"]
