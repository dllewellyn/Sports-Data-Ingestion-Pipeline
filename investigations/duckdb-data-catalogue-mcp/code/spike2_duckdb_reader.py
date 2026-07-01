from pathlib import Path

import duckdb


def test_duckdb_introspection():
    con = duckdb.connect(":memory:")

    # Check if any parquet files exist in data/ or evidence/
    sample_parquet = (
        Path(__file__).resolve().parents[2]
        / "football-data-co-uk-ingestion"
        / "evidence"
        / "spike2_bronze_sample.parquet"
    )

    if sample_parquet.exists():
        print(f"Inspecting sample parquet: {sample_parquet}")
        # Register as view
        con.execute(f"CREATE VIEW sample_table AS SELECT * FROM read_parquet('{sample_parquet}')")

        # Schema inspection
        schema_df = con.execute("DESCRIBE sample_table").df()
        print("\n--- Schema ---")
        print(schema_df[["column_name", "column_type"]])

        # Row summary / count
        count = con.execute("SELECT count(*) FROM sample_table").fetchone()[0]
        print(f"\nTotal rows: {count}")

        # Sample rows
        sample_df = con.execute("SELECT * FROM sample_table LIMIT 3").df()
        print("\n--- Sample Rows ---")
        print(sample_df.to_dict(orient="records"))
    else:
        print(f"Sample parquet not found at {sample_parquet}")


if __name__ == "__main__":
    test_duckdb_introspection()
