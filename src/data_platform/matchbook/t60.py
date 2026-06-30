"""Matchbook T-60 enrichment engine — pre-match favourite identification.

Pure-Python module (Dagster-free). The thin Dagster wrapper lives in
``assets/matchbook_t60.py``.

T-60 window: [kickoff_ms - 4500000, kickoff_ms - 2700000]
(75 min to 45 min before kickoff, in epoch milliseconds).

Favourite = runner with lowest best_back_price in the window
(lower back price = shorter odds = more likely winner on a betting exchange).
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from rapidfuzz.fuzz import token_sort_ratio

logger = logging.getLogger(__name__)

# T-60 window expressed in epoch milliseconds
T60_WINDOW_START_OFFSET_MS = 4_500_000  # 75 minutes before kickoff
T60_WINDOW_END_OFFSET_MS = 2_700_000  # 45 minutes before kickoff

RUNNER_MATCH_THRESHOLD = 0.70

# 1X2 market type — Matchbook sends this as "match_odds" but accept common variants
# case-insensitively in case the string differs across API versions or ingestor versions.
MARKET_TYPE_1X2_VARIANTS: frozenset[str] = frozenset(
    {"match_odds", "1x2", "match_result", "win_draw_win"}
)


@dataclass
class T60Report:
    enriched_count: int = 0
    skipped_no_ticks: int = 0
    skipped_no_runner_resolution: int = 0
    failures: list[str] = field(default_factory=list)


def filter_t60_ticks(ticks_df: pd.DataFrame, kickoff_ms: float) -> pd.DataFrame:
    """Filter ticks to the T-60 window [kickoff_ms - 4500000, kickoff_ms - 2700000].

    Ticks with NULL kickoff_ms are excluded (E3). Returns the filtered DataFrame.
    """
    if ticks_df.empty:
        return ticks_df

    window_start = kickoff_ms - T60_WINDOW_START_OFFSET_MS
    window_end = kickoff_ms - T60_WINDOW_END_OFFSET_MS

    mask = (
        ticks_df["ingested_at"].notna()
        & (ticks_df["ingested_at"] >= window_start)
        & (ticks_df["ingested_at"] <= window_end)
    )
    return ticks_df[mask].copy()


def find_favourite_runner(ticks_in_window: pd.DataFrame) -> str | None:
    """Find the runner_id with the minimum best_back_price in the T-60 window.

    Ticks with NULL best_back_price are skipped. Returns None if no valid ticks.
    """
    if ticks_in_window.empty:
        return None

    valid = ticks_in_window.dropna(subset=["best_back_price"])
    if valid.empty:
        return None

    min_idx = valid["best_back_price"].idxmin()
    return str(valid.loc[min_idx, "runner_id"])


def resolve_runner_to_team(
    runners_json: list[dict],
    home_team_name: str,
    away_team_name: str,
) -> dict[str, str | None]:
    """Fuzzy-match runner names to home/away team names using token_sort_ratio.

    Returns {"home_runner_id": ..., "away_runner_id": ...} where values are
    runner IDs (as strings) or None when no runner reaches the 0.70 threshold.

    Each runner in runners_json is expected to have "id" and "name" keys.
    """
    home_runner_id: str | None = None
    away_runner_id: str | None = None
    home_best_score = 0.0
    away_best_score = 0.0

    for runner in runners_json:
        runner_id = str(runner.get("id", ""))
        runner_name = str(runner.get("name", ""))

        home_score = token_sort_ratio(runner_name, home_team_name) / 100.0
        away_score = token_sort_ratio(runner_name, away_team_name) / 100.0

        if home_score >= RUNNER_MATCH_THRESHOLD and home_score > home_best_score:
            home_runner_id = runner_id
            home_best_score = home_score

        if away_score >= RUNNER_MATCH_THRESHOLD and away_score > away_best_score:
            away_runner_id = runner_id
            away_best_score = away_score

    return {"home_runner_id": home_runner_id, "away_runner_id": away_runner_id}


def _write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to Parquet atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    df.to_parquet(tmp_path, index=False)
    tmp_path.replace(path)


def run_t60_enrichment(
    resolved_links_path: Path,
    odds_dir: Path,
    canonical_dir: Path,
    events_bronze_dir: Path,
    out_path: Path,
    log: logging.Logger | None = None,
) -> T60Report:
    """Run the T-60 enrichment engine.

    For each linked Matchbook event:
    1. Filter odds to 'match_odds' market in the T-60 window.
    2. Find the favourite runner (lowest best_back_price).
    3. Resolve runner to team using raw_event["runners"] from events bronze.
    4. Write enrichment Parquet atomically.
    """
    if log is None:
        log = logger
    report = T60Report()

    # ── Load resolved links ─────────────────────────────────────────────
    if not resolved_links_path.exists():
        log.warning(
            "Resolved links not found at %s; writing empty T-60 Parquet", resolved_links_path
        )
        _write_parquet_atomic(
            pd.DataFrame(
                columns=[
                    "match_id",
                    "matchbook_event_id",
                    "favourite_runner_id",
                    "best_back_price_at_t60",
                    "tick_count_in_window",
                    "window_start_ms",
                    "window_end_ms",
                    "favourite_team_id",
                ]
            ),
            out_path,
        )
        return report

    resolved_df = pd.read_parquet(resolved_links_path)
    if resolved_df.empty:
        _write_parquet_atomic(
            pd.DataFrame(
                columns=[
                    "match_id",
                    "matchbook_event_id",
                    "favourite_runner_id",
                    "best_back_price_at_t60",
                    "tick_count_in_window",
                    "window_start_ms",
                    "window_end_ms",
                    "favourite_team_id",
                ]
            ),
            out_path,
        )
        return report

    # ── Load canonical match Parquet (for kickoff_time + team names) ────
    match_parquet = canonical_dir / "match.parquet"
    if not match_parquet.exists():
        log.warning("Canonical match.parquet not found at %s", match_parquet)
        match_map: dict[str, dict] = {}
    else:
        matches_df = pd.read_parquet(match_parquet)
        match_map = {row["match_id"]: row.to_dict() for _, row in matches_df.iterrows()}

    # ── Load Matchbook events bronze (for raw_event JSON) ───────────────
    event_files = (
        sorted(events_bronze_dir.glob("**/*.parquet")) if events_bronze_dir.exists() else []
    )
    events_df = pd.DataFrame()
    if event_files:
        events_df = pd.concat([pd.read_parquet(f) for f in event_files], ignore_index=True)
        if "ingested_at" in events_df.columns:
            events_df = events_df.sort_values("ingested_at", ascending=False)
        events_df = events_df.drop_duplicates(subset=["event_id"], keep="first")

    events_by_id: dict[str, dict] = {}
    if not events_df.empty:
        events_by_id = {str(row["event_id"]): row.to_dict() for _, row in events_df.iterrows()}

    # ── Load odds Parquet ───────────────────────────────────────────────
    odds_files = sorted(odds_dir.glob("**/*.parquet")) if odds_dir.exists() else []
    if not odds_files:
        log.warning("No odds Parquet files found in %s", odds_dir)
        _write_parquet_atomic(
            pd.DataFrame(
                columns=[
                    "match_id",
                    "matchbook_event_id",
                    "favourite_runner_id",
                    "best_back_price_at_t60",
                    "tick_count_in_window",
                    "window_start_ms",
                    "window_end_ms",
                    "favourite_team_id",
                ]
            ),
            out_path,
        )
        return report

    odds_df = pd.concat([pd.read_parquet(f) for f in odds_files], ignore_index=True)

    # ── Process each linked event ────────────────────────────────────────
    enrichment_rows: list[dict] = []

    for _, link_row in resolved_df.iterrows():
        event_id = str(link_row["matchbook_event_id"])
        match_id = str(link_row["match_id"])

        # Get match data for kickoff_time and team names
        match_data = match_map.get(match_id)
        if match_data is None:
            report.skipped_no_ticks += 1
            continue

        kickoff_time = match_data.get("kickoff_time")
        if kickoff_time is None or pd.isna(kickoff_time):
            report.skipped_no_ticks += 1
            continue

        kickoff_ms = pd.Timestamp(kickoff_time).value // 1_000_000  # ns -> ms

        # Filter odds to the 1X2 (match odds) market for this event.
        # Accept common variants case-insensitively in case the ingestor
        # passes through a different string from Matchbook's API.
        event_odds = odds_df[
            (odds_df["event_id"].astype(str) == event_id)
            & odds_df["market_type"].str.lower().isin(MARKET_TYPE_1X2_VARIANTS)
        ]

        if event_odds.empty:
            report.skipped_no_ticks += 1
            continue

        # Drop rows with NULL kickoff_ms (E3)
        if "kickoff_ms" in event_odds.columns:
            event_odds = event_odds.dropna(subset=["kickoff_ms"])

        # Apply T-60 window filter
        ticks_in_window = filter_t60_ticks(event_odds, kickoff_ms)

        if ticks_in_window.empty:
            report.skipped_no_ticks += 1
            continue

        # Find favourite runner
        favourite_runner_id = find_favourite_runner(ticks_in_window)
        if favourite_runner_id is None:
            report.skipped_no_ticks += 1
            continue

        # Get the best_back_price for the favourite
        fav_ticks = ticks_in_window[ticks_in_window["runner_id"].astype(str) == favourite_runner_id]
        best_price = fav_ticks["best_back_price"].min() if not fav_ticks.empty else None

        window_start = kickoff_ms - T60_WINDOW_START_OFFSET_MS
        window_end = kickoff_ms - T60_WINDOW_END_OFFSET_MS

        # Resolve runner to team
        favourite_team_id: str | None = None
        event_data = events_by_id.get(event_id)
        if event_data is not None:
            raw_event = event_data.get("raw_event", "{}")
            if isinstance(raw_event, str):
                try:
                    raw_event_dict = json.loads(raw_event)
                except (json.JSONDecodeError, TypeError):
                    raw_event_dict = {}
            else:
                raw_event_dict = raw_event or {}

            runners = raw_event_dict.get("runners", [])
            home_team_name = str(match_data.get("home_team_name", ""))
            away_team_name = str(match_data.get("away_team_name", ""))

            if runners and (home_team_name or away_team_name):
                resolution = resolve_runner_to_team(runners, home_team_name, away_team_name)
                home_runner_id = resolution["home_runner_id"]
                away_runner_id = resolution["away_runner_id"]

                if favourite_runner_id == home_runner_id and home_runner_id is not None:
                    favourite_team_id = str(match_data.get("home_team_id", "")) or None
                elif favourite_runner_id == away_runner_id and away_runner_id is not None:
                    favourite_team_id = str(match_data.get("away_team_id", "")) or None

        enrichment_rows.append(
            {
                "match_id": match_id,
                "matchbook_event_id": event_id,
                "favourite_runner_id": favourite_runner_id,
                "best_back_price_at_t60": best_price,
                "tick_count_in_window": len(ticks_in_window),
                "window_start_ms": window_start,
                "window_end_ms": window_end,
                "favourite_team_id": favourite_team_id,
            }
        )
        report.enriched_count += 1

    enrichment_df = pd.DataFrame(
        enrichment_rows,
        columns=[
            "match_id",
            "matchbook_event_id",
            "favourite_runner_id",
            "best_back_price_at_t60",
            "tick_count_in_window",
            "window_start_ms",
            "window_end_ms",
            "favourite_team_id",
        ],
    )
    _write_parquet_atomic(enrichment_df, out_path)

    log.info(
        "t60_enrichment: enriched=%d, skipped_no_ticks=%d, skipped_no_runner=%d",
        report.enriched_count,
        report.skipped_no_ticks,
        report.skipped_no_runner_resolution,
    )
    return report
