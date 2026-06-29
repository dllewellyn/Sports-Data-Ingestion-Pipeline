"""S3 — Matchbook events config fields and directory property (Spec 004 AC11, AC12)."""

from data_platform.config import Settings


def test_matchbook_username_field_exists() -> None:
    """Settings accepts matchbook_username (AC11)."""
    s = Settings(matchbook_username="myuser", matchbook_password="mypass")
    assert s.matchbook_username == "myuser"


def test_matchbook_password_field_exists() -> None:
    """Settings accepts matchbook_password (AC11)."""
    s = Settings(matchbook_username="u", matchbook_password="secret")
    assert s.matchbook_password == "secret"


def test_matchbook_username_defaults_empty() -> None:
    """matchbook_username defaults to '' so import never fails at startup."""
    s = Settings()
    assert s.matchbook_username == ""


def test_matchbook_password_defaults_empty() -> None:
    """matchbook_password defaults to '' so import never fails at startup."""
    s = Settings()
    assert s.matchbook_password == ""


def test_matchbook_throttle_seconds_field_exists() -> None:
    """matchbook_throttle_seconds field present, defaults to 0.0 (Q1)."""
    s = Settings()
    assert s.matchbook_throttle_seconds == 0.0


def test_matchbook_events_base_url_field_exists() -> None:
    """matchbook_events_base_url config field present with correct default (A9)."""
    s = Settings()
    assert s.matchbook_events_base_url == "https://api.matchbook.com"


def test_matchbook_events_bronze_dir_property() -> None:
    """matchbook_events_bronze_dir returns bronze_dir / 'matchbook_events' (AC12)."""
    s = Settings()
    assert s.matchbook_events_bronze_dir == s.bronze_dir / "matchbook_events"


def test_matchbook_events_bronze_dir_distinct_from_matchbook_bronze_dir() -> None:
    """matchbook_events_bronze_dir is distinct from matchbook_bronze_dir (AC12)."""
    s = Settings()
    assert s.matchbook_events_bronze_dir != s.matchbook_bronze_dir


def test_existing_matchbook_redis_fields_unchanged() -> None:
    """Existing Redis fields are unchanged (guard against regression)."""
    s = Settings()
    assert s.matchbook_redis_host == "redis"
    assert s.matchbook_redis_port == 6379


def test_matchbook_bronze_dir_still_returns_matchbook_odds() -> None:
    """matchbook_bronze_dir still returns bronze_dir / 'matchbook_odds' (not renamed)."""
    s = Settings()
    assert s.matchbook_bronze_dir == s.bronze_dir / "matchbook_odds"
