-- Canonical domain entity: team (silver). Typed, empty scaffold — the conform
-- layer that populates it from bronze is a later feature. Materialized as a table
-- (not a view) so it is a real, writable canonical relation.
select
    cast(null as varchar)   as team_id,
    cast(null as varchar)   as name,
    cast(null as varchar[]) as similar_names
limit 0
