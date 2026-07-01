"""T017: the Matchbook mint path resolves the FULL season→league→team chain.

Spec 011 / US1 / FR-001/FR-002/FR-003/FR-012/FR-013/FR-016 (E1/E5/E9/E10).

Minting a match must resolve its whole chain through the shared resolver + seeds
and emit FOUR additions frames (match/team/league/season), each Pandera-validated,
with the bogus ``md5('matchbook_football')`` league id gone. Seeded chain members
reuse their seed id and are NOT re-emitted when already canonical. A blank parsed
team name routes to exceptions and emits NO addition (E5). A mapped provider_key
de-dups onto the ESPN league id (E9); an unmapped one mints provider-scoped.
"""

import hashlib
import json

import pandas as pd
import pytest

from data_platform.conform import resolve
from data_platform.conform.matchbook import (
    _mint_canonical_chain,
    league_additions_schema,
    team_additions_schema,
)


def _md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def _event(event_name: str, *, category_id: str = "Soccer-1234", sport_id: int = 15) -> pd.Series:
    """Build an event Series shaped like a deduped bronze row."""
    raw_event = {"category-id": category_id}
    return pd.Series(
        {
            "event_id": "evt",
            "event_name": event_name,
            "sport_id": sport_id,
            "start_utc": "2026-08-10T15:00:00Z",
            "raw_event": json.dumps(raw_event),
        }
    )


def _team_aliases() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"team_id": _md5("arsenal"), "canonical_name": "Arsenal", "alias": "Arsenal FC"},
        ]
    )


def _league_aliases() -> pd.DataFrame:
    """Matchbook Premier League mapped to the ESPN-anchored md5('eng.1')."""
    return pd.DataFrame(
        [
            {
                "league_id": _md5("eng.1"),
                "canonical_name": "Premier League",
                "provider": "matchbook",
                "provider_key": "15|Soccer-1234",
            }
        ]
    )


# ── U6: full chain — unseen team + unmapped league emits all four members ────


def test_full_chain_unseen_team_unmapped_league_emits_four() -> None:
    """U6: unseen teams + unmapped provider_key emit team/season/league/match adds."""
    event = _event("Foo Town vs Bar City", category_id="Soccer-9999")
    match_id, result = _mint_canonical_chain(
        event_name="Foo Town vs Bar City",
        event=event,
        team_aliases_df=_team_aliases(),
        league_aliases_df=_league_aliases(),
        existing_league_ids=set(),
        existing_season_ids=set(),
        existing_team_ids=set(),
    )

    assert result.exception is None
    provider_key = "15|Soccer-9999"
    league_id = resolve.mint_provider_scoped("matchbook", provider_key)
    season_id = resolve.derive_season_id(league_id, 2026)
    home_id = _md5("foo town")
    away_id = _md5("bar city")

    # team additions: one per team, id == md5(lower(name))
    team_ids = {t["team_id"] for t in result.team_additions}
    assert team_ids == {home_id, away_id}

    # season addition with derived id
    assert len(result.season_additions) == 1
    assert result.season_additions[0]["season_id"] == season_id
    assert result.season_additions[0]["league_id"] == league_id

    # league addition with provider-scoped id (unmapped)
    assert len(result.league_additions) == 1
    assert result.league_additions[0]["league_id"] == league_id

    # match addition present with the computed canonical match id
    assert result.match_addition is not None
    assert result.match_addition["match_id"] == match_id
    assert match_id == resolve.compute_canonical_match_id(
        league_id, season_id, "2026-08-10", home_id, away_id
    )


# ── E1: seeded team reuses the seed id and is NOT re-emitted when canonical ──


def test_seeded_team_reuses_seed_id_and_not_re_emitted() -> None:
    """E1: an aliased team resolves to the SEED team_id; skipped if already canonical."""
    event = _event("Arsenal FC vs Bar City", category_id="Soccer-9999")
    seed_team_id = _md5("arsenal")
    match_id, result = _mint_canonical_chain(
        event_name="Arsenal FC vs Bar City",
        event=event,
        team_aliases_df=_team_aliases(),
        league_aliases_df=_league_aliases(),
        existing_league_ids=set(),
        existing_season_ids=set(),
        existing_team_ids={seed_team_id},  # Arsenal already canonical
    )
    emitted_ids = {t["team_id"] for t in result.team_additions}
    # Arsenal resolves to the seed id and is already canonical => not re-emitted
    assert seed_team_id not in emitted_ids
    # Bar City is unseen => emitted
    assert _md5("bar city") in emitted_ids
    # the match still references the seed team id
    assert result.match_addition["home_team_id"] == seed_team_id


