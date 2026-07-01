"""Dagster wrapper for the Matchbook T-60 enrichment engine (Spec 006 S8).

Thin asset that calls run_t60_enrichment() and emits MaterializeResult.
No ``from __future__ import annotations`` — Dagster introspects the annotations.
"""

from dagster import AssetKey, MaterializeResult, asset

from ...config import settings
from ...matchbook.t60 import run_t60_enrichment
from ...otel import get_tracer


@asset(
    key=AssetKey(["matchbook_t60_enrichment"]),
    group_name="intermediate",
    compute_kind="python",
    deps=[
        AssetKey(["intermediate", "int_matchbook_event_link"]),
        AssetKey(["matchbook_events_bronze"]),
    ],
    description=(
        "Matchbook T-60 enrichment: identifies pre-match favourites from odds lake "
        "and writes matchbook_t60_enrichment.parquet for dbt to join into match."
    ),
)
def matchbook_t60_enrichment(context) -> MaterializeResult:
    """Run the T-60 enrichment engine and write silver-layer enrichment Parquet."""
    tracer = get_tracer()
    out_path = settings.matchbook_t60_dir / "matchbook_t60_enrichment.parquet"
    with tracer.start_as_current_span("matchbook_t60_enrichment"):
        report = run_t60_enrichment(
            resolved_links_path=settings.matchbook_conform_dir / "matchbook_resolved_links.parquet",
            odds_dir=settings.matchbook_bronze_dir,
            canonical_dir=settings.matchbook_conform_canonical_dir,
            events_bronze_dir=settings.matchbook_events_bronze_dir,
            out_path=out_path,
            log=context.log,
        )
    context.log.info(
        "matchbook_t60_enrichment: enriched=%d, skipped=%d",
        report.enriched_count,
        report.skipped_no_ticks,
    )
    return MaterializeResult(
        metadata={
            "enriched_count": report.enriched_count,
            "skipped_no_ticks": report.skipped_no_ticks,
            "out_path": str(out_path),
        }
    )
