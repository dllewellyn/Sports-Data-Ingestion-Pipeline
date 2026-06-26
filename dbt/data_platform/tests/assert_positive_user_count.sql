-- Singular data test: every gold city row must have a positive user_count.
-- Returns offending rows; the test passes when zero rows are returned.
select city, user_count
from {{ ref('dim_users_by_city') }}
where user_count < 1
