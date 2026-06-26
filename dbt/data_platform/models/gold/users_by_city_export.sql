-- Gold publish: write the curated aggregate out as Parquet.
-- dbt-duckdb's `external` materialization writes the file as part of the build,
-- so there is a single DuckDB writer (no cross-process race) and the gold layer
-- ends in Parquet, ready for downstream consumers.
{{
  config(
    materialized = 'external',
    location = env_var('DATA_DIR', '/app/data') ~ '/gold/users_by_city.parquet',
    format = 'parquet'
  )
}}

select
    city,
    user_count
from {{ ref('dim_users_by_city') }}
order by user_count desc
