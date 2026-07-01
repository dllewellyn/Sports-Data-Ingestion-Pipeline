# Feature Specification: Cross-Provider Conform — Symmetric Resolve-or-Mint for Every Provider

**Feature directory**: `specs/012-cross-provider-conform/`
**Created**: 2026-07-01
**Status**: Draft
**Input**: "Today 'conform' (resolving raw provider records onto canonical entities — link an existing match/team or mint a new one) lives inside the matchbook package, which falsely implies conforming only happens for Matchbook. Every provider (ESPN, Matchbook, football-data) must be able to BOTH link to an existing canonical match/team AND mint a new one, and there must never be a record without a match or a team. Fix both the naming/location AND the structural gap. Fold in a naming/location recommendation."

## Clarifications

### Session 2026-07-01

Run non-interactively (no user available). Two detail-level ambiguities were surfaced during the
`speckit-clarify` scan; neither is a build-blocker (no materially divergent build hinges on them).
Best-guess answers are recorded here and encoded into the requirements below as resolved assumptions.

- Q: What is the `league_aliases` seed's uniqueness/natural key — which column(s) carry the `unique`
  test? (`league_id` cannot be unique — several providers deliberately map onto one ESPN-anchored
  `league_id`; `provider_key` alone can collide across providers.) → A: The composite
  `(provider, provider_key)` is the unique natural key (one canonical mapping per provider key);
  `league_id` and `provider_key` are `not_null`; `league_id` is intentionally NON-unique. Mirrors how
  `team_aliases` allows many `alias` rows per `team_id`. (Encoded in FR-015.)
- Q: When a Python provider must RESOLVE (not mint) an existing canonical league/season, what data
  source does it read — given FR-011 forbids a DuckLake connection and only `canonical_team_export` /
  `canonical_match_export` exist today (no league/season export)? → A: Add
  `canonical_league_export` and `canonical_season_export` dbt external-Parquet models alongside the
  existing team/match exports, and have the Python conform read those files — never the DuckLake
  catalog. League/season resolution otherwise follows the seed-first `coalesce(seed, mint)` formula, so
  the export is only needed to detect an already-minted-this-run league/season and avoid a duplicate
  addition row (dedup also collapses at the dbt `distinct`/keep-one layer as a backstop). (Encoded in
  FR-011.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A minted match always has its full season→league→team chain (referential integrity holds) (Priority: P1)

When any provider's conform step mints a **new** canonical match — because the fixture does not yet
exist in the canonical set — it must also mint (or reuse) every canonical row that match references:
its two **team** rows, its **season**, and that season's **league**. Today a Matchbook `new_canonical`
override mints a match whose `home_team_id`/`away_team_id` are `md5(lower(parsed_name))`
(`matchbook/conform/engine.py:227-228`), but those team ids are never added to `int_team` (which is
built solely from ESPN names, `int_team.sql:18-22`), and the minted `season_id`/`league_id` are never
added to `int_season`/`int_league`. Because `int_match` carries dbt `relationships` tests
`home_team_id`/`away_team_id` → `int_team.team_id` (`_intermediate.yml:76-91`) and `season_id` →
`int_season.season_id` (`_intermediate.yml:68-75`), and `int_season.league_id` → `int_league.league_id`
(`_intermediate.yml:49-56`), a minted-but-orphaned team/season/league turns `dbt build` **red**. This
is the core structural gap: the invariant "no record without a match or a team" closes to "no match
without a real season→league→team chain".

**Why this priority**: This is the confirmed latent hard failure and the user's non-negotiable
invariant. Every other story builds on the guarantee that minting a match also mints its full chain. It
is the smallest slice that delivers real value: a `new_canonical` decision no longer breaks the FK tests.

**Independent Test**: Seed one Matchbook event whose parsed team names are **not** in the ESPN data or
the `team_aliases` seed and whose league is not covered by ESPN, mark it `new_canonical` via an
override, run the conform asset then `dbt build --select int_team int_league int_season int_match
int_matchbook_event_link`. The minted match's team/season/league ids all appear in their canonical
tables, and all four `relationships` tests pass green (they go red today).

**Acceptance Scenarios**:

1. **Given** a provider event that resolves to no existing canonical match and is designated to mint a
   new one, **When** the provider's conform step runs, **Then** it writes a canonical match-addition row
   **and** a canonical team-addition row per referenced team id **and** the referenced season- and
   league-addition rows (only for the chain members not already resolved), to provider-scoped Parquet
   files (`data/silver/<provider>_canonical_match_additions.parquet`,
   `<provider>_canonical_team_additions.parquet`, `<provider>_canonical_season_additions.parquet`,
   `<provider>_canonical_league_additions.parquet`).
2. **Given** those addition Parquet files exist, **When** `dbt build --select int_league int_season
   int_team int_match` runs, **Then** each canonical table contains the minted rows (unioned in via
   `read_parquet`, mirroring how `int_match` already unions match additions, `int_match.sql:73-92`) and
   all four `int_match`/`int_season` `relationships` tests pass.
3. **Given** a minted match, **When** `int_match` is queried for that `match_id`, **Then** its
   `home_team_id`, `away_team_id`, and `season_id` (whose `league_id` in turn) all exist as rows in
   `int_team`/`int_season`/`int_league` (no orphan anywhere in the chain).

---

### User Story 2 - Minted teams AND leagues de-duplicate through their alias seeds (no duplicate clubs or competitions) (Priority: P1)

A provider that mints a team must resolve the name through the `team_aliases` seed **first**, exactly
as ESPN does (`coalesce(seed.team_id, md5(lower(name)))`, `int_team.sql:27`). Today Matchbook team
minting does raw `md5(home_parsed.lower())` (`engine.py:227`) with **no** seed lookup, so a Matchbook
event for "Wolves" mints a brand-new team even though ESPN already has "Wolverhampton Wanderers" under a
seeded alias — a duplicate canonical club. Symmetrically, a provider that mints a **league** must
resolve its provider league identifier through a new `league_aliases` seed. Today Matchbook league
minting uses the constant `league_id = md5('matchbook_football')` (`engine.py:224`), which can **never**
equal ESPN's `md5(league_slug)` for the same competition — so a Matchbook-minted match can never share a
`match_id` with the ESPN fixture. The `league_aliases` seed maps each provider's league key
(ESPN `league_slug`, a Matchbook `sport_id`/`category_id` composite, etc.) onto the **ESPN-anchored**
canonical `league_id` (`md5(league_slug)`), so a minted league lands on the existing canonical id when a
mapping exists. Both seed-resolutions live in one shared helper reused by ESPN's SQL conform and every
Python provider's minting path.

**Why this priority**: Without this, User Story 1's structural fix would still produce duplicate teams
and duplicate leagues (and, because team/league/season identity feeds `canonical_match_id`, duplicate
matches) — undermining the cross-provider de-dup that is the entire point of a canonical model. It is
co-P1 with Story 1: fixing one without the other trades a hard failure for a silent data-quality failure.

**Independent Test**: (teams) add "Wolves" as an alias in `team_aliases`; mint a Matchbook team from an
event naming "Wolves"; assert the minted `team_id` equals the seed's Wolverhampton Wanderers id (not
`md5('wolves')`) and `int_team` has one row for that club. (leagues) add a `league_aliases` row mapping
the Matchbook `(sport_id, category_id)` for the Premier League onto ESPN's `md5('eng.1')`; mint a
Matchbook match for that competition; assert the minted `league_id`/`season_id`/`match_id` equal the
ESPN-anchored values so the fixture de-dups.

