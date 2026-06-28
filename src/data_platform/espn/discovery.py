"""ESPN unit discovery — season resolution + scoreboard URL building (Dagster-free).

For each allowlisted league we ask ESPN's own ``/leagues/{slug}/seasons`` endpoint
for its per-season ``startDate``/``endDate``, pick the seasons whose window overlaps
the run's target range (``select_season_windows`` in :mod:`.season`), and build one
scoreboard URL per selected season. ``fetch_json(url) -> dict`` is injected (the
throttled client in production, a fixture map in tests), so the module itself makes
no network calls and the result is deterministic and unit-testable.

Output is de-duplicated by (league_slug, season_year) and stably sorted, so repeated
runs over unchanged source content produce an identical unit list.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime

from .registry import EspnLeague
from .season import EspnSeason, select_season_windows


@dataclass(frozen=True, slots=True)
class EspnUnit:
    """One fetchable league×season scoreboard, tagged with everything downstream needs."""

    league_slug: str  # ESPN soccer slug, e.g. "eng.1"
    league_name: str  # display name from the registry
    season_year: int  # ESPN-reported season start year, e.g. 2025
    start_date: date  # ESPN-reported season start
    end_date: date  # ESPN-reported season end
    scoreboard_url: str  # absolute scoreboard URL for this league×season window


def _parse_espn_date(value: str) -> date:
    """Parse an ESPN ISO date (``2025-08-01T00:00Z``) to a calendar date."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _seasons_url(core_base_url: str, slug: str) -> str:
    return f"{core_base_url}/v2/sports/soccer/leagues/{slug}/seasons?limit=100"


def _scoreboard_url(site_base_url: str, slug: str, start: date, end: date) -> str:
    window = f"{start:%Y%m%d}-{end:%Y%m%d}"
    return f"{site_base_url}/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={window}&limit=1000"


def _resolve_seasons(fetch_json: Callable[[str], dict], url: str) -> list[EspnSeason]:
    payload = fetch_json(url)
    seasons: list[EspnSeason] = []
    for item in payload.get("items", []):
        try:
            seasons.append(
                EspnSeason(
                    year=int(item["year"]),
                    start_date=_parse_espn_date(item["startDate"]),
                    end_date=_parse_espn_date(item["endDate"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue  # malformed season entry — skip, never fabricate a window
    return seasons


def discover_units(
    fetch_json: Callable[[str], dict],
    leagues: Iterable[EspnLeague],
    run_date: date,
    horizon_days: int,
    *,
    core_base_url: str,
    site_base_url: str,
) -> list[EspnUnit]:
    """Discover every fetchable league×season unit overlapping ``run_date ± horizon``.

    ``fetch_json`` is injected; this module performs no network I/O itself. Units are
    de-duplicated by (slug, season_year) and stably sorted for deterministic output.
    """
    units: dict[tuple[str, int], EspnUnit] = {}
    for league in leagues:
        seasons = _resolve_seasons(fetch_json, _seasons_url(core_base_url, league.slug))
        for season in select_season_windows(seasons, run_date, horizon_days):
            unit = EspnUnit(
                league_slug=league.slug,
                league_name=league.name,
                season_year=season.year,
                start_date=season.start_date,
                end_date=season.end_date,
                scoreboard_url=_scoreboard_url(
                    site_base_url, league.slug, season.start_date, season.end_date
                ),
            )
            units[(league.slug, season.year)] = unit
    return sorted(units.values(), key=lambda u: (u.league_slug, u.season_year))


__all__ = ["EspnUnit", "discover_units"]
