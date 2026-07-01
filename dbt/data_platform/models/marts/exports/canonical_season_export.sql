-- Export canonical season table to Parquet for Python conform asset consumption.
-- Python reads this file directly; it never opens DuckLake.
{{
  config(
    materialized = 'external',
    location = env_var('DATA_DIR', '/app/data') ~ '/silver/canonical/season.parquet',
    format = 'parquet'
  )
}}

select
    season_id,
    league_id,
    name,
    start_date,
    end_date
from {{ ref('int_season') }}
