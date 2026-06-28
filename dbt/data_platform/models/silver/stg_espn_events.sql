-- Silver: typed ESPN events (one row per event) staged from the faithful bronze
-- Parquet. The ESPN `date` is ISO-8601 with a `Z` (UTC) offset; DuckDB's bare
-- `cast(... as timestamp)` won't parse the trailing `Z`, so kickoff_time is parsed
-- with strptime (both with- and without-seconds shapes) into a UTC timestamp so
-- downstream conform can do `cast(kickoff_time as date)`.
with src as (
    select * from {{ source('bronze', 'espn_events') }}
)

select
    espn_event_id,
    league_slug,
    cast(season_year as integer)            as season_year,
    season_display,
    coalesce(
        try_strptime(kickoff_time, '%Y-%m-%dT%H:%M:%SZ'),
        try_strptime(kickoff_time, '%Y-%m-%dT%H:%MZ')
    )                                        as kickoff_time,
    home_team_id,
    home_team_name,
    away_team_id,
    away_team_name,
    status_name,
    status_state,
    cast(status_completed as boolean)        as status_completed,
    try_cast(home_score as integer)          as home_score,
    try_cast(away_score as integer)          as away_score
from src
