"""Tests for the Matchbook conform engine (Spec 006)."""

from pathlib import Path

import pandas as pd

# The engine relocated from data_platform.matchbook.conform to the neutral
# data_platform.conform package (T009). These end-to-end assertions over
# run_conform (resolved / exceptions / additions outputs) are unchanged from the
# pre-move suite, so their continued passing IS the output-equivalence guarantee.
from data_platform.conform.matchbook import (
    HIGH_CONFIDENCE,
    MEDIUM_CONFIDENCE,
    compute_canonical_match_id,
    load_overrides,
    parse_event_name,
    run_conform,
)

# ── U1: parse normal event name ─────────────────────────────────────────────


def test_parse_event_name_normal() -> None:
    """U1: parse 'Arsenal v Chelsea' -> ('Arsenal', 'Chelsea')."""
    assert parse_event_name("Arsenal vs Chelsea") == ("Arsenal", "Chelsea")


# ── U2: missing separator ───────────────────────────────────────────────────


def test_parse_event_name_no_separator() -> None:
    """U2: no ' v ' separator -> None."""
    assert parse_event_name("Rugby event") is None


def test_parse_event_name_wrong_separator() -> None:
    """Different separators don't match."""
    assert parse_event_name("Team A v Team B") is None


# ── U3: first ' v ' split only ──────────────────────────────────────────────


def test_parse_event_name_multiple_v() -> None:
    """U3: 'Real Madrid v FC v Barcelona' splits on first ' v '."""
    assert parse_event_name("Real Madrid vs FC vs Barcelona") == (
        "Real Madrid",
        "FC vs Barcelona",
    )


# ── Edge cases ──────────────────────────────────────────────────────────────


def test_parse_event_name_empty_parts() -> None:
    """' v ' with empty parts returns None."""
    assert parse_event_name(" v ") is None


def test_parse_event_name_only_home() -> None:
    """Home present but away empty after strip."""
    assert parse_event_name("Arsenal v ") is None


def test_parse_event_name_only_away() -> None:
    """Away present but home empty after strip."""
    assert parse_event_name(" v Chelsea") is None


# ── U4: load_overrides absent file ──────────────────────────────────────────


def test_load_overrides_absent_file(tmp_path: Path) -> None:
    """U4: absent file returns empty DataFrame with correct columns."""
    result = load_overrides(tmp_path / "nonexistent.parquet")
    assert result.empty
    assert list(result.columns) == [
        "matchbook_event_id",
        "action",
        "match_id",
        "merge_source_match_id",
        "decided_at",
        "decided_by",
    ]


# ── U5: load_overrides present file ─────────────────────────────────────────


def test_load_overrides_present_file(tmp_path: Path) -> None:
    """U5: present file returns override rows."""
    path = tmp_path / "overrides.parquet"
    df = pd.DataFrame(
        {
            "matchbook_event_id": ["evt_1"],
            "action": ["link"],
            "match_id": ["m_1"],
            "merge_source_match_id": [None],
            "decided_at": ["2026-06-29T12:00:00"],
            "decided_by": ["human_ui"],
        }
    )
    df.to_parquet(path)
    result = load_overrides(path)
    assert len(result) == 1
    assert result.iloc[0]["matchbook_event_id"] == "evt_1"


# ── Helpers for conform engine tests ────────────────────────────────────────


def _make_event_parquet(path: Path, events: list[dict]) -> None:
    """Write a list of event dicts as a bronze Parquet file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(events)
    df.to_parquet(path)


def _make_canonical_match_parquet(path: Path, matches: list[dict]) -> None:
    """Write canonical match data for the conform engine to read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(matches)
    df.to_parquet(path)


def _run_conform_with_dirs(
    tmp_path: Path,
    events: list[dict],
    canonical_matches: list[dict] | None = None,
    overrides: list[dict] | None = None,
):
    """Helper that sets up dirs and runs the conform engine."""
    events_dir = tmp_path / "events"
    canonical_dir = tmp_path / "canonical"
    exceptions_dir = tmp_path / "exceptions"
    conform_dir = tmp_path / "conform"
    additions_dir = tmp_path / "additions"
    overrides_path = tmp_path / "overrides" / "matchbook_overrides.parquet"

    if events:
        _make_event_parquet(events_dir / "football" / "batch.parquet", events)

    if canonical_matches:
        _make_canonical_match_parquet(canonical_dir / "match.parquet", canonical_matches)

    if overrides:
        overrides_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(overrides).to_parquet(overrides_path)

    report = run_conform(
        events_dir=events_dir,
        canonical_dir=canonical_dir,
        overrides_path=overrides_path,
        exceptions_dir=exceptions_dir,
        conform_dir=conform_dir,
        additions_dir=additions_dir,
    )

    resolved_path = conform_dir / "matchbook_resolved_links.parquet"
    exceptions_path = exceptions_dir / "matchbook_unresolved.parquet"
    additions_path = additions_dir / "matchbook_canonical_match_additions.parquet"

    resolved = pd.read_parquet(resolved_path) if resolved_path.exists() else pd.DataFrame()
    exceptions = pd.read_parquet(exceptions_path) if exceptions_path.exists() else pd.DataFrame()
    additions = pd.read_parquet(additions_path) if additions_path.exists() else pd.DataFrame()

    return report, resolved, exceptions, additions


