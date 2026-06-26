"""Dagster code location: assets, resources, the hello-world job and schedule."""

from __future__ import annotations

from dagster import (
    AssetSelection,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)
from dagster_dbt import DbtCliResource

from .assets.bronze import raw_users
from .assets.dbt import dbt_models, dbt_project
from .assets.football_extra import football_extra
from .assets.football_main import football_main
from .assets.gold import publish_gold_parquet
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
medallion_job = define_asset_job(
    name="medallion_hello_world",
    selection=AssetSelection.all() - football_assets,
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

defs = Definitions(
    assets=[raw_users, dbt_models, publish_gold_parquet, football_main, football_extra],
    jobs=[medallion_job, football_backfill_job],
    schedules=[daily_schedule],
    resources={
        "dbt": DbtCliResource(project_dir=dbt_project),
        "football_http": ThrottledHttpClient(),
    },
)
