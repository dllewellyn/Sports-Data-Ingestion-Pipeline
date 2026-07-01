---
title: "Phase 1 — Data model: Cross-Provider Conform"
---

# Phase 1 — Data model: Cross-Provider Conform

Entities extracted from `spec.md` §Key Entities, grounded in the actual `models/intermediate/int_*`
tree (Spec 011). "Canonical = union of all providers" is the through-line: each canonical table's ESPN
CTE is the base, unioned with per-provider additions, then de-duped keep-one on the id.

## Canonical entities (dbt `int_*` tables)

### `int_team` — canonical club
- `team_id` VARCHAR — canonical surrogate. `coalesce(team_aliases.team_id, md5(lower(name)))`. **unique, not_null.**
- `name` VARCHAR — seed `canonical_name` else provider name. **not_null.**
- `similar_names` ARRAY<VARCHAR> — seed aliases, else `[name]`.
- **New:** rows are the UNION of the ESPN CTE + `read_parquet(<provider>_canonical_team_additions)` per
  Python provider, keep-one on `team_id`. No longer ESPN-only.

### `int_league` — canonical competition
- `league_id` VARCHAR — **ESPN-anchored** `md5(league_slug)`. **unique, not_null.** (NON-unique in the
  *seed*; unique in the *table* after keep-one.)
- `name` VARCHAR — league display name. **not_null.**
- `is_tournament` BOOLEAN — **not_null.**
- **New:** UNION of ESPN CTE + `read_parquet(<provider>_canonical_league_additions)` per provider,
  keep-one on `league_id`.

### `int_season` — canonical edition
- `season_id` VARCHAR — `md5(league_id || '|' || season_year)`. **unique, not_null.**
- `league_id` VARCHAR — FK → `int_league.league_id`. **not_null + relationships.**
- `name` VARCHAR — season label.
- `start_date` / `end_date` DATE — nullable.
- **New:** UNION of ESPN CTE + `read_parquet(<provider>_canonical_season_additions)` per provider,
  keep-one on `season_id`.

### `int_match` — canonical fixture
- `match_id` VARCHAR — `canonical_match_id(league_id, season_id, kickoff_date_utc, home, away)`. **unique, not_null.**
- `season_id` VARCHAR — FK → `int_season.season_id`. **not_null + relationships.**
- `home_team_id` / `away_team_id` VARCHAR — FK → `int_team.team_id`. **not_null + relationships (each).**
- `favourite_team_id`, `kickoff_time`, `ht_score`, `ft_score`.
- **Existing:** already unions `matchbook_canonical_additions` (→ renamed `matchbook_canonical_match_additions`)
  and future football_data match additions; keep-one on `match_id` via `qualify row_number()`.

## Seeds

### `team_aliases` (existing, unchanged)
- `team_id, canonical_name, alias`. Many rows per `team_id`. `team_id = md5(lower(canonical_name))`.
  Seed-only, no auto-learn. (23 rows today.) Currently has NO data tests — out of scope to add, but the
  new `_seeds.yml` created for `league_aliases` can optionally document it.

### `league_aliases` (NEW — FR-015)
- `league_id` VARCHAR — ESPN-anchored `md5(league_slug)`. **not_null; NOT unique.**
- `canonical_name` VARCHAR.
- `provider` VARCHAR ∈ {`espn`,`matchbook`,`football_data`}. **not_null + accepted_values.**
- `provider_key` VARCHAR — ESPN: `league_slug` (`eng.1`); Matchbook: `"<sport_id>|<category_id>"`;
  football_data: `<family|division>`. **not_null.**
- Natural key: composite `(provider, provider_key)` — **unique** (via singular test, D6).
- Seed-only, no auto-learn. Additive: RECORDS ESPN's own mapping + maps other providers onto it.

Minimum seed rows to make US2 testable (real, not fixtures):
- `md5('eng.1'), Premier League, espn, eng.1`
- `md5('eng.1'), Premier League, matchbook, 15|<premier-league-category>`

