"""Tests for the Matchbook T-60 enrichment engine (Spec 006 S5)."""

from pathlib import Path

import pandas as pd

from data_platform.matchbook.t60 import (
    filter_t60_ticks,
    find_favourite_runner,
    resolve_runner_to_team,
    run_t60_enrichment,
)

# ── U19: T-60 window filter ─────────────────────────────────────────────────


def test_filter_t60_ticks_keeps_ticks_in_window() -> None:
    """U19: ticks within [kickoff - 4500000, kickoff - 2700000] are kept."""
    kickoff_ms = 1_000_000_000_000
    window_start = kickoff_ms - 4_500_000  # = 999_995_500_000
    window_end = kickoff_ms - 2_700_000  # = 999_997_300_000

    ticks = pd.DataFrame(
        {
            "ingested_at": [
                window_start,  # on boundary (included)
                window_end,  # on boundary (included)
                window_start - 1,  # just outside (excluded)
                window_end + 1,  # just outside (excluded)
                window_start + 100_000,  # inside (included)
            ],
            "runner_id": ["r1", "r2", "r3", "r4", "r5"],
            "best_back_price": [2.0, 2.1, 1.9, 2.2, 2.05],
        }
    )

    result = filter_t60_ticks(ticks, kickoff_ms)
    assert len(result) == 3  # boundary + inside
    assert set(result["runner_id"]) == {"r1", "r2", "r5"}


def test_filter_t60_ticks_excludes_null_ingested_at() -> None:
    """Ticks with NULL ingested_at are excluded from window."""
    kickoff_ms = 1_000_000_000_000
    ticks = pd.DataFrame(
        {
            "ingested_at": [kickoff_ms - 4_000_000, None],
            "runner_id": ["r1", "r2"],
            "best_back_price": [2.0, 1.5],
        }
    )
    result = filter_t60_ticks(ticks, kickoff_ms)
    assert len(result) == 1
    assert result.iloc[0]["runner_id"] == "r1"


def test_filter_t60_ticks_empty_df() -> None:
    """Empty DataFrame returns empty DataFrame."""
    result = filter_t60_ticks(pd.DataFrame(), 1_000_000_000_000)
    assert result.empty


def test_filter_t60_ticks_datetime64_ms_utc() -> None:
    """Production Parquet stores ingested_at as datetime64[ms, UTC] — must normalise correctly."""

    kickoff_ms = 1_000_000_000_000  # epoch-ms
    window_start_ms = kickoff_ms - 4_500_000
    window_end_ms = kickoff_ms - 2_700_000

    # Build timestamps as datetime64[ms, UTC] (production dtype)
    def ms_to_ts(ms: int) -> pd.Timestamp:
        return pd.Timestamp(ms * 1_000_000, unit="ns", tz="UTC")

    ticks = pd.DataFrame(
        {
            "ingested_at": pd.array(
                [
                    ms_to_ts(window_start_ms),  # included
                    ms_to_ts(window_end_ms),  # included
                    ms_to_ts(window_start_ms - 1),  # excluded
                    ms_to_ts(window_end_ms + 1),  # excluded
                ],
                dtype="datetime64[ms, UTC]",
            ),
            "runner_id": ["r1", "r2", "r3", "r4"],
            "best_back_price": [2.0, 2.1, 1.9, 2.2],
        }
    )

    result = filter_t60_ticks(ticks, kickoff_ms)
    assert set(result["runner_id"]) == {"r1", "r2"}


# ── U20: Find favourite runner ───────────────────────────────────────────────


def test_find_favourite_runner_lowest_price() -> None:
    """U20: runner with lowest best_back_price is the favourite."""
    ticks = pd.DataFrame(
        {
            "runner_id": ["r1", "r2", "r3", "r1"],
            "best_back_price": [2.5, 1.8, 3.2, 2.0],
        }
    )
    result = find_favourite_runner(ticks)
    assert result == "r2"  # r2 has the lowest price (1.8)


def test_find_favourite_runner_skips_null_price() -> None:
    """Ticks with NULL best_back_price are skipped."""
    ticks = pd.DataFrame(
        {
            "runner_id": ["r1", "r2"],
            "best_back_price": [None, 2.5],
        }
    )
    result = find_favourite_runner(ticks)
    assert result == "r2"


def test_find_favourite_runner_all_null_prices() -> None:
    """Returns None when all prices are NULL."""
    ticks = pd.DataFrame(
        {
            "runner_id": ["r1", "r2"],
            "best_back_price": [None, None],
        }
    )
    result = find_favourite_runner(ticks)
    assert result is None


def test_find_favourite_runner_empty_df() -> None:
    """Returns None for empty DataFrame."""
    result = find_favourite_runner(pd.DataFrame())
    assert result is None


# ── U22: Runner-to-team resolution ──────────────────────────────────────────


