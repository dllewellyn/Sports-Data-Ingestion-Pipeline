{#
    Provider-agnostic canonical match identity resolver.

    Computes a deterministic surrogate `match_id` as an md5 over the 5-component
    natural key of a fixture, in this exact order:
        (canonical league, canonical season, kickoff UTC calendar date,
         canonical home team, canonical away team)

    This is the single identity authority reused by EVERY soccer provider. It has
    NO provider-specific arguments: the raw ESPN `event_id` (or any other provider
    id) is NEVER an identity input. Every provider's conform layer must call this
    same macro so two providers describing the same fixture resolve to one id.

    `kickoff_date_utc` is the date component. Callers pass `cast(kickoff_time as
    date)` (interpreted in UTC) so identity cannot drift across timezone
    representations. The macro re-casts to `date` internally so that whether a
    caller passes a timestamp or an already-cast date, only the calendar date is
    used — an intra-day kickoff-time revision keeps the same `match_id`. The
    `cast(... as date)` is idempotent on a date input.

    Computed entirely inside dbt over DuckDB's md5(); single-writer-safe (no second
    Python writer touches the warehouse).
#}
{% macro canonical_match_id(league, season, kickoff_date_utc, home, away) %}
    md5(concat_ws('|',
        cast({{ league }} as varchar),
        cast({{ season }} as varchar),
        cast(cast({{ kickoff_date_utc }} as date) as varchar),
        cast({{ home }} as varchar),
        cast({{ away }} as varchar)
    ))
{% endmacro %}