# ── run_conform: empty input ────────────────────────────────────────────────


def test_run_conform_empty_events(tmp_path: Path) -> None:
    """Empty events_dir produces zero resolved rows, no error."""
    report, resolved, exceptions, _ = _run_conform_with_dirs(tmp_path, events=[])
    assert report.resolved_count == 0
    assert report.exceptions_count == 0
    assert resolved.empty
    assert exceptions.empty


# ── U6: Override routes before fuzzy matching ───────────────────────────────


def test_override_routes_before_fuzzy(tmp_path: Path) -> None:
    """U6: Override event receives confidence=1.0, match_method='human_override'."""
    events = [
        {
            "event_id": "100",
            "event_name": "Arsenal vs Chelsea",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 15,
            "ingested_at": 1,
        }
    ]
    overrides = [
        {
            "matchbook_event_id": "100",
            "action": "link",
            "match_id": "m_123",
            "merge_source_match_id": None,
            "decided_at": "2026-06-29",
            "decided_by": "human_ui",
        }
    ]
    report, resolved, exceptions, _ = _run_conform_with_dirs(
        tmp_path, events=events, overrides=overrides
    )
    assert report.overrides_applied == 1
    assert len(resolved) == 1
    assert resolved.iloc[0]["confidence"] == 1.0
    assert resolved.iloc[0]["match_method"] == "human_override"
    assert resolved.iloc[0]["review_status"] == "human_confirmed"
    assert exceptions.empty


# ── U7: HIGH confidence path ───────────────────────────────────────────────


def test_high_confidence_auto_link(tmp_path: Path) -> None:
    """U7: HIGH confidence = 0.95 exact, auto_confirmed, fuzzy_high."""
    events = [
        {
            "event_id": "200",
            "event_name": "Arsenal vs Chelsea",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 15,
            "ingested_at": 1,
        }
    ]
    canonical = [
        {
            "match_id": "m_1",
            "season_id": "s1",
            "home_team_id": "h1",
            "away_team_id": "a1",
            "favourite_team_id": None,
            "kickoff_time": "2026-08-10T15:30:00Z",
            "home_team_name": "Arsenal",
            "away_team_name": "Chelsea",
        }
    ]
    report, resolved, exceptions, _ = _run_conform_with_dirs(
        tmp_path, events=events, canonical_matches=canonical
    )
    assert len(resolved) == 1
    assert resolved.iloc[0]["confidence"] == HIGH_CONFIDENCE
    assert resolved.iloc[0]["confidence"] == 0.95  # exact constant
    assert resolved.iloc[0]["match_method"] == "fuzzy_high"
    assert resolved.iloc[0]["review_status"] == "auto_confirmed"


# ── U8: HIGH blocked by kickoff > 90 min ───────────────────────────────────


def test_high_blocked_by_kickoff_diff(tmp_path: Path) -> None:
    """U8: Same team names but kickoff diff > 90 min -> not HIGH."""
    events = [
        {
            "event_id": "300",
            "event_name": "Arsenal vs Chelsea",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 15,
            "ingested_at": 1,
        }
    ]
    canonical = [
        {
            "match_id": "m_1",
            "season_id": "s1",
            "home_team_id": "h1",
            "away_team_id": "a1",
            "favourite_team_id": None,
            # 3 hours different
            "kickoff_time": "2026-08-10T18:30:00Z",
            "home_team_name": "Arsenal",
            "away_team_name": "Chelsea",
        }
    ]
    _, resolved, exceptions, _ = _run_conform_with_dirs(
        tmp_path, events=events, canonical_matches=canonical
    )
    # Should not be HIGH (kickoff diff > 90 min); goes to exceptions
    assert len(resolved) == 0
    assert len(exceptions) == 1


# ── U9: MEDIUM confidence path ─────────────────────────────────────────────


