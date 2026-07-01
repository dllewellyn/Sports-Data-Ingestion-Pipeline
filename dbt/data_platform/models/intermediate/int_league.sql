-- Canonical domain entity: league/competition (silver), conformed from ESPN.
-- A league is the competition itself (e.g. 'Premier League'); each edition is a
-- separate `season` row (season.league_id -> league.league_id).
--
-- Identity: `league_id = md5(league_slug)` is a deterministic surrogate of the
-- league. It is stable across runs (full-rebuild safe) and — crucially — is the
-- value fed into `canonical_match_id` by `match.sql`, NOT the raw provider slug.
-- A future provider conforms its own league to the SAME canonical league_id (via a
-- shared league mapping), so the same competition resolves identically.
with espn as (
    select distinct
        league_slug,
        season_display
    from {{ ref('stg_espn_events') }}
)

select
    md5(league_slug)                  as league_id,
    league_slug                       as name,
    -- Domestic ESPN league slugs are '<country>.<tier>' (e.g. 'eng.1'); tournament
    -- slugs are named (e.g. 'uefa.champions'). A purely numeric tier => domestic.
    not regexp_matches(split_part(league_slug, '.', 2), '^[0-9]+$') as is_tournament
from espn
group by league_slug
