# Phase 0 — Research: Cross-Provider Conform

Every spec open question is a *non-blocker detail* (0 `[NEEDS CLARIFICATION]`, 0 BLOCKER). This file
resolves each plan-level unknown (OQ1–OQ3 from the spec + the orchestrator's OQ1–OQ3) with a
**Decision / Rationale / Alternatives considered** so no unknown survives into Phase 1.

---

## D1 — Neutral conform module path + shared-resolver layout

**Decision.** Relocate the Python engine to `src/data_platform/conform/` with:
- `conform/resolve.py` — the shared, provider-agnostic resolver: `team_aliases` seed resolution,
  `league_aliases` seed resolution, `canonical_match_id` Python replica, and the `season_id` derivation
  (`md5(league_id || '|' || year)`). It exposes typed pure functions (`resolve_team_id(name, seed)`,
  `resolve_league_id(provider, provider_key, seed)`, `derive_season_id(league_id, year)`,
  `compute_canonical_match_id(...)`).
- `conform/matchbook.py` — the Matchbook resolve-or-mint body (the current `engine.py` logic, moved and
  rewired to call `resolve.py`).
- `conform/football_data.py` — the placeholder interface module (US5): declares the shared
  resolve-or-mint contract; its record-matching body is a documented `NotImplementedError` stub, but its
  additions-file bootstrap + interface shape are real.
- `conform/__init__.py` — re-exports `run_conform` (Matchbook) for the asset import.
- The current sibling helpers (`event_name.py`, `overrides.py`, `scoring.py`) move under
  `conform/matchbook_*` or a `conform/matchbook/` subpackage — they are Matchbook-specific parsing/scoring
  and must not leak into the shared resolver.

**Rationale.** Matches spec Assumption 2 and CLAUDE.md "do not overengineer": per-provider modules + one
shared resolver is the KISS shape. A shared `resolve.py` is the single identity authority (FR-007) that
guarantees the ESPN SQL path and every Python path compute identical `team_id`/`league_id`/`match_id`.

**Alternatives considered.** A plugin/registry abstraction (rejected — overengineering, no third caller
yet); leaving parsing in `matchbook/` and only moving `engine.py` (rejected — the spec requires the old
`matchbook/conform/` path removed outright, constitution I, and splitting the package across two trees is
less legible).

## D2 — Dagster AssetKey for the relocated conform asset (orchestrator OQ1)

**Decision.** Keep the asset AssetKey **`AssetKey(["matchbook_conform"])`** unchanged, but move the asset
*module* to `src/data_platform/assets/intermediate/matchbook_conform.py` (unchanged path) importing from
the new `...conform.matchbook`. The **Python asset key is a free choice** — a stable string, not derived
from a folder — so keeping `matchbook_conform` avoids a gratuitous churn of the `BronzeAwareTranslator`
source-map (`assets/dbt.py:35`), the `deps=[...]` edges, and every `AssetSelection` reference in
`definitions.py`. The asset stays **one asset per provider** (spec Assumption 5).

**Rationale.** FR-008 requires the AssetKey change to keep lineage intact; the *lowest-risk* way to keep it
intact is to not change the key at all. The neutral-ness the spec asks for is delivered by the **module
relocation** (`src/data_platform/conform/`), which is what a reader greps for — not by the asset-key
string. Renaming the key to e.g. `conform_matchbook` would force edits to `assets/dbt.py:35`,
`definitions.py:59-65,131`, and every job/schedule selection with zero behavioural gain and a real
silent-edge-drop risk (a wrong source-map key severs bronze→conform).

**Alternatives considered.** `AssetKey(["conform_matchbook"])` or `AssetKey(["conform","matchbook"])`
(rejected — churns lineage wiring, higher risk of a silently dropped edge, no functional gain; the spec's
"first-class layer" goal is met by the module path + docs). Documented as a deliberate keep-the-key
decision so the reviewer does not read it as a missed rename.

## D3 — ESPN stays in-SQL; does it emit additions files? (spec OQ2 / orchestrator OQ2)

**Decision.** **ESPN stays purely in-SQL.** It is the anchor/base CTE of each canonical model's UNION
(`int_league`/`int_season`/`int_team`/`int_match` already `select ... from stg_espn_events` as their first
CTE). ESPN does **not** emit `espn_canonical_*_additions.parquet`. The four-file additions convention is
for the **Python** providers (Matchbook now, football-data later). This is documented as "ESPN's conform,
in SQL" (US3, FR-006 note).

**Rationale.** ESPN already mints team/league/season/match directly in SQL from the seed-resolved values;
routing it through Parquet would be a pointless round-trip and would *remove* the base of the union
(making every canonical model empty when no additions exist). The union base MUST remain the ESPN CTE.
Consistent with the union model: `<base ESPN CTE> UNION ALL <read_parquet(provider additions)> per
provider`, then distinct/keep-one.

**Alternatives considered.** Force ESPN through the additions convention "for symmetry" (rejected — breaks
the union base, adds an export/read round-trip, and is explicitly the spec's non-preferred OQ2 answer).

## D4 — Matchbook `provider_key` composite format for `league_aliases` (spec OQ3 / orchestrator OQ3)

**Decision.** Matchbook `provider_key` = the string **`"<sport_id>|<category_id>"`** (pipe-separated,
`sport_id` first), e.g. `"15|Soccer-1234"` — matching how `int_matchbook_league_link` already partitions on
the `(sport_id, category_id)` pair (`int_matchbook_league_link.sql:23-24,40-42`). ESPN `provider_key` =
the `league_slug` verbatim (e.g. `eng.1`). football_data `provider_key` = its `<family>|<division>` (or
`<country>|<division>`) key (finalised when its conform lands; the seed column is provider-scoped so this
does not block).

**Rationale.** The pipe composite is the same delimiter the codebase already uses for identity keys
(`concat_ws('|', ...)` in `canonical_match_id`, `md5(league_id || '|' || year)` for season). Deterministic,
human-readable in the CSV, and collision-free within a provider. `category_id` is extracted in the link
model as `json_extract_string(raw_event, '$.category-id')`, so the same value is available to the Python
conform from `raw_event`.

**Alternatives considered.** A JSON object key or a hash of the pair (rejected — the seed is human-curated;
a readable pipe string is the KISS choice and matches the existing link-table grain). `category_id` alone
(rejected — `sport_id` disambiguates football (15) from other sports sharing a category namespace).

## D5 — `league_aliases` seed shape, identity anchoring, and tests

**Decision.** New seed `dbt/data_platform/seeds/league_aliases.csv` with columns
`league_id, canonical_name, provider, provider_key`. `league_id` is **ESPN-anchored** (`md5(league_slug)`)
— the seed RECORDS the ESPN mapping (`provider=espn, provider_key=eng.1, league_id=md5('eng.1')`) and maps
OTHER providers' keys onto that same id (`provider=matchbook, provider_key=15|Soccer-XXXX,
league_id=md5('eng.1')`). Tests, declared in a **new `dbt/data_platform/seeds/_seeds.yml`** (there is no
`_seeds.yml` today; `team_aliases` currently has only column-type config in `dbt_project.yml` and **no
data tests**):
- composite `(provider, provider_key)` → `unique` (dbt `unique_combination_of_columns` or a
  `dbt_utils`-style combo; if `dbt_utils` is unavailable, a `unique` on a derived `provider || '|' ||
  provider_key` surrogate column materialised in a thin staging view — see D6).
- `league_id` → `not_null`, **NOT** `unique` (several providers map onto one id).
- `provider_key` → `not_null`. `provider` → `not_null` + `accepted_values [espn, matchbook, football_data]`.

**Rationale.** FR-015 + spec Clarification Q1. Mirrors how `team_aliases` allows many rows per `team_id`.
Anchoring on `md5(league_slug)` keeps ESPN identity byte-for-byte unchanged (the seed is additive).

**Alternatives considered.** Making `league_id` unique (rejected — directly contradicts the cross-provider
de-dup design). A single `provider_key`-unique test (rejected — keys collide across providers, per the
spec clarification).

## D6 — Composite-unique test facility for `(provider, provider_key)`

**Decision.** Check whether `dbt_utils` is installed (`packages.yml` / `dbt_packages/`). If present, use
`dbt_utils.unique_combination_of_columns(combination_of_columns=['provider','provider_key'])`. If **not**
present, do **not** add a new package dependency for one test (KISS + no tooling swap): instead add a
`unique` test on a seed-side or model-side surrogate. Simplest zero-dependency option: add a
`custom` singular test SQL under `dbt/data_platform/tests/` asserting
`select provider, provider_key from {{ ref('league_aliases') }} group by 1,2 having count(*) > 1` returns
zero rows. This is the standard dbt singular-test pattern and needs no package.

**Rationale.** Avoids a dependency/tooling change (constitution: no tool swaps). A singular test is a
first-class dbt test and is genuinely falsifiable (add a duplicate row → red).

**Alternatives considered.** Adding `dbt_utils` solely for this (rejected unless already present — new dep
for one test). A `unique` on a concatenated seed column (rejected — would require adding a derived column
to the human CSV, polluting the curated seed).

## D7 — `canonical_league_export` / `canonical_season_export` (FR-011)

**Decision.** Add two new dbt external-Parquet models under `models/marts/exports/` mirroring
`canonical_team_export.sql` / `canonical_match_export.sql`:
- `canonical_league_export.sql` → `$DATA_DIR/silver/canonical/league.parquet` (columns `league_id, name,
  is_tournament`).
- `canonical_season_export.sql` → `$DATA_DIR/silver/canonical/season.parquet` (columns `season_id,
  league_id, name, start_date, end_date`).
The Python conform reads these files to detect an already-resolved-this-run league/season and avoid
emitting a duplicate addition row; identity still follows seed-first `coalesce(seed, mint)` (the dbt
distinct/keep-one is the backstop). No Python DuckLake connection (FR-011, ARCHITECTURE rule 3).

**Rationale.** FR-011 + spec Clarification Q2. The team/match exports already establish this exact pattern
(two-file: table + external export). Adding league/season completes the set so a Python provider can
RESOLVE the whole chain from Parquet.

**Alternatives considered.** Reading the DuckLake catalog read-only (rejected — explicitly forbidden,
FR-011). Skipping the export and relying only on the dbt dedup backstop (rejected — the conform then
cannot detect an already-minted league within one run and would emit avoidable duplicate addition rows;
the export is the resolution data source).

## D8 — Rename `matchbook_canonical_additions.parquet` → `matchbook_canonical_match_additions.parquet`

**Decision.** Clean replace (constitution I — no dual-read shim). In the SAME change: update
`int_match.sql:83-85` `read_parquet` path, the `_sources.yml` `matchbook_canonical_additions`
`external_location` (`_sources.yml:77-80`), the asset bootstrap path
(`matchbook_conform.py:44-47`), the `config.py` additions path, and `engine.py`'s write path. The three
NEW Matchbook additions files (`_team_`, `_season_`, `_league_`) join it under `data/silver/`.

**Rationale.** FR-003, spec Assumption 3, Edge E4. One consistent naming across four files per provider.

**Alternatives considered.** Keep the old name for match, new names for the other three (rejected —
inconsistent, and constitution I forbids accreting a legacy name alongside the new convention).

## D9 — Four-file union in `int_team` / `int_league` / `int_season` (mirrors `int_match`)

**Decision.** Each canonical model keeps its ESPN CTE as the base, then `UNION ALL` a
`read_parquet('$DATA_DIR/silver/<provider>_canonical_<entity>_additions.parquet')` CTE **per Python
provider** (Matchbook now; football_data's file exists as a bootstrap-empty file so its union contributes
0 rows), then a final `distinct` / `qualify row_number() ... = 1` keep-one on the id so seed-resolved
duplicates collapse to one row (Edge E3, spec Assumption 4). `int_match` already does this for matches;
extend the same shape to team/league/season. All four additions files per provider MUST be
bootstrap-written empty before dbt runs (FR-016, Edge E4) because `read_parquet` **errors on a missing
file** (it is NOT `try_read_parquet` — the comment in `int_match.sql:72,95` is stale and in-scope to fix,
FR-014).

**Rationale.** FR-003 + FR-016 + spec Assumption 4. Single consistent extension pattern; the keep-one
collapse is what makes minting idempotent and de-dup-correct.

**Alternatives considered.** A separate canonical additions table in DuckLake (rejected — reintroduces the
second-writer problem, CLAUDE.md). `try_read_parquet` to tolerate a missing file (rejected — the function
used is `read_parquet`; the fix is the bootstrap-empty-file discipline, not swapping the reader, and the
stale comment must be corrected).

## D10 — Blank-name guard (Edge E5)

**Decision.** The provider conform MUST NOT emit a team-/league-addition row with an empty/blank parsed
name (it would violate `not_null` on `int_team.name` / `int_league.name`). Such an event is routed to the
exceptions queue (`<provider>_unresolved.parquet`) instead of minting an unnamed entity. Implemented in the
shared resolver / provider body as an explicit pre-mint guard, covered by a pytest.

**Rationale.** Edge E5; keeps the canonical tables' `not_null` gates green by fixing the data path, not
weakening the test (constitution II/III).

**Alternatives considered.** Minting with a placeholder name (rejected — reward-hacking / fabrication).
