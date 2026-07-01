-- Maps Matchbook sport/category to canonical `league_id` via resolved match links.
with events as (
    select
        event_id as matchbook_event_id,
        sport_id,
        json_extract_string(raw_event, '$.category-id') as category_id
    from {{ source('bronze', 'matchbook_events') }}
),

resolved as (
    select * from {{ source('bronze', 'matchbook_resolved_links') }}
    where match_id is not null and match_id != ''
),

matches as (
    select match_id, league_id
    from {{ ref('match') }}
),

event_leagues as (
    select
        cast(e.sport_id as varchar)                   as sport_id,
        coalesce(e.category_id, 'unknown')            as category_id,
        m.league_id,
        r.match_method,
        r.confidence
    from resolved r
    join events e on cast(r.matchbook_event_id as varchar) = cast(e.matchbook_event_id as varchar)
    join matches m on r.match_id = m.match_id
),

ranked as (
    select
        sport_id,
        category_id,
        league_id,
        match_method,
        confidence,
        row_number() over (
            partition by sport_id, category_id, league_id
            order by confidence desc
        ) as rn
    from event_leagues
)

select
    md5('matchbook_league|' || sport_id || '|' || category_id || '|' || league_id) as link_id,
    league_id,
    sport_id                                                                      as matchbook_sport_id,
    category_id                                                                   as matchbook_category_id,
    match_method,
    cast(confidence as double)                                                    as confidence
from ranked
where rn = 1
