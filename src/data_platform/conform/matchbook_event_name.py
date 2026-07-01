"""Event name parsing for the Matchbook conform engine."""

from __future__ import annotations


def parse_event_name(event_name: str) -> tuple[str, str] | None:
    """Parse a Matchbook event name into (home, away) team names.

    Split on `` vs `` (the Matchbook separator). Returns None if
    no separator found or either part is empty after stripping.
    """
    if " vs " not in event_name:
        return None
    parts = event_name.split(" vs ", maxsplit=1)
    home = parts[0].strip()
    away = parts[1].strip()
    if not home or not away:
        return None
    return (home, away)
