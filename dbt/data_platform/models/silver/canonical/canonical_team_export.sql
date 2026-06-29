-- Export canonical team table to Parquet for Python conform asset consumption.
-- Python reads this file directly; it never opens DuckLake.
{{
  config(
    materialized = 'external',
    location = env_var('DATA_DIR', '/app/data') ~ '/silver/canonical/team.parquet',
    format = 'parquet'
  )
}}

select
    team_id,
    name,
    similar_names
from {{ ref('team') }}
