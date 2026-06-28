"""S4 — ESPN discovery: season resolution + scoreboard URL building (Dagster-free)."""

from datetime import date

from data_platform.espn.discovery import discover_units
from data_platform.espn.registry import EspnLeague

CORE = "https://sports.core.api.espn.com"
SITE = "https://site.api.espn.com"
EPL = EspnLeague("eng.1", "English Premier League")


def _seasons_payload() -> dict:
    return {
        "items": [
            {"year": 2025, "startDate": "2025-08-01T00:00Z", "endDate": "2026-05-31T00:00Z"},
            {"year": 2024, "startDate": "2024-08-01T00:00Z", "endDate": "2025-05-31T00:00Z"},
        ]
    }


def test_discover_builds_scoreboard_url_for_overlapping_season() -> None:
    seasons_url = f"{CORE}/v2/sports/soccer/leagues/eng.1/seasons?limit=100"
    fetched: list[str] = []

    def fetch_json(url: str) -> dict:
        fetched.append(url)
        return _seasons_payload()

    units = discover_units(
        fetch_json,
        [EPL],
        run_date=date(2025, 9, 1),
        horizon_days=30,
        core_base_url=CORE,
        site_base_url=SITE,
    )

    assert len(units) == 1
    u = units[0]
    assert u.league_slug == "eng.1"
    assert u.season_year == 2025
    assert u.scoreboard_url == (
        f"{SITE}/apis/site/v2/sports/soccer/eng.1/scoreboard?dates=20250801-20260531&limit=1000"
    )
    assert seasons_url in fetched


def test_discover_is_deterministic_and_sorted() -> None:
    def fetch_json(url: str) -> dict:
        return _seasons_payload()

    leagues = [EspnLeague("esp.1", "La Liga"), EspnLeague("eng.1", "EPL")]
    units = discover_units(
        fetch_json,
        leagues,
        run_date=date(2025, 9, 1),
        horizon_days=30,
        core_base_url=CORE,
        site_base_url=SITE,
    )
    slugs = [(u.league_slug, u.season_year) for u in units]
    assert slugs == sorted(slugs)
