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
from .assets.gold import publish_gold_parquet
from .otel import configure_telemetry

# Install tracing as soon as the code location is imported (covers both the
# webserver process and every run subprocess).
configure_telemetry()

# Hello-world flow: bronze (ingest) -> silver+gold (dbt) -> gold Parquet export.
medallion_job = define_asset_job(
    name="medallion_hello_world",
    selection=AssetSelection.all(),
    description="End-to-end: ingest raw users -> dbt silver/gold (+tests) -> gold Parquet.",
)

daily_schedule = ScheduleDefinition(
    name="medallion_daily",
    job=medallion_job,
    cron_schedule="0 6 * * *",  # stopped by default; toggle on in the UI
)

defs = Definitions(
    assets=[raw_users, dbt_models, publish_gold_parquet],
    jobs=[medallion_job],
    schedules=[daily_schedule],
    resources={
        "dbt": DbtCliResource(project_dir=dbt_project),
    },
)
