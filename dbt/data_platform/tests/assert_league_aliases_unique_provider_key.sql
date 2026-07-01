-- The composite (provider, provider_key) must uniquely identify one league
-- alias row. Returns the offending tuples (any that appear more than once) ->
-- dbt fails if the result is non-empty. `league_id` is deliberately NOT unique
-- (several providers map onto one canonical id); the uniqueness contract lives
-- on the (provider, provider_key) pair.
select
    provider,
    provider_key,
    count(*) as n
from {{ ref('league_aliases') }}
group by 1, 2
having count(*) > 1
