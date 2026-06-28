"""
SPIKE — ESPN Unofficial API: Full Event Catalogue Discovery
============================================================
Throwaway investigation code. DO NOT ship to production.

Answers: Can we discover all ESPN football + rugby leagues and fetch their
matches (upcoming + historic) without any hardcoded competition IDs?

Findings so far:
  - sports.core.api.espn.com/v2/sports/{sport}/leagues  → paginated list of all leagues
  - Soccer leagues use string slugs (e.g. "eng.1"), rugby uses numeric IDs
  - Each league exposes a /seasons endpoint with startDate/endDate per season
  - site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates={YYYYMMDD}-{YYYYMMDD}
    returns ALL matches in that window (tested: 380 EPL events for a full season)
"""

import json
import time
import urllib.request
from dataclasses import dataclass


@dataclass
class Match:
    provider: str = "espn"
    sport: str = ""
    league_id: str = ""
    league_name: str = ""
    event_id: str = ""
    home_team_id: str = ""
    home_team_name: str = ""
    away_team_id: str = ""
    away_team_name: str = ""
    kickoff_utc: str = ""
    status: str = ""


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _get_safe(url: str) -> dict | None:
    try:
        return _get(url)
    except Exception as e:
        print(f"  WARN: {e} — {url}")
        return None


# ── League discovery ──────────────────────────────────────────────────────────


def discover_soccer_leagues() -> list[dict]:
    """Returns list of {id, name} for all ESPN soccer leagues (239 total)."""
    leagues = []
    page = 1
    while True:
        data = _get(
            f"https://sports.core.api.espn.com/v2/sports/soccer/leagues?limit=100&page={page}"
        )
        for item in data["items"]:
            ref = item["$ref"]
            league_id = ref.split("/leagues/")[1].split("?")[0]
            leagues.append({"id": league_id, "sport_slug": "soccer"})
        if page >= data["pageCount"]:
            break
        page += 1
        time.sleep(0.1)

    # Fetch names in batch (sample only — full run would hit all 239)
    print(f"  Discovered {len(leagues)} soccer leagues")
    return leagues


def discover_rugby_leagues() -> list[dict]:
    """Returns list of {id, name} for all ESPN rugby leagues (25 total)."""
    data = _get("https://sports.core.api.espn.com/v2/sports/rugby/leagues?limit=100")
    leagues = []
    for item in data["items"]:
        ref = item["$ref"]
        league_id = ref.split("/leagues/")[1].split("?")[0]
        leagues.append({"id": league_id, "sport_slug": "rugby"})
    print(f"  Discovered {len(leagues)} rugby leagues")
    return leagues


# ── Season discovery ──────────────────────────────────────────────────────────


def get_seasons(sport_slug: str, league_id: str, max_seasons: int = 3) -> list[dict]:
    """Returns up to max_seasons seasons with start/end dates."""
    if sport_slug == "soccer":
        url = f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{league_id}/seasons?limit={max_seasons}"
    else:
        url = f"https://sports.core.api.espn.com/v2/sports/rugby/leagues/{league_id}/seasons?limit={max_seasons}"

    data = _get_safe(url)
    if not data:
        return []

    seasons = []
    for item in data.get("items", [])[:max_seasons]:
        s = _get_safe(item["$ref"])
        if s and s.get("startDate") and s.get("endDate"):
            seasons.append(
                {
                    "year": s.get("year"),
                    "start": s["startDate"][:10].replace("-", ""),  # YYYYMMDD
                    "end": s["endDate"][:10].replace("-", ""),
                }
            )
        time.sleep(0.05)
    return seasons


# ── Scoreboard fetch ──────────────────────────────────────────────────────────


def fetch_matches(
    sport_slug: str, league_id: str, league_name: str, start_date: str, end_date: str
) -> list[Match]:
    """Fetches all matches for a league in the given date window."""
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/{sport_slug}"
        f"/{league_id}/scoreboard?dates={start_date}-{end_date}&limit=1000"
    )
    data = _get_safe(url)
    if not data:
        return []

    # Infer sport name from slug
    sport = "football" if sport_slug == "soccer" else "rugby_union"

    matches = []
    for event in data.get("events", []):
        comps = event.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        home = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "home"), None)
        away = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue

        matches.append(
            Match(
                sport=sport,
                league_id=str(league_id),
                league_name=league_name,
                event_id=str(event.get("id", "")),
                home_team_id=str(home.get("team", {}).get("id", "")),
                home_team_name=home.get("team", {}).get("displayName", ""),
                away_team_id=str(away.get("team", {}).get("id", "")),
                away_team_name=away.get("team", {}).get("displayName", ""),
                kickoff_utc=event.get("date", ""),
                status=comp.get("status", {}).get("type", {}).get("name", ""),
            )
        )
    return matches


# ── Full spike run ────────────────────────────────────────────────────────────


def run_spike(sample_only: bool = True):
    """
    sample_only=True: runs on a handful of leagues to verify the pattern.
    sample_only=False: full run across all 239 soccer + 25 rugby leagues.
    """
    SAMPLE_SOCCER = ["eng.1", "esp.1", "ger.1", "uefa.champions", "fifa.world"]
    SAMPLE_RUGBY = ["180659", "270557", "267979", "164205"]  # Six Nations, URC, Prem, RWC

    print("=== ESPN API Discovery Spike ===\n")

    all_matches: list[Match] = []

    for sport_slug, sample_ids in [("soccer", SAMPLE_SOCCER), ("rugby", SAMPLE_RUGBY)]:
        print(f"--- {sport_slug.upper()} ---")

        if sample_only:
            leagues = [{"id": lid, "sport_slug": sport_slug} for lid in sample_ids]
        else:
            leagues = (
                discover_soccer_leagues() if sport_slug == "soccer" else discover_rugby_leagues()
            )

        for league in leagues:
            lid = league["id"]

            # Get league name
            if sport_slug == "soccer":
                detail = _get_safe(
                    f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{lid}"
                )
            else:
                detail = _get_safe(
                    f"https://sports.core.api.espn.com/v2/sports/rugby/leagues/{lid}"
                )
            league_name = detail.get("name", lid) if detail else lid

            # Get last 2 seasons
            seasons = get_seasons(sport_slug, lid, max_seasons=2)
            if not seasons:
                print(f"  {league_name}: no seasons found")
                continue

            for season in seasons:
                matches = fetch_matches(
                    sport_slug, lid, league_name, season["start"], season["end"]
                )
                print(f"  {league_name} ({season['year']}): {len(matches)} matches")
                all_matches.extend(matches)
                time.sleep(0.1)

    print(f"\nTotal matches fetched: {len(all_matches)}")

    # Spot-check output
    print("\nSample (first 5):")
    for m in all_matches[:5]:
        print(
            f"  [{m.sport}] {m.league_name} | {m.home_team_name} vs "
            f"{m.away_team_name} | {m.kickoff_utc} | {m.status}"
        )

    return all_matches


if __name__ == "__main__":
    run_spike(sample_only=True)
