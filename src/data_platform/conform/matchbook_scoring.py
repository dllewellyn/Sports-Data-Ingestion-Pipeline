"""Scoring logic for the Matchbook conform engine."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from rapidfuzz.fuzz import token_sort_ratio

HIGH_CONFIDENCE = 0.95
MEDIUM_CONFIDENCE = 0.75
HIGH_THRESHOLD = 0.85
MEDIUM_THRESHOLD = 0.70
KICKOFF_TOLERANCE_MINUTES = 90


def _parse_start_utc(value: str) -> datetime | None:
    """Parse a start_utc string to a naive UTC datetime. Returns None on failure."""
    try:
        ts = pd.Timestamp(value)
        # Normalize to UTC and strip tzinfo so arithmetic with naive kickoff_time works.
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        return ts.to_pydatetime()
    except Exception:
        return None


def _score_candidate(
    home_parsed: str,
    away_parsed: str,
    start_utc: datetime,
    match_row: dict,
) -> dict | None:
    """Score a candidate canonical match against a parsed Matchbook event.

    Returns a dict with match_id, home_score, away_score, combined_score,
    kickoff_diff_minutes, or None if kickoff_time is missing.
    """
    canon_home = match_row.get("home_team_name", "")
    canon_away = match_row.get("away_team_name", "")
    kickoff_time = match_row.get("kickoff_time")

    if kickoff_time is None or pd.isna(kickoff_time):
        return None

    kickoff_ts = pd.Timestamp(kickoff_time)
    if kickoff_ts.tzinfo is not None:
        kickoff_ts = kickoff_ts.tz_convert("UTC").tz_localize(None)
    kickoff_dt = kickoff_ts.to_pydatetime()
    diff_minutes = abs((start_utc - kickoff_dt).total_seconds()) / 60.0

    home_score = token_sort_ratio(home_parsed, canon_home) / 100.0
    away_score = token_sort_ratio(away_parsed, canon_away) / 100.0

    return {
        "match_id": match_row["match_id"],
        "home_team_name": canon_home,
        "away_team_name": canon_away,
        "kickoff_time": str(kickoff_time),
        "home_score": home_score,
        "away_score": away_score,
        "combined_score": home_score + away_score,
        "kickoff_diff_minutes": diff_minutes,
    }