**Acceptance Scenarios**:

1. **Given** a provider-parsed team name that matches an alias in `team_aliases`, **When** the provider
   mints (or references) that team, **Then** the resulting `team_id` is the seed's canonical `team_id`,
   not `md5(lower(parsed_name))`.
2. **Given** a provider-parsed team name absent from the seed, **When** the provider mints that team,
   **Then** the resulting `team_id` is `md5(lower(parsed_name))` — the identical formula ESPN uses — so
   if the name is later seeded as a `canonical_name` the id is unchanged.
3. **Given** a provider league key that matches a `league_aliases` row, **When** the provider mints (or
   references) that league, **Then** the resulting `league_id` is the seed's ESPN-anchored canonical
   `league_id` (`md5(league_slug)`), not a provider-private constant, and `season_id =
   md5(league_id || '|' || year)` — so the minted match de-dups onto the ESPN fixture.
4. **Given** a provider league key absent from `league_aliases`, **When** the provider mints that
   league, **Then** a deterministic provider-scoped canonical `league_id` is minted (graceful degrade,
   like an unseen team) and the league stays provider-scoped until a `league_aliases` mapping is added —
   never a hard failure and never a duplicate of an already-mapped league.
5. **Given** ESPN has already minted a canonical team/league and a second provider mints the same
   club/competition (via the same seed row), **When** both conform steps have run, **Then** `int_team`
   and `int_league` each contain exactly one row for that entity and their `unique` id tests pass.
6. **Given** a minted match whose team and league resolved through their seeds, **When** the
   `canonical_match_id` for that fixture is computed by the provider and independently by ESPN, **Then**
   both yield the **same** `match_id` (the fixture de-dups onto one canonical match).

---

### User Story 3 - Conform is a first-class cross-provider layer, not a Matchbook-only concept (Priority: P2)

