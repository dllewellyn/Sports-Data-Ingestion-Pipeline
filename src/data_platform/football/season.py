"""Current-season vs historical classification (A3) — a pure leaf module.

Historical files at football-data.co.uk are immutable (fetch once, then skip);
current-season files are updated in place and must always be re-fetched (AC5/AC16).
The run date is always passed in — there is no hidden global clock — so the
classification is deterministic and unit-testable.

Main season tokens are two two-digit years, e.g. ``2324`` = the 2023/24 season,
``9394`` = 1993/94. The extra family packs every season into one file, so it is
always re-fetched.
"""

from __future__ import annotations

from datetime import date

from .registry import Family

# Football seasons roll over in July: a date in month >= 7 belongs to the season
# starting that calendar year; earlier months belong to the prior year's season.
_SEASON_START_MONTH = 7


def current_main_season_token(run_date: date) -> str:
    """The main-family season token in progress on ``run_date`` (e.g. "2526")."""
    start_year = run_date.year if run_date.month >= _SEASON_START_MONTH else run_date.year - 1
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def is_current_main_season(season_token: str, run_date: date) -> bool:
    """True if a main season token is the current (in-progress) season."""
    return season_token == current_main_season_token(run_date)


def should_refetch(family: Family, season_token: str | None, run_date: date) -> bool:
    """Whether a file must be re-fetched rather than skipped when already landed.

    Extra files always (all seasons in one file); main files only for the current
    season. Historical main files are immutable → skipped if already present.
    """
    if family is Family.EXTRA:
        return True
    if season_token is None:
        raise ValueError("main-family files must carry a season token")
    return is_current_main_season(season_token, run_date)


__all__ = [
    "current_main_season_token",
    "is_current_main_season",
    "should_refetch",
]
