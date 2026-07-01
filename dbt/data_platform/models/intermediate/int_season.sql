-- Canonical domain entity: season/edition of a competition (silver), conformed
-- from ESPN. One row per edition of a league (e.g. the 2025-26 Premier League).
-- A match belongs to a season: match -> season -> league.
--
-- Identity: `season_id = md5(league_id || '|' || season_year)` — a deterministic
-- surrogate of (league, season year). Stable across runs.
-- NOTE: `match.sql` feeds the macro this canonical `season_id` (the md5 surrogate,
-- which already encodes league_id + season_year), so a future provider lands on the
-- same match_id once it agrees on the league mapping + season year and computes the
-- same season_id. ESPN does not expose a season window in the staged
-- event payload, so start_date/end_date are NULL (ERD makes them nullable) rather
-- than fabricated.
with espn as (
    select distinct
        league_slug,
        season_year,
        season_display
    from {{ ref('stg_espn_events') }}
)

select
    md5(md5(league_slug) || '|' || cast(season_year as varchar)) as season_id,
    md5(league_slug)                                             as league_id,
    season_display                                               as name,
    cast(null as date)                                           as start_date,
    cast(null as date)                                           as end_date
from espn
