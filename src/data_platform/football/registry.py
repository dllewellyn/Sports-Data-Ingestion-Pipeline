"""Hard-coded football-data.co.uk league whitelist — the discovery registry (D6).

This is a version-controlled, in-repo **constant**, not data entering the system,
so it is modelled with frozen dataclasses rather than Pydantic (which this codebase
reserves for validating data crossing a boundary — see CLAUDE.md). It is the single
source of truth for which leagues discovery may emit; `discovery.py` holds no
hard-coded URLs of its own.

Two dataset families (D5), each reached through a country landing page:

* **main** — `<country>m.php` → ``mmz4281/<season>/<div>.csv`` (latin-1; one
  season×division per file; season carried in the URL path).
* **extra** — `<country>.php` → ``new/<CODE>.csv`` (utf-8-sig; all seasons packed
  into one file; season carried in-file).

Contents are evidence-backed: enumerated live from football-data.co.uk on
2026-06-26 (11 main `*m.php` pages; 16 extra `new/<CODE>.csv` leagues). The spec
and plan estimated "~19" extra leagues; the live site exposes **16** — this
registry reflects the real list, not the estimate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Family(StrEnum):
    """Which ingestion track + encoding a discovered file belongs to."""

    MAIN = "main"
    EXTRA = "extra"


@dataclass(frozen=True, slots=True)
class MainLeague:
    """A main-family league: discovered via its `<country>m.php` landing page."""

    name: str  # e.g. "england" — the football_main/<league> partition segment
    landing_page: str  # e.g. "englandm.php"
    family: Family = Family.MAIN


@dataclass(frozen=True, slots=True)
class ExtraLeague:
    """An extra-family league: one `new/<CODE>.csv` file holding all seasons."""

    name: str  # e.g. "argentina"
    landing_page: str  # e.g. "argentina.php"
    code: str  # e.g. "ARG" — the <CODE> in new/<CODE>.csv and the partition key
    family: Family = Family.EXTRA


# 11 main leagues (England 153, Scotland 122, Germany 66, France 63, Spain 63,
# Italy 62, Netherlands 33, Greece 32, Portugal 32, Turkey 32, Belgium 31 files).
# Ordered by name for deterministic discovery output.
MAIN_LEAGUES: tuple[MainLeague, ...] = (
    MainLeague("belgium", "belgiumm.php"),
    MainLeague("england", "englandm.php"),
    MainLeague("france", "francem.php"),
    MainLeague("germany", "germanym.php"),
    MainLeague("greece", "greecem.php"),
    MainLeague("italy", "italym.php"),
    MainLeague("netherlands", "netherlandsm.php"),
    MainLeague("portugal", "portugalm.php"),
    MainLeague("scotland", "scotlandm.php"),
    MainLeague("spain", "spainm.php"),
    MainLeague("turkey", "turkeym.php"),
)

# 16 extra leagues. Ordered by name for deterministic discovery output.
EXTRA_LEAGUES: tuple[ExtraLeague, ...] = (
    ExtraLeague("argentina", "argentina.php", "ARG"),
    ExtraLeague("austria", "austria.php", "AUT"),
    ExtraLeague("brazil", "brazil.php", "BRA"),
    ExtraLeague("china", "china.php", "CHN"),
    ExtraLeague("denmark", "denmark.php", "DNK"),
    ExtraLeague("finland", "finland.php", "FIN"),
    ExtraLeague("ireland", "ireland.php", "IRL"),
    ExtraLeague("japan", "japan.php", "JPN"),
    ExtraLeague("mexico", "mexico.php", "MEX"),
    ExtraLeague("norway", "norway.php", "NOR"),
    ExtraLeague("poland", "poland.php", "POL"),
    ExtraLeague("romania", "romania.php", "ROU"),
    ExtraLeague("russia", "russia.php", "RUS"),
    ExtraLeague("sweden", "sweden.php", "SWE"),
    ExtraLeague("switzerland", "switzerland.php", "SWZ"),
    ExtraLeague("usa", "usa.php", "USA"),
)

__all__ = [
    "Family",
    "MainLeague",
    "ExtraLeague",
    "MAIN_LEAGUES",
    "EXTRA_LEAGUES",
]