The Python resolve-or-mint engine is relocated out of `src/data_platform/matchbook/conform/` to a
neutral, cross-provider location so "conform" reads as a first-class layer that every provider
participates in. The Dagster asset `matchbook_conform` (`assets/intermediate/matchbook_conform.py`) is
renamed/re-homed accordingly, and ESPN's dbt `int_*` models are documented as "ESPN's conform, in SQL".
Per the constitution (No Backward Compatibility, I), the move **replaces** the old location — no shim,
no re-export from the old path.

**Why this priority**: This is the naming/location correction the user asked for. It carries no data
behaviour of its own (it is a structural rename), so it ranks below the two correctness stories, but it
is what makes the model legible and prevents the next provider from re-learning that conforming is
universal.

**Independent Test**: After the move, `grep -r "matchbook/conform"` finds no imports; the conform
engine imports from the neutral location; `dagster definitions validate` and `dbt parse` both succeed;
the Matchbook conform still produces identical resolved-links/additions/exceptions output for the same
input.

**Acceptance Scenarios**:

1. **Given** the relocation is complete, **When** the codebase is searched, **Then** no module under
   `src/data_platform/matchbook/conform/` exists and no code imports from that path (the old path is
   removed, not aliased).
2. **Given** the shared team/match resolution logic (seed resolution + `canonical_match_id`), **When**
   inspected, **Then** it lives in one shared helper reused by every Python provider's conform, and the
   dbt-side ESPN resolution (`int_team.sql`, `int_match.sql`) computes an identical `team_id`/`match_id`
   for the same inputs (asserted by an existing or added parity check).
3. **Given** the Matchbook conform asset runs after the rename, **When** the same bronze events and
   overrides are supplied, **Then** the resolved-links, canonical-additions, and exceptions Parquet
   outputs are byte-for-byte equivalent to the pre-rename behaviour (a pure move, no behaviour change).

---

### User Story 4 - Matchbook link tables carry the missing FK tests (Priority: P2)

`int_matchbook_event_link.match_id` already has a `relationships` test to `int_match`
(`_intermediate.yml:150-156`), but `int_matchbook_team_link.team_id` (→ `int_team.team_id`) and
`int_matchbook_league_link.league_id` (→ `int_league.league_id`) have **no** `relationships` test — the
gap recorded as Spec 010 OQ3. Adding them turns a silent resolution-drift into a caught failure, and
they are only safely green once Stories 1–2 guarantee every referenced team/league exists canonically.

**Why this priority**: A correctness gate, but a smaller, additive one that depends on the integrity
established by Stories 1–2 to pass. It closes a known omission rather than fixing a live break.

**Independent Test**: Add the two `relationships` tests to `_intermediate.yml`, run
`dbt build --select int_matchbook_team_link int_matchbook_league_link`. With Stories 1–2 in place the
tests pass; introducing a Matchbook team id that is absent from `int_team` makes the team-link test go
red (proving it bites).

**Acceptance Scenarios**:

1. **Given** the updated `_intermediate.yml`, **When** `dbt test` runs, **Then** a `relationships` test
   asserts `int_matchbook_team_link.team_id` exists in `int_team.team_id`, and another asserts
   `int_matchbook_league_link.league_id` exists in `int_league.league_id`.
2. **Given** a Matchbook team-link row whose `team_id` is not present in `int_team`, **When** `dbt test`
   runs, **Then** the team-link `relationships` test fails (the test genuinely bites).

---

### User Story 5 - football-data conform is scaffolded to the shared contract (Priority: P3)

`int_football_data_match_link` is a typed empty scaffold (`limit 0`) with no conform at all. Rather than
implement a full football-data conform (which would balloon scope — see Assumptions), this feature wires
football-data into the **same** shared resolve-or-mint contract: a placeholder/interface module in the
neutral conform location and the four-file additions convention (`<provider>_canonical_match_additions`
/ `_team_additions` / `_season_additions` / `_league_additions`), so a later football-data conform slots
in without re-deriving the model.

**Why this priority**: Lowest priority because it is enabling scaffolding, not shipped conform
behaviour. It proves the model generalises to a third provider without committing to that provider's
matching logic now.

**Independent Test**: The football-data conform module exists in the neutral location and declares the
shared resolve-or-mint interface; `int_match` and `int_team` union football-data additions files when
present (and materialise unchanged when absent); `dbt build` stays green with no football-data
additions present.

**Acceptance Scenarios**:

1. **Given** no football-data additions Parquet files exist, **When** `dbt build --select int_match
   int_team` runs, **Then** both models materialise exactly as they would with only ESPN + Matchbook
   data (the absent-file union contributes zero rows and does not error).
2. **Given** the shared conform contract, **When** the football-data conform module is inspected,
   **Then** it conforms to the same resolve-or-mint interface (seed-resolved team ids via
   `team_aliases`, seed-resolved league via `league_aliases`, `canonical_match_id` for matches, the
   four provider-scoped additions files) that Matchbook uses — even if its record-matching body is a
   documented not-yet-implemented placeholder.

