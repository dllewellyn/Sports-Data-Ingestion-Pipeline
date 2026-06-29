"""Verify DuckDB runtime version satisfies the DuckLake 1.0 minimum (Spec 002)."""
import duckdb
from packaging.version import Version


def test_duckdb_version_meets_ducklake_minimum():
    # DuckLake 1.0 requires >= 1.5.2 per spec 002 §5.4
    assert Version(duckdb.__version__) >= Version("1.5.2"), (
        f"duckdb {duckdb.__version__} is too old; DuckLake 1.0 requires >=1.5.2"
    )
