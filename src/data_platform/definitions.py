"""Dagster code location: assets, resources, and orchestration."""

from __future__ import annotations

from dagster import (
    AssetKey,
    AssetSelection,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)
from dagster_dbt import DbtCliResource

from .assets.dbt import dbt_models, dbt_project
from .assets.ingestion.espn import espn_bronze
from .assets.ingestion.football_extra import football_extra
from .assets.ingestion.football_main import football_main
from .assets.ingestion.matchbook_events import matchbook_events_bronze
from .assets.ingestion.matchbook_odds import matchbook_odds_bronze, odds_stream_fresh
from .assets.intermediate.matchbook_conform import matchbook_conform
from .assets.intermediate.matchbook_t60 import matchbook_t60_enrichment
from .espn.http_client import ThrottledHttpClient as EspnThrottledHttpClient
from .football.http_client import ThrottledHttpClient
from .otel import configure_telemetry

# Install tracing as soon as the code location is imported (covers both the
# webserver process and every run subprocess).
configure_telemetry()

# Football bronze assets: separate, on-demand source (full backfill is ~705 files).
football_assets = AssetSelection.assets(football_main, football_extra)

# ESPN soccer flow: end-to-end source (bronze scoreboards -> dbt staging +
# intermediate conform + link models). Run via the dedicated `espn_job`. The dbt model
# AssetKeys are `["staging","<model>"]` for staging and `["intermediate","<model>"]` for
# intermediate (verified from the manifest); the `team_aliases` seed surfaces as
# `["staging","team_aliases"]`, so it rides with this source.
espn_assets = AssetSelection.assets(
    espn_bronze,
    AssetKey(["staging", "stg_espn_events"]),
    AssetKey(["intermediate", "int_league"]),
    AssetKey(["intermediate", "int_season"]),
    AssetKey(["intermediate", "int_team"]),
    AssetKey(["intermediate", "int_match"]),
    AssetKey(["intermediate", "int_espn_match_link"]),
    AssetKey(["staging", "team_aliases"]),
)

# Matchbook events bronze ingest: standalone 6-hourly source.
matchbook_events_assets = AssetSelection.assets(matchbook_events_bronze)

# Matchbook odds bronze: an observable source asset over the out-of-band
# ingestor daemon's Parquet output. The observe job records freshness (age of
# the newest tick file) and runs the freshness check; it never materializes.
matchbook_odds_observe_assets = AssetSelection.assets(
    matchbook_odds_bronze.key
) | AssetSelection.checks_for_assets(matchbook_odds_bronze.key)

# Matchbook conform layer: conform + T-60 enrichment + the dbt models they feed.
# Heavy standalone pipeline that depends on a full Matchbook events bronze lake.
matchbook_conform_assets = AssetSelection.assets(
    matchbook_conform,
    matchbook_t60_enrichment,
    AssetKey(["intermediate", "int_matchbook_event_link"]),
    AssetKey(["marts", "canonical_match_export"]),
    AssetKey(["marts", "canonical_team_export"]),
    AssetKey(["marts", "canonical_league_export"]),
    AssetKey(["marts", "canonical_season_export"]),
)


# On-demand backfill of the football-data.co.uk bronze source (both families).
# No schedule: run it manually. Idempotent re-runs skip already-landed historical files
# and always refresh current-season files.
football_backfill_job = define_asset_job(
    name="football_backfill",
    selection=football_assets,
    description="Backfill football-data.co.uk main + extra bronze Parquet over the registry.",
)

# ESPN runs end-to-end on a cadence: the bronze scoreboard ingest plus the dbt staging
# + intermediate conform + link models, so each run lands fresh scoreboards AND re-derives
# the canonical match/link rows. Every 6 hours.
espn_job = define_asset_job(
    name="espn_ingestion",
    selection=espn_assets,
    description="ESPN end-to-end: bronze scoreboards -> dbt staging + intermediate conform + link.",
)

espn_schedule = ScheduleDefinition(
    name="espn_every_6h",
    job=espn_job,
    cron_schedule="0 */6 * * *",
)

# Matchbook events: dedicated job + 6-hourly schedule.
matchbook_events_job = define_asset_job(
    name="matchbook_events_ingestion",
    selection=matchbook_events_assets,
    description="Matchbook open events (football + rugby union) → bronze Parquet every 6 hours.",
)

matchbook_events_schedule = ScheduleDefinition(
    name="matchbook_events_schedule",
    job=matchbook_events_job,
    cron_schedule="0 */6 * * *",
)

# Matchbook odds freshness: observe the daemon's bronze output + run the freshness
# check every 15 minutes. Cheap (stats the newest Parquet file); no materialization.
matchbook_odds_observe_job = define_asset_job(
    name="matchbook_odds_observe",
    selection=matchbook_odds_observe_assets,
    description="Observe matchbook_odds bronze freshness (age of the newest tick Parquet).",
)

matchbook_odds_observe_schedule = ScheduleDefinition(
    name="matchbook_odds_observe_schedule",
    job=matchbook_odds_observe_job,
    cron_schedule="*/15 * * * *",
)

# Matchbook conform job: runs 1 hour after matchbook_events_ingestion so the bronze lake
# is fresh before conform runs.
matchbook_conform_job = define_asset_job(
    name="matchbook_conform_job",
    selection=matchbook_conform_assets,
    description=(
        "Matchbook conform layer: fuzzy-match events to canonical matches, "
        "T-60 enrichment, and dbt rebuild of int_matchbook_event_link + int_match."
    ),
)

matchbook_conform_schedule = ScheduleDefinition(
    name="matchbook_conform_schedule",
    job=matchbook_conform_job,
    cron_schedule="0 1,7,13,19 * * *",  # 1 hour after the 6-hourly events ingestion
)

defs = Definitions(
    assets=[
        dbt_models,
        football_main,
        football_extra,
        espn_bronze,
        matchbook_events_bronze,
        matchbook_odds_bronze,
        matchbook_conform,
        matchbook_t60_enrichment,
    ],
    asset_checks=[odds_stream_fresh],
    jobs=[
        football_backfill_job,
        espn_job,
        matchbook_events_job,
        matchbook_odds_observe_job,
        matchbook_conform_job,
    ],
    schedules=[
        espn_schedule,
        matchbook_events_schedule,
        matchbook_odds_observe_schedule,
        matchbook_conform_schedule,
    ],
    resources={
        "dbt": DbtCliResource(project_dir=dbt_project),
        "football_http": ThrottledHttpClient(),
        "espn_http": EspnThrottledHttpClient(),
    },
)