def test_resolve_runner_to_team_exact_match() -> None:
    """U22: exact match assigns home/away runner IDs correctly."""
    runners = [
        {"id": "r1", "name": "Arsenal"},
        {"id": "r2", "name": "Chelsea"},
    ]
    result = resolve_runner_to_team(runners, "Arsenal", "Chelsea")
    assert result["home_runner_id"] == "r1"
    assert result["away_runner_id"] == "r2"


def test_resolve_runner_to_team_fuzzy_match() -> None:
    """Fuzzy match with partial names resolves correctly (>= 0.70 threshold)."""
    runners = [
        {"id": "r1", "name": "Arsenal FC"},
        {"id": "r2", "name": "Chelsea FC"},
    ]
    # "Arsenal FC" vs "Arsenal" -> token_sort_ratio ~0.82 (>= 0.70)
    # "Chelsea FC" vs "Chelsea" -> token_sort_ratio ~0.82 (>= 0.70)
    result = resolve_runner_to_team(runners, "Arsenal", "Chelsea")
    assert result["home_runner_id"] == "r1"
    assert result["away_runner_id"] == "r2"


def test_resolve_runner_to_team_below_threshold_returns_none() -> None:
    """Scores below 0.70 return None for that team."""
    runners = [
        {"id": "r1", "name": "Team XYZ"},
        {"id": "r2", "name": "Unknown FC"},
    ]
    result = resolve_runner_to_team(runners, "Arsenal", "Chelsea")
    assert result["home_runner_id"] is None
    assert result["away_runner_id"] is None


def test_resolve_runner_to_team_empty_runners() -> None:
    """Empty runners list returns None for both."""
    result = resolve_runner_to_team([], "Arsenal", "Chelsea")
    assert result["home_runner_id"] is None
    assert result["away_runner_id"] is None


# ── U21: No T-60 tick -> no row in enrichment ───────────────────────────────