# ── U2/E9: mapped provider_key de-dups onto the ESPN league id ───────────────


def test_mapped_league_dedups_onto_espn_id() -> None:
    """E9: mapped provider_key '15|Soccer-1234' => league_id == md5('eng.1')."""
    event = _event("Foo Town vs Bar City", category_id="Soccer-1234")
    _, result = _mint_canonical_chain(
        event_name="Foo Town vs Bar City",
        event=event,
        team_aliases_df=_team_aliases(),
        league_aliases_df=_league_aliases(),
        existing_league_ids=set(),
        existing_season_ids=set(),
        existing_team_ids=set(),
    )
    assert len(result.league_additions) == 1
    assert result.league_additions[0]["league_id"] == "552ec47f642b6312ec1e7f09b6d25141"
    assert result.league_additions[0]["league_id"] == _md5("eng.1")


def test_unmapped_league_mints_provider_scoped() -> None:
    """E9 degrade: unmapped provider_key mints a provider-scoped league id."""
    event = _event("Foo Town vs Bar City", category_id="Soccer-0000")
    _, result = _mint_canonical_chain(
        event_name="Foo Town vs Bar City",
        event=event,
        team_aliases_df=_team_aliases(),
        league_aliases_df=_league_aliases(),
        existing_league_ids=set(),
        existing_season_ids=set(),
        existing_team_ids=set(),
    )
    provider_scoped = resolve.mint_provider_scoped("matchbook", "15|Soccer-0000")
    assert result.league_additions[0]["league_id"] == provider_scoped
    assert result.league_additions[0]["league_id"] != _md5("matchbook_football")


# ── E5: blank parsed team name routes to exceptions, emits NO addition ───────


def test_blank_team_name_routes_to_exception_no_addition() -> None:
    """E5: an unparseable/blank name yields an exception outcome and no additions."""
    event = _event("Just One Team")  # no ' vs ' -> unparseable
    match_id, result = _mint_canonical_chain(
        event_name="Just One Team",
        event=event,
        team_aliases_df=_team_aliases(),
        league_aliases_df=_league_aliases(),
        existing_league_ids=set(),
        existing_season_ids=set(),
        existing_team_ids=set(),
    )
    assert match_id is None
    assert result.exception is not None
    assert result.exception["unresolved_reason"] == "blank_team_name"
    assert result.match_addition is None
    assert result.team_additions == []
    assert result.league_additions == []
    assert result.season_additions == []


# ── U6: Pandera rejects a malformed additions frame (blank name) ─────────────


def test_team_additions_schema_rejects_blank_name() -> None:
    """A team-addition with a blank/null name must be REJECTED by Pandera."""
    import pandera.errors as pa_errors

    bad = pd.DataFrame([{"team_id": "x", "name": "", "similar_names": ["x"]}])
    with pytest.raises(pa_errors.SchemaError):
        team_additions_schema.validate(bad)

    bad_null = pd.DataFrame([{"team_id": "x", "name": None, "similar_names": ["x"]}])
    with pytest.raises(pa_errors.SchemaError):
        team_additions_schema.validate(bad_null)


def test_league_additions_schema_rejects_blank_name() -> None:
    """A league-addition with a blank name must be REJECTED by Pandera."""
    import pandera.errors as pa_errors

    bad = pd.DataFrame([{"league_id": "x", "name": "", "is_tournament": False}])
    with pytest.raises(pa_errors.SchemaError):
        league_additions_schema.validate(bad)


# ── Idempotency: minting twice yields identical ids ──────────────────────────


def test_mint_chain_idempotent() -> None:
    """Minting the same event twice yields identical ids (deterministic)."""
    event = _event("Foo Town vs Bar City", category_id="Soccer-9999")
    m1, r1 = _mint_canonical_chain(
        event_name="Foo Town vs Bar City",
        event=event,
        team_aliases_df=_team_aliases(),
        league_aliases_df=_league_aliases(),
        existing_league_ids=set(),
        existing_season_ids=set(),
        existing_team_ids=set(),
    )
    m2, r2 = _mint_canonical_chain(
        event_name="Foo Town vs Bar City",
        event=event,
        team_aliases_df=_team_aliases(),
        league_aliases_df=_league_aliases(),
        existing_league_ids=set(),
        existing_season_ids=set(),
        existing_team_ids=set(),
    )
    assert m1 == m2
    assert r1.match_addition == r2.match_addition
    assert r1.league_additions == r2.league_additions
    assert r1.season_additions == r2.season_additions
    assert sorted(t["team_id"] for t in r1.team_additions) == sorted(
        t["team_id"] for t in r2.team_additions
    )