## Provider canonical additions (four Parquet files per Python provider)

Written to `data/silver/`, all **bootstrap-written empty** before dbt (FR-016, E4):

| File | Columns (empty-bootstrap) | Unioned into |
|------|---------------------------|--------------|
| `<provider>_canonical_match_additions.parquet` | match_id, season_id, home_team_id, away_team_id, kickoff_time, ht_score, ft_score, status_completed | `int_match` |
| `<provider>_canonical_team_additions.parquet` | team_id, name, similar_names | `int_team` |
| `<provider>_canonical_league_additions.parquet` | league_id, name, is_tournament | `int_league` |
| `<provider>_canonical_season_additions.parquet` | season_id, league_id, name, start_date, end_date | `int_season` |

`<provider>` ∈ {`matchbook`, `football_data`}. ESPN emits NONE (D3).

## Canonical external exports (dbt `materialized='external'`, `models/marts/exports/`)

| Export | Output Parquet | Columns | Status |
|--------|----------------|---------|--------|
| `canonical_team_export` | `silver/canonical/team.parquet` | team_id, name, similar_names | exists |
| `canonical_match_export` | `silver/canonical/match.parquet` | match_id, season_id, home/away_team_id, favourite_team_id, kickoff_time, home/away_team_name | exists |
| `canonical_league_export` | `silver/canonical/league.parquet` | league_id, name, is_tournament | **NEW (D7)** |
| `canonical_season_export` | `silver/canonical/season.parquet` | season_id, league_id, name, start_date, end_date | **NEW (D7)** |

## Provider link tables (`int_<provider>_*_link`) — FK relationships tests

| Link table | FK column | → target | Test today | After this feature |
|------------|-----------|----------|------------|--------------------|
| `int_matchbook_event_link` | match_id | int_match.match_id | relationships ✓ | unchanged |
| `int_matchbook_team_link` | team_id | int_team.team_id | **MISSING** | **relationships added (FR-009)** |
| `int_matchbook_league_link` | league_id | int_league.league_id | **MISSING** | **relationships added (FR-009)** |
| `int_espn_*_link` | team_id/league_id/match_id | resp. | relationships ✓ | unchanged |

## Shared resolver (Python, `conform/resolve.py`) — pure functions

| Function | Signature (shape) | Mirrors dbt |
|----------|-------------------|-------------|
| `resolve_team_id(name, aliases)` | `(str, DataFrame) -> str` | `coalesce(seed.team_id, md5(lower(name)))` — `int_team.sql:27`, `int_match.sql:43-44` |
| `resolve_league_id(provider, provider_key, aliases)` | `(str, str, DataFrame) -> str` | seed `league_aliases` else `mint_provider_scoped(provider, provider_key)` |
| `derive_season_id(league_id, year)` | `(str, int) -> str` | `md5(league_id || '|' || year)` — `int_season.sql:22` |
| `compute_canonical_match_id(league_id, season_id, date_str, home, away)` | → `str` | `macros/canonical_match_id.sql` (concat_ws `|`, md5) — already exists at `engine.py:77-85` |
| `mint_provider_scoped(provider, provider_key)` | → `str` | deterministic provider-scoped league_id when no seed hit (E9) — e.g. `md5(provider || '|' || provider_key)` |

## State / invariants

- **Referential-integrity invariant (SC-001):** minting a match ALWAYS emits every un-resolved chain
  member (team×2, season, league). No code path mints a match without its full chain (FR-001).
- **De-dup invariant (SC-002/SC-003):** identity is seed-first and deterministic, so two providers
  describing one fixture compute the same `match_id`; keep-one collapses duplicates to one canonical row.
- **Idempotency:** additions files are full-rebuilt each run; keep-one on the id makes re-runs stable.
- **Blank-name guard (E5):** no addition row with a blank `name`; route to exceptions instead.
- **Exceptions ≠ auto-mint (E6):** a failed fuzzy match with no override goes to exceptions, never mints.
