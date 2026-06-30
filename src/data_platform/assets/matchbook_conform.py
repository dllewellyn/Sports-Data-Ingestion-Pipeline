"""Dagster wrapper for the Matchbook conform engine (Spec 006 S7).

Thin asset that calls run_conform() and emits MaterializeResult with metadata.
No ``from __future__ import annotations`` — Dagster introspects the annotations.
"""

from dagster import AssetKey, MaterializeResult, asset

from ..config import settings
from ..matchbook.conform import run_conform
from ..otel import get_tracer


@asset(
    key=AssetKey(["matchbook_conform"]),
    group_name="silver",
    compute_kind="python",
    deps=[
        AssetKey(["matchbook_events_bronze"]),
        AssetKey(["silver", "canonical_match_export"]),
        AssetKey(["silver", "canonical_team_export"]),
    ],
    description=(
        "Matchbook conform: fuzzy-matches football events to canonical matches, "
        "writes resolved-links, exceptions, and canonical-additions Parquet files."
    ),
)
def matchbook_conform(context) -> MaterializeResult:
    """Run the Matchbook conform engine and write silver-layer Parquet outputs."""
    tracer = get_tracer()
    with tracer.start_as_current_span("matchbook_conform"):
        report = run_conform(
            events_dir=settings.matchbook_events_bronze_dir,
            canonical_dir=settings.matchbook_conform_canonical_dir,
            overrides_path=settings.matchbook_overrides_dir / "matchbook_overrides.parquet",
            exceptions_dir=settings.matchbook_exceptions_dir,
            conform_dir=settings.matchbook_conform_dir,
            additions_dir=settings.matchbook_canonical_additions_dir,
            log=context.log,
        )
    context.log.info(
        "matchbook_conform: resolved=%d, exceptions=%d, overrides=%d, additions=%d",
        report.resolved_count,
        report.exceptions_count,
        report.overrides_applied,
        report.additions_count,
    )
    return MaterializeResult(
        metadata={
            "resolved_count": report.resolved_count,
            "exceptions_count": report.exceptions_count,
            "overrides_applied": report.overrides_applied,
            "additions_count": report.additions_count,
        }
    )
