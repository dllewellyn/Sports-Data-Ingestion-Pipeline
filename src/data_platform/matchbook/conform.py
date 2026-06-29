"""Matchbook conform engine — fuzzy matching, override lookup, exceptions queue.

Pure-Python module (Dagster-free). The thin Dagster wrapper lives in
``assets/matchbook_conform.py``.
"""

from __future__ import annotations


def parse_event_name(event_name: str) -> tuple[str, str] | None:
    """Parse a Matchbook event name into (home, away) team names.

    Split on the FIRST occurrence of `` v `` (space-v-space). Returns None if
    no separator found or either part is empty after stripping.
    """
    if " v " not in event_name:
        return None
    parts = event_name.split(" v ", maxsplit=1)
    home = parts[0].strip()
    away = parts[1].strip()
    if not home or not away:
        return None
    return (home, away)
