-- Singular test for the provider-agnostic canonical_match_id() resolver.
-- A dbt singular test returns rows ONLY on failure; this query is empty when the
-- macro is correct.
--
-- Two assertions:
--   1. On FIXED literals the macro returns a FIXED, hand-derived md5. The expected
--      hash was computed from the EXACT expression the macro emits:
--        python3 -c "import hashlib; print(hashlib.md5(
--          '|'.join(['eng.1','2025','2025-08-16','Liverpool','Bournemouth']).encode()
--        ).hexdigest())"  -> 74bd5a8143f7e52d98d140ba8bb5c8eb
--      i.e. md5(concat_ws('|', league, season, cast(date as varchar), home, away))
--      with a date rendering as YYYY-MM-DD. "Green" is reachable only by emitting
--      that exact expression — never by editing the expected value.
--   2. UTC calendar-date identity: two kickoff timestamps on the SAME UTC day
--      collapse to ONE match_id (an intra-day time revision does not change it),
--      while a different day yields a DIFFERENT id. The resolver takes NO provider
--      argument — the raw ESPN event id is never an identity input.

with fixed as (
    select {{ canonical_match_id("'eng.1'", "'2025'", "cast('2025-08-16' as date)", "'Liverpool'", "'Bournemouth'") }} as match_id
),
same_day_morning as (
    select {{ canonical_match_id("'eng.1'", "'2025'", "cast('2025-08-16 12:30:00' as timestamp)", "'Liverpool'", "'Bournemouth'") }} as match_id
),
same_day_evening as (
    select {{ canonical_match_id("'eng.1'", "'2025'", "cast('2025-08-16 19:45:00' as timestamp)", "'Liverpool'", "'Bournemouth'") }} as match_id
),
next_day as (
    select {{ canonical_match_id("'eng.1'", "'2025'", "cast('2025-08-17 19:45:00' as timestamp)", "'Liverpool'", "'Bournemouth'") }} as match_id
)

-- Assertion 1: fixed literals -> hand-derived hash.
select 'fixed_hash_mismatch' as failure, fixed.match_id as got
from fixed
where fixed.match_id != '74bd5a8143f7e52d98d140ba8bb5c8eb'

union all

-- Assertion 2a: same UTC day collapses to one id.
select 'same_day_drifted' as failure, same_day_evening.match_id as got
from same_day_morning, same_day_evening
where same_day_morning.match_id != same_day_evening.match_id

union all

-- Assertion 2b: a different UTC day must be a different id.
select 'different_day_collided' as failure, next_day.match_id as got
from same_day_evening, next_day
where same_day_evening.match_id = next_day.match_id
