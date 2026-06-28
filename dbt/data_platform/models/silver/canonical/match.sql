-- Canonical domain entity: match/fixture (silver), conformed from ESPN.
-- A match belongs to a season (match -> season -> league); the league is reached
-- via season.league_id, so there is no direct league_id here.
--
-- IDENTITY (the load-bearing design decision): `match_id` is computed by the shared
-- provider-agnostic `canonical_match_id(league, season, date, home, away)` macro over
-- the CANONICAL RESOLVED identifiers, NOT raw ESPN strings, so a future provider
-- (Matchbook / football-data) describing the same real-world fixture lands on the SAME
-- match_id and de-dups. The five macro args, in order, are:
--   * league   -> the canonical league_id (md5(league_slug)), NOT the raw slug;
--   * season   -> the canonical season_id (md5(league_id || '|' || season_year)) — a
--                  deterministic surrogate any provider computes identically once it
--                  agrees on the league mapping + season year, NOT a raw season token;
--   * date     -> cast(kickoff_time as date) (UTC; kickoff_time is a UTC TIMESTAMP);
--   * home/away -> the canonical team_id, resolved through the team_aliases seed FIRST
--                  (so 'Wolves' and 'Wolverhampton Wanderers' both yield one team_id).
-- The raw ESPN event_id is NEVER an identity input. Because every argument is a
-- canonical surrogate (league_id reachable via season->league; season_id/team_ids
-- stored on the row; date = the row's kickoff_time), the AC8 test reconstructs this
-- exact call from the canonical tables alone and proves a non-ESPN caller lands on the
-- same match_id (see assert_resolver_provider_agnostic).
--
-- Idempotency: full-rebuild `+materialized: table` keyed on the deterministic
-- surrogate => re-running over a post-match scoreboard yields the SAME match_id with
-- ft_score now populated (E4, E9).
--
-- Scores (E11 — no fabrication): ESPN exposes full-time scores only.
--   * ht_score is always NULL (not exposed by ESPN).
--   * ft_score = the score columns only when the event is FINAL (status_completed),
--     else NULL (a pre-match fixture has no result).
with events as (
    select * from {{ ref('stg_espn_events') }}
),

-- Resolve each event's league/season to canonical surrogates and its home/away ESPN
-- name to a canonical team_id via the seed, exactly as league/season/team.sql do
-- (alias -> team_id; unseen -> md5(lower(name))).
resolved as (
    select
        e.espn_event_id,
        md5(e.league_slug)                                               as league_id,
        md5(md5(e.league_slug) || '|' || cast(e.season_year as varchar)) as season_id,
        coalesce(h.team_id, md5(lower(e.home_team_name)))                as home_team_id,
        coalesce(a.team_id, md5(lower(e.away_team_name)))                as away_team_id,
        e.kickoff_time,
        e.status_completed,
        e.home_score,
        e.away_score
    from events e
    left join {{ ref('team_aliases') }} h on e.home_team_name = h.alias
    left join {{ ref('team_aliases') }} a on e.away_team_name = a.alias
),

final as (
    select
        {{ canonical_match_id('league_id', 'season_id', 'cast(kickoff_time as date)', 'home_team_id', 'away_team_id') }} as match_id,
        season_id,
        home_team_id,
        away_team_id,
        cast(null as varchar) as favourite_team_id,
        kickoff_time,
        cast(null as varchar) as ht_score,
        case
            when status_completed then concat(cast(home_score as varchar), '-', cast(away_score as varchar))
            else null
        end                   as ft_score,
        status_completed
    from resolved
)

-- One row per canonical match_id. If a fixture appears more than once for the same
-- (season, UTC date, home, away), prefer the FINAL row (carries ft_score).
select
    match_id,
    season_id,
    home_team_id,
    away_team_id,
    favourite_team_id,
    kickoff_time,
    ht_score,
    ft_score
from final
qualify row_number() over (
    partition by match_id
    order by status_completed desc, kickoff_time desc
) = 1
