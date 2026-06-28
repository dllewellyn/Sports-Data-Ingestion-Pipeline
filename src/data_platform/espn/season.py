"""Season-window selection from ESPN's own per-season dates (S1) — a pure leaf module.

ESPN reports each season's ``year``/``startDate``/``endDate``; we select the seasons
whose ``[start_date, end_date]`` window overlaps the run's target range
(``run_date ± horizon_days``) rather than hard-coding date ranges. The run date is
always injected — there is no hidden global clock — so the selection is
deterministic and unit-testable.

Edge E8: a season window spanning a calendar split (Aug→May) is selected from
ESPN's own dates, never a hand-coded calendar-year rollover.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True, slots=True)
class EspnSeason:
    """A season descriptor carrying ESPN's own reported window."""

    year: int
    start_date: date
    end_date: date


def select_season_windows(
    seasons: Iterable[EspnSeason],
    run_date: date,
    horizon_days: int,
) -> tuple[EspnSeason, ...]:
    """Return the seasons whose window overlaps ``run_date ± horizon_days``.

    Overlap of closed intervals ``[start_date, end_date]`` and
    ``[run_date - horizon, run_date + horizon]`` holds when the season starts no
    later than the target range ends and ends no earlier than it begins. Input
    order is preserved.
    """
    horizon = timedelta(days=horizon_days)
    range_start = run_date - horizon
    range_end = run_date + horizon
    return tuple(
        season
        for season in seasons
        if season.start_date <= range_end and season.end_date >= range_start
    )


__all__ = [
    "EspnSeason",
    "select_season_windows",
]
