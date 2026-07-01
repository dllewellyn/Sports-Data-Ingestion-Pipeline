-- Faithful projection of Matchbook bronze Parquet. No enrichment here —
-- market/runner/team names from the Postgres catalogue are out of scope
-- for this staging layer (deferred to a future enrichment model).
--
-- union_by_name=true (in the source definition) handles old files that
-- pre-date the kickoff_ms column: DuckDB fills the absent column with NULL.

select
    event_id,
    market_id,
    runner_id,
    ingested_at,
    sport_id,
    market_type,
    market_status,
    in_running,
    best_back_price,
    best_back_available,
    best_lay_price,
    best_lay_available,
    back_price_2,
    back_available_2,
    back_price_3,
    back_available_3,
    lay_price_2,
    lay_available_2,
    lay_price_3,
    lay_available_3,
    back_depth,
    lay_depth,
    wom,
    market_volume,
    runner_volume,
    handicap_line,
    event_participant_id,
    kickoff_ms
from {{ source('bronze', 'matchbook_odds') }}
