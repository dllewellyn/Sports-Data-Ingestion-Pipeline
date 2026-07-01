"""The single provider-agnostic identity authority (FR-007).

Pure functions over an in-memory seed DataFrame — NO DuckLake, NO I/O, no
`duckdb.connect`. Every id formula mirrors its dbt source of truth byte-for-byte
so a Python provider's conform and the ESPN dbt path compute identical ids for
identical inputs (SC-003, E8):

  * resolve_team_id           -> int_team.sql:27   coalesce(s.team_id, md5(lower(name)))
  * derive_season_id          -> int_season.sql:22 md5(md5(slug) || '|' || year)
  * compute_canonical_match_id -> macros/canonical_match_id.sql concat_ws('|', ...)

`resolve_league_id` de-dups a mapped (provider, provider_key) onto the ESPN-anchored
league_id recorded in the `league_aliases` seed; an unmapped key gracefully mints a
deterministic provider-scoped id (E9).
"""

import hashlib

import pandas as pd


def resolve_team_id(name: str, aliases: pd.DataFrame) -> str:
    """Resolve a raw team name to its canonical `team_id`.

    Match `name` against the `alias` column of the `team_aliases` seed frame
    (columns: team_id, canonical_name, alias). Hit -> the seed's `team_id`; miss ->
    `md5(lower(name))`. Mirrors int_team.sql:27 (`coalesce(s.team_id, md5(lower(e.name)))`).
    """
    match = aliases.loc[aliases["alias"] == name, "team_id"]
    if not match.empty:
        return str(match.iloc[0])
    return hashlib.md5(name.lower().encode()).hexdigest()


def resolve_league_id(provider: str, provider_key: str, aliases: pd.DataFrame) -> str:
    """Resolve a (provider, provider_key) to its canonical `league_id`.

    Filter the `league_aliases` seed frame (columns: league_id, canonical_name,
    provider, provider_key). Hit -> the seed's `league_id` (the ESPN-anchored
    `md5(league_slug)`, so mapped keys de-dup onto ESPN); miss ->
    `mint_provider_scoped(provider, provider_key)` (E9 graceful degrade).
    """
    match = aliases.loc[
        (aliases["provider"] == provider) & (aliases["provider_key"] == provider_key),
        "league_id",
    ]
    if not match.empty:
        return str(match.iloc[0])
    return mint_provider_scoped(provider, provider_key)


def mint_provider_scoped(provider: str, provider_key: str) -> str:
    """Deterministic provider-scoped `league_id` when no `league_aliases` mapping exists.

    `md5(provider + '|' + provider_key)`. Stable across runs; never equals an ESPN id
    unless a seed row later maps the key.
    """
    return hashlib.md5(f"{provider}|{provider_key}".encode()).hexdigest()


def derive_season_id(league_id: str, year: int) -> str:
    """Derive a canonical `season_id` from an already-computed `league_id` and year.

    `md5(league_id || '|' || year)`. Mirrors int_season.sql:22
    (`md5(md5(league_slug) || '|' || cast(season_year as varchar))`) — the caller
    passes the already-computed `league_id` (which is `md5(league_slug)`).
    """
    return hashlib.md5(f"{league_id}|{year}".encode()).hexdigest()


def compute_canonical_match_id(
    league_id: str, season_id: str, date_str: str, home_team_id: str, away_team_id: str
) -> str:
    """Replicate the dbt canonical_match_id macro in Python.

    md5(concat_ws('|', league_id, season_id, date, home, away)).
    Mirrors macros/canonical_match_id.sql EXACTLY.
    """
    key = "|".join([league_id, season_id, date_str, home_team_id, away_team_id])
    return hashlib.md5(key.encode()).hexdigest()


def is_mintable_name(name: str) -> bool:
    """Blank-name guard (E5): reject empty/blank/whitespace names before minting.

    The caller routes an event to the exceptions queue when this returns False.
    """
    return bool(name and name.strip())
