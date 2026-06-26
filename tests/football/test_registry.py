"""S2 — the league registry is the single source of truth for discovery.

The registry contents are evidence-backed: enumerated live from football-data.co.uk
(11 `*m.php` main country pages; 16 `new/<CODE>.csv` extra leagues). The spec/plan
estimated "~19" extra leagues; the live site exposes 16 — see the module docstring.
"""

from data_platform.config import settings
from data_platform.football.registry import (
    EXTRA_LEAGUES,
    MAIN_LEAGUES,
    ExtraLeague,
    Family,
    MainLeague,
)


def test_main_registry_has_eleven_leagues() -> None:
    assert len(MAIN_LEAGUES) == 11
    assert all(isinstance(m, MainLeague) for m in MAIN_LEAGUES)
    # Every main league is reached through a `<country>m.php` landing page.
    assert all(m.landing_page.endswith("m.php") for m in MAIN_LEAGUES)
    assert all(m.family is Family.MAIN for m in MAIN_LEAGUES)
    names = [m.name for m in MAIN_LEAGUES]
    assert names == sorted(names), "registry must be deterministically ordered"
    assert len(set(names)) == len(names), "league names must be unique"


def test_extra_registry_has_sixteen_leagues() -> None:
    assert len(EXTRA_LEAGUES) == 16
    assert all(isinstance(e, ExtraLeague) for e in EXTRA_LEAGUES)
    # Extra landing pages are plain `<country>.php` (NOT the main `m.php` form).
    assert all(e.landing_page.endswith(".php") for e in EXTRA_LEAGUES)
    assert all(not e.landing_page.endswith("m.php") for e in EXTRA_LEAGUES)
    assert all(e.family is Family.EXTRA for e in EXTRA_LEAGUES)
    codes = [e.code for e in EXTRA_LEAGUES]
    assert all(c.isupper() for c in codes), "league codes are upper-case (new/<CODE>.csv)"
    assert len(set(codes)) == len(codes), "league codes must be unique"
    names = [e.name for e in EXTRA_LEAGUES]
    assert names == sorted(names), "registry must be deterministically ordered"


def test_known_anchor_entries_present() -> None:
    # Anchors proven by the investigation's downloaded samples.
    main_pages = {m.landing_page for m in MAIN_LEAGUES}
    assert "englandm.php" in main_pages
    assert "scotlandm.php" in main_pages
    extra_codes = {e.code for e in EXTRA_LEAGUES}
    assert {"ARG", "USA"} <= extra_codes


def test_config_exposes_football_settings() -> None:
    assert settings.football_base_url.startswith("https://")
    assert settings.football_throttle_seconds == 0.4
    # Bronze partitioning roots derive from bronze_dir.
    assert settings.football_main_dir == settings.bronze_dir / "football_main"
    assert settings.football_extra_dir == settings.bronze_dir / "football_extra"
