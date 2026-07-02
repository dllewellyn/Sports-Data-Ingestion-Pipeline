---
name: dbt-model-build
description: >
  Add or modify a dbt intermediate (models/intermediate/int_*.sql) or marts
  model, a dbt macro, or a dbt singular/schema test in the
  Sports-Data-Ingestion-Pipeline warehouse layer. Codifies the
  ESPN-base-union-additions pattern, the canonical-identity-via-macro rule,
  the source()-vs-raw-read_parquet choice (and its CircularDependencyError
  trap), and the non-tautological singular-test convention. USE WHEN adding
  a new canonical/intermediate entity, changing how a provider's data folds
  into int_team/int_league/int_season/int_match, writing a new dbt macro, or
  adding a dbt test that must prove something real (not vacuously pass).
---

# dbt-model-build

Adds or changes a dbt intermediate/marts model, macro, or test in this repo's
DuckLake warehouse layer. The pattern is confirmed across `int_team.sql`,
`int_league.sql`, `int_season.sql`, `int_match.sql`, `int_espn_team_link.sql`,
`macros/canonical_match_id.sql`, and
`tests/assert_resolver_provider_agnostic.sql`. Read the actual current files
before writing new SQL — don't work from memory of this skill; the union
CTEs and additions-file lists change as providers are added.

## When to use

- User says "add a dbt model for X", "change how int_team resolves Y",
  "write a macro for Z", "add a dbt test proving W".
- A new canonical entity or a new provider's contribution to an existing
  canonical entity (`int_team`/`int_league`/`int_season`/`int_match`) is
  being added.
- Do NOT use for bronze ingestion (see `bronze-ingest-source`) or for wiring
  a new Dagster asset/job (see `dagster-asset-build`) — those are separate
  concerns even when they land in the same feature.

## The conform-is-symmetric pattern (intermediate models)

