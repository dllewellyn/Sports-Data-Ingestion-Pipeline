-- Provider link: one row per ESPN event, mapping it to its canonical `match_id`.
--
-- IDENTITY: `match_id` is recomputed here by the SAME resolution + the SAME
-- `canonical_match_id(...)` call as `match.sql` (resolve league_id/season_id and the
-- home/away team_id via the team_aliases seed with the identical
-- `coalesce(seed.team_id, md5(lower(name)))` fallback, then call the macro with the
-- identical arg order). It therefore EQUALS the `match.match_id` for the same
-- fixture; the relationships test on `match_id -> ref('match')` catches any drift.
-- The raw ESPN `event_id` is the stored provider reference, NOT an identity input —
-- `match_id` is derived from the canonical natural key, never from `espn_event_id`.
--
-- `link_id` is a deterministic surrogate of `espn_event_id` (`md5(espn_event_id)`),
-- so a full-rebuild over the same events yields the SAME link_id and never
-- duplicates a link (one link per event).
--
-- PROVENANCE (the forward-compatible linkage seam): ESPN events resolve via the
-- shared deterministic macro, so every link is an EXACT match. The three columns
-- carry that truth — `match_method = 'deterministic'`, `confidence = 1.0`,
-- `review_status = 'auto_confirmed'` — not stubs. A future fuzzy/confidence linkage
-- engine (a deferred epic) will write sub-1.0 confidence + 'needs_review' rows here;
-- the columns exist now so that engine is purely additive.
with events as (
    select * from {{ ref('stg_espn_events') }}
),

-- Resolve each event's league/season to canonical surrogates and its home/away ESPN
-- name to a canonical team_id via the seed, IDENTICALLY to match.sql (alias ->
-- team_id; unseen -> md5(lower(name))).
resolved as (
    select
        e.espn_event_id,
        md5(e.league_slug)                                               as league_id,
        md5(md5(e.league_slug) || '|' || cast(e.season_year as varchar)) as season_id,
        coalesce(h.team_id, md5(lower(e.home_team_name)))                as home_team_id,
        coalesce(a.team_id, md5(lower(e.away_team_name)))                as away_team_id,
        e.kickoff_time
    from events e
    left join {{ ref('team_aliases') }} h on e.home_team_name = h.alias
    left join {{ ref('team_aliases') }} a on e.away_team_name = a.alias
)

select
    md5(espn_event_id) as link_id,
    {{ canonical_match_id('league_id', 'season_id', 'cast(kickoff_time as date)', 'home_team_id', 'away_team_id') }} as match_id,
    espn_event_id,
    'deterministic'      as match_method,
    cast(1.0 as double)  as confidence,
    'auto_confirmed'     as review_status
from resolved
