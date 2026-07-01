---
title: "Contract: Shared conform resolver (`src/data_platform/conform/resolve.py`)"
---

# Contract: Shared conform resolver (`src/data_platform/conform/resolve.py`)

The single provider-agnostic identity authority (FR-007). Every Python provider's conform and the ESPN
dbt path MUST compute identical ids for identical inputs (SC-003, E8, parity check).

## Pure functions (Python)

```python
def resolve_team_id(name: str, aliases: pd.DataFrame) -> str:
    """coalesce(seed.team_id, md5(lower(name))).
    aliases = team_aliases seed frame (columns: team_id, canonical_name, alias).
    Match `name` against `alias`; hit -> seed.team_id; miss -> md5(name.lower()).
    Mirrors int_team.sql:27 / int_match.sql:43-44 EXACTLY."""

def resolve_league_id(provider: str, provider_key: str, aliases: pd.DataFrame) -> str:
    """coalesce(league_aliases.league_id for (provider, provider_key),
                mint_provider_scoped(provider, provider_key)).
    Hit -> the ESPN-anchored md5(league_slug) recorded in the seed (de-dups onto ESPN).
    Miss -> deterministic provider-scoped id (E9 graceful degrade)."""

def mint_provider_scoped(provider: str, provider_key: str) -> str:
    """Deterministic provider-scoped league_id when no league_aliases mapping exists.
    md5(provider + '|' + provider_key). Stable across runs; never equals an ESPN id
    unless a seed row later maps the key. Replaces engine.py:224 md5('matchbook_football')."""

def derive_season_id(league_id: str, year: int) -> str:
    """md5(league_id || '|' || year). Mirrors int_season.sql:22 EXACTLY."""

def compute_canonical_match_id(
    league_id: str, season_id: str, date_str: str, home_team_id: str, away_team_id: str
) -> str:
    """md5(concat_ws('|', league_id, season_id, cast(date as varchar), home, away)).
    Mirrors macros/canonical_match_id.sql EXACTLY. Already present at engine.py:77-85 — moves here."""
```

## Invariants the parity check asserts (SC-003, E8)

- For any ESPN league_slug L: `resolve_league_id('espn', L, seed)` == `md5(L)` (seed records ESPN mapping).
- For any team name N present as a `team_aliases.alias`: `resolve_team_id(N, seed)` == the seed's team_id
  == what `int_team.sql` computes for that name.
- For any unseen name N: `resolve_team_id(N, seed)` == `md5(N.lower())` == `int_team.sql` unseen branch.
- For a fixture whose league is mapped in `league_aliases`, the Python `compute_canonical_match_id(...)`
  over resolved surrogates == the `int_match` macro output for the ESPN fixture (same `match_id`, SC-008).

## Blank-name guard (E5)

Before emitting a team/league addition row, the caller MUST reject an empty/blank resolved `name`; the
event is routed to the exceptions queue instead. `resolve.py` MAY expose a `is_mintable_name(name) -> bool`
helper; the provider body enforces it and routes to exceptions on `False`.
