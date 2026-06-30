"""Tests for LakehouseInspector dataset sampling (Spec 007 S3)."""

from pathlib import Path

import duckdb

from data_platform.mcp.inspector import LakehouseInspector


def test_get_dataset_sample_materialized(tmp_path: Path):
    bronze_dir = tmp_path / "data" / "bronze"
    bronze_dir.mkdir(parents=True)
    parquet_path = bronze_dir / "users.parquet"

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE users (id INT, name VARCHAR)")
    for i in range(15):
        conn.execute(f"INSERT INTO users VALUES ({i}, 'User_{i}')")
    conn.execute(f"COPY users TO '{parquet_path}' (FORMAT PARQUET)")
    conn.close()

    inspector = LakehouseInspector(data_dir=tmp_path / "data")
    result = inspector.get_dataset_sample("bronze", "users")

    assert result["dataset"] == "bronze.users"
    assert result["sample_count"] == 10
    rows = result["sample_rows"]
    assert len(rows) == 10
    assert rows[0] == {"id": 0, "name": "User_0"}
    assert rows[9] == {"id": 9, "name": "User_9"}


def test_get_dataset_sample_missing(tmp_path: Path):
    inspector = LakehouseInspector(data_dir=tmp_path / "data")
    result = inspector.get_dataset_sample("silver", "missing_table")

    assert result["status"] == "Sample unavailable"
    assert "Parquet file not found" in result["details"]
