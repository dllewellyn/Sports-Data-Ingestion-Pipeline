-- Gold: one row per completed match with all human-readable data points joined in.
-- "Complete" means ft_score IS NOT NULL (ESPN has marked status_completed = true
-- and the score has been populated by a subsequent ingest run).
--
-- Columns:
--   match_id          — canonical surrogate (stable across providers)
--   kickoff_time      — UTC timestamp
--   league            — league slug (e.g. 'eng.1')
--   season            — season display name (e.g. '2024-25')
--   home_team         — canonical home team name
--   away_team         — canonical away team name
--   ft_score          — full-time score string '<home>-<away>'
--   favourite_team    — name of the pre-match Matchbook favourite (NULL if no odds data)
select
    m.match_id,
    m.kickoff_time,
    l.name                  as league,
    s.name                  as season,
    home.name               as home_team,
    away.name               as away_team,
    m.ft_score,
    fav.name                as favourite_team
from {{ ref('match') }}          m
join {{ ref('season') }}         s    on s.season_id  = m.season_id
join {{ ref('league') }}         l    on l.league_id  = s.league_id
join {{ ref('team') }}           home on home.team_id = m.home_team_id
join {{ ref('team') }}           away on away.team_id = m.away_team_id
left join {{ ref('team') }}      fav  on fav.team_id  = m.favourite_team_id
where m.ft_score is not null
order by m.kickoff_time desc
