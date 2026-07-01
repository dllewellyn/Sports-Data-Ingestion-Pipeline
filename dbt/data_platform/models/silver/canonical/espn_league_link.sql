-- Maps raw ESPN league slugs to canonical `league_id`.
with espn_leagues as (
    select distinct league_slug
    from {{ ref('stg_espn_events') }}
    where league_slug is not null
)

select
    md5('espn_league|' || league_slug) as link_id,
    md5(league_slug)                   as league_id,
    league_slug                        as espn_league_slug,
    'deterministic'                    as match_method,
    cast(1.0 as double)                as confidence
from espn_leagues
