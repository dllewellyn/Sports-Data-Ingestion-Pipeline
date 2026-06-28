"""Curated ESPN soccer league allowlist — the discovery registry (S1).

This is a version-controlled, in-repo **constant**, not data entering the system,
so it is modelled with a frozen dataclass rather than Pydantic (which this codebase
reserves for validating data crossing a boundary — see CLAUDE.md). It is the single
source of truth for which leagues discovery may query; discovery holds no
hard-coded league slugs of its own and there is no pre-seeded id table.

Each entry is an ESPN soccer ``slug`` (e.g. ``eng.1``) plus a display ``name``.
ESPN exposes ~239 soccer leagues; this list is a deliberately curated subset of
top-flight European competitions, not the full catalogue. The tuple is ordered by
slug for deterministic discovery output.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EspnLeague:
    """An allowlisted ESPN soccer league: an API slug plus a display name."""

    slug: str  # ESPN soccer league slug, e.g. "eng.1"
    name: str  # human-readable display name, e.g. "English Premier League"


# Curated top-flight European competitions. Ordered by slug for deterministic
# discovery output.
SOCCER_LEAGUES: tuple[EspnLeague, ...] = (
    EspnLeague("eng.1", "English Premier League"),
    EspnLeague("esp.1", "Spanish La Liga"),
    EspnLeague("fra.1", "French Ligue 1"),
    EspnLeague("ger.1", "German Bundesliga"),
    EspnLeague("ita.1", "Italian Serie A"),
    EspnLeague("ned.1", "Dutch Eredivisie"),
    EspnLeague("por.1", "Portuguese Primeira Liga"),
    EspnLeague("uefa.champions", "UEFA Champions League"),
    EspnLeague("uefa.europa", "UEFA Europa League"),
)

__all__ = [
    "EspnLeague",
    "SOCCER_LEAGUES",
]
