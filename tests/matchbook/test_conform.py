"""Tests for the Matchbook conform engine (Spec 006)."""

from pathlib import Path

import pandas as pd

from data_platform.matchbook.conform import load_overrides, parse_event_name


# ── U1: parse normal event name ─────────────────────────────────────────────


def test_parse_event_name_normal() -> None:
    """U1: parse 'Arsenal v Chelsea' -> ('Arsenal', 'Chelsea')."""
    assert parse_event_name("Arsenal v Chelsea") == ("Arsenal", "Chelsea")


# ── U2: missing separator ───────────────────────────────────────────────────


def test_parse_event_name_no_separator() -> None:
    """U2: no ' v ' separator -> None."""
    assert parse_event_name("Rugby event") is None


def test_parse_event_name_wrong_separator() -> None:
    """Different separators don't match."""
    assert parse_event_name("Team A vs Team B") is None


# ── U3: first ' v ' split only ──────────────────────────────────────────────


def test_parse_event_name_multiple_v() -> None:
    """U3: 'Real Madrid v FC v Barcelona' splits on first ' v '."""
    assert parse_event_name("Real Madrid v FC v Barcelona") == (
        "Real Madrid",
        "FC v Barcelona",
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
