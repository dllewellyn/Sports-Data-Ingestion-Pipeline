-- Maps Matchbook team names (parsed from event names) to canonical `team_id` via resolved match links.
with events as (
    select
        event_id as matchbook_event_id,
        event_name
    from {{ source('bronze', 'matchbook_events') }}
    where event_name like '% vs %'
),

resolved as (
    select * from {{ source('bronze', 'matchbook_resolved_links') }}
    where match_id is not null and match_id != ''
),

matches as (
    select match_id, home_team_id, away_team_id
    from {{ ref('match') }}
),

event_teams as (
    select
        trim(split_part(e.event_name, ' vs ', 1)) as matchbook_team_name,
        m.home_team_id                            as team_id,
        r.match_method,
        r.confidence
    from resolved r
    join events e on cast(r.matchbook_event_id as varchar) = cast(e.matchbook_event_id as varchar)
    join matches m on r.match_id = m.match_id

    union all

    select
        trim(split_part(e.event_name, ' vs ', 2)) as matchbook_team_name,
        m.away_team_id                            as team_id,
        r.match_method,
        r.confidence
    from resolved r
    join events e on cast(r.matchbook_event_id as varchar) = cast(e.matchbook_event_id as varchar)
    join matches m on r.match_id = m.match_id
),

ranked as (
    select
        matchbook_team_name,
        team_id,
        match_method,
        confidence,
        row_number() over (
            partition by matchbook_team_name
            order by confidence desc
        ) as rn
    from event_teams
    where matchbook_team_name != ''
)

select
    md5('matchbook_team|' || matchbook_team_name) as link_id,
    team_id,
    matchbook_team_name,
    match_method,
    cast(confidence as double)                    as confidence
from ranked
where rn = 1
