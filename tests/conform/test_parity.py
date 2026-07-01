"""Python↔dbt parity guard for canonical match identity (T029, S11, U12, E2, SC-003).

The Python-side complement to the dbt singular test
`dbt/data_platform/tests/assert_resolver_provider_agnostic.sql`.

`data_platform.conform.resolve.compute_canonical_match_id` is a hand-written Python
replica of the dbt `canonical_match_id` macro
(`dbt/data_platform/macros/canonical_match_id.sql`):

    md5(concat_ws('|',
        cast(league  as varchar), cast(season as varchar),
        cast(cast(kickoff_date_utc as date) as varchar),
        cast(home as varchar), cast(away as varchar)))

If those two ever DRIFT — e.g. someone changes the resolver's join separator, the
component order, or the number of components — an ESPN fixture and a Matchbook
fixture for the same real-world game would stop resolving to the same `match_id`,
silently breaking cross-provider de-dup (FR-005, SC-003). This test fails in that
case.

Non-tautological by construction: the "macro side" of every equality is rebuilt
INDEPENDENTLY of `resolve.compute_canonical_match_id` — it re-implements the macro's
`concat_ws('|', cast(... as varchar))` + `md5` shape directly with `hashlib`. So the
assertion is `resolver_output == independently_reconstructed_macro_output`, not
`resolver_output == resolver_output`.

Concretely: changing `resolve.compute_canonical_match_id`'s `"|".join(...)` to
`"-".join(...)`, or reordering its components, makes `_macro_match_id` (below) and
`resolve.compute_canonical_match_id` diverge, turning this test RED.
"""

import hashlib

import pandas as pd

from data_platform.conform import resolve

# The Matchbook Premier League key that must be MAPPED onto the ESPN-anchored id.
MATCHBOOK_EPL_KEY = "15|Soccer-1234"
ESPN_EPL_SLUG = "eng.1"


def _md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def _macro_match_id(
    league_id: str, season_id: str, date_str: str, home_id: str, away_id: str
) -> str:
    """Rebuild the dbt `canonical_match_id` macro output INDEPENDENTLY of resolve.

    Mirrors the macro's shape:
        md5(concat_ws('|', cast(league as varchar), cast(season as varchar),
                       cast(cast(date as date) as varchar),
                       cast(home as varchar), cast(away as varchar)))

    All five inputs here are already varchar (the resolver's own output types), and
    `date_str` is already a canonical `YYYY-MM-DD` calendar date, so the cast-to-date
    is identity. `concat_ws('|', ...)` == `"|".join([...])` for non-null components.
    This deliberately does NOT call `resolve.compute_canonical_match_id`.
    """
    components = [
        str(league_id),
        str(season_id),
        str(date_str),
        str(home_id),
        str(away_id),
    ]
    return hashlib.md5("|".join(components).encode()).hexdigest()


def league_aliases() -> pd.DataFrame:
    """`league_aliases` seed frame mapping BOTH providers' EPL key onto md5('eng.1').

    Columns: league_id, canonical_name, provider, provider_key. Both the ESPN slug
    ('eng.1') and the Matchbook key ('15|Soccer-1234') record the SAME
    `league_id = md5('eng.1')`, so a mapped Matchbook key de-dups onto the
    ESPN-anchored league identity (SC-003, E2).
    """
    return pd.DataFrame(
        [
            {
                "league_id": _md5(ESPN_EPL_SLUG),
                "canonical_name": "English Premier League",
                "provider": "espn",
                "provider_key": ESPN_EPL_SLUG,
            },
            {
                "league_id": _md5(ESPN_EPL_SLUG),
                "canonical_name": "English Premier League",
                "provider": "matchbook",
                "provider_key": MATCHBOOK_EPL_KEY,
            },
        ]
    )


def team_aliases() -> pd.DataFrame:
    """`team_aliases` seed frame (columns: team_id, canonical_name, alias)."""
    return pd.DataFrame(
        [
            {"team_id": _md5("arsenal"), "canonical_name": "Arsenal", "alias": "Arsenal FC"},
            {"team_id": _md5("chelsea"), "canonical_name": "Chelsea", "alias": "Chelsea FC"},
        ]
    )


# --- U12 / E2 / SC-003: Python resolver stays in lock-step with the dbt macro ---


def test_mapped_matchbook_key_dedups_onto_espn_anchored_league_id():
    """A MAPPED Matchbook league key resolves to the ESPN-anchored league_id (SC-003)."""
    aliases = league_aliases()

    league_id = resolve.resolve_league_id("matchbook", MATCHBOOK_EPL_KEY, aliases)

    # The mapped key de-dups onto the ESPN-anchored id, NOT a provider-scoped mint.
    assert league_id == _md5(ESPN_EPL_SLUG) == "552ec47f642b6312ec1e7f09b6d25141"
    assert league_id != resolve.mint_provider_scoped("matchbook", MATCHBOOK_EPL_KEY)


def test_python_match_id_matches_independently_reconstructed_macro():
    """The resolver's match_id == the macro shape rebuilt independently (U12).

    Builds the canonical components the Python (resolve) way for a mapped Matchbook
    fixture, then asserts the resolver's `compute_canonical_match_id` equals the
    macro-shape id reconstructed WITHOUT calling that resolver function. Drift in the
    resolver's join separator / component order / component count turns this RED.
    """
    leagues = league_aliases()
    teams = team_aliases()

    # Resolve every canonical component the Python way.
    league_id = resolve.resolve_league_id("matchbook", MATCHBOOK_EPL_KEY, leagues)
    season_id = resolve.derive_season_id(league_id, 2025)
    home_id = resolve.resolve_team_id("Arsenal FC", teams)
    away_id = resolve.resolve_team_id("Chelsea FC", teams)
    date_str = "2025-08-16"

    match_id_py = resolve.compute_canonical_match_id(
        league_id, season_id, date_str, home_id, away_id
    )

    # Independent macro-shape reconstruction (concat_ws('|', ...) + md5).
    match_id_macro = _macro_match_id(league_id, season_id, date_str, home_id, away_id)

    assert match_id_py == match_id_macro


def test_espn_and_matchbook_same_fixture_yield_same_match_id():
    """E2: two providers resolving the SAME fixture compute the SAME match_id.

    ESPN slug 'eng.1' and Matchbook key '15|Soccer-1234' both map to md5('eng.1'),
    so with identical season/date/home/away they land on one canonical match_id.
    This is the cross-provider de-dup property (SC-003, FR-005).
    """
    leagues = league_aliases()
    teams = team_aliases()

    home_id = resolve.resolve_team_id("Arsenal FC", teams)
    away_id = resolve.resolve_team_id("Chelsea FC", teams)
    date_str = "2025-08-16"

    espn_league_id = resolve.resolve_league_id("espn", ESPN_EPL_SLUG, leagues)
    mb_league_id = resolve.resolve_league_id("matchbook", MATCHBOOK_EPL_KEY, leagues)
    assert espn_league_id == mb_league_id  # de-dup precondition

    espn_season_id = resolve.derive_season_id(espn_league_id, 2025)
    mb_season_id = resolve.derive_season_id(mb_league_id, 2025)

    espn_match_id = resolve.compute_canonical_match_id(
        espn_league_id, espn_season_id, date_str, home_id, away_id
    )
    mb_match_id = resolve.compute_canonical_match_id(
        mb_league_id, mb_season_id, date_str, home_id, away_id
    )

    assert espn_match_id == mb_match_id
