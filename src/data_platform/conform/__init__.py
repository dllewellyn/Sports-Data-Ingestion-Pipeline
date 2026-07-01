"""Provider-agnostic conform layer.

Home of the single identity authority (`resolve.py`) that every soccer provider's
conform and the ESPN dbt path share, so identical inputs compute identical ids.
The Matchbook conform engine now lives here too (`matchbook.py` + `matchbook_*`
helpers), rewired onto the shared resolver.
"""

from pathlib import Path

import pandas as pd

from .matchbook import ConformReport, compute_canonical_match_id, run_conform
from .matchbook_event_name import parse_event_name
from .matchbook_overrides import load_overrides
from .matchbook_scoring import HIGH_CONFIDENCE, MEDIUM_CONFIDENCE

__all__ = [
    "run_conform",
    "ConformReport",
    "compute_canonical_match_id",
    "load_overrides",
    "parse_event_name",
    "HIGH_CONFIDENCE",
    "MEDIUM_CONFIDENCE",
    "bootstrap_additions_files",
]

# Column sets for the four canonical-additions Parquet files, keyed by entity.
# Shared by every provider's conform so bootstrapped empties match the int_* unions.
_ADDITIONS_COLUMNS: dict[str, list[str]] = {
    "match": [
        "match_id",
        "season_id",
        "home_team_id",
        "away_team_id",
        "kickoff_time",
        "ht_score",
        "ft_score",
        "status_completed",
    ],
    "team": ["team_id", "name", "similar_names"],
    "league": ["league_id", "name", "is_tournament"],
    "season": ["season_id", "league_id", "name", "start_date", "end_date"],
}


def bootstrap_additions_files(provider: str, additions_dir: Path) -> None:
    """Write the four empty `<provider>_canonical_*_additions.parquet` files.

    Provider-agnostic helper reused by every conform layer: it materialises the four
    canonical-additions Parquet files (match/team/league/season) with the correct
    columns and ZERO rows, so the `int_*` `read_parquet` unions find a valid file and
    contribute no rows before that provider's matching body exists (Spec 012 US5).
    """
    additions_dir.mkdir(parents=True, exist_ok=True)
    for entity, columns in _ADDITIONS_COLUMNS.items():
        path = additions_dir / f"{provider}_canonical_{entity}_additions.parquet"
        pd.DataFrame(columns=columns).to_parquet(path, index=False)
