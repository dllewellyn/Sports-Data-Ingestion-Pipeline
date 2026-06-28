-- Canonical domain entity: league/competition (silver). Typed, empty scaffold.
-- A league is the competition itself (e.g. 'Premier League'); each edition is a
-- separate `season` row (season.league_id -> league.league_id).
select
    cast(null as varchar) as league_id,
    cast(null as varchar) as name,
    cast(null as boolean) as is_tournament
limit 0
