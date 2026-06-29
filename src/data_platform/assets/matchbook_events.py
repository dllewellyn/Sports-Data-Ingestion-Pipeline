"""Bronze ingestor for Matchbook open events (the network edge).

One Parquet per sport per run under
``data/bronze/matchbook_events/<sport>/<YYYY-MM-DD>/<batch-timestamp>.parquet``.
Network access stays in the bronze layer (ARCHITECTURE rule #1). Per-sport
failures are isolated in the engine; this wrapper surfaces them via
MaterializeResult metadata and re-raises so the run status reflects failures.

No ``from __future__ import annotations`` — Dagster introspects the annotations.
"""

from dagster import AssetKey, MaterializeResult, asset

from ..config import settings
from ..matchbook.ingest import IngestionReport, run_matchbook_events_ingest
from ..models.validation import matchbook_events_bronze_schema


@asset(
    key=AssetKey(["matchbook_events_bronze"]),
    group_name="bronze",
    compute_kind="python",
    description=(
        "Matchbook open events (football + rugby union) → one bronze Parquet per sport per run."
    ),
)
def matchbook_events_bronze(context) -> MaterializeResult:
    """Fetch all open Matchbook events and write to bronze Parquet."""
    report: IngestionReport = run_matchbook_events_ingest(
        username=settings.matchbook_username,
        password=settings.matchbook_password,
        base_url=settings.matchbook_events_base_url,
        per_page=20,
        timeout=30.0,
        out_dir=settings.matchbook_events_bronze_dir,
        log=context.log,
        schema=matchbook_events_bronze_schema,
    )
    context.log.info(
        "matchbook_events_bronze: written=%d, skipped=%d, failed=%d",
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
        }
    )
