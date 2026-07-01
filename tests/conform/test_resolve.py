"""Unit tests for the provider-agnostic identity authority (conform/resolve.py).

Every id formula here is asserted byte-identical to its dbt source of truth so a
Python provider's conform and the ESPN dbt path compute the same ids (SC-003, E8):
  * resolve_team_id     -> int_team.sql:27   coalesce(s.team_id, md5(lower(name)))
  * derive_season_id    -> int_season.sql:22 md5(md5(slug) || '|' || year)
  * compute_canonical_match_id -> macros/canonical_match_id.sql concat_ws('|', ...)
"""

import hashlib

import pandas as pd

from data_platform.conform import resolve


def _md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def team_aliases() -> pd.DataFrame:
    """Small in-memory team_aliases seed (columns: team_id, canonical_name, alias)."""
    return pd.DataFrame(
        [
            {
                "team_id": _md5("arsenal"),
                "canonical_name": "Arsenal",
                "alias": "Arsenal FC",
            },
            {
                "team_id": _md5("arsenal"),
                "canonical_name": "Arsenal",
                "alias": "The Gunners",
            },
        ]
    )


def league_aliases() -> pd.DataFrame:
    """Small in-memory league_aliases seed.

    The ESPN row records league_id = md5('eng.1') so mapped keys de-dup onto ESPN.
    """
    return pd.DataFrame(
        [
            {
                "league_id": _md5("eng.1"),
                "canonical_name": "English Premier League",
                "provider": "espn",
                "provider_key": "eng.1",
            }
        ]
    )


# --- U1: resolve_team_id ---------------------------------------------------


def test_resolve_team_id_seeded_alias_returns_seed_team_id():
    aliases = team_aliases()
    assert resolve.resolve_team_id("Arsenal FC", aliases) == _md5("arsenal")


def test_resolve_team_id_unseen_name_mints_md5_lower():
    aliases = team_aliases()
    assert resolve.resolve_team_id("Newcastle United", aliases) == _md5("newcastle united")


# --- U2: resolve_league_id -------------------------------------------------


def test_resolve_league_id_mapped_key_returns_seed_league_id():
    aliases = league_aliases()
    resolved = resolve.resolve_league_id("espn", "eng.1", aliases)
    assert resolved == aliases.loc[0, "league_id"]
    assert resolved == _md5("eng.1")


def test_resolve_league_id_unmapped_key_mints_provider_scoped():
    aliases = league_aliases()
    resolved = resolve.resolve_league_id("matchbook", "football", aliases)
    assert resolved == resolve.mint_provider_scoped("matchbook", "football")
    # Provider-scoped id must NOT collide with the naive md5('matchbook_football')
    # the old engine.py used.
    assert resolved != _md5("matchbook_football")


# --- mint_provider_scoped --------------------------------------------------


def test_mint_provider_scoped_matches_pipe_formula_and_is_deterministic():
    assert resolve.mint_provider_scoped("matchbook", "football") == _md5("matchbook|football")
    assert resolve.mint_provider_scoped("matchbook", "football") == resolve.mint_provider_scoped(
        "matchbook", "football"
    )


# --- U3: derive_season_id --------------------------------------------------


def test_derive_season_id_matches_int_season_formula():
    league_id = _md5("eng.1")  # already-computed league_id (md5 of the slug)
    year = 2025
    # int_season.sql:22  md5(md5(league_slug) || '|' || cast(season_year as varchar))
    # -> here league_id IS md5(league_slug); so md5(league_id || '|' || '2025').
    assert resolve.derive_season_id(league_id, year) == _md5(f"{league_id}|{year}")
    assert (
        resolve.derive_season_id(league_id, year)
        == hashlib.md5((league_id + "|" + str(year)).encode()).hexdigest()
    )


# --- U4: compute_canonical_match_id ---------------------------------------


def test_compute_canonical_match_id_matches_macro_shape():
    league_id = _md5("eng.1")
    season_id = _md5(f"{league_id}|2025")
    date_str = "2025-08-16"
    home = _md5("arsenal")
    away = _md5("chelsea")
    key = "|".join([league_id, season_id, date_str, home, away])
    assert (
        resolve.compute_canonical_match_id(league_id, season_id, date_str, home, away)
        == hashlib.md5(key.encode()).hexdigest()
    )


# --- E5: is_mintable_name guard -------------------------------------------


def test_is_mintable_name_rejects_blank_and_accepts_real_name():
    assert resolve.is_mintable_name("Arsenal") is True
    assert resolve.is_mintable_name("") is False
    assert resolve.is_mintable_name("   ") is False
    assert resolve.is_mintable_name("\t\n") is False
