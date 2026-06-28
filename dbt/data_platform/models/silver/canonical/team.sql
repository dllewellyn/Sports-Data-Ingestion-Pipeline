-- Canonical domain entity: team (silver), conformed from ESPN + the team_aliases
-- seed. One row per canonical team.
--
-- Resolution (AC7, AC7b; D2 seed-only):
--   * Every distinct ESPN team name (home and away, unioned) is matched against the
--     `team_aliases` seed on `alias`. A seeded name resolves to the seed's canonical
--     `team_id` + `canonical_name`.
--   * An UNSEEN name (no seed match) mints a NEW deterministic team of its own:
--     `team_id = md5(lower(name))`, `name = the ESPN name`. This is the SAME formula
--     the seed uses (`team_id = md5(lower(canonical_name))`), so if that name is later
--     added to the seed as a canonical_name the id is unchanged.
--   * `similar_names` = the seed's aliases for a seeded team, else just [name]. No new
--     ESPN spellings are written back into the seed (seed-only; no auto-learn).
--
-- `team_id` is the canonical identity fed into `canonical_match_id` by `match.sql`,
-- so a second provider resolving its own raw names through the same seed lands on the
-- same team_id and therefore the same match_id.
with espn_names as (
    select home_team_name as name from {{ ref('stg_espn_events') }}
    union
    select away_team_name as name from {{ ref('stg_espn_events') }}
),

-- Resolve each ESPN name to its canonical team via the seed (alias -> team_id).
resolved as (
    select distinct
        coalesce(s.team_id, md5(lower(e.name)))        as team_id,
        coalesce(s.canonical_name, e.name)             as name
    from espn_names e
    left join {{ ref('team_aliases') }} s
        on e.name = s.alias
),

-- All aliases known per canonical team from the seed.
seed_aliases as (
    select
        team_id,
        array_agg(distinct alias) as similar_names
    from {{ ref('team_aliases') }}
    group by team_id
)

select
    r.team_id,
    r.name,
    coalesce(a.similar_names, [r.name]) as similar_names
from resolved r
left join seed_aliases a
    on r.team_id = a.team_id
