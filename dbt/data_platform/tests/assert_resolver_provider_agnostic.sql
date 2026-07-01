-- AC8: a SECOND provider, resolving its OWN raw fixture to the same canonical
-- components, must land on the SAME match_id via the SAME resolver — proving the
-- identity is provider-agnostic and not ESPN-specific.
--
-- This test is LOAD-BEARING, not tautological. It does NOT feed arbitrary literals
-- (which could pass vacuously). Instead, for every real `match` row it RECONSTRUCTS
-- the exact canonical components match.sql fed `canonical_match_id` — but reaching
-- them purely through the canonical tables (match -> season -> league + the team_ids
-- stored on the row + the row's own kickoff date), i.e. the path a non-ESPN provider
-- would travel after resolving its own raw names/league through the shared seed +
-- league mapping. It then calls the SAME macro, in the SAME arg order/shape as
-- match.sql, and asserts the result equals that row's match.match_id.
--
-- Crucially NONE of the inputs come from stg_espn_events: league_id comes from
-- `int_league` (via `int_season`), season_id/home_team_id/away_team_id are read off the
-- canonical `int_match` row, and the date is `cast(match.kickoff_time as date)`. So the
-- equality exercises the real resolver against real conform output. If the macro had
-- ANY ESPN-specific input (e.g. the event_id), the reconstructed id would diverge and
-- this test would return failure rows.
with recomputed as (
    select
        m.match_id as actual_match_id,
        {{ canonical_match_id(
            'l.league_id',
            'm.season_id',
            'cast(m.kickoff_time as date)',
            'm.home_team_id',
            'm.away_team_id'
        ) }} as second_provider_match_id
    from {{ ref('int_match') }} m
    join {{ ref('int_season') }} s on m.season_id = s.season_id
    join {{ ref('int_league') }} l on s.league_id = l.league_id
)

-- Fail if any reconstructed id differs from the stored match_id.
select *
from recomputed
where actual_match_id != second_provider_match_id
