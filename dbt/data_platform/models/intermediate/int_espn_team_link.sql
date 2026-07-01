-- Maps raw ESPN team references (ID and name) to canonical `team_id`.
with espn_teams as (
    select distinct
        home_team_id   as espn_team_id,
        home_team_name as espn_team_name
    from {{ ref('stg_espn_events') }}
    where home_team_id is not null
    union
    select distinct
        away_team_id   as espn_team_id,
        away_team_name as espn_team_name
    from {{ ref('stg_espn_events') }}
    where away_team_id is not null
),

resolved as (
    select distinct
        e.espn_team_id,
        e.espn_team_name,
        coalesce(s.team_id, md5(lower(e.espn_team_name))) as team_id,
        case when s.team_id is not null then 'seed_alias' else 'deterministic_md5' end as match_method
    from espn_teams e
    left join {{ ref('team_aliases') }} s
        on e.espn_team_name = s.alias
)

select
    md5('espn_team|' || cast(espn_team_id as varchar)) as link_id,
    team_id,
    cast(espn_team_id as varchar)                      as espn_team_id,
    espn_team_name,
    match_method,
    cast(1.0 as double)                                as confidence
from resolved
qualify row_number() over (partition by espn_team_id order by match_method desc) = 1