def _write_parquet(path: Path, data: list[dict]) -> None:
    """Helper: write a list of dicts as a Parquet file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(data).to_parquet(path, index=False)


def test_no_t60_tick_produces_no_row(tmp_path: Path) -> None:
    """U21: event with no ticks in T-60 window produces no row in enrichment."""
    kickoff_ms = 1_000_000_000_000

    # Resolved links
    resolved_path = tmp_path / "resolved.parquet"
    _write_parquet(
        resolved_path,
        [
            {
                "matchbook_event_id": "evt1",
                "match_id": "m1",
                "match_method": "fuzzy_high",
                "confidence": 0.95,
                "review_status": "auto_confirmed",
            }
        ],
    )

    # Canonical match (with kickoff_time corresponding to kickoff_ms)
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir()
    kickoff_ts = pd.Timestamp(kickoff_ms, unit="ms", tz="UTC")
    _write_parquet(
        canonical_dir / "match.parquet",
        [
            {
                "match_id": "m1",
                "season_id": "s1",
                "home_team_id": "h1",
                "away_team_id": "a1",
                "favourite_team_id": None,
                "kickoff_time": kickoff_ts,
                "home_team_name": "Arsenal",
                "away_team_name": "Chelsea",
            }
        ],
    )

    # Odds: tick OUTSIDE the T-60 window (e.g. at kickoff time itself)
    odds_dir = tmp_path / "odds"
    odds_dir.mkdir()
    _write_parquet(
        odds_dir / "odds.parquet",
        [
            {
                "event_id": "evt1",
                "market_type": "match_odds",
                "runner_id": "r1",
                "best_back_price": 2.0,
                "ingested_at": kickoff_ms,  # AT kickoff, not in T-60 window
                "kickoff_ms": kickoff_ms,
            }
        ],
    )

    events_bronze_dir = tmp_path / "events"

    out_path = tmp_path / "enrichment.parquet"
    report = run_t60_enrichment(
        resolved_links_path=resolved_path,
        odds_dir=odds_dir,
        canonical_dir=canonical_dir,
        events_bronze_dir=events_bronze_dir,
        out_path=out_path,
    )

    result = pd.read_parquet(out_path)
    assert result.empty
    assert report.enriched_count == 0


def test_t60_enrichment_with_ticks_in_window(tmp_path: Path) -> None:
    """T-60 enrichment produces a row when ticks exist in the window."""
    kickoff_ms = 1_000_000_000_000

    # Resolved links
    resolved_path = tmp_path / "resolved.parquet"
    _write_parquet(
        resolved_path,
        [
            {
                "matchbook_event_id": "evt1",
                "match_id": "m1",
                "match_method": "fuzzy_high",
                "confidence": 0.95,
                "review_status": "auto_confirmed",
            }
        ],
    )

    # Canonical match
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir()
    kickoff_ts = pd.Timestamp(kickoff_ms, unit="ms", tz="UTC")
    _write_parquet(
        canonical_dir / "match.parquet",
        [
            {
                "match_id": "m1",
                "season_id": "s1",
                "home_team_id": "h1",
                "away_team_id": "a1",
                "favourite_team_id": None,
                "kickoff_time": kickoff_ts,
                "home_team_name": "Arsenal",
                "away_team_name": "Chelsea",
            }
        ],
    )

    # Odds: two runners, one tick each, in the T-60 window
    tick_in_window = kickoff_ms - 4_000_000  # 66.7 min before kickoff
    odds_dir = tmp_path / "odds"
    odds_dir.mkdir()
    _write_parquet(
        odds_dir / "odds.parquet",
        [
            {
                "event_id": "evt1",
                "market_type": "match_odds",
                "runner_id": "r1",
                "best_back_price": 2.5,
                "ingested_at": tick_in_window,
                "kickoff_ms": kickoff_ms,
            },
            {
                "event_id": "evt1",
                "market_type": "match_odds",
                "runner_id": "r2",
                "best_back_price": 1.8,
                "ingested_at": tick_in_window,
                "kickoff_ms": kickoff_ms,
            },
        ],
    )

    # Events bronze: raw_event with runners
    events_bronze_dir = tmp_path / "events"
    events_bronze_dir.mkdir()
    import json

    raw_event_json = json.dumps(
        {
            "runners": [
                {"id": "r1", "name": "Arsenal", "prices": []},
                {"id": "r2", "name": "Chelsea", "prices": []},
            ]
        }
    )
    _write_parquet(
        events_bronze_dir / "batch.parquet",
        [
            {
                "event_id": "evt1",
                "event_name": "Arsenal v Chelsea",
                "start_utc": "2026-08-10T15:00:00Z",
                "sport_id": 15,
                "ingested_at": 1,
                "raw_event": raw_event_json,
            }
        ],
    )

    out_path = tmp_path / "enrichment.parquet"
    report = run_t60_enrichment(
        resolved_links_path=resolved_path,
        odds_dir=odds_dir,
        canonical_dir=canonical_dir,
        events_bronze_dir=events_bronze_dir,
        out_path=out_path,
    )

    result = pd.read_parquet(out_path)
    assert len(result) == 1
    assert result.iloc[0]["match_id"] == "m1"
    assert result.iloc[0]["favourite_runner_id"] == "r2"  # r2 has lower price (1.8)
    assert report.enriched_count == 1


def test_no_resolved_links_file(tmp_path: Path) -> None:
    """Missing resolved links file produces empty enrichment Parquet without error."""
    resolved_path = tmp_path / "nonexistent.parquet"
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir()
    events_bronze_dir = tmp_path / "events"
    odds_dir = tmp_path / "odds"
    out_path = tmp_path / "enrichment.parquet"

    run_t60_enrichment(
        resolved_links_path=resolved_path,
        odds_dir=odds_dir,
        canonical_dir=canonical_dir,
        events_bronze_dir=events_bronze_dir,
        out_path=out_path,
    )
    assert out_path.exists()
    result = pd.read_parquet(out_path)
    assert result.empty


def test_null_kickoff_ms_ticks_excluded(tmp_path: Path) -> None:
    """E3: ticks with NULL kickoff_ms in the odds lake are excluded from T-60 window.

    The spec says: "Ticks with NULL kickoff_ms are excluded from the T-60 window
    calculation for that event." When ALL ticks for an event have NULL kickoff_ms,
    no row is written to the enrichment Parquet for that event.
    """
    kickoff_ms = 1_000_000_000_000

    resolved_path = tmp_path / "resolved.parquet"
    _write_parquet(
        resolved_path,
        [
            {
                "matchbook_event_id": "evt1",
                "match_id": "m1",
                "match_method": "fuzzy_high",
                "confidence": 0.95,
                "review_status": "auto_confirmed",
            }
        ],
    )

    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir()
    kickoff_ts = pd.Timestamp(kickoff_ms, unit="ms", tz="UTC")
    _write_parquet(
        canonical_dir / "match.parquet",
        [
            {
                "match_id": "m1",
                "season_id": "s1",
                "home_team_id": "h1",
                "away_team_id": "a1",
                "favourite_team_id": None,
                "kickoff_time": kickoff_ts,
                "home_team_name": "Arsenal",
                "away_team_name": "Chelsea",
            }
        ],
    )

    tick_in_window = kickoff_ms - 4_000_000
    odds_dir = tmp_path / "odds"
    odds_dir.mkdir()
    # ALL ticks have NULL kickoff_ms — they should all be excluded
    _write_parquet(
        odds_dir / "odds.parquet",
        [
            {
                "event_id": "evt1",
                "market_type": "match_odds",
                "runner_id": "r1",
                "best_back_price": 2.0,
                "ingested_at": tick_in_window,
                "kickoff_ms": None,
            },  # NULL kickoff_ms
        ],
    )

    events_bronze_dir = tmp_path / "events"
    out_path = tmp_path / "enrichment.parquet"

    report = run_t60_enrichment(
        resolved_links_path=resolved_path,
        odds_dir=odds_dir,
        canonical_dir=canonical_dir,
        events_bronze_dir=events_bronze_dir,
        out_path=out_path,
    )

    result = pd.read_parquet(out_path)
    # Ticks with NULL kickoff_ms are excluded; no valid ticks remain => no enrichment row
    assert result.empty
    assert report.enriched_count == 0
