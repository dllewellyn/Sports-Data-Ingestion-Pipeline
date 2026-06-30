"""Tests for LakehouseInspector SQL query execution (Spec 007 S4)."""

from pathlib import Path

import duckdb

from data_platform.mcp.inspector import LakehouseInspector


def test_run_sql_query_valid_and_truncation(tmp_path: Path):
    bronze_dir = tmp_path / "data" / "bronze"
    bronze_dir.mkdir(parents=True)
    parquet_path = bronze_dir / "matches.parquet"

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE matches (id INT, score VARCHAR)")
    for i in range(70):
        conn.execute(f"INSERT INTO matches VALUES ({i}, '2-1')")
    conn.execute(f"COPY matches TO '{parquet_path}' (FORMAT PARQUET)")
    conn.close()

    inspector = LakehouseInspector(data_dir=tmp_path / "data")
    result = inspector.run_sql_query("SELECT * FROM bronze_matches")

    assert result["query"] == "SELECT * FROM bronze_matches"
    assert result["row_count"] == 70
    rows = result["records"]
    assert len(rows) == 50
    assert rows[0] == {"id": 0, "score": "2-1"}


def test_run_sql_query_mutation_rejection(tmp_path: Path):
    inspector = LakehouseInspector(data_dir=tmp_path / "data")

    mutations = [
        "DROP TABLE bronze_matches",
        "INSERT INTO bronze_matches VALUES (1, '0-0')",
        "UPDATE bronze_matches SET score='1-1'",
        "DELETE FROM bronze_matches",
        "ALTER TABLE bronze_matches ADD COLUMN extra INT",
        "CREATE TABLE hack AS SELECT * FROM bronze_matches",
        "ATTACH 'hack.db' AS hack",
    ]
    for q in mutations:
        res = inspector.run_sql_query(q)
        assert "error" in res
        assert "Only read-only SELECT queries are permitted" in res["error"]


def test_run_sql_query_syntax_error(tmp_path: Path):
    inspector = LakehouseInspector(data_dir=tmp_path / "data")
    res = inspector.run_sql_query("SELECT * FROM nonexistent_view")
    assert "error" in res
    assert "nonexistent_view" in res["error"]
