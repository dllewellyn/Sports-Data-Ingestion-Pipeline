"""One-off migration: extract ESPN event data from sports-gaming-engine PostgreSQL
and write it as bronze Parquet in the standard medallion structure.

Two sources, merged and de-duplicated:

1. ``bronze.espn_restored_summaries`` — 955 events with full game-summary payloads
   and proper league_id slugs.  These carry ``raw_event`` in the game-summary
   format (``payload.header`` section), tagged ``"_migration_source": "postgres"``.

2. ``bronze.provider_match_cache WHERE provider='espn'`` — supplementary events
   that are not in source 1 and have a proper league slug in ``competition_name``
   (skips the catch-all "all" bucket which has no usable league context).

Target path mirrors the live ingest: ``data/bronze/espn/<league_slug>/<season_year>.parquet``.
Groups are merged across sources, then one Parquet is written per (league_slug, season_year).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pandera.pandas as pa
import psycopg2
from pydantic import ValidationError

from ..models.schemas import EspnEventRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UnitResult:
    league_slug: str
    season_year: int
    status: str  # "written" | "skipped" | "failed"
    out_path: Path | None = None
    total_rows: int = 0
    valid_rows: int = 0
    failed_rows: int = 0
    error: str | None = None


@dataclass
class MigrationReport:
    written: list[UnitResult] = field(default_factory=list)
    skipped: list[UnitResult] = field(default_factory=list)
    failed: list[UnitResult] = field(default_factory=list)

    @property
    def total_failures(self) -> int:
        return sum(r.failed_rows for r in self.written + self.skipped) + len(self.failed)


def _season_year_from_kickoff(kickoff_utc) -> int:
    """Infer the ESPN season start year from a kickoff timestamp.

    ESPN seasons run roughly Aug–May, so Jan–Jul belong to the prior year's season.
    A July cutoff (matching football/season.py) gives the best approximation.
    """
    if kickoff_utc is None:
        return datetime.now(UTC).year
    month = kickoff_utc.month if hasattr(kickoff_utc, "month") else datetime.now(UTC).month
    year = kickoff_utc.year if hasattr(kickoff_utc, "year") else datetime.now(UTC).year
    return year if month >= 7 else year - 1


def _fetch_restored_summaries(conn) -> list[dict]:
    """Fetch all rows from bronze.espn_restored_summaries."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT match_id, league_id, payload, fetched_at
            FROM bronze.espn_restored_summaries
            ORDER BY league_id, (payload->'header'->'competitions'->0->>'date')
        """)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]


def _fetch_cache_events(conn) -> list[dict]:
    """Fetch ESPN events from provider_match_cache that have a real league slug.

    Excludes the "all" bucket — those events have no usable league context for
    partitioning into the bronze path structure.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT provider_id, sport, home_team_id, home_team_name,
                   away_team_id, away_team_name, competition_name,
                   kickoff_utc, status
            FROM bronze.provider_match_cache
            WHERE provider = 'espn'
              AND competition_name != 'all'
              AND competition_name != ''
        """)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]


def _row_from_summary(row: dict, *, ingested_at: str) -> dict | None:
    """Map a restored-summary row to a flattened EspnEventRecord dict."""
    payload = row.get("payload") or {}
    header = payload.get("header") or {}
    competitions = header.get("competitions") or []
    if not competitions:
        return None
    comp = competitions[0]
    competitors = comp.get("competitors") or []

    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if home is None or away is None:
        return None

    home_team = home.get("team") or {}
    away_team = away.get("team") or {}
    status = (comp.get("status") or {}).get("type") or {}
    season = header.get("season") or {}

    espn_event_id = str(header.get("id") or "")
    kickoff_time = str(comp.get("date") or "")
    home_team_id = str(home_team.get("id") or "")
    home_team_name = str(home_team.get("displayName") or "")
    away_team_id = str(away_team.get("id") or "")
    away_team_name = str(away_team.get("displayName") or "")
    status_name = str(status.get("name") or "")

    # Add migration provenance into the payload before storing as raw_event.
    payload["_migration_source"] = "postgres"
    payload["_migration_table"] = "bronze.espn_restored_summaries"

    return {
        "espn_event_id": espn_event_id,
        "kickoff_time": kickoff_time,
        "home_team_id": home_team_id,
        "home_team_name": home_team_name,
        "away_team_id": away_team_id,
        "away_team_name": away_team_name,
        "status_name": status_name,
        # ride-along (open schema, strict=False)
        "league_slug": row.get("league_id") or "",
        "season_year": season.get("year"),
        "home_score": str(home.get("score") or "").strip() or None,
        "away_score": str(away.get("score") or "").strip() or None,
        "status_state": status.get("state"),
        "status_completed": status.get("completed"),
        "ingested_at": ingested_at,
        "raw_event": json.dumps(payload, separators=(",", ":"), sort_keys=True),
    }


def _row_from_cache(row: dict, *, ingested_at: str) -> dict | None:
    """Map a provider_match_cache row to a flattened EspnEventRecord dict."""
    kickoff = row.get("kickoff_utc")
    kickoff_str = kickoff.isoformat() if kickoff else ""

    raw = {
        "id": row.get("provider_id") or "",
        "status": {"type": {"name": row.get("status") or ""}},
        "date": kickoff_str,
        "competitors": [
            {
                "homeAway": "home",
                "team": {
                    "id": row.get("home_team_id") or "",
                    "displayName": row.get("home_team_name") or "",
                },
            },
            {
                "homeAway": "away",
                "team": {
                    "id": row.get("away_team_id") or "",
                    "displayName": row.get("away_team_name") or "",
                },
            },
        ],
        "_migration_source": "postgres",
        "_migration_table": "bronze.provider_match_cache",
        "_sport": row.get("sport") or "",
        "_competition": row.get("competition_name") or "",
    }

    return {
        "espn_event_id": str(row.get("provider_id") or ""),
        "kickoff_time": kickoff_str,
        "home_team_id": str(row.get("home_team_id") or ""),
        "home_team_name": str(row.get("home_team_name") or ""),
        "away_team_id": str(row.get("away_team_id") or ""),
        "away_team_name": str(row.get("away_team_name") or ""),
        "status_name": str(row.get("status") or ""),
        "league_slug": str(row.get("competition_name") or ""),
        "season_year": _season_year_from_kickoff(kickoff),
        "ingested_at": ingested_at,
        "raw_event": json.dumps(raw, separators=(",", ":"), sort_keys=True),
    }


def run_espn_postgres_migration(
    postgres_url: str,
    *,
    out_dir: Path,
    log: Any | None,
    schema: pa.DataFrameSchema,
) -> MigrationReport:
    """Extract ESPN events from PostgreSQL and write bronze Parquet files.

    Merges espn_restored_summaries (rich) with provider_match_cache (supplementary),
    de-duplicates by espn_event_id, groups by (league_slug, season_year), and writes
    one Parquet per group at ``out_dir/<league_slug>/<season_year>.parquet``.
    """
    ingested_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = psycopg2.connect(postgres_url)
    try:
        summary_rows = _fetch_restored_summaries(conn)
        cache_rows = _fetch_cache_events(conn)
    finally:
        conn.close()

    if log:
        log.info(
            "espn postgres migration: fetched %d restored summaries, %d cache events",
            len(summary_rows),
            len(cache_rows),
        )

    # Build flat rows; restored summaries take priority over cache for same event_id.
    flat: dict[str, dict] = {}  # event_id → flat row

    for row in summary_rows:
        flat_row = _row_from_summary(row, ingested_at=ingested_at)
        if flat_row is None:
            continue
        flat[flat_row["espn_event_id"]] = flat_row

    for row in cache_rows:
        flat_row = _row_from_cache(row, ingested_at=ingested_at)
        if flat_row is None:
            continue
        eid = flat_row["espn_event_id"]
        if eid not in flat:
            flat[eid] = flat_row

    if log:
        log.info("espn postgres migration: %d unique events after merge", len(flat))

    # Group by (league_slug, season_year).
    groups: dict[tuple[str, int], list[dict]] = {}
    for flat_row in flat.values():
        league = flat_row.get("league_slug") or "unknown"
        season = flat_row.get("season_year") or _season_year_from_kickoff(None)
        groups.setdefault((league, season), []).append(flat_row)

    report = MigrationReport()

    for (league_slug, season_year), group_rows in sorted(groups.items()):
        try:
            event_rows: list[dict] = []
            failed = 0
            for flat_row in group_rows:
                try:
                    EspnEventRecord.model_validate(flat_row)
                    event_rows.append(flat_row)
                except ValidationError as exc:
                    failed += 1
                    if log:
                        log.warning(
                            "espn migration: skipping invalid event_id=%s (%s/%s): %s",
                            flat_row.get("espn_event_id"),
                            league_slug,
                            season_year,
                            exc,
                        )

            if not event_rows:
                report.skipped.append(
                    UnitResult(
                        league_slug,
                        season_year,
                        "skipped",
                        total_rows=len(group_rows),
                        failed_rows=failed,
                    )
                )
                continue

            df = pd.DataFrame(event_rows)
            schema.validate(df)

            out_path = out_dir / league_slug / f"{season_year}.parquet"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = out_path.with_suffix(".tmp")
            df.to_parquet(tmp, index=False)
            tmp.replace(out_path)

            if log:
                log.info(
                    "espn migration: wrote %d rows → %s (skipped %d)",
                    len(df),
                    out_path,
                    failed,
                )

            report.written.append(
                UnitResult(
                    league_slug,
                    season_year,
                    "written",
                    out_path=out_path,
                    total_rows=len(group_rows),
                    valid_rows=len(event_rows),
                    failed_rows=failed,
                )
            )

        except Exception as exc:  # noqa: BLE001
            if log:
                log.error("espn migration: failed for %s/%s: %s", league_slug, season_year, exc)
            report.failed.append(UnitResult(league_slug, season_year, "failed", error=str(exc)))

    return report


__all__ = [
    "UnitResult",
    "MigrationReport",
    "run_espn_postgres_migration",
]
