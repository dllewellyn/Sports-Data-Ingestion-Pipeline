-- Maps a canonical match to a Matchbook exchange event.
-- Reads the Python conform asset output (matchbook_resolved_links.parquet)
-- and materializes as a typed DuckLake table.
--
-- link_id: deterministic surrogate md5(matchbook_event_id) — stable across re-runs.
-- match_id: FK -> match.match_id (includes new_canonical rows via match.sql UNION ALL).
-- matchbook_event_id: provider reference (NOT a match_id input).
-- match_method: how the link was made ('fuzzy_high' | 'fuzzy_medium' | 'human_override').
-- confidence: 0.95 (fuzzy_high), 0.75 (fuzzy_medium), 1.0 (human_override).
-- review_status: 'auto_confirmed' | 'needs_review' | 'human_confirmed'.
{{
  config(
    materialized = 'table'
  )
}}

with resolved as (
    select * from {{ source('bronze', 'matchbook_resolved_links') }}
)

select
    md5(cast(matchbook_event_id as varchar))    as link_id,
    cast(match_id as varchar)                   as match_id,
    cast(matchbook_event_id as varchar)         as matchbook_event_id,
    cast(match_method as varchar)               as match_method,
    cast(confidence as double)                  as confidence,
    cast(review_status as varchar)              as review_status
from resolved
