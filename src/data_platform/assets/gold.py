"""Gold publish asset.

The gold aggregate is materialized to Parquet by the dbt `external` model
`users_by_city_export` (single DuckDB writer — no cross-process races). This
asset depends on that model and reads the published Parquet to attach run
metadata and emit a gold-layer OTel span, completing the trace across the flow.

Reading the Parquet file directly (not the warehouse) keeps DuckDB single-writer:
dbt owns the warehouse, this step only consumes the published artifact.
"""

import duckdb
from dagster import AssetKey, MaterializeResult, MetadataValue, asset

from ..config import settings
from ..otel import get_tracer


@asset(
    deps=[AssetKey(["gold", "users_by_city_export"])],
    group_name="gold",
    compute_kind="duckdb",
    description="Verifies and publishes the gold Parquet produced by dbt; emits a gold-layer span.",
)
def publish_gold_parquet() -> MaterializeResult:
    tracer = get_tracer()
    with tracer.start_as_current_span("publish.gold_users_by_city") as span:
        path = settings.gold_dir / "users_by_city.parquet"
        # Pure file read via DuckDB — no warehouse catalog, no writer contention.
        df = duckdb.sql(f"select * from read_parquet('{path}') order by user_count desc").df()
        span.set_attribute("gold.path", str(path))
        span.set_attribute("gold.rows", len(df))

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(len(df)),
            "path": MetadataValue.path(str(path)),
            "preview": MetadataValue.md(df.head(20).to_markdown(index=False)),
        }
    )
