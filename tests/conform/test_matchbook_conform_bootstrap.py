"""T038: the matchbook_conform asset bootstraps BOTH providers' additions files.

The four `int_*` canonical dbt models each `read_parquet(...
<provider>_canonical_*_additions.parquet)` against a LITERAL path, which DuckDB
ERRORS on when the file is absent (it does not return zero rows). The
`matchbook_conform` asset is the pre-dbt step, so it must bootstrap-write empty
additions files for EVERY provider the int_* models union — matchbook AND
football-data — before the dbt build reads them (Spec 012 T038, FR-016/FR-010/
SC-006/E4).

This exercises the asset's production bootstrap seam directly (no bronze data,
no run_conform, no DuckLake catalog).
"""

from pathlib import Path

import pandas as pd

from data_platform.conform import _ADDITIONS_COLUMNS

_MATCHBOOK_ENTITIES = ("match", "team", "league", "season")


def test_bootstrap_writes_football_data_additions(tmp_path: Path) -> None:
    """The bootstrap seam writes all four football_data additions files empty."""
    from data_platform.assets.intermediate.matchbook_conform import _bootstrap_additions

    additions_dir = tmp_path / "silver"
    t60_dir = tmp_path / "silver"

    _bootstrap_additions(additions_dir, t60_dir)

    for entity, columns in _ADDITIONS_COLUMNS.items():
        path = additions_dir / f"football_data_canonical_{entity}_additions.parquet"
        assert path.exists(), f"missing football_data {entity} additions file"
        frame = pd.read_parquet(path)
        assert list(frame.columns) == columns
        assert len(frame) == 0


def test_bootstrap_still_writes_matchbook_additions_and_t60(tmp_path: Path) -> None:
    """Adding football-data must not disturb the existing matchbook + t60 bootstrap."""
    from data_platform.assets.intermediate.matchbook_conform import _bootstrap_additions

    additions_dir = tmp_path / "silver"
    t60_dir = tmp_path / "silver"

    _bootstrap_additions(additions_dir, t60_dir)

    for entity in _MATCHBOOK_ENTITIES:
        assert (additions_dir / f"matchbook_canonical_{entity}_additions.parquet").exists(), (
            f"missing matchbook {entity} additions file"
        )

    t60_path = t60_dir / "matchbook_t60_enrichment.parquet"
    assert t60_path.exists()
    assert list(pd.read_parquet(t60_path).columns) == ["match_id", "favourite_team_id"]
