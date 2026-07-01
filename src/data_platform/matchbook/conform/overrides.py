"""Override handling for the Matchbook conform engine."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OVERRIDE_COLUMNS = [
    "matchbook_event_id",
    "action",
    "match_id",
    "merge_source_match_id",
    "decided_at",
    "decided_by",
]


def load_overrides(path: Path) -> pd.DataFrame:
    """Load human-override decisions from a Parquet file.

    Returns an empty DataFrame with the correct columns when the file is absent.
    """
    if not path.exists():
        return pd.DataFrame(columns=OVERRIDE_COLUMNS)
    return pd.read_parquet(path)
