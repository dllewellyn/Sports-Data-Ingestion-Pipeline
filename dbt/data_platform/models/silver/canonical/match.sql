-- Canonical domain entity: match/fixture (silver). Typed, empty scaffold.
-- A match belongs to a season (match -> season -> league); the league is reached
-- via season.league_id, so there is no direct league_id here.
-- favourite_team_id is nullable (captured T-45m before kickoff).
select
    cast(null as varchar)   as match_id,
    cast(null as varchar)   as season_id,
    cast(null as varchar)   as home_team_id,
    cast(null as varchar)   as away_team_id,
    cast(null as varchar)   as favourite_team_id,
    cast(null as timestamp) as kickoff_time,
    cast(null as varchar)   as ht_score,
    cast(null as varchar)   as ft_score
limit 0
