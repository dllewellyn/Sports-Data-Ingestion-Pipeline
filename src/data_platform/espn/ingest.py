"""ESPN bronze ingest engine (Dagster-free), mirroring ``football/ingest.py``.

One league×season scoreboard → one bronze Parquet. The flow per unit is: fetch the
scoreboard JSON (always — the unit is overwritten with the latest scoreboard each
run) → flatten each event to a bronze row → row-level core validation (Pydantic,
skip-and-count invalid rows) → frame-level validation (Pandera, open contract) →
write **one** Parquet at a deterministic path, inside an OTel span. Failures are
**isolated per unit** (E1/E2): a fetch error, a zero-event window, a schema failure,
or any unexpected error is recorded and the run continues — and crucially **no
partial or empty Parquet is written** for a failed unit. The write is atomic (temp
file + rename), and writing to the same path **overwrites** the prior run's Parquet
(never appends), so a post-match re-fetch captures the richer payload (AC2).

This module is intentionally free of Dagster so it is unit-testable; the thin
``assets/espn.py`` wrapper supplies the resource, discovery, run date, and Dagster
metadata/run-status surfacing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
import pandera.pandas as pa
from pydantic import ValidationError

from ..config import settings
from ..models.schemas import EspnEventRecord
from ..otel import get_tracer
from .discovery import EspnUnit

# The mandatory flattened-event core enforced per row by Pydantic (schemas.py).
ESPN_CORE = [
    "espn_event_id",
    "kickoff_time",
    "home_team_id",
    "home_team_name",
    "away_team_id",
    "away_team_name",
    "status_name",
]


class EspnZeroEventsError(RuntimeError):
    """A scoreboard returned no events that pass core validation (E2)."""


class EspnSourceFetcher(Protocol):
    """The slice of the throttled client this engine needs (eases faking in tests)."""

    def get_json(self, url: str) -> dict: ...


@dataclass(frozen=True)
class UnitResult:
    unit: EspnUnit
    status: str  # "written" | "failed"
    out_path: Path | None = None
    raw_count: int = 0
    valid_count: int = 0
    reject_count: int = 0
    error: str | None = None


@dataclass
class IngestionReport:
    written: list[UnitResult] = field(default_factory=list)
    failed: list[UnitResult] = field(default_factory=list)

    @property
    def attempted(self) -> int:
        return len(self.written) + len(self.failed)


def espn_out_path(unit: EspnUnit) -> Path:
    """Deterministic bronze path for one unit: bronze/espn/<league>/<season>.parquet."""
    return settings.espn_bronze_dir / unit.league_slug / f"{unit.season_year}.parquet"


def _score_of(competitor: dict) -> str | None:
    """Competitor score as a string; ``None`` when absent/blank (E11: never fabricate)."""
    raw = competitor.get("score")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _competitor(competitors: list[dict], home_away: str) -> dict | None:
    for c in competitors:
        if c.get("homeAway") == home_away:
            return c
    return None


def flatten_events(scoreboard_json: dict) -> list[dict]:
    """Flatten a scoreboard payload to one bronze row per event.

    Events with no competition or a missing home/away competitor are dropped here
    (they cannot form a row); a row missing a CORE *field* is left for Pydantic to
    reject downstream. Scores ride along as strings, null when not present.

    The complete original event dict is preserved verbatim in ``raw_event`` (the
    whole ESPN event JSON, serialized deterministically) so bronze stays faithful
    to source: every field ESPN sent — venue, broadcasts, odds, leaders, stats,
    ``team.shortDisplayName``, ... — is recoverable later WITHOUT re-fetching.
    """
    rows: list[dict] = []
    for event in scoreboard_json.get("events", []):
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]
        competitors = competition.get("competitors") or []
        home = _competitor(competitors, "home")
        away = _competitor(competitors, "away")
        if home is None or away is None:
            continue

        status = (competition.get("status") or {}).get("type") or {}
        season = event.get("season") or {}
        home_team = home.get("team") or {}
        away_team = away.get("team") or {}

        rows.append(
            {
                "espn_event_id": event.get("id"),
                "kickoff_time": event.get("date"),
                "home_team_id": home_team.get("id"),
                "home_team_name": home_team.get("displayName"),
                "away_team_id": away_team.get("id"),
                "away_team_name": away_team.get("displayName"),
                "status_name": status.get("name"),
                # ride-along
                "league_slug": None,  # filled per-unit by ingest_unit
                "season_year": season.get("year"),
                "season_display": season.get("displayName"),
                "home_score": _score_of(home),
                "away_score": _score_of(away),
                "status_state": status.get("state"),
                "status_completed": status.get("completed"),
                # faithful bronze: the COMPLETE original event verbatim (no field
                # lost; recoverable by parsing this JSON without re-fetching)
                "raw_event": json.dumps(event, separators=(",", ":"), sort_keys=True),
            }
        )
    return rows


def validate_rows(rows: list[dict]) -> tuple[pd.DataFrame, int, int, int]:
    """Row-level core validation: keep rows passing the Pydantic core, count rejects.

    Invalid rows (missing/blank core field) are dropped — never raised out — so one
    bad event can't lose a whole unit. Returns (valid_frame, raw, valid, reject).
    """
    raw_count = len(rows)
    kept: list[dict] = []
    for row in rows:
        try:
            EspnEventRecord.model_validate(row)
            kept.append(row)
        except ValidationError:
            continue
    valid_df = pd.DataFrame(kept)
    return valid_df, raw_count, len(kept), raw_count - len(kept)


def ingest_unit(
    unit: EspnUnit,
    fetcher: EspnSourceFetcher,
    *,
    schema: pa.DataFrameSchema,
    out_path: Path,
) -> UnitResult:
    """Ingest one unit's scoreboard into one bronze Parquet (overwrite), or raise.

    Raises on any failure (fetch, zero-event, schema) *before* writing, so a failed
    unit never leaves a partial/empty Parquet behind. The write is atomic (temp file
    + rename) and replaces any prior Parquet at the same path (overwrite, not append).
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("ingest.espn") as span:
        span.set_attribute("source.url", unit.scoreboard_url)
        span.set_attribute("league.slug", unit.league_slug)
        span.set_attribute("season.year", unit.season_year)

        scoreboard = fetcher.get_json(unit.scoreboard_url)
        rows = flatten_events(scoreboard)
        for row in rows:
            row["league_slug"] = unit.league_slug

        valid_df, raw_count, valid_count, reject_count = validate_rows(rows)
        span.set_attribute("ingest.raw_rows", raw_count)
        span.set_attribute("ingest.valid_rows", valid_count)
        span.set_attribute("ingest.reject_rows", reject_count)

        if valid_count == 0:
            raise EspnZeroEventsError(f"{unit.scoreboard_url}: 0 valid events of {raw_count}")

        validated = schema.validate(valid_df)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_name(out_path.name + ".tmp")
        validated.to_parquet(tmp_path, index=False)
        tmp_path.replace(out_path)  # atomic + overwrite: no partial/stale Parquet
        span.set_attribute("output.path", str(out_path))
        span.set_attribute("output.rows", len(validated))

        return UnitResult(unit, "written", out_path, raw_count, valid_count, reject_count)


def ingest_units(
    units: list[EspnUnit],
    fetcher: EspnSourceFetcher,
    *,
    log: Any | None,
    schema: pa.DataFrameSchema,
) -> IngestionReport:
    """Ingest every discovered unit, isolating per-unit failures (E1/E2).

    Each unit lands a Parquet or fails — failures are logged and recorded but never
    abort the run, and never leave a partial/empty Parquet. The caller decides how to
    surface ``report.failed`` in the asset's run status (it re-raises at the end).
    """
    report = IngestionReport()
    for unit in units:
        out_path = espn_out_path(unit)
        try:
            result = ingest_unit(unit, fetcher, schema=schema, out_path=out_path)
        except Exception as exc:  # noqa: BLE001 — per-unit isolation is the design
            if log is not None:
                log.error("espn ingest failed for %s: %s", unit.scoreboard_url, exc)
            report.failed.append(UnitResult(unit, "failed", None, error=str(exc)))
            continue
        report.written.append(result)
    return report


__all__ = [
    "ESPN_CORE",
    "EspnZeroEventsError",
    "EspnSourceFetcher",
    "UnitResult",
    "IngestionReport",
    "espn_out_path",
    "flatten_events",
    "validate_rows",
    "ingest_unit",
    "ingest_units",
]
