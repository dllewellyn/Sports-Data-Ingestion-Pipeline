"""S1 — the ESPN soccer league allowlist drives discovery (no pre-seeded id table).

The allowlist is a version-controlled in-repo constant (frozen dataclass, not
Pydantic — Pydantic is reserved for data crossing a boundary, see CLAUDE.md). It is
the single source of truth for which leagues discovery may query; nothing off-list
leaks through.
"""

from data_platform.config import settings
from data_platform.espn.registry import SOCCER_LEAGUES, EspnLeague


def test_allowlist_entries_are_typed_dataclass() -> None:
    assert len(SOCCER_LEAGUES) >= 3
    assert all(isinstance(league, EspnLeague) for league in SOCCER_LEAGUES)


def test_allowlist_is_deterministically_ordered_and_unique() -> None:
    slugs = [league.slug for league in SOCCER_LEAGUES]
    assert slugs == sorted(slugs), "allowlist must be deterministically ordered by slug"
    assert len(set(slugs)) == len(slugs), "league slugs must be unique"


def test_known_anchor_slugs_present() -> None:
    slugs = {league.slug for league in SOCCER_LEAGUES}
    assert {"eng.1", "esp.1", "uefa.champions"} <= slugs


def test_entries_carry_slug_and_display_name() -> None:
    by_slug = {league.slug: league for league in SOCCER_LEAGUES}
    assert by_slug["eng.1"].name
    assert all(league.slug and league.name for league in SOCCER_LEAGUES)


def test_nothing_off_list_leaks() -> None:
    # The allowlist is curated, not the full ESPN catalogue of 239 leagues.
    assert len(SOCCER_LEAGUES) < 239


def test_config_exposes_espn_settings() -> None:
    assert settings.espn_core_base_url.startswith("https://")
    assert settings.espn_site_base_url.startswith("https://")
    assert settings.espn_fetch_horizon_days == 30
    assert settings.espn_throttle_seconds == 0.1
    assert settings.espn_request_timeout == 30.0
    assert settings.espn_max_retries == 3
    assert settings.espn_user_agent
    assert settings.espn_bronze_dir == settings.bronze_dir / "espn"
