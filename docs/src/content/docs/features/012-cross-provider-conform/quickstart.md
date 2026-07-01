---
title: "Quickstart — validating Cross-Provider Conform"
---

# Quickstart — validating Cross-Provider Conform

Runnable validation scenarios proving the feature end-to-end. Not test code — the reference for a human
(or the self-review) to confirm the change works. Assumes bronze data present (spec Assumption 8) and the
DuckLake catalog service up.

## Prerequisites

```bash
uv sync
# dbt manifest must exist before any dagster/pytest import that loads definitions:
( cd dbt/data_platform && uv run --project ../.. dbt parse --profiles-dir . )
```

## 1. Shared resolver + provider conform unit tests (pytest)

```bash
PYTHONPATH=src uv run pytest tests/conform -v
```
Expected: parity tests green — `resolve_team_id`/`resolve_league_id`/`compute_canonical_match_id` agree
with the dbt formulas; blank-name guard routes to exceptions; `md5('matchbook_football')` appears nowhere.

## 2. Full-chain minting closes referential integrity (dbt) — US1 / SC-001

Seed a Matchbook event with team names absent from ESPN + `team_aliases`, a league absent from ESPN,
mark it `new_canonical` via an override, run conform, then:
```bash
( cd dbt/data_platform && uv run --project ../.. dbt build \
    --select int_league int_season int_team int_match int_matchbook_event_link --profiles-dir . )
```
Expected: minted team/season/league ids all present in their canonical tables; all four
`int_match`/`int_season` relationships tests PASS (they go red today for an orphaned chain).

## 3. Seed de-dup — US2 / SC-002 / SC-008

Add `"Wolves"` to `team_aliases` and a `league_aliases` row mapping the Matchbook `(sport_id,category_id)`
for the Premier League onto `md5('eng.1')`. Mint a Matchbook match for that fixture, then rebuild:
```bash
( cd dbt/data_platform && uv run --project ../.. dbt build \
    --select league_aliases int_team int_league int_match --profiles-dir . )
```
Expected: minted `team_id` == the seed's Wolverhampton Wanderers id (not `md5('wolves')`); minted
`league_id`/`season_id`/`match_id` == the ESPN-anchored values; `int_team`/`int_league` have exactly one
row for that club/competition; `unique` id tests pass.

## 4. Matchbook link-table FK tests bite — US4 / SC-005

```bash
( cd dbt/data_platform && uv run --project ../.. dbt build \
    --select int_matchbook_team_link int_matchbook_league_link --profiles-dir . )
```
Expected: PASS with Stories 1–2 in place. Then introduce a Matchbook team id absent from `int_team` and
re-run: the team-link relationships test goes RED (proves it bites).

## 5. Relocation complete — US3 / SC-004

```bash
grep -rn "matchbook/conform\|matchbook\.conform" src/ tests/ ; echo "exit=$?"
( cd dbt/data_platform && uv run --project ../.. dbt parse --profiles-dir . )
PYTHONPATH=src DATA_DIR="$PWD/data" DUCKDB_PATH="$PWD/data/warehouse.duckdb" \
  DAGSTER_HOME="$PWD/.dagster" uv run dagster definitions validate -m data_platform.definitions
```
Expected: grep finds no `matchbook/conform` module or import (old path removed); `dbt parse` and
`definitions validate` succeed.

## 6. football-data scaffold is green-when-empty — US5 / SC-006

With NO football-data additions (bootstrap-empty files present):
```bash
( cd dbt/data_platform && uv run --project ../.. dbt build --select int_match int_team --profiles-dir . )
```
Expected: both materialise exactly as with only ESPN + Matchbook; the empty union contributes 0 rows and
does not error (E4).

## 7. Orchestration launches a real queued run — US1/FR-008 (daemon-path guardrail)

`dagster definitions validate` is NOT sufficient for asset/job/AssetSelection changes (CLAUDE.md). Launch
the conform job through the daemon/queued path:
```bash
PYTHONPATH=src DATA_DIR="$PWD/data" DUCKDB_PATH="$PWD/data/warehouse.duckdb" \
  DAGSTER_HOME="$PWD/.dagster" \
  uv run dagster job execute -m data_platform.definitions -j matchbook_conform_job
```
Expected: the run launches and the bronze→conform→dbt lineage edges resolve (no
`DagsterCodeLocationNotFoundError`, no dropped-edge / wrong-AssetKey failure). Confirms the asset key +
`deps` + source-map are intact after the relocation.

## 8. Gates clean

```bash
uv run pre-commit run --all-files   # ruff clean on your files (pre-existing SIM105 in the MCP server is not yours)
```
