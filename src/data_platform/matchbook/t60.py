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
from collections.abc import Callable
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
    {"match_odds", "1x2", "match_result", "win_draw_win", "one_x_two"}
)

ENRICHMENT_COLUMNS = [
    "match_id",
    "matchbook_event_id",
    "favourite_runner_id",
    "best_back_price_at_t60",
    "tick_count_in_window",
    "window_start_ms",
    "window_end_ms",
    "favourite_team_id",
]


@dataclass
class T60Report:
    enriched_count: int = 0
    skipped_no_ticks: int = 0
    skipped_no_runner_resolution: int = 0
    failures: list[str] = field(default_factory=list)


def filter_t60_ticks(ticks_df: pd.DataFrame, kickoff_ms: float) -> pd.DataFrame:
    """Filter ticks to the T-60 window [kickoff_ms - 4500000, kickoff_ms - 2700000].

    Ticks with NULL ingested_at are excluded. ingested_at may be integer epoch-ms
    (test fixtures) or datetime64[ms, UTC] (production Parquet) — normalise to int ms.
    """
    if ticks_df.empty:
        return ticks_df

    window_start = kickoff_ms - T60_WINDOW_START_OFFSET_MS
    window_end = kickoff_ms - T60_WINDOW_END_OFFSET_MS

    ingested_ms = ticks_df["ingested_at"]
    if pd.api.types.is_datetime64_any_dtype(ingested_ms):
        # Remove timezone if present (production Parquet uses datetime64[ms, UTC])
        if hasattr(ingested_ms.dtype, "tz") and ingested_ms.dtype.tz is not None:
            ingested_ms = ingested_ms.dt.tz_convert("UTC").dt.tz_localize(None)
        # Normalise to epoch-milliseconds regardless of original unit (ns, ms, us, s)
        ingested_ms = ingested_ms.astype("datetime64[ms]").astype("int64")

    mask = ingested_ms.notna() & (ingested_ms >= window_start) & (ingested_ms <= window_end)
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
    log = log or logger
    report = T60Report()

    if not resolved_links_path.exists():
        log.warning(
            "Resolved links not found at %s; writing empty T-60 Parquet", resolved_links_path
        )
        _write_empty_enrichment(out_path)
        return report

    resolved_df = pd.read_parquet(resolved_links_path)
    if resolved_df.empty:
        _write_empty_enrichment(out_path)
        return report

    if not odds_dir.exists():
        log.warning("No odds directory found at %s", odds_dir)
        _write_empty_enrichment(out_path)
        return report

    match_map = _load_match_map(canonical_dir, log)
    events_by_id = _load_events_by_id(events_bronze_dir)
    load_odds = _make_odds_loader(odds_dir)

    enrichment_rows: list[dict] = []
    for _, link_row in resolved_df.iterrows():
        row = _enrich_link(link_row, match_map, events_by_id, load_odds, report)
        if row is not None:
            enrichment_rows.append(row)
            report.enriched_count += 1

    enrichment_df = pd.DataFrame(enrichment_rows, columns=ENRICHMENT_COLUMNS)
    _write_parquet_atomic(enrichment_df, out_path)

    log.info(
        "t60_enrichment: enriched=%d, skipped_no_ticks=%d, skipped_no_runner=%d",
        report.enriched_count,
        report.skipped_no_ticks,
        report.skipped_no_runner_resolution,
    )
    return report


# ── Load ────────────────────────────────────────────────────────────────────


def _write_empty_enrichment(out_path: Path) -> None:
    """Write an empty enrichment Parquet with the canonical column set."""
    _write_parquet_atomic(pd.DataFrame(columns=ENRICHMENT_COLUMNS), out_path)


def _load_match_map(canonical_dir: Path, log: logging.Logger) -> dict[str, dict]:
    """Index canonical matches by match_id (for kickoff_time + team names)."""
    match_parquet = canonical_dir / "match.parquet"
    if not match_parquet.exists():
        log.warning("Canonical match.parquet not found at %s", match_parquet)
        return {}
    matches_df = pd.read_parquet(match_parquet)
    return {row["match_id"]: row.to_dict() for _, row in matches_df.iterrows()}