---

### Edge Cases

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | A provider mints a match; one team resolves via seed alias, the other is unseen | The seeded team reuses the existing canonical `team_id`; the unseen team gets `md5(lower(name))`. Both team ids appear in `int_team`; the match's two team FKs are satisfied. |
| E2 | Two providers mint the same real-world fixture independently (both leagues mapped in `league_aliases`) | Both resolve the same ESPN-anchored league/season and seed-resolved teams, so both compute the identical `canonical_match_id`; `int_match` de-dups to one row (existing `qualify row_number()` keep-one logic, `int_match.sql:116-119`); both provider link tables point at that one `match_id`. |
| E3 | A provider mints two events that resolve to the same team/league (same seed row) | `int_team`/`int_league` emit exactly one row per id; the `unique` id tests pass (dedup via `distinct`/keep-one, as `int_team.sql` already does). |
| E4 | A provider's `<provider>_canonical_{match,team,season,league}_additions.parquet` is absent (provider never minted) | Each additions file is **bootstrap-written empty** before the dbt models run — mirroring the existing empty-file bootstrap in `assets/intermediate/matchbook_conform.py:44-51` — because `int_*` reads them via `read_parquet`, which **errors on a missing file** (it is NOT `try_read_parquet`, despite a stale comment in `int_match.sql`). With the empty file present, the union contributes zero rows and the model materialises normally. |
| E5 | A minted team's name (or league key), after parsing, is empty/blank | The provider conform must not emit a team-/league-addition row with a blank name (it would violate the `not_null` on `int_team.name` / `int_league.name`); the event is routed to the exceptions queue instead of minting an unnamed entity. |
| E6 | A Matchbook fuzzy match finds no candidate and there is no override | Unchanged behaviour: the event goes to the exceptions queue (`matchbook_unresolved.parquet`) and is **not** auto-minted — auto-minting on every no-match would flood the canonical set with low-confidence fixtures. Minting a match is deliberate (override / a provider that authoritatively defines fixtures), not a fallback for failed matching. |
| E7 | The same team appears under two different seed aliases that resolve to two different `team_id`s (seed data error) | This is a seed data-quality issue, not a conform bug; the `unique` test on `int_team.team_id` still holds (each id is distinct), but the club is split. Surface as a seed-curation concern, do not paper over it in code. |
| E8 | ESPN's SQL minting and a Python provider's minting disagree on the formula for an unseen team/league | Prevented by construction: both MUST use `coalesce(seed_lookup, md5(...))` from the shared resolver. A parity check asserts the shared resolver and the dbt path agree; divergence is a test failure, not a silent drift. |
| E9 | A provider mints a match whose league key is NOT in `league_aliases` | A deterministic provider-scoped canonical `league_id` (and its `season_id`) is minted and emitted to the league/season additions files, so the FK chain stays green; the league remains provider-scoped (will not de-dup with an ESPN league) until a `league_aliases` mapping is curated. No hard failure. |
| E10 | A `league_aliases` row points a provider key at a canonical `league_id` that does not correspond to any ESPN league (seed error) | The `int_season.league_id → int_league.league_id` relationships test bites if the minted league row is not also present in `int_league`; the conform must emit the league-addition row for any `league_id` it references. Surface a broken mapping as a seed-curation concern; do not weaken the test. |

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When a provider conform step mints a new canonical match, the system MUST also emit the
  canonical rows the match references that are not already resolved — a team-addition per
  `home_team_id`/`away_team_id`, a season-addition for its `season_id`, and a league-addition for that
  season's `league_id` — so every minted match's full `match → season → league` and `match → team`
  chain resolves. There MUST be no code path that mints a match without its complete season→league→team
  chain.
- **FR-002**: Provider team minting MUST resolve the parsed team name through the `team_aliases` seed
  first, using `coalesce(seed.team_id, md5(lower(name)))` — the identical formula ESPN's `int_team`
  uses (`int_team.sql:27`). Provider league minting MUST resolve the provider league key through the new
  `league_aliases` seed first, using `coalesce(seed.league_id, mint_provider_scoped(provider_key))`,
  where a seed hit yields the ESPN-anchored canonical `league_id` (`md5(league_slug)`). Raw
  `md5(lower(name))` for a team, or a provider-private league constant, without a prior seed lookup MUST
  NOT be used.
- **FR-003**: The system MUST expose provider-minted teams, leagues, and seasons to
  `int_team`/`int_league`/`int_season` via the same external-Parquet + `read_parquet` UNION pattern
  `int_match` already uses for match additions: Python writes
  `data/silver/<provider>_canonical_team_additions.parquet`,
  `<provider>_canonical_league_additions.parquet`, and `<provider>_canonical_season_additions.parquet`;
  each canonical model unions its file in. `int_team`, `int_league`, and `int_season` MUST stop being
  ESPN-only.
