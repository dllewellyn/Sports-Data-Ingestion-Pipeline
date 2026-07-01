"""football-data.co.uk conform interface — the resolve-or-mint SCAFFOLD (Spec 012 US5).

This module wires football-data into the SAME shared resolve-or-mint contract that the
Matchbook conform engine uses: it binds the single identity authority from
`conform/resolve.py` (so identical inputs compute identical canonical ids across
providers, SC-006) and declares the four canonical-additions filenames using the
`football_data_canonical_{match,team,league,season}_additions.parquet` naming that the
`int_team` / `int_league` / `int_season` unions already read (FR-010).

The record-MATCHING body is intentionally NOT implemented yet (spec Assumption 1): a
future task supplies football-data's own event->canonical matching. Until then
`run_conform` raises NotImplementedError — an honestly-labelled placeholder, and the
additions files are produced empty (zero rows) by `conform.bootstrap_additions_files`
so the intermediate dbt unions stay green with football_data contributing no rows.
"""

from .resolve import (
    compute_canonical_match_id,
    derive_season_id,
    resolve_league_id,
    resolve_team_id,
)

# Canonical-additions filenames (must match the int_* union read_parquet paths).
MATCH_ADDITIONS_FILENAME = "football_data_canonical_match_additions.parquet"
TEAM_ADDITIONS_FILENAME = "football_data_canonical_team_additions.parquet"
LEAGUE_ADDITIONS_FILENAME = "football_data_canonical_league_additions.parquet"
SEASON_ADDITIONS_FILENAME = "football_data_canonical_season_additions.parquet"

__all__ = [
    "resolve_team_id",
    "resolve_league_id",
    "derive_season_id",
    "compute_canonical_match_id",
    "MATCH_ADDITIONS_FILENAME",
    "TEAM_ADDITIONS_FILENAME",
    "LEAGUE_ADDITIONS_FILENAME",
    "SEASON_ADDITIONS_FILENAME",
    "run_conform",
]


def run_conform(*args, **kwargs) -> None:
    """Placeholder entry point for the football-data resolve-or-mint conform (US5).

    INTENTIONALLY not implemented (spec 012 Assumption 1): the interface — shared
    resolver bindings above and the four additions filenames — is the deliverable for
    this scaffold. The matching body (reading football-data bronze, resolving/minting
    canonical rows onto the shared identity, writing the additions Parquet) lands in a
    later task. Raising here keeps the placeholder honest rather than silently no-op'ing.
    """
    raise NotImplementedError(
        "football-data conform matching not yet implemented (Spec 012 US5 scaffold)"
    )
