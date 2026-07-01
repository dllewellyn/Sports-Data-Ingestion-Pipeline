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
),

espn_leagues as (
    select
        md5(league_slug)                  as league_id,
        league_slug                       as name,
        -- Domestic ESPN league slugs are '<country>.<tier>' (e.g. 'eng.1'); tournament
        -- slugs are named (e.g. 'uefa.champions'). A purely numeric tier => domestic.
        not regexp_matches(split_part(league_slug, '.', 2), '^[0-9]+$') as is_tournament
    from espn
    group by league_slug
),

-- Canonical leagues minted by a provider's conform engine (action='new_canonical').
-- read_parquet REQUIRES the file to exist (it errors if absent); the conform asset
-- bootstrap-writes it empty, so an un-minted provider contributes zero rows.
matchbook_additions as (
    select
        cast(league_id as varchar)      as league_id,
        cast(name as varchar)           as name,
        cast(is_tournament as boolean)  as is_tournament
    from read_parquet(
        '{{ env_var("DATA_DIR", "/app/data") }}/silver/matchbook_canonical_league_additions.parquet'
    )
),

football_data_additions as (
    select
        cast(league_id as varchar)      as league_id,
        cast(name as varchar)           as name,
        cast(is_tournament as boolean)  as is_tournament
    from read_parquet(
        '{{ env_var("DATA_DIR", "/app/data") }}/silver/football_data_canonical_league_additions.parquet'
    )
),

combined as (
    select league_id, name, is_tournament, 0 as source_rank from espn_leagues
    union all
    select league_id, name, is_tournament, 1 as source_rank from matchbook_additions
    union all
    select league_id, name, is_tournament, 1 as source_rank from football_data_additions
)

-- One row per canonical league_id. On a collision, prefer the ESPN row.
select
    league_id,
    name,
    is_tournament
from combined
qualify row_number() over (
    partition by league_id
    order by source_rank
) = 1
