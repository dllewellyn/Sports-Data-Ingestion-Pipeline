-- Gold: one row per completed match with all human-readable data points joined in.
-- "Complete" means ft_score IS NOT NULL (ESPN has marked status_completed = true
-- and the score has been populated by a subsequent ingest run).
--
-- Favourite team: the home or away team whose runner had the lowest best_back_price
-- in the 1X2 (match odds) market at T-60 minutes before kickoff, sourced from the
-- Matchbook T-60 enrichment. NULL when no Matchbook odds data is linked.
--
-- Columns:
--   match_id            — canonical surrogate (stable across providers)
--   kickoff_time        — UTC timestamp
--   league              — league slug (e.g. 'eng.1')
--   season              — season display name (e.g. '2024-25')
--   home_team           — canonical home team name
--   away_team           — canonical away team name
--   ft_score            — full-time score string '<home>-<away>'
--   favourite_team      — name of the 1X2 pre-match favourite (NULL if no odds data)
--   favourite_odds      — best back price of the favourite runner at T-60 (NULL if no data)

-- T-60 enrichment Parquet (written by the matchbook_t60_enrichment Python asset).
-- try_read_parquet returns zero rows when the file is absent — favourite columns stay NULL.
with t60 as (
    select match_id, favourite_team_id, best_back_price_at_t60
    from read_parquet(
        '{{ env_var("DATA_DIR", "/app/data") }}/silver/matchbook_t60_enrichment.parquet'
    )
)

select
    m.match_id,
    m.kickoff_time,
    l.name                       as league,
    s.name                       as season,
    home.name                    as home_team,
    away.name                    as away_team,
    m.ft_score,
    fav.name                     as favourite_team,
    t60.best_back_price_at_t60   as favourite_odds
from {{ ref('match') }}          m
join {{ ref('season') }}         s    on s.season_id  = m.season_id
join {{ ref('league') }}         l    on l.league_id  = s.league_id
join {{ ref('team') }}           home on home.team_id = m.home_team_id
join {{ ref('team') }}           away on away.team_id = m.away_team_id
join t60                              on t60.match_id = m.match_id
join {{ ref('team') }}           fav  on fav.team_id  = cast(t60.favourite_team_id as varchar)
where m.ft_score is not null
order by m.kickoff_time desc