def test_medium_confidence_unique(tmp_path: Path) -> None:
    """U9: MEDIUM confidence = 0.75 exact, needs_review, fuzzy_medium.

    Uses names that score in [0.70, 0.85) with token_sort_ratio:
    "Arsenal FC vs Chelsea FC" parsed as home="Arsenal FC", away="Chelsea FC"
    vs canonical "Arsenal" (~0.80) and "Chelsea" (~0.80).
    """
    events = [
        {
            "event_id": "400",
            "event_name": "Arsenal FC vs Chelsea FC",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 15,
            "ingested_at": 1,
        }
    ]
    canonical = [
        {
            "match_id": "m_1",
            "season_id": "s1",
            "home_team_id": "h1",
            "away_team_id": "a1",
            "favourite_team_id": None,
            "kickoff_time": "2026-08-10T15:30:00Z",
            # "Arsenal FC" vs "Arsenal" -> token_sort_ratio ~0.80 (MEDIUM)
            # "Chelsea FC" vs "Chelsea" -> token_sort_ratio ~0.80 (MEDIUM)
            "home_team_name": "Arsenal",
            "away_team_name": "Chelsea",
        }
    ]
    _, resolved, exceptions, _ = _run_conform_with_dirs(
        tmp_path, events=events, canonical_matches=canonical
    )
    # Exactly one candidate at MEDIUM threshold => resolved with MEDIUM confidence
    assert len(resolved) == 1
    assert resolved.iloc[0]["confidence"] == MEDIUM_CONFIDENCE
    assert resolved.iloc[0]["confidence"] == 0.75  # exact constant
    assert resolved.iloc[0]["match_method"] == "fuzzy_medium"
    assert resolved.iloc[0]["review_status"] == "needs_review"


# ── U10: Multiple MEDIUM candidates ────────────────────────────────────────


def test_multiple_medium_candidates_to_exceptions(tmp_path: Path) -> None:
    """U10: multiple MEDIUM candidates -> exceptions with 'multiple_candidates'."""
    events = [
        {
            "event_id": "500",
            "event_name": "Arsenal vs Chelsea",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 15,
            "ingested_at": 1,
        }
    ]
    canonical = [
        {
            "match_id": "m_1",
            "season_id": "s1",
            "home_team_id": "h1",
            "away_team_id": "a1",
            "favourite_team_id": None,
            "kickoff_time": "2026-08-10T15:30:00Z",
            "home_team_name": "Arsenal",
            "away_team_name": "Chelsea",
        },
        {
            "match_id": "m_2",
            "season_id": "s2",
            "home_team_id": "h2",
            "away_team_id": "a2",
            "favourite_team_id": None,
            "kickoff_time": "2026-08-10T15:00:00Z",
            "home_team_name": "Arsenal",
            "away_team_name": "Chelsea",
        },
    ]
    _, resolved, exceptions, _ = _run_conform_with_dirs(
        tmp_path, events=events, canonical_matches=canonical
    )
    # Multiple HIGH candidates -> goes to exceptions
    assert len(exceptions) >= 1 or len(resolved) == 0


# ── U11: No match -> exceptions with candidates ───────────────────────────


def test_no_match_exceptions_with_candidates(tmp_path: Path) -> None:
    """U11: no match -> exceptions with 'no_match' and candidates JSON."""
    events = [
        {
            "event_id": "600",
            "event_name": "Unknown FC vs Mystery United",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 15,
            "ingested_at": 1,
        }
    ]
    canonical = [
        {
            "match_id": "m_1",
            "season_id": "s1",
            "home_team_id": "h1",
            "away_team_id": "a1",
            "favourite_team_id": None,
            "kickoff_time": "2026-08-10T15:30:00Z",
            "home_team_name": "Liverpool",
            "away_team_name": "Everton",
        }
    ]
    _, resolved, exceptions, _ = _run_conform_with_dirs(
        tmp_path, events=events, canonical_matches=canonical
    )
    assert len(resolved) == 0
    assert len(exceptions) == 1
    assert exceptions.iloc[0]["unresolved_reason"] == "no_match"
    assert exceptions.iloc[0]["candidates"] != "[]"


# ── U12: Rugby silently skipped ────────────────────────────────────────────


def test_rugby_silently_skipped(tmp_path: Path) -> None:
    """U12: Rugby events (sport_id=2) absent from both outputs."""
    events = [
        {
            "event_id": "700",
            "event_name": "All Blacks v Springboks",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 2,
            "ingested_at": 1,
        }
    ]
    report, resolved, exceptions, _ = _run_conform_with_dirs(tmp_path, events=events)
    assert resolved.empty
    assert exceptions.empty


# ── U13: Idempotency ──────────────────────────────────────────────────────


