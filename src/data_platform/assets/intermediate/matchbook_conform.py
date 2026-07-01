"""Dagster wrapper for the Matchbook conform engine (Spec 006 S7).

Thin asset that calls run_conform() and emits MaterializeResult with metadata.
No ``from __future__ import annotations`` — Dagster introspects the annotations.
"""

import pandas as pd
from dagster import AssetKey, MaterializeResult, asset

from ...config import settings
from ...conform import bootstrap_additions_files, run_conform
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


def _bootstrap_additions(additions_dir, t60_dir) -> None:
    """Write every Parquet file the intermediate dbt models read via read_parquet().

    read_parquet REQUIRES the file to exist (it errors on a missing literal path;
    it is not try_read_parquet), so each int_* model's per-provider union CTE needs
    its additions file present even when nothing is minted. The int_* models union
    BOTH providers, so both are bootstrapped empty here — Matchbook via the explicit
    column lists it has always used, football-data via the shared helper.
    """
    _ensure_empty_parquet(
        additions_dir / "matchbook_canonical_match_additions.parquet",
        columns=[
            "match_id",
            "season_id",
            "home_team_id",
            "away_team_id",
            "kickoff_time",
            "ht_score",
            "ft_score",
            "status_completed",
        ],
    )
    _ensure_empty_parquet(
        additions_dir / "matchbook_canonical_team_additions.parquet",
        columns=["team_id", "name", "similar_names"],
    )
    _ensure_empty_parquet(
        additions_dir / "matchbook_canonical_league_additions.parquet",
        columns=["league_id", "name", "is_tournament"],
    )
    _ensure_empty_parquet(
        additions_dir / "matchbook_canonical_season_additions.parquet",
        columns=["season_id", "league_id", "name", "start_date", "end_date"],
    )
    _ensure_empty_parquet(
        t60_dir / "matchbook_t60_enrichment.parquet",
        columns=["match_id", "favourite_team_id"],
    )
    # football-data has no conform body yet (US5 scaffold): bootstrap its four
    # additions files empty so int_* stays green with football-data contributing
    # zero rows, reusing the shared provider-agnostic helper.
    bootstrap_additions_files("football_data", additions_dir)


@asset(
    key=AssetKey(["matchbook_conform"]),
    group_name="intermediate",
    compute_kind="python",
    deps=[
        AssetKey(["matchbook_events_bronze"]),
        AssetKey(["marts", "canonical_match_export"]),
        AssetKey(["marts", "canonical_team_export"]),
        AssetKey(["marts", "canonical_league_export"]),
        AssetKey(["marts", "canonical_season_export"]),
    ],
    description=(
        "Matchbook conform: fuzzy-matches football events to canonical matches, "
        "writes resolved-links, exceptions, and canonical-additions Parquet files."
    ),
)
def matchbook_conform(context) -> MaterializeResult:
    """Run the Matchbook conform engine and write silver-layer Parquet outputs."""
    # Bootstrap: ensure every Parquet file the dbt intermediate models read via
    # read_parquet() exists before they run (even if conform/t60 have not produced
    # real data yet, and even for the still-scaffolded football-data provider). The
    # mint path emits four canonical-additions frames.
    _bootstrap_additions(settings.matchbook_canonical_additions_dir, settings.matchbook_t60_dir)

    tracer = get_tracer()
    with tracer.start_as_current_span("matchbook_conform"):
        report = run_conform(
            events_dir=settings.matchbook_events_bronze_dir,
            canonical_dir=settings.matchbook_conform_canonical_dir,
            overrides_path=settings.matchbook_overrides_dir / "matchbook_overrides.parquet",
            exceptions_dir=settings.matchbook_exceptions_dir,
            conform_dir=settings.matchbook_conform_dir,
            additions_dir=settings.matchbook_canonical_additions_dir,
            team_aliases_path=settings.team_aliases_seed_path,
            league_aliases_path=settings.league_aliases_seed_path,
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