- **FR-004**: `int_team.team_id`, `int_league.league_id`, and `int_season.season_id` MUST each remain
  `unique` and `not_null`, and all four FK `relationships` tests — `int_match.home_team_id`/`away_team_id`
  → `int_team.team_id` (`_intermediate.yml:76-91`), `int_match.season_id` → `int_season.season_id`
  (`:68-75`), and `int_season.league_id` → `int_league.league_id` (`:49-56`) — MUST pass with
  provider-minted rows present. These tests MUST NOT be weakened, narrowed, or removed to make minted
  rows pass (constitution II/III) — the data path is fixed instead.
- **FR-005**: Canonical match identity MUST continue to be computed by the `canonical_match_id` macro /
  its Python replica over canonical-resolved surrogates (seed-resolved league_id, derived season_id, UTC
  kickoff date, seed-resolved home/away team_id), never a raw provider event id, so any provider
  describing the same fixture lands on the same `match_id` (`macros/canonical_match_id.sql`,
  `engine.py:77-85`).
- **FR-006**: The Python resolve-or-mint engine MUST be relocated out of
  `src/data_platform/matchbook/conform/` to a neutral cross-provider location with per-provider modules;
  the old location MUST be removed (no backward-compatible re-export), per constitution I.
- **FR-007**: The seed-resolution + `canonical_match_id` logic MUST be a single shared helper reused by
  every Python provider's conform, so team/match resolution is identical across providers and matches
  ESPN's SQL resolution.
- **FR-008**: The Matchbook conform Dagster asset MUST be renamed/re-homed to reflect the neutral
  location, and its AssetKey change MUST keep the bronze→conform and conform→dbt lineage edges intact
  (the dbt source-to-AssetKey mapping in `assets/dbt.py:35` and any `deps=[...]` must be updated to the
  new key — a wrong key silently drops the edge).
- **FR-009**: The system MUST add `relationships` tests for `int_matchbook_team_link.team_id` →
  `int_team.team_id` and `int_matchbook_league_link.league_id` → `int_league.league_id`
  (`_intermediate.yml`), closing Spec 010 OQ3.
- **FR-010**: football-data MUST be wired into the shared resolve-or-mint contract via an interface
  module in the neutral conform location and the four-file additions convention
  (`<provider>_canonical_{match,team,season,league}_additions.parquet`); `int_match`, `int_team`,
  `int_season`, and `int_league` MUST union football-data additions when present and materialise
  unchanged when the (bootstrap-written empty) files contribute no rows. A full football-data
  record-matching implementation is out of scope (see Assumptions).
- **FR-011**: No Python conform module MAY open a DuckLake connection (even read-only). Conform reads
  bronze Parquet and any needed canonical data via dbt external-Parquet exports and writes additions as
  Parquet files that dbt unions via `read_parquet` (CLAUDE.md; ARCHITECTURE.md rule 3). The existing
  `canonical_team_export`/`canonical_match_export` are joined by new `canonical_league_export` and
  `canonical_season_export` external-Parquet models so a Python provider can RESOLVE against existing
  canonical leagues/seasons (e.g. to detect an already-minted-this-run league and avoid a duplicate
  addition row) without touching the catalog. League/season identity still follows the seed-first
  `coalesce(seed, mint)` formula (FR-012); these exports are the resolution data source, with the dbt
  `distinct`/keep-one layer as a de-dup backstop.
- **FR-012**: Minting a canonical match MUST resolve its `league_id`/`season_id` through the shared
  seed resolver rather than a provider-private constant, replacing the bogus
  `league_id = md5('matchbook_football')` (`engine.py:224`). The minted `league_id` is
  `coalesce(league_aliases.league_id_for(provider, provider_key), mint_provider_scoped(provider_key))`
  and `season_id = md5(league_id || '|' || year)` (as ESPN derives it), so when a `league_aliases`
  mapping exists the minted match de-dups onto the ESPN fixture, and when absent it mints a
  deterministic provider-scoped canonical league (graceful degrade — see E9).
- **FR-013**: Every behaviour above MUST map to a failing-first check using the right facility (dbt
  `relationships`/`unique`/`not_null` tests, pytest over the shared resolver and provider conform,
  Pandera on addition frames) per constitution III; no check may be satisfied by a placeholder, stub,
  or weakened gate (constitution II).
- **FR-014**: The doc set MUST be updated in the same change to describe the symmetric cross-provider
  conform (not the ESPN-only / Matchbook-only model), including the new `league_aliases.csv` seed and
  its `_seeds.yml`, and the four `<provider>_canonical_*_additions.parquet` files: `CLAUDE.md`
  (constraints that assert "canonical from ESPN" / "conform lives in matchbook" / the `int_match`
  UNION ALL note), `ARCHITECTURE.md`, `ERD.md`, and `data flows.md`.