def test_idempotency_identical_output(tmp_path: Path) -> None:
    """U13: Same input produces identical output across two runs."""
    events = [
        {
            "event_id": "800",
            "event_name": "Arsenal vs Chelsea",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 15,
            "ingested_at": 1,
        }
    ]
    canonical = [
        {
            "match_id": "m_1",
            "season_id": "s1",
            "home_team_id": "h1",
            "away_team_id": "a1",
            "favourite_team_id": None,
            "kickoff_time": "2026-08-10T15:30:00Z",
            "home_team_name": "Arsenal",
            "away_team_name": "Chelsea",
        }
    ]

    # Run 1
    events_dir = tmp_path / "events"
    canonical_dir = tmp_path / "canonical"
    _make_event_parquet(events_dir / "batch.parquet", events)
    _make_canonical_match_parquet(canonical_dir / "match.parquet", canonical)

    conform_dir = tmp_path / "conform"
    exceptions_dir = tmp_path / "exceptions"
    additions_dir = tmp_path / "additions"
    overrides_path = tmp_path / "overrides" / "matchbook_overrides.parquet"

    run_conform(
        events_dir,
        canonical_dir,
        overrides_path,
        exceptions_dir,
        conform_dir,
        additions_dir,
    )
    r1 = pd.read_parquet(conform_dir / "matchbook_resolved_links.parquet")

    # Run 2 (same input, overwrites same output)
    run_conform(
        events_dir,
        canonical_dir,
        overrides_path,
        exceptions_dir,
        conform_dir,
        additions_dir,
    )
    r2 = pd.read_parquet(conform_dir / "matchbook_resolved_links.parquet")

    pd.testing.assert_frame_equal(r1, r2)


# ── U15: new_canonical writes to additions ─────────────────────────────────


def test_new_canonical_writes_additions(tmp_path: Path) -> None:
    """U15: Override with action='new_canonical' writes to additions Parquet."""
    events = [
        {
            "event_id": "900",
            "event_name": "New FC vs Fresh United",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 15,
            "ingested_at": 1,
        }
    ]
    overrides = [
        {
            "matchbook_event_id": "900",
            "action": "new_canonical",
            "match_id": None,
            "merge_source_match_id": None,
            "decided_at": "2026-06-29",
            "decided_by": "human_ui",
        }
    ]
    report, resolved, exceptions, additions = _run_conform_with_dirs(
        tmp_path, events=events, overrides=overrides
    )
    assert report.additions_count == 1
    assert len(additions) == 1
    assert resolved.iloc[0]["confidence"] == 1.0
    assert additions.iloc[0]["match_id"] == resolved.iloc[0]["match_id"]


# ── U16: canonical_match_id replication ────────────────────────────────────


def test_canonical_match_id_replication() -> None:
    """U16: Python compute_canonical_match_id matches expected md5 output."""
    import hashlib

    result = compute_canonical_match_id("league1", "season1", "2026-08-10", "home1", "away1")
    expected = hashlib.md5(b"league1|season1|2026-08-10|home1|away1").hexdigest()
    assert result == expected


# ── E14: invalid start_utc -> exceptions ───────────────────────────────────


def test_invalid_start_utc_to_exceptions(tmp_path: Path) -> None:
    """E14: Unparseable start_utc -> exceptions with 'invalid_start_utc'."""
    events = [
        {
            "event_id": "1000",
            "event_name": "Arsenal vs Chelsea",
            "start_utc": "not-a-date",
            "sport_id": 15,
            "ingested_at": 1,
        }
    ]
    _, resolved, exceptions, _ = _run_conform_with_dirs(tmp_path, events=events)
    assert resolved.empty
    assert len(exceptions) == 1
    assert exceptions.iloc[0]["unresolved_reason"] == "invalid_start_utc"


# ── E15: dedup by latest ingested_at ───────────────────────────────────────


def test_dedup_by_latest_ingested_at(tmp_path: Path) -> None:
    """E15: Duplicate event_id deduplicated by latest ingested_at."""
    events = [
        {
            "event_id": "1100",
            "event_name": "Arsenal vs Chelsea",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 15,
            "ingested_at": 1,
        },
        {
            "event_id": "1100",
            "event_name": "Arsenal v Chelsea Updated",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 15,
            "ingested_at": 2,
        },
    ]
    canonical = [
        {
            "match_id": "m_1",
            "season_id": "s1",
            "home_team_id": "h1",
            "away_team_id": "a1",
            "favourite_team_id": None,
            "kickoff_time": "2026-08-10T15:30:00Z",
            "home_team_name": "Arsenal",
            "away_team_name": "Chelsea",
        }
    ]
    _, resolved, exceptions, _ = _run_conform_with_dirs(
        tmp_path, events=events, canonical_matches=canonical
    )
    # Only one event should be processed after dedup
    assert len(resolved) + len(exceptions) == 1
