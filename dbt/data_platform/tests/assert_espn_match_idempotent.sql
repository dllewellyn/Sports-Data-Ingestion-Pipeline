-- Idempotency of the ESPN conform (AC4, E4, E9).
--
-- A dbt singular test runs over BUILT state and returns rows ONLY on failure. The
-- conform models are full-rebuild `+materialized: table` keyed on the deterministic
-- `canonical_match_id` surrogate, so the testable invariant on a single build is:
-- each fixture maps to exactly ONE match_id and no match_id is duplicated.
--
--   * Re-running over the SAME bronze scoreboard is a no-op: the surrogate is a pure
--     function of (league_id, season_year, UTC date, home_team_id, away_team_id), so
--     the rebuild reproduces the identical match_id set.
--   * Re-running over a POST-MATCH scoreboard fills ft_score on the SAME match_id:
--     the identity inputs are unchanged by the result, only ft_score flips from NULL
--     to a score. (Cross-build verification procedure: build over a SCHEDULED
--     fixture, then over the FINAL fixture, and confirm `select count(*) from int_match`
--     is unchanged while the row's ft_score becomes non-null. Run it via:
--       dbt build --select intermediate.int_match  # twice, swapping the bronze parquet
--     this single test asserts the within-build half that dbt can evaluate.)
--
-- Failure rows: any match_id appearing more than once (a second match_id for the
-- same fixture, or a duplicate link, would show up here).
select
    match_id,
    count(*) as n
from {{ ref('int_match') }}
group by match_id
having count(*) > 1
