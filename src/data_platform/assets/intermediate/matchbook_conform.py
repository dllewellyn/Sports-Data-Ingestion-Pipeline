"""Dagster wrapper for the Matchbook conform engine (Spec 006 S7).

Thin asset that calls run_conform() and emits MaterializeResult with metadata.
No ``from __future__ import annotations`` — Dagster introspects the annotations.
"""

import pandas as pd
from dagster import AssetKey, MaterializeResult, asset

from ...config import settings
from ...conform import run_conform
from ...otel import get_tracer


def _ensure_empty_parquet(path, columns: list[str]) -> None:
    """Write an empty Parquet file with the given columns if the file doesn't exist."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(columns=columns)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.rename(path)


@asset(
    key=AssetKey(["matchbook_conform"]),
    group_name="intermediate",
    compute_kind="python",
    deps=[
        AssetKey(["matchbook_events_bronze"]),
        AssetKey(["marts", "canonical_match_export"]),
        AssetKey(["marts", "canonical_team_export"]),
    ],
    description=(
        "Matchbook conform: fuzzy-matches football events to canonical matches, "
        "writes resolved-links, exceptions, and canonical-additions Parquet files."
    ),
)
def matchbook_conform(context) -> MaterializeResult:
    """Run the Matchbook conform engine and write silver-layer Parquet outputs."""
    # Bootstrap: ensure both Parquet files that match.sql reads via read_parquet() exist
    # before the dbt silver models run (even if conform/t60 have not produced real data yet).
    _ensure_empty_parquet(
        settings.matchbook_canonical_additions_dir / "matchbook_canonical_match_additions.parquet",
        columns=["match_id", "season_id", "home_team_id", "away_team_id", "kickoff_time"],
    )
    _ensure_empty_parquet(
        settings.matchbook_t60_dir / "matchbook_t60_enrichment.parquet",
        columns=["match_id", "favourite_team_id"],
    )

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