- **FR-015**: The system MUST introduce a human-curated `league_aliases` seed
  (`dbt/data_platform/seeds/league_aliases.csv`) mapping each provider's league identifier to a
  canonical league — columns `league_id, canonical_name, provider, provider_key` (provider ∈
  `espn|matchbook|football_data`; `provider_key` = ESPN `league_slug`, or a Matchbook
  `sport_id`/`category_id` composite, etc.) — registered in a `_seeds.yml`. Its natural key is the
  composite `(provider, provider_key)`, which MUST be `unique` (one canonical mapping per provider
  key); `league_id` and `provider_key` MUST be `not_null`; `league_id` MUST NOT be tested `unique`
  (several providers deliberately map onto one ESPN-anchored `league_id`, mirroring how `team_aliases`
  allows many `alias` rows per `team_id`). The canonical `league_id` stays ESPN-anchored (`md5(league_slug)`): the seed
  RECORDS the ESPN mapping and maps OTHER providers' keys onto that same id, mirroring how
  `team_aliases` maps names onto `md5(lower(canonical_name))`. It MUST be seed-only (no auto-learn
  write-back), and ESPN's existing `int_league`/`int_match`/`int_espn_*_link` identity MUST be
  unchanged (the seed is additive).
- **FR-016**: Every `<provider>_canonical_{match,team,season,league}_additions.parquet` MUST be
  bootstrap-written (empty, with the correct columns) before the dbt models run — mirroring the
  existing empty-file bootstrap in `assets/intermediate/matchbook_conform.py:44-51` — because `int_*`
  reads them via `read_parquet`, which ERRORS on a missing file (it is NOT `try_read_parquet`, despite
  a stale comment in `int_match.sql`).

### Key Entities *(include only if the feature involves data)*

- **Canonical team (`int_team`)**: One row per real-world club. Attributes: `team_id` (canonical
  surrogate — seed `team_id` or `md5(lower(name))`), `name`, `similar_names`. Now the **union of all
  providers' teams**, not ESPN-only.
- **Canonical league (`int_league`)**: One row per competition. `league_id` is ESPN-anchored
  (`md5(league_slug)`). Now the **union of all providers' leagues**, not ESPN-only.
- **Canonical season (`int_season`)**: One edition of a league; `season_id = md5(league_id || '|' ||
  year)`, `league_id` FK → `int_league`. Now the **union of all providers' seasons**.
- **Canonical match (`int_match`)**: One row per real-world fixture, identified by `canonical_match_id`
  over canonical league/season/date/home/away. References two canonical teams and one season. Union of
  all providers' fixtures.
- **`team_aliases` seed**: The single source of truth for team identity resolution (`team_id`,
  `canonical_name`, `alias`). Every provider — ESPN in SQL, others in Python — resolves through it.
- **`league_aliases` seed (NEW)**: The single source of truth for league identity resolution
  (`league_id`, `canonical_name`, `provider`, `provider_key`). Maps each provider's league key onto the
  ESPN-anchored canonical `league_id`. Seed-only; no auto-learn.
- **Provider canonical additions (four files per provider)**:
  `<provider>_canonical_match_additions.parquet`, `_team_additions`, `_season_additions`,
  `_league_additions` — the minted rows a provider emits, each unioned into its canonical model. All are
  bootstrap-written empty when the provider mints nothing (FR-016).
- **Provider link tables (`int_<provider>_match_link`, `int_<provider>_team_link`,
  `int_<provider>_league_link`)**: Cross-walks from raw provider references to canonical ids, each with
  FK `relationships` tests to their canonical target.
- **Exceptions queue (`<provider>_unresolved.parquet`)**: Events that neither resolved nor were
  designated to mint — for human review, not silently dropped or auto-minted.

## Success Criteria *(mandatory)*

- **SC-001**: A `new_canonical` (minted) fixture from any provider produces a canonical match whose two
  team ids, its season id, and that season's league id all exist in their canonical tables — 0 orphaned
  FKs anywhere in the `match → season → league` and `match → team` chain — and all four
  `int_match`/`int_season` `relationships` tests pass green (they fail today for minted-but-unseen
  chain members).
- **SC-002**: For any real-world club under a `team_aliases` row and any competition under a
  `league_aliases` row, the canonical team/league sets contain exactly **one** row regardless of how
  many providers reference it — 0 duplicate clubs or competitions introduced by minting.
- **SC-003**: Two providers describing the same real-world fixture (league mapped in `league_aliases`)
  resolve to the **same** canonical match id — 1 canonical match, not 2 — verified by a parity check
  over the shared resolver and the dbt path.
- **SC-004**: After relocation, 0 modules and 0 imports reference the old `matchbook/conform` path, and
  the Matchbook conform produces output equivalent to its pre-move behaviour for identical input.
