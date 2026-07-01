"""Bronze migration asset: Matchbook events from sports-gaming-engine PostgreSQL.

One-off Dagster asset that extracts Matchbook event rows from the
sports-gaming-engine PostgreSQL database (bronze.provider_match_cache) and
materialises them as bronze Parquet files in the standard medallion structure
(data/bronze/matchbook_events/<sport>/<date>/migration_<ts>.parquet).

Requires SPORTS_GAMING_ENGINE_POSTGRES_URL in the environment (.env).
Run once via the Dagster UI; not included in any scheduled job.

No ``from __future__ import annotations`` — Dagster introspects the annotations.
"""

from dagster import AssetKey, MaterializeResult, asset

from ...config import settings
from ...matchbook.migrate_from_postgres import MigrationReport, run_matchbook_postgres_migration
from ...models.validation import matchbook_events_bronze_schema


@asset(
    key=AssetKey(["matchbook_postgres_migration"]),
    group_name="bronze",
    compute_kind="python",
    description=(
        "One-off migration: extract Matchbook events from sports-gaming-engine "
        "PostgreSQL (bronze.provider_match_cache) → bronze Parquet in the same "
        "structure as matchbook_events_bronze."
    ),
)
def matchbook_postgres_migration(context) -> MaterializeResult:
    """Migrate Matchbook events from sports-gaming-engine PostgreSQL to bronze Parquet."""
    if not settings.sports_gaming_engine_postgres_url:
        raise ValueError(
            "SPORTS_GAMING_ENGINE_POSTGRES_URL must be set to run the Postgres migration"
        )

    report: MigrationReport = run_matchbook_postgres_migration(
        postgres_url=settings.sports_gaming_engine_postgres_url,
        out_dir=settings.matchbook_events_bronze_dir,
        log=context.log,
        schema=matchbook_events_bronze_schema,
    )

    context.log.info(
        "matchbook_postgres_migration: written=%d, skipped=%d, failed=%d",
        len(report.written),
        len(report.skipped),
        len(report.failed),
    )

    return MaterializeResult(
        metadata={
            "sports_written": len(report.written),
            "sports_skipped": len(report.skipped),
            "sports_failed": len(report.failed),
            "paths": [str(r.out_path) for r in report.written if r.out_path],
            "total_valid_rows": sum(r.valid_rows for r in report.written),
            "total_failed_rows": report.total_failures,
        }
    )
