"""Bronze migration asset: ESPN events from sports-gaming-engine PostgreSQL.

One-off Dagster asset that extracts ESPN event rows from the sports-gaming-engine
PostgreSQL database (bronze.espn_restored_summaries + bronze.provider_match_cache)
and materialises them as bronze Parquet files at:
  data/bronze/espn/<league_slug>/<season_year>.parquet

Requires SPORTS_GAMING_ENGINE_POSTGRES_URL in the environment (.env).
Run once via the Dagster UI; not included in any scheduled job.

No ``from __future__ import annotations`` — Dagster introspects the annotations.
"""

from dagster import AssetKey, MaterializeResult, asset

from ...config import settings
from ...espn.migrate_from_postgres import MigrationReport, run_espn_postgres_migration
from ...models.validation import espn_bronze_schema


@asset(
    key=AssetKey(["espn_postgres_migration"]),
    group_name="bronze",
    compute_kind="python",
    description=(
        "One-off migration: extract ESPN events from sports-gaming-engine PostgreSQL "
        "(espn_restored_summaries + provider_match_cache) → bronze Parquet in the same "
        "structure as espn_bronze."
    ),
)
def espn_postgres_migration(context) -> MaterializeResult:
    """Migrate ESPN events from sports-gaming-engine PostgreSQL to bronze Parquet."""
    if not settings.sports_gaming_engine_postgres_url:
        raise ValueError(
            "SPORTS_GAMING_ENGINE_POSTGRES_URL must be set to run the ESPN Postgres migration"
        )

    report: MigrationReport = run_espn_postgres_migration(
        postgres_url=settings.sports_gaming_engine_postgres_url,
        out_dir=settings.espn_bronze_dir,
        log=context.log,
        schema=espn_bronze_schema,
    )

    context.log.info(
        "espn_postgres_migration: written=%d, skipped=%d, failed=%d",
        len(report.written),
        len(report.skipped),
        len(report.failed),
    )

    return MaterializeResult(
        metadata={
            "units_written": len(report.written),
            "units_skipped": len(report.skipped),
            "units_failed": len(report.failed),
            "total_valid_rows": sum(r.valid_rows for r in report.written),
            "total_failed_rows": report.total_failures,
            "paths": [str(r.out_path) for r in report.written if r.out_path],
        }
    )
