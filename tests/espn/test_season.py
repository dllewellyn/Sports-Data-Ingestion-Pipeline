"""S1 — pure season-window selection from ESPN's own per-season dates.

`select_season_windows` reads each season's `start_date`/`end_date` and returns the
seasons whose window overlaps the run's target range (`run_date ± horizon_days`).
The run date is always injected — there is no hidden `date.today()` in the logic —
so the selection is deterministic and unit-testable. Edge E8: a season that spans a
calendar split (Aug→May) is selected from ESPN's own dates, never a hand-coded
calendar-year rollover.
"""

from datetime import date

from data_platform.espn.season import EspnSeason, select_season_windows

# A January run date: inside the Aug 2025 → May 2026 season window (E8).
RUN_DATE = date(2026, 1, 15)
HORIZON_DAYS = 30

PAST_SEASON = EspnSeason(year=2023, start_date=date(2023, 8, 1), end_date=date(2024, 5, 31))
CURRENT_SEASON = EspnSeason(year=2025, start_date=date(2025, 8, 1), end_date=date(2026, 5, 31))


def test_past_season_excluded() -> None:
    selected = select_season_windows([PAST_SEASON], RUN_DATE, HORIZON_DAYS)
    assert selected == ()


def test_current_season_overlapping_today_included() -> None:
    selected = select_season_windows([CURRENT_SEASON], RUN_DATE, HORIZON_DAYS)
    assert selected == (CURRENT_SEASON,)


def test_aug_to_may_split_selected_for_january_run() -> None:
    # E8: the season spans the calendar split. A January run sits inside it, proving
    # selection uses ESPN's own start/end dates, not a guessed calendar-year range.
    selected = select_season_windows([PAST_SEASON, CURRENT_SEASON], RUN_DATE, HORIZON_DAYS)
    assert selected == (CURRENT_SEASON,)


def test_window_edge_overlap_via_horizon() -> None:
    # A season ending shortly before the run date still overlaps via the horizon.
    just_ended = EspnSeason(year=2025, start_date=date(2025, 8, 1), end_date=date(2025, 12, 20))
    selected = select_season_windows([just_ended], RUN_DATE, HORIZON_DAYS)
    assert selected == (just_ended,)
