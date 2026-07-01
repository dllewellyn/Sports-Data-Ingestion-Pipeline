-- Export canonical match table to Parquet for Python conform/T-60 asset consumption.
-- Includes home/away team names (joined from team) for runner resolution (AC9).
-- Python reads this file directly; it never opens DuckLake.
{{
  config(
    materialized = 'external',
    location = env_var('DATA_DIR', '/app/data') ~ '/silver/canonical/match.parquet',
    format = 'parquet'
  )
}}

select
    m.match_id,
    m.season_id,
    m.home_team_id,
    m.away_team_id,
    m.favourite_team_id,
    m.kickoff_time,
    ht.name as home_team_name,
    away_t.name as away_team_name
from {{ ref('int_match') }} m
left join {{ ref('int_team') }} ht on m.home_team_id = ht.team_id
left join {{ ref('int_team') }} away_t on m.away_team_id = away_t.team_id
