---
title: "Contract: Per-provider conform module + four-file additions convention"
---

# Contract: Per-provider conform module + four-file additions convention

Every Python provider module (`conform/matchbook.py`, `conform/football_data.py`) implements the SAME
resolve-or-mint contract (FR-006, FR-010, US5). ESPN is exempt — it conforms in SQL (D3).

## Provider entry point

```python
def run_conform(...) -> ConformReport
```

- Reads bronze Parquet for the provider (never DuckLake, FR-011).
- Reads canonical exports for resolution: `silver/canonical/{team,match,league,season}.parquet` (D7).
- Resolves each record: link to an existing canonical match, OR (override / authoritative) mint a new
  one — and when minting a match, emit EVERY un-resolved chain member (FR-001).
- Writes provider-scoped outputs atomically (temp-file + rename): resolved-links, exceptions, and the
  FOUR additions files.
- Returns a `ConformReport` (counts per output). Per-record failures accumulate; the outer function
  re-raises at the end (mirrors `matchbook/ingest.py` / `espn/ingest.py` isolation pattern).

## Four additions files (written by every Python provider; bootstrap-empty when nothing minted, FR-016)

| File | Empty-bootstrap columns |
|------|-------------------------|
| `<provider>_canonical_match_additions.parquet` | match_id, season_id, home_team_id, away_team_id, kickoff_time, ht_score, ft_score, status_completed |
| `<provider>_canonical_team_additions.parquet` | team_id, name, similar_names |
| `<provider>_canonical_league_additions.parquet` | league_id, name, is_tournament |
| `<provider>_canonical_season_additions.parquet` | season_id, league_id, name, start_date, end_date |

## Minting a match ⇒ mint the whole chain (FR-001, SC-001)

When a provider mints match M with resolved (league_id, season_id, home_team_id, away_team_id):
1. team-addition per team_id NOT already in `canonical/team.parquet` (name from parsed provider name,
   seed-resolved; blank-name → exceptions, E5).
2. season-addition for season_id NOT already in `canonical/season.parquet`.
3. league-addition for league_id NOT already in `canonical/league.parquet` (E10: any league_id the
   match references MUST get its row, else the season→league relationships test bites).
4. match-addition for M.

De-dup within a run: skip a chain member already present in the corresponding canonical export or already
emitted this run; the dbt keep-one is the backstop (E3, spec Assumption 4).

## football-data placeholder (US5, FR-010)

`conform/football_data.py` declares this interface with a documented `NotImplementedError` record-matching
body, BUT its four additions files ARE bootstrap-written empty so `int_*` union them at 0 rows and
`dbt build` stays green (US5 AC1). No football-data record-matching in this feature (spec Assumption 1).

## Pandera frame contracts (boundary validation, FR-013)

Each additions frame is validated by a Pandera schema before write (columns + dtypes + `name` not-blank
on team/league). A frame violating the schema raises; a conforming frame passes. Lives alongside the
existing Matchbook contracts (`tests/matchbook/test_contracts.py` pattern / `models/validation.py`).