- **SC-005**: `int_matchbook_team_link.team_id` and `int_matchbook_league_link.league_id` each carry a
  `relationships` FK test that genuinely bites (fails when an id is absent from its canonical target).
- **SC-006**: `dbt build` (over the intermediate + marts models, given bronze data present, with the
  `league_aliases` seed loaded) and `dagster definitions validate` and `dbt parse` all pass with
  provider-minted team/season/league rows present and with football-data additions being empty
  bootstrap files.
- **SC-007**: The four ripple docs (`CLAUDE.md`, `ARCHITECTURE.md`, `ERD.md`, `data flows.md`) describe
  conform as a symmetric cross-provider layer — including the `league_aliases` seed and the four
  additions files — with no remaining "canonical is ESPN-only" or "conform is Matchbook-only" statements.
- **SC-008**: A Matchbook-minted match whose league key is mapped in `league_aliases` shares its
  `league_id`/`season_id`/`match_id` with the ESPN fixture for the same competition (the bogus
  `md5('matchbook_football')` constant no longer appears anywhere in the minting path).

## Constraints & things to be aware of *(mandatory)*

- **No backward compatibility (constitution I).** Replace the ESPN-only `int_team` build and the
  `matchbook/conform` location; do not add a parallel path or a re-export shim. Remove legacy.
- **No reward hacking / test-first (constitution II & III).** Every behaviour maps to a real
  failing-first check (dbt tests, pytest, Pandera). The `int_match` → `int_team` `relationships` tests
  and the new Matchbook link-table FK tests MUST NOT be weakened, narrowed, `xfail`ed, or removed to
  make minted teams "pass" — fix the data path. Any constraint-bypass requires escalation, never
  self-approval.
- **Python assets MUST NOT open a DuckLake connection, even read-only** (CLAUDE.md; ARCHITECTURE.md
  rule 3). Conform reads bronze Parquet + canonical data via dbt external-Parquet exports, and writes
  additions as Parquet that dbt unions via `read_parquet`. The single-writer `warehouse.duckdb` rule
  stands.
- **dbt AssetKey uses the schema-folder prefix only** (`models/intermediate/int_x.sql` →
  `AssetKey(["intermediate","int_x"])`), while the dbt node selector uses dotted folders
  (`intermediate.int_x`). Two different namings, both load-bearing — resolve real keys from the manifest,
  not by guessing, when re-homing the conform asset (CLAUDE.md).
- **No `from __future__ import annotations` in Dagster asset modules** — Dagster introspects annotations
  at runtime (CLAUDE.md). Config via `pydantic-settings` (`config.py`); use `pathlib.Path`. Check
  `config.py` for existing property-name collisions before adding fields — the Matchbook conform paths
  are properties (`matchbook_conform_dir`, `matchbook_canonical_additions_dir`, etc.,
  `config.py:99-129`); a cross-provider rename must not silently overwrite a live property.
- **Actual model tree is `dbt/data_platform/models/{staging,intermediate,marts}/` with `int_*` names**
  (Spec 011 restructure). CLAUDE.md/ERD.md/ARCHITECTURE.md still say `models/silver/canonical/` in
  places — that is **stale**; spec and build against the actual `intermediate/int_*` tree, and correct
  the stale docs (FR-014).
- **Canonical match identity goes through `canonical_match_id` over canonical-resolved surrogates,
  never a raw provider id** (`macros/canonical_match_id.sql`). The Python replica (`engine.py:77-85`)
  must stay in lock-step with the macro.
- **Extending `int_match`/`int_team`/`int_season`/`int_league` for a provider uses `read_parquet` +
  `UNION ALL` over a provider-scoped additions file** — never a direct DuckLake write and never a
  separate canonical table (CLAUDE.md; `int_match.sql:73-92`). `read_parquet` **errors on a missing
  file** (it is NOT `try_read_parquet`, despite a stale comment in `int_match.sql`), so all four
  additions files MUST be bootstrap-written empty before the dbt models run, as the conform asset
  already does for matches + t60 (`matchbook_conform.py:44-51`) — extend that bootstrap to the new
  team/season/league files (FR-016).
- **`league_id` stays ESPN-anchored (`md5(league_slug)`); `league_aliases` is additive.** The seed
  RECORDS the ESPN league mapping and maps OTHER providers' keys onto that same id — it does NOT
  redefine ESPN identity. ESPN's `int_league`/`int_match`/`int_espn_*_link` must be byte-for-byte
  unchanged; the season derivation `md5(league_id || '|' || year)` is likewise unchanged, so season
  de-dups iff league does. Seed-only, no auto-learn (same discipline as `team_aliases`).
- **The Matchbook exceptions queue (`matchbook_unresolved.parquet`) is deliberate.** Minting is for
  authoritative/override decisions, not a fallback for failed fuzzy matching — do not auto-mint every
  no-match (constitution II: no fallback-to-meet-requirement). This is why "resolve-or-mint" does not
  mean "resolve-or-always-mint".
