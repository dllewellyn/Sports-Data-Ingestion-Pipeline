"""S5 — deterministic current-season vs historical classification (A3).

The run date is injected (no hidden `date.today()` in the logic) so AC5/AC16 apply
deterministically. Main season tokens are `<start><end>` two-digit pairs (2324 =
2023/24). The extra family packs all seasons in one file → always re-fetch.
"""

from datetime import date

from data_platform.football.registry import Family
from data_platform.football.season import (
    current_main_season_token,
    is_current_main_season,
    should_refetch,
)

RUN_DATE = date(2026, 6, 26)  # June 2026 → season 2025/26 is in progress


def test_current_token_for_run_date() -> None:
    assert current_main_season_token(RUN_DATE) == "2526"


def test_main_current_vs_historical() -> None:
    assert is_current_main_season("2526", RUN_DATE) is True
    assert is_current_main_season("2324", RUN_DATE) is False
    assert is_current_main_season("9394", RUN_DATE) is False


def test_season_rollover_boundary() -> None:
    # Seasons roll over in July (month >= 7 starts the new season).
    assert current_main_season_token(date(2025, 7, 1)) == "2526"
    assert current_main_season_token(date(2025, 6, 30)) == "2425"
    assert current_main_season_token(date(2026, 8, 1)) == "2627"


def test_extra_family_always_refetched() -> None:
    # Extra files carry every season in one file → never treated as historical.
    assert should_refetch(Family.EXTRA, None, RUN_DATE) is True


def test_main_refetch_only_for_current_season() -> None:
    assert should_refetch(Family.MAIN, "2526", RUN_DATE) is True
    assert should_refetch(Family.MAIN, "2324", RUN_DATE) is False
    assert should_refetch(Family.MAIN, "9394", RUN_DATE) is False
