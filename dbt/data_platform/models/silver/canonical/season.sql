-- Canonical domain entity: season/edition of a competition (silver). Typed,
-- empty scaffold — populated by a later conform layer.
--
-- A season is one edition of a league/competition (e.g. the 2025-2026 Premier
-- League). It is the level a match belongs to: match -> season -> league.
-- Provider season tokens (e.g. football-data.co.uk's '2324') are resolved to a
-- canonical season_id by the conform layer.
select
    cast(null as varchar) as season_id,    -- internal canonical season identifier
    cast(null as varchar) as league_id,    -- FK -> league.league_id
    cast(null as varchar) as name,         -- season label (e.g. '2025-2026' / '2026')
    cast(null as date)    as start_date,   -- first day of the season (nullable)
    cast(null as date)    as end_date      -- last day of the season (nullable)
limit 0
