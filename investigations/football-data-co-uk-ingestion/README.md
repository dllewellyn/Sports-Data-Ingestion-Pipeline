# Investigation: Ingesting football-data.co.uk into the medallion platform

**Status:** concluded
**Owner:** daniel.llewellyn
**Started:** 2026-06-26

## Question
What is the right way to ingest *all* of football-data.co.uk (every country/league,
full history) into this medallion platform as **validated bronze Parquet** — is it
feasible, and how do we handle the heavy **schema drift** across leagues and seasons?

This deliberately rolls three sub-questions into one (the user chose "all of the above"):
1. **Feasibility** — is the source reliably reachable and parseable?
2. **Platform fit** — what ingestion design fits the existing Dagster / Pydantic /
   Pandera / Parquet pattern (see `src/data_platform/assets/bronze.py`)?
3. **Schema drift** — how do columns/schemas vary, and what should a canonical bronze
   schema look like?

## Why now
This is the blocker before writing a *specification* for a real Dagster ingestion
asset. We don't yet know whether the source is stable/parseable enough, or what a
canonical bronze schema should be, so we can't commit to a build.

## Hypotheses / options
- **H1 (feasibility):** The site exposes static, directly-downloadable `.csv` files
  linked from per-country `*m.php` pages; a backfill is mostly an HTTP + parse problem,
  not a JS-rendered-scraping problem.
- **H2 (stack):** Link discovery can be done with `requests` + a light HTML parse and
  may not require adding `BeautifulSoup` to the platform stack.
- **H3 (drift):** Column sets vary substantially across leagues/seasons (betting-odds
  columns especially), so a strict per-file Pydantic model is impractical; a
  **superset / sparse canonical schema** with a small mandatory core (Div, Date,
  HomeTeam, AwayTeam, FT result/goals) is the viable bronze contract.
- **H4 (volume/politeness):** "All leagues, all history" is hundreds of files;
  rate-limiting and terms-of-use posture need an explicit recommendation.

## Done criteria
An evidence-backed **approach recommendation doc** (in `findings.md`):
- feasibility verdict,
- a schema-drift map across sampled leagues/seasons,
- a recommended bronze ingestion design.

**No production code.** The doc must be *backed* by a small disposable spike under
`code/` that actually downloads real files and lands a validated **bronze Parquet**
sample — proving the Pydantic + Pandera pattern survives contact with this data.

## Scope & constraints
**In scope**
- "All leagues, all history" as the *target* the recommended design must support.
- A spike that samples enough leagues/seasons to characterize drift and prove the
  Parquet + validation pattern end-to-end on a few real files.

**Out of scope**
- Production Dagster assets, silver/gold dbt models.
- The full historical backfill (we sample, we don't backfill now).
- Scheduling / incremental-update design (note it, don't build it).

**Constraints**
- Target output: **bronze Parquet, platform fit** (mirror `raw_users`).
- Be polite to the source: throttle requests; respect any terms of use.
- Network access required for the spike.
