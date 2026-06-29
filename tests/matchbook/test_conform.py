"""Tests for the Matchbook conform engine (Spec 006)."""

from data_platform.matchbook.conform import parse_event_name


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
