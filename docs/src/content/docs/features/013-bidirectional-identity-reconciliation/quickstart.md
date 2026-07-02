---
title: "Quickstart: Bidirectional Identity Reconciliation"
---

# Quickstart: Bidirectional Identity Reconciliation

**Feature directory**: `specs/013-bidirectional-identity-reconciliation/`

Runnable validation scenarios proving the feature works end-to-end. Not test code — a manual/CI
reference for demonstrating each user story.

## Prerequisites

```bash
uv sync
cp .env.example .env   # if not already done
( cd dbt/data_platform && uv run --project ../.. dbt parse --profiles-dir . )
```

A running DuckLake catalog (`docker compose up ducklake-catalog` or the full stack) is needed for any
step that runs `dbt build` for real; `dbt parse` alone (no catalog) is enough to prove the manifest
compiles.

## Scenario 1 — ESPN mints first, Matchbook bridges onto it (the previously-broken direction)

1. Seed ESPN bronze with a fixture whose team is named "Wolverhampton Wanderers" (no `team_aliases`
   seed entry for it) and run `espn_ingestion` once — confirm `int_team` now has exactly one row for
   that club, `team_id = md5(lower("wolverhampton wanderers"))`.
2. Seed Matchbook bronze with an event name `"Wolves vs Some Other Team"` (`"Wolves"` scores at or
   above `HIGH_THRESHOLD` against "Wolverhampton Wanderers" via `token_sort_ratio`) and run
   `matchbook_ingestion`.
3. Inspect `data/silver/learned_team_aliases.parquet` — a row exists:
   `raw_name="Wolves", team_id=md5(lower("wolverhampton wanderers")), source_provider="matchbook",
   match_method="auto_confirmed"`.
4. Re-run `matchbook_ingestion` (or wait for its next scheduled tick) and inspect `int_team` — still
   exactly one row for the club; the Matchbook-minted match for "Wolves vs ..." resolves
   `home_team_id`/`away_team_id` onto the SAME `team_id` ESPN minted, and `int_match` shows one
   canonical match, not two.

**Expected outcome**: matches User Story 1, Acceptance Scenario 2 (the direction not covered by
today's Matchbook→ESPN-only fix).

## Scenario 2 — Confidence tiers (User Story 2)

1. Add a raw name scoring in `[MEDIUM_THRESHOLD, HIGH_THRESHOLD)` against an existing canonical team —
   confirm the bridge is written with `match_method="needs_review"` and is still applied (the
   resulting match resolves onto the bridged id, not a fresh self-mint).
2. Add a raw name scoring below `MEDIUM_THRESHOLD` against every candidate (e.g. "Man Utd" vs.
   "Manchester United") — confirm no row is written for it in `learned_team_aliases.parquet`, and the
   provider still self-mints its own canonical team (unchanged, current behaviour).
3. Construct two canonical candidates that tie exactly at the top score for one raw name — confirm no
   bridge row is written.

## Scenario 3 — Traceability (User Story 3)

1. After a run that produces at least one `auto_confirmed` and one `needs_review` bridge, read
   `data/silver/learned_team_aliases.parquet` with pandas and confirm every row has non-null
   `raw_name`, `team_id`, `source_provider`, `confidence`, `match_method`.

## Scenario 4 — Orchestration guardrail (Dagster wiring)

1. `uv run dagster definitions validate -w workspace.yaml` — passes (loads the location once; does
   NOT by itself prove the daemon/queued path or catch a `CircularDependencyError` from the dbt
   multi-asset step-subsetting — see CLAUDE.md's own caveat on this command).
2. Launch a **queued** run of `matchbook_ingestion` through the UI/daemon (not `dagster job execute`)
   and confirm: (a) the run launches without a `CircularDependencyError` at `Definitions` build time;
   (b) `identity_reconciliation` executes and completes before `matchbook_conform` starts (inspect the
   run's step ordering in the Dagster UI).
3. Launch `espn_ingestion` the same way and confirm `identity_reconciliation` executes as part of that
   job's selection too (FR-012 — both providers covered).
