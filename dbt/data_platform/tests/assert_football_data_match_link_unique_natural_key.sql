-- The composite natural key must uniquely identify one football-data.co.uk match.
-- Returns the offending tuples (any that appear more than once) -> dbt fails if
-- the result is non-empty. Trivially passes while the table is empty; it enforces
-- the contract once the link table is populated by the conform layer.
select
    family,
    country,
    division,
    season,
    match_date,
    home_team,
    away_team,
    count(*) as n
from {{ ref('int_football_data_match_link') }}
group by 1, 2, 3, 4, 5, 6, 7
having count(*) > 1
