-- NEW link table: maps a canonical match to a football-data.co.uk source row.
--
-- football-data.co.uk exposes NO stable match id, so the external reference is a
-- COMPOSITE NATURAL KEY rather than a single provider id. The columns mirror the
-- two raw bronze record cores in src/data_platform/models/schemas.py:
--   main  (MainMatchRecord):  Div, Date, HomeTeam, AwayTeam   (country = league dir)
--   extra (ExtraMatchRecord): Country, League, Season, Date, Home, Away
-- unified here as family + country + division + season + match_date + home/away.
-- Typed, empty scaffold — populated by a later conform layer.
select
    cast(null as varchar) as link_id,
    cast(null as varchar) as match_id,
    cast(null as varchar) as family,      -- 'main' | 'extra'
    cast(null as varchar) as country,     -- extra-family only (e.g. 'Argentina'); null for main
    cast(null as varchar) as division,    -- Div for main (e.g. 'E0') / League for extra
    cast(null as varchar) as season,      -- season token (e.g. '2324' / '2025')
    cast(null as varchar) as match_date,  -- raw source Date
    cast(null as varchar) as home_team,   -- raw source HomeTeam / Home
    cast(null as varchar) as away_team    -- raw source AwayTeam / Away
limit 0