def _load_events_by_id(events_bronze_dir: Path) -> dict[str, dict]:
    """Index Matchbook bronze events by event_id, preferring live-ingest rows."""
    event_files = (
        sorted(events_bronze_dir.glob("**/*.parquet")) if events_bronze_dir.exists() else []
    )
    if not event_files:
        return {}
    events_df = pd.concat([pd.read_parquet(f) for f in event_files], ignore_index=True)
    events_df = _dedup_events_preferring_live_rows(events_df)
    return {str(row["event_id"]): row.to_dict() for _, row in events_df.iterrows()}


def _dedup_events_preferring_live_rows(events_df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate events by event_id, breaking ties in favour of live-ingest rows.

    This is the one place migration and live ingest interact. Live-ingest rows carry
    ``markets`` in raw_event (and therefore runner data); Postgres-migration rows do
    not, yet the migration stamps ``ingested_at`` with the migration timestamp — so a
    plain recency dedup would let a data-poor migration row beat a rich live row for a
    shared event_id. Sorting by "has markets" first keeps the row we can actually
    resolve runners from. (See CLAUDE.md: migration ingested_at overrides live rows.)
    """

    def _has_markets(raw: object) -> bool:
        if isinstance(raw, str):
            return '"markets"' in raw
        return isinstance(raw, dict) and "markets" in raw

    if "raw_event" in events_df.columns:
        events_df = events_df.assign(_has_markets=events_df["raw_event"].map(_has_markets))
        events_df = events_df.sort_values(["_has_markets", "ingested_at"], ascending=[False, False])
        events_df = events_df.drop("_has_markets", axis=1)
    elif "ingested_at" in events_df.columns:
        events_df = events_df.sort_values("ingested_at", ascending=False)
    return events_df.drop_duplicates(subset=["event_id"], keep="first")


def _odds_files_for_date(odds_dir: Path, dt: pd.Timestamp) -> list[Path]:
    """Parquet files under the year=/month=/day= partition for a given date."""
    day_dir = odds_dir / f"year={dt.year}" / f"month={dt.month:02d}" / f"day={dt.day:02d}"
    return sorted(day_dir.glob("*.parquet")) if day_dir.exists() else []


def _make_odds_loader(odds_dir: Path) -> Callable[[pd.Timestamp], pd.DataFrame | None]:
    """Build a loader that returns the odds ticks relevant to a kickoff.

    Production odds are partitioned as ``year=YYYY/month=MM/day=DD/part-*.parquet``;
    the loader reads only the kickoff day and the day before (the T-60 window can
    cross midnight) to avoid loading the whole lake. Tests use a flat layout, in
    which case every Parquet under ``odds_dir`` is read once and reused. Returns
    None when no odds are available for the kickoff.
    """
    is_partitioned = any(odds_dir.glob("year=*"))
    flat_odds_df: pd.DataFrame | None = None
    if not is_partitioned:
        flat_files = sorted(odds_dir.glob("**/*.parquet"))
        if flat_files:
            flat_odds_df = pd.concat([pd.read_parquet(f) for f in flat_files], ignore_index=True)

    def load_odds(kickoff_ts: pd.Timestamp) -> pd.DataFrame | None:
        if is_partitioned:
            relevant = _odds_files_for_date(
                odds_dir, kickoff_ts - pd.Timedelta(days=1)
            ) + _odds_files_for_date(odds_dir, kickoff_ts)
            if not relevant:
                return None
            return pd.concat([pd.read_parquet(f) for f in relevant], ignore_index=True)
        return flat_odds_df

    return load_odds


# ── Enrich one link ───────────────────────────────────────────────────────────


def _enrich_link(
    link_row: pd.Series,
    match_map: dict[str, dict],
    events_by_id: dict[str, dict],
    load_odds: Callable[[pd.Timestamp], pd.DataFrame | None],
    report: T60Report,
) -> dict | None:
    """Enrich a single resolved link, or count a skip and return None."""
    event_id = str(link_row["matchbook_event_id"])
    match_id = str(link_row["match_id"])

    match_data = match_map.get(match_id)
    if match_data is None:
        report.skipped_no_ticks += 1
        return None

    kickoff_time = match_data.get("kickoff_time")
    if kickoff_time is None or pd.isna(kickoff_time):
        report.skipped_no_ticks += 1
        return None

    kickoff_ts = pd.Timestamp(kickoff_time)
    kickoff_ms = kickoff_ts.value // 1_000_000  # ns -> ms

    day_odds = load_odds(kickoff_ts)
    if day_odds is None:
        report.skipped_no_ticks += 1
        return None

    # Filter odds to the 1X2 (match odds) market for this event.
    event_odds = day_odds[
        (day_odds["event_id"].astype(str) == event_id)
        & day_odds["market_type"].str.lower().isin(MARKET_TYPE_1X2_VARIANTS)
    ]
    if event_odds.empty:
        report.skipped_no_ticks += 1
        return None

    # Drop rows with NULL kickoff_ms (E3)
    if "kickoff_ms" in event_odds.columns:
        event_odds = event_odds.dropna(subset=["kickoff_ms"])

    ticks_in_window = filter_t60_ticks(event_odds, kickoff_ms)
    if ticks_in_window.empty:
        report.skipped_no_ticks += 1
        return None

    favourite_runner_id = find_favourite_runner(ticks_in_window)
    if favourite_runner_id is None:
        report.skipped_no_ticks += 1
        return None

    fav_ticks = ticks_in_window[ticks_in_window["runner_id"].astype(str) == favourite_runner_id]
    best_price = fav_ticks["best_back_price"].min() if not fav_ticks.empty else None

    favourite_team_id = _resolve_favourite_team_id(
        favourite_runner_id, match_data, events_by_id.get(event_id)
    )

    return {
        "match_id": match_id,
        "matchbook_event_id": event_id,
        "favourite_runner_id": favourite_runner_id,
        "best_back_price_at_t60": best_price,
        "tick_count_in_window": len(ticks_in_window),
        "window_start_ms": kickoff_ms - T60_WINDOW_START_OFFSET_MS,
        "window_end_ms": kickoff_ms - T60_WINDOW_END_OFFSET_MS,
        "favourite_team_id": favourite_team_id,
    }


def _resolve_favourite_team_id(
    favourite_runner_id: str, match_data: dict, event_data: dict | None
) -> str | None:
    """Map the favourite runner to home/away team_id via raw_event runners."""
    if event_data is None:
        return None

    runners = _one_x_two_runners(event_data.get("raw_event", "{}"))
    home_team_name = str(match_data.get("home_team_name", ""))
    away_team_name = str(match_data.get("away_team_name", ""))
    if not runners or not (home_team_name or away_team_name):
        return None

    resolution = resolve_runner_to_team(runners, home_team_name, away_team_name)
    home_runner_id = resolution["home_runner_id"]
    away_runner_id = resolution["away_runner_id"]
    if home_runner_id is not None and favourite_runner_id == home_runner_id:
        return str(match_data.get("home_team_id", "")) or None
    if away_runner_id is not None and favourite_runner_id == away_runner_id:
        return str(match_data.get("away_team_id", "")) or None
    return None


def _one_x_two_runners(raw_event: object) -> list[dict]:
    """Extract 1X2-market runners from a raw_event payload.

    Runners live at the top level in some API formats, or nested inside the
    one_x_two market in Matchbook's live-ingest format. Migration rows have neither.
    """
    if isinstance(raw_event, str):
        try:
            raw_event_dict = json.loads(raw_event)
        except (json.JSONDecodeError, TypeError):
            return []
    else:
        raw_event_dict = raw_event or {}

    runners = raw_event_dict.get("runners", [])
    if runners:
        return runners
    for market in raw_event_dict.get("markets", []):
        if market.get("market-type", "").lower() in MARKET_TYPE_1X2_VARIANTS:
            return market.get("runners", [])
    return []