- **Spec dependencies:** builds on Spec 002 (ESPN conform in SQL), Spec 006 (Matchbook conform engine),
  Spec 010 (link tables + OQ3), Spec 011 (staging/intermediate/marts restructure).

## Assumptions *(mandatory)*

1. **football-data conform is scaffolded, not implemented, in this feature.** A full football-data
   record-matching + minting engine (fuzzy/composite-key matching against canonical fixtures) is a
   separate, sizeable piece of work; folding it in here would balloon scope and dilute the
   integrity-and-naming objective. This feature delivers the shared contract + interface + additions-file
   wiring so football-data slots in later. Recorded as a scoping decision the user can challenge.
2. **Neutral location is `src/data_platform/conform/` with per-provider modules** (e.g.
   `conform/matchbook.py`, `conform/football_data.py`) and a shared resolver (e.g.
   `conform/resolve.py` holding `team_aliases` + `league_aliases` seed resolution + `canonical_match_id`
   + the `season_id` derivation). ESPN's conform stays in dbt (`int_*.sql`) and is documented as "ESPN's
   conform, in SQL". Chosen for KISS (CLAUDE.md "do not overengineer") over a heavier plugin/registry
   abstraction.
3. **The additions-file naming generalises to four files per provider** under `data/silver/`:
   `<provider>_canonical_match_additions.parquet`, `_team_additions`, `_season_additions`,
   `_league_additions`. Matchbook's existing match-additions file (`matchbook_canonical_additions.parquet`)
   is renamed to `matchbook_canonical_match_additions.parquet` for consistency (constitution I: rename,
   no dual-read shim; update `int_match.sql` and the config property together).
4. **Each canonical model gains a provider-additions union analogous to `int_match`'s**: `int_team`,
   `int_league`, and `int_season` each keep their current ESPN CTE, then UNION ALL a
   `read_parquet(<provider>_canonical_<entity>_additions)` CTE per provider, then `distinct`/keep-one on
   the id so seed-resolved duplicates collapse to one row.
9. **`league_aliases` provider_key encoding**: ESPN rows use the `league_slug` (e.g. `eng.1`); Matchbook
   rows use a `sport_id|category_id` composite string; football_data rows use its division/country key.
   The exact composite string format is a plan-phase detail; the seed columns are
   `league_id, canonical_name, provider, provider_key`.
5. **The Dagster asset rename keeps a single conform asset per provider** (Matchbook remains one asset,
   re-keyed to reflect the neutral location); the AssetKey and the `assets/dbt.py` source mapping are
   updated together so lineage is preserved. The exact new AssetKey string is a plan-phase detail.
6. **The `team_aliases` seed remains the sole identity authority** (23 rows today: `team_id`,
   `canonical_name`, `alias`); no auto-learn write-back of provider spellings into the seed (matches
   `int_team.sql` "seed-only; no auto-learn").
7. **The T-60 enrichment logic is not rewritten.** It interacts with minting only insofar as an
   enrichment row references a `match_id` that must exist in `int_match`; the symmetric-conform
   guarantee (every referenced match exists) strengthens that, but T-60's own logic is untouched.
8. **`dbt build` green from a clean checkout still requires bronze data present** (CLAUDE.md documents
   the environmental IO error); success criteria are evaluated with the relevant bronze artifacts
   materialised, not from an empty `data/`.

## Open Questions *(mandatory)*

No blockers. The league-identity question (formerly OQ1) is RESOLVED — the user decided on a
`league_aliases` seed; encoded as FR-002/FR-012/FR-015 and User Story 2. Remaining non-blocking
detail-level questions:

| # | Question | Blocker? | Best guess |
|---|----------|----------|------------|
| OQ1 | Exact neutral module path and the new conform AssetKey string. | Non-blocker | `src/data_platform/conform/` with `resolve.py` (shared team+league seed resolution + `canonical_match_id`) + per-provider modules; asset re-keyed to an `AssetKey(["intermediate","matchbook_conform"])`-equivalent under the new module, decided in plan. |
| OQ2 | Should ESPN's SQL conform ALSO emit into the shared `<provider>_canonical_*_additions` convention for symmetry, or stay purely in-SQL (it already mints team/league/season/match directly)? | Non-blocker | Keep ESPN in-SQL (it is the ESPN base of each canonical model's union already); the additions-file convention is for the Python providers. Documented as "ESPN conform in SQL" for legibility rather than forced through Parquet. |
| OQ3 | Exact `provider_key` composite string format for Matchbook `sport_id`/`category_id` in `league_aliases`. | Non-blocker | A `"sport_id|category_id"` composite (matching how `int_matchbook_league_link` already treats the pair); finalised in plan alongside the seed rows. |
