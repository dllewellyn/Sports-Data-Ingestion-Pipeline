-- Export canonical league table to Parquet for Python conform asset consumption.
-- Python reads this file directly; it never opens DuckLake.
{{
  config(
    materialized = 'external',
    location = env_var('DATA_DIR', '/app/data') ~ '/silver/canonical/league.parquet',
    format = 'parquet'
  )
}}

select
    league_id,
    name,
    is_tournament
from {{ ref('int_league') }}
