"""The seed paths must be absolute and CWD-independent.

`run_conform` reads `team_aliases_seed_path` / `league_aliases_seed_path` via
`_load_seed`; Dagster happens to run from the repo root, but the paths must
resolve to the real seed CSVs from *any* CWD (the repo convention is that config
paths are absolute/anchored, not relative to the process CWD).
"""

import os
from pathlib import Path

from data_platform.config import Settings

_SEED_PROPS = ("team_aliases_seed_path", "league_aliases_seed_path")


def test_seed_paths_are_absolute_and_exist():
    s = Settings()
    for prop in _SEED_PROPS:
        path: Path = getattr(s, prop)
        assert path.is_absolute(), f"{prop} must be absolute, got {path}"
        assert path.is_file(), f"{prop} must point at a real seed CSV, got {path}"
        assert path.parent.name == "seeds"


def test_seed_paths_resolve_from_a_foreign_cwd(tmp_path, monkeypatch):
    """Changing CWD to an unrelated dir must not change where the seeds resolve."""
    monkeypatch.chdir(tmp_path)
    assert os.getcwd() == str(tmp_path)

    s = Settings()
    for prop in _SEED_PROPS:
        path: Path = getattr(s, prop)
        assert path.is_absolute()
        assert path.is_file(), f"{prop} did not resolve from a foreign CWD: {path}"
