-- Canonical domain entity: season/edition of a competition (silver), conformed
-- from ESPN. One row per edition of a league (e.g. the 2025-26 Premier League).
-- A match belongs to a season: match -> season -> league.
--
-- Identity: `season_id = md5(league_id || '|' || season_year)` — a deterministic
-- surrogate of (league, season year). Stable across runs.
-- NOTE: `match.sql` feeds the macro this canonical `season_id` (the md5 surrogate,
-- which already encodes league_id + season_year), so a future provider lands on the
-- same match_id once it agrees on the league mapping + season year and computes the
-- same season_id. ESPN does not expose a season window in the staged
-- event payload, so start_date/end_date are NULL (ERD makes them nullable) rather
-- than fabricated.
with espn as (
    select distinct
        league_slug,
        season_year,
        season_display
    from {{ ref('stg_espn_events') }}
),

espn_seasons as (
    select
        md5(md5(league_slug) || '|' || cast(season_year as varchar)) as season_id,
        md5(league_slug)                                             as league_id,
        season_display                                               as name,
        cast(null as date)                                           as start_date,
        cast(null as date)                                           as end_date
    from espn
),

-- Canonical seasons minted by a provider's conform engine (action='new_canonical').
-- read_parquet REQUIRES the file to exist (it errors if absent); the conform asset
-- bootstrap-writes it empty, so an un-minted provider contributes zero rows. Every
-- addition row carries its non-null league_id so the int_season->int_league
-- relationships test holds (E10).
matchbook_additions as (
    select
        cast(season_id as varchar)  as season_id,
        cast(league_id as varchar)  as league_id,
        cast(name as varchar)       as name,
        cast(start_date as date)    as start_date,
        cast(end_date as date)      as end_date
    from read_parquet(
        '{{ env_var("DATA_DIR", "/app/data") }}/silver/matchbook_canonical_season_additions.parquet'
    )
),

football_data_additions as (
    select
        cast(season_id as varchar)  as season_id,
        cast(league_id as varchar)  as league_id,
        cast(name as varchar)       as name,
        cast(start_date as date)    as start_date,
        cast(end_date as date)      as end_date
    from read_parquet(
        '{{ env_var("DATA_DIR", "/app/data") }}/silver/football_data_canonical_season_additions.parquet'
    )
),

combined as (
    select season_id, league_id, name, start_date, end_date, 0 as source_rank from espn_seasons
    union all
    select season_id, league_id, name, start_date, end_date, 1 as source_rank from matchbook_additions
    union all
    select season_id, league_id, name, start_date, end_date, 1 as source_rank from football_data_additions
)

-- One row per canonical season_id. On a collision, prefer the ESPN row.
select
    season_id,
    league_id,
    name,
    start_date,
    end_date
from combined
qualify row_number() over (
    partition by season_id
    order by source_rank
) = 1
