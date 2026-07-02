"""Provider-agnostic one-off PostgreSQL → bronze Parquet migration engines.

Home of the historic backfill engines that extract event data from the legacy
sports-gaming-engine PostgreSQL database and write it as bronze Parquet in the same
structure as the live ingest. Each provider engine (`espn.py`, `matchbook.py`) shares
the boundary-validation and atomic-write flow in `base.py`; the report shapes stay
per-provider.
"""

from .espn import run_espn_postgres_migration
from .matchbook import run_matchbook_postgres_migration

__all__ = [
    "run_espn_postgres_migration",
    "run_matchbook_postgres_migration",
]