Every `int_*` canonical model is shaped the same way: an ESPN base CTE
(resolved via a seed alias, self-minting a deterministic id when unseeded)
`UNION ALL` each other provider's additions file, then `qualify
row_number()` keep-one on the id (ESPN wins ties — `source_rank` ordering).
Read `int_team.sql` end to end as the reference: `espn_names` →
`resolved` (seed lookup) → `espn_teams` → per-provider `*_additions` CTEs →
`combined` → final `qualify`. A new provider's contribution is a new
`<provider>_additions` CTE added to `combined`, not a structural change to
the ESPN base.

**Adding a new resolution tier** (e.g. a learned/bridged alias between the
seed and self-mint) means changing the `coalesce(...)` in the base CTE at
**every** model that independently resolves the same raw value — check for
copy-pasted resolution logic across `int_team.sql`, `int_match.sql`, and any
`int_<provider>_*_link.sql` before assuming one change suffices. Extract a
macro (see below) so they can't drift.

## Canonical identity: always through a macro, never a raw provider id

`match_id` goes through `macros/canonical_match_id.sql` — a 5-component
natural key (`league, season, kickoff_date_utc, home, away`), never a raw
ESPN `event_id` or any other provider's private id. If you're minting a new
kind of derived identity (not `match_id` itself), write a purpose-built
macro following `canonical_match_id.sql`'s shape: single responsibility, a
documented header explaining *why* each component is there and in that
order, called identically from every SQL site that needs it. A macro that's
only ever called from one place is still worth it once a second call site is
imminent — that's exactly what prevents the copy-paste drift above.

## `source()` vs raw `read_parquet()` literal — read this before touching a model that consumes a Python asset's output

A dbt model reading a Parquet file a Dagster Python asset produces has two
choices:

- **`{{ source('bronze', '<name>') }}`**, registered in `_sources.yml` and
  mapped in `BronzeAwareTranslator._SOURCE_ASSET_KEYS`
  (`src/data_platform/assets/dbt.py`) to the producing asset's `AssetKey`.
  This is what makes Dagster draw a real dependency edge — the model gets
  **scheduled to rebuild** after that asset produces new data, within the
  same job run if both are in the same `AssetSelection`.
- **A raw `read_parquet('{{ env_var("DATA_DIR", ...) }}/...')` literal.**
  Reads the exact same file, but is **invisible to Dagster's asset graph** —
  nothing knows the model needs to rebuild after the producer runs. The
  model will still get fresh data whenever it *next* happens to build for
  any other reason (eventual consistency), not immediately.

**Default to `source()`** — that's the whole point of a Dagster+dbt medallion
pipeline. But there's a hard ceiling: **dagster-dbt's automatic step
-subsetting can only resolve ONE external cross-op dependency tier per
`@dbt_assets` multi-asset op.** If a model already has one `source()`-tracked
Python-asset dependency (check whether it does — grep the model's SQL for
`{{ source(` and cross-reference `_SOURCE_ASSET_KEYS`) and you're about to
add a *second*, distinct Python-asset `source()` dependency to that same
model — especially if the two producing assets themselves depend on each
other — `Definitions` build raises a `CircularDependencyError`, even though
there's no real data cycle. This is documented, hit, and fixed once already:
read the comment block in `int_match.sql` around its `t60_enrichment` CTE
(search for `"Deliberately a raw read_parquet literal"`) for the exact
mechanism. When you hit this ceiling, the second dependency's file is read
via the raw-literal form instead — you accept next-run (not same-run)
freshness for that one input, register it in `_sources.yml` +
`BronzeAwareTranslator` anyway for documentation (harmless — a registered-
but-unreferenced source is inert), and say so in a comment at the read site,
mirroring `int_match.sql`'s.

Before writing a new `source()` reference, count how many *distinct* Python
-asset-produced sources the target model already consumes via `source()`. If
it's already one, and the asset you're adding a dependency on doesn't
already sit in a chain with the existing one, you're safe. If it does sit in
a chain (A depends on B, and the model wants to `source()` both A and B, or
already sources B and wants to add A where A→B), you're at the ceiling —
use the raw literal for the new one and document why, exactly as
`int_match.sql` does for T-60.

## `+database: lake` / selector gotchas

Pull the mechanical DuckLake/selector rules from `CLAUDE.md`'s "Non-obvious
constraints" section rather than re-deriving them here (they drift with the
warehouse config, and duplicating them risks going stale) — specifically the
`+database: lake` requirement, the `--indirect-selection=empty` gotcha when
selecting a subgraph whose `relationships` tests point at unselected tables,
and the `AssetKey(["intermediate","int_match"])` (schema-prefix only) vs.
`dbt build --select intermediate.int_match` (full path) distinction.

## Writing a non-tautological singular test

A dbt test that calls the same code path on both sides of its assertion
passes vacuously. Read `dbt/data_platform/tests/assert_resolver_provider_agnostic.sql`
as the reference shape: it reconstructs the canonical components a
*different* provider's raw fixture would independently produce — reached
purely through the canonical tables (never through `stg_espn_events`, so
nothing ESPN-specific leaks in), calls the *same* macro in the *same*
arg order the model under test uses, and asserts equality against a real row.
If the macro had any provider-specific input, the reconstruction would
diverge and the test would return failure rows. Structure every new singular
test this way: build the "expected" side via an independent path, not by
calling the thing being tested.

## Step order

1. Confirm the resolution/identity formula (macro or inline `coalesce`) —
   write it once, call it from every site.
2. Write the model SQL, following the union-CTEs-then-qualify shape.
3. Decide `source()` vs raw literal for any Python-asset-produced input
   (see above) — this decision affects `_sources.yml` and
   `src/data_platform/assets/dbt.py` too, do it before wiring Dagster
   (`dagster-asset-build` picks up from here).
4. Write the singular test (non-tautological) and/or schema tests
   (`not_null`, `unique`, `relationships`) in the model's `.yml`.
5. `dbt parse` (manifest only, no catalog needed) to confirm the SQL
   compiles; `dbt build --select <model>` (needs a live DuckLake catalog)
   for the real green criterion.

## Reference implementations

- Union-additions shape: `dbt/data_platform/models/intermediate/int_team.sql`
- Identity macro: `dbt/data_platform/macros/canonical_match_id.sql`
- `source()`-ceiling / raw-literal precedent:
  `dbt/data_platform/models/intermediate/int_match.sql` (`t60_enrichment` CTE)
- Non-tautological singular test:
  `dbt/data_platform/tests/assert_resolver_provider_agnostic.sql`
- Cross-language parity test (Python side of a shared formula):
  `tests/conform/test_parity.py`
