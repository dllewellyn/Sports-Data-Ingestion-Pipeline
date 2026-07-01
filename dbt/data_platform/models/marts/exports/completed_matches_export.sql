-- Gold publish: write completed_matches out as Parquet for downstream consumers
-- (notebooks, Python assets, external tools).
{{
  config(
    materialized = 'external',
    location = env_var('DATA_DIR', '/app/data') ~ '/gold/completed_matches.parquet',
    format = 'parquet'
  )
}}

select * from {{ ref('fct_completed_matches') }}
