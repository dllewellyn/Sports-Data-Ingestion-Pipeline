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
),

espn_teams as (
    select
        r.team_id,
        r.name,
        coalesce(a.similar_names, [r.name]) as similar_names
    from resolved r
    left join seed_aliases a
        on r.team_id = a.team_id
),

-- Canonical teams minted by a provider's conform engine (action='new_canonical').
-- Sourced via the dbt source() macro (not a raw read_parquet literal) so Dagster's
-- BronzeAwareTranslator can draw the edge from this model to the matchbook_conform
-- asset that produces the file — required for the model to be scheduled to rebuild
-- after conform mints new rows. The file still errors if absent; the conform asset
-- bootstrap-writes it empty, so an un-minted provider contributes zero rows.
matchbook_additions as (
    select
        cast(team_id as varchar)       as team_id,
        cast(name as varchar)          as name,
        cast(similar_names as varchar[]) as similar_names
    from {{ source('bronze', 'matchbook_canonical_team_additions') }}
),

football_data_additions as (
    select
        cast(team_id as varchar)       as team_id,
        cast(name as varchar)          as name,
        cast(similar_names as varchar[]) as similar_names
    from read_parquet(
        '{{ env_var("DATA_DIR", "/app/data") }}/silver/football_data_canonical_team_additions.parquet'
    )
),

combined as (
    select team_id, name, similar_names, 0 as source_rank from espn_teams
    union all
    select team_id, name, similar_names, 1 as source_rank from matchbook_additions
    union all
    select team_id, name, similar_names, 1 as source_rank from football_data_additions
)

-- One row per canonical team_id. On a collision (same id from ESPN and a provider
-- addition — only possible when they describe the same club), prefer the ESPN row.
select
    team_id,
    name,
    similar_names
from combined
qualify row_number() over (
    partition by team_id
    order by source_rank
) = 1
