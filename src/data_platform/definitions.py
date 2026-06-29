"""Dagster code location: assets, resources, the hello-world job and schedule."""

from __future__ import annotations

from dagster import (
    AssetKey,
    AssetSelection,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)
from dagster_dbt import DbtCliResource

from .assets.bronze import raw_users
from .assets.dbt import dbt_models, dbt_project
from .assets.espn import espn_bronze
from .assets.football_extra import football_extra
from .assets.football_main import football_main
from .assets.gold import publish_gold_parquet
from .assets.matchbook_events import matchbook_events_bronze
from .espn.http_client import ThrottledHttpClient as EspnThrottledHttpClient
from .football.http_client import ThrottledHttpClient
from .otel import configure_telemetry

# Install tracing as soon as the code location is imported (covers both the
# webserver process and every run subprocess).
configure_telemetry()

# Hello-world flow: bronze (ingest) -> silver+gold (dbt) -> gold Parquet export.
# Exclude the football bronze assets — they are a separate, on-demand source (a full
# backfill is ~705 files); `AssetSelection.all()` would otherwise sweep them into this
# demo job (and the daily schedule). Run football via `football_backfill` instead.
football_assets = AssetSelection.assets(football_main, football_extra)

# ESPN soccer flow: its own end-to-end source (bronze scoreboards -> the dbt silver
# staging + canonical conform + link models). Like football, it must NOT be swept into
# the all()-based hello-world job/daily schedule — run it via the dedicated `espn_job`
# below. The dbt model AssetKeys are `["silver","<model>"]` (verified from the manifest;
# NOT `["silver","canonical",...]`); the `team_aliases` seed is an ESPN-conform input and
# surfaces as `["silver","team_aliases"]`, so it rides with this source too.
espn_assets = AssetSelection.assets(
    espn_bronze,
    AssetKey(["silver", "stg_espn_events"]),
    AssetKey(["silver", "league"]),
    AssetKey(["silver", "season"]),
    AssetKey(["silver", "team"]),
    AssetKey(["silver", "match"]),
    AssetKey(["silver", "espn_match_link"]),
    AssetKey(["silver", "team_aliases"]),
)

# Matchbook events bronze ingest: standalone 6-hourly source, excluded from the
# all()-based hello-world job. Run via dedicated `matchbook_events_ingestion` job.
matchbook_events_assets = AssetSelection.assets(matchbook_events_bronze)

medallion_job = define_asset_job(
    name="medallion_hello_world",
    selection=AssetSelection.all() - football_assets - espn_assets - matchbook_events_assets,
    description="End-to-end: ingest raw users -> dbt silver/gold (+tests) -> gold Parquet.",
)

daily_schedule = ScheduleDefinition(
    name="medallion_daily",
    job=medallion_job,
    cron_schedule="0 6 * * *",  # stopped by default; toggle on in the UI
)

# On-demand backfill of the football-data.co.uk bronze source (both families).
# No schedule (Non-goal): run it manually. Idempotent re-runs skip already-landed
# historical files and always refresh current-season files (skip-existing in the
# throttled client). Pacing (0.4s) applies to discovery + file GETs within each run.
football_backfill_job = define_asset_job(
    name="football_backfill",
    selection=football_assets,
    description="Backfill football-data.co.uk main + extra bronze Parquet over the registry.",
)

# ESPN runs end-to-end on a cadence (Q-plan-2 Option A): the bronze scoreboard ingest
# plus the dbt staging + canonical conform + link models, so each run lands fresh
# scoreboards AND re-derives the canonical match/link rows (deterministic surrogate ids
# make the conform an idempotent overwrite). Every 6 hours (AC9).
espn_job = define_asset_job(
    name="espn_ingestion",
    selection=espn_assets,
    description="ESPN end-to-end: bronze scoreboards -> dbt staging + canonical conform + link.",
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

defs = Definitions(
    assets=[
        raw_users,
        dbt_models,
        publish_gold_parquet,
        football_main,
        football_extra,
        espn_bronze,
        matchbook_events_bronze,
    ],
    jobs=[medallion_job, football_backfill_job, espn_job, matchbook_events_job],
    schedules=[daily_schedule, espn_schedule, matchbook_events_schedule],
    resources={
        "dbt": DbtCliResource(project_dir=dbt_project),
        "football_http": ThrottledHttpClient(),
        "espn_http": EspnThrottledHttpClient(),
    },
)
