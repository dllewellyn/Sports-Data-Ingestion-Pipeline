"""T027: football-data conform scaffold (Spec 012 US5, FR-010, SC-006, U18).

Wires football-data into the SAME shared resolve-or-mint contract as Matchbook via
a placeholder interface module (`conform/football_data.py`) plus a shared four-file
bootstrap helper (`conform.bootstrap_additions_files`) that both providers can reuse.

The matching BODY is an honestly-labelled placeholder (spec Assumption 1): the entry
point raises NotImplementedError. What IS real here is the shared interface: the module
imports the `conform/resolve.py` identity functions, declares the four additions
filenames, and the bootstrap helper writes the four empty (correct-column) Parquet files
so `int_*` unions stay green with football_data contributing zero rows.
"""

from pathlib import Path

import pandas as pd
import pytest


def test_module_imports_shared_resolver_interface() -> None:
    """The football_data module reuses the shared resolve-or-mint identity functions."""
    from data_platform.conform import football_data
    from data_platform.conform import resolve as shared_resolve

    # The module declares the shared resolve-or-mint interface by binding the
    # canonical identity functions from conform/resolve.py.
    assert football_data.resolve_team_id is shared_resolve.resolve_team_id
    assert football_data.resolve_league_id is shared_resolve.resolve_league_id
    assert football_data.derive_season_id is shared_resolve.derive_season_id
    assert football_data.compute_canonical_match_id is shared_resolve.compute_canonical_match_id


def test_module_declares_four_additions_filenames() -> None:
    """The four additions filenames match football_data_canonical_{match,team,league,season}."""
    from data_platform.conform import football_data

    expected = {
        "match": "football_data_canonical_match_additions.parquet",
        "team": "football_data_canonical_team_additions.parquet",
        "league": "football_data_canonical_league_additions.parquet",
        "season": "football_data_canonical_season_additions.parquet",
    }
    names = {
        football_data.MATCH_ADDITIONS_FILENAME,
        football_data.TEAM_ADDITIONS_FILENAME,
        football_data.LEAGUE_ADDITIONS_FILENAME,
        football_data.SEASON_ADDITIONS_FILENAME,
    }
    assert names == set(expected.values())


def test_entry_point_is_honest_placeholder() -> None:
    """The record-matching entry point raises NotImplementedError (Assumption 1)."""
    from data_platform.conform import football_data

    with pytest.raises(NotImplementedError, match="football-data conform matching"):
        football_data.run_conform()


def test_bootstrap_helper_writes_four_empty_files(tmp_path: Path) -> None:
    """The shared bootstrap helper writes four empty, correct-column additions files."""
    from data_platform.conform import bootstrap_additions_files

    additions_dir = tmp_path / "silver"
    additions_dir.mkdir(parents=True, exist_ok=True)

    bootstrap_additions_files("football_data", additions_dir)

    expected_columns = {
        "football_data_canonical_match_additions.parquet": [
            "match_id",
            "season_id",
            "home_team_id",
            "away_team_id",
            "kickoff_time",
            "ht_score",
            "ft_score",
            "status_completed",
        ],
        "football_data_canonical_team_additions.parquet": [
            "team_id",
            "name",
            "similar_names",
        ],
        "football_data_canonical_league_additions.parquet": [
            "league_id",
            "name",
            "is_tournament",
        ],
        "football_data_canonical_season_additions.parquet": [
            "season_id",
            "league_id",
            "name",
            "start_date",
            "end_date",
        ],
    }

    for filename, columns in expected_columns.items():
        path = additions_dir / filename
        assert path.exists(), f"missing {filename}"
        frame = pd.read_parquet(path)
        assert list(frame.columns) == columns
        assert len(frame) == 0


def test_bootstrap_helper_is_provider_general(tmp_path: Path) -> None:
    """The helper is reusable: passing another provider names its files accordingly."""
    from data_platform.conform import bootstrap_additions_files

    additions_dir = tmp_path / "silver"
    additions_dir.mkdir(parents=True, exist_ok=True)

    bootstrap_additions_files("matchbook", additions_dir)

    for entity in ("match", "team", "league", "season"):
        assert (additions_dir / f"matchbook_canonical_{entity}_additions.parquet").exists()
