"""One-off migration: extract Matchbook event data from sports-gaming-engine
PostgreSQL and write it as bronze Parquet in the standard medallion structure.

Source: bronze.provider_match_cache WHERE provider = 'matchbook'
Target: data/bronze/matchbook_events/<sport>/<run_date>/migration_<batch_ts>.parquet

Rows with unmapped sport or missing kickoff_utc are skipped-and-counted.
The raw_event column carries a synthetic JSON (not the original API payload)
tagged with ``"_migration_source": "postgres"`` so downstream can distinguish
migrated rows from live-ingest rows.
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

from ..models.schemas import MatchbookEventRecord

logger = logging.getLogger(__name__)

# Maps the sport string in provider_match_cache to the Matchbook API sport_id.
# Sports not in this map are skipped (unknown sport_id → fails Pydantic validation).
SPORT_ID_MAP: dict[str, int] = {
    "football": 15,
    "rugby_union": 2,
}


@dataclass(frozen=True)
class SportResult:
    sport_name: str
    status: str  # "written" | "skipped" | "failed"
    out_path: Path | None = None
    total_rows: int = 0
    valid_rows: int = 0
    failed_rows: int = 0
    error: str | None = None


@dataclass
class MigrationReport:
    written: list[SportResult] = field(default_factory=list)
    skipped: list[SportResult] = field(default_factory=list)
    failed: list[SportResult] = field(default_factory=list)

    @property
    def total_failures(self) -> int:
        return sum(r.failed_rows for r in self.written + self.skipped) + len(self.failed)


def _fetch_matchbook_rows(postgres_url: str) -> list[dict]:
    """Query bronze.provider_match_cache for all Matchbook events."""
    conn = psycopg2.connect(postgres_url)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    provider_id,
                    sport,
                    home_team_name,
                    away_team_name,
                    competition_name,
                    kickoff_utc,
                    status,
                    total_liquidity
                FROM bronze.provider_match_cache
                WHERE provider = 'matchbook'
                ORDER BY sport, kickoff_utc NULLS LAST
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]
    finally:
        conn.close()


def _to_event_dict(row: dict, *, ingested_at: str) -> dict | None:
    """Map a provider_match_cache row to a MatchbookEventRecord dict.

    Returns None to signal skip if the sport is unmapped or kickoff_utc is NULL.
    """
    sport = row.get("sport") or ""
    sport_id = SPORT_ID_MAP.get(sport)
    if sport_id is None:
        return None

    kickoff = row.get("kickoff_utc")
    if kickoff is None:
        return None

    home = row.get("home_team_name") or ""
    away = row.get("away_team_name") or ""
    event_name = f"{home} vs {away}" if home and away else (row.get("competition_name") or "")

    # Fall back to "open" for events where status wasn't captured in the cache.
    status = row.get("status") or "open"

    volume_raw = row.get("total_liquidity")
    volume = float(volume_raw) if volume_raw else None

    # Synthesise a raw_event JSON from available Postgres columns. Not the original
    # API payload, but tagged so downstream knows the provenance.
    raw_event = json.dumps(
        {
            "id": row.get("provider_id", ""),
            "name": event_name,
            "sport-id": sport_id,
            "status": status,
            "start": kickoff.isoformat(),
            "volume": volume,
            "competition": row.get("competition_name") or "",
            "home_team_name": home,
            "away_team_name": away,
            "_migration_source": "postgres",
            "_migration_table": "bronze.provider_match_cache",
        },
        separators=(",", ":"),
        sort_keys=True,
    )

    return {
        "event_id": str(row.get("provider_id", "")),
        "event_name": event_name,
        "sport_id": sport_id,
        "status": status,
        "start_utc": kickoff.isoformat(),
        "volume": volume,
        "ingested_at": ingested_at,
        "raw_event": raw_event,
    }


def run_matchbook_postgres_migration(
    postgres_url: str,
    *,
    out_dir: Path,
    log: Any | None,
    schema: pa.DataFrameSchema,
) -> MigrationReport:
    """Extract Matchbook events from PostgreSQL and write bronze Parquet files.

    Groups by sport (mirroring the live ingest pattern), writing one file per
    sport under ``out_dir/<sport>/<run_date>/migration_<batch_ts>.parquet``.
    Per-sport failures are isolated; the report collects all outcomes.
    """
    ingested_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    batch_ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_date = datetime.now(UTC).strftime("%Y-%m-%d")

    rows = _fetch_matchbook_rows(postgres_url)
    if log:
        log.info(
            "matchbook postgres migration: fetched %d rows from provider_match_cache", len(rows)
        )

    by_sport: dict[str, list[dict]] = {}
    for row in rows:
        sport = row.get("sport") or "unknown"
        by_sport.setdefault(sport, []).append(row)

    report = MigrationReport()

    for sport_name, sport_rows in by_sport.items():
        try:
            event_rows: list[dict] = []
            failed = 0
            for row in sport_rows:
                flat = _to_event_dict(row, ingested_at=ingested_at)
                if flat is None:
                    failed += 1
                    if log:
                        log.warning(
                            "migration: skipping event_id=%s "
                            "(unmapped sport=%s or missing kickoff)",
                            row.get("provider_id"),
                            row.get("sport"),
                        )
                    continue
                try:
                    MatchbookEventRecord.model_validate(flat)
                    event_rows.append(flat)
                except ValidationError as exc:
                    failed += 1
                    if log:
                        log.warning(
                            "migration: skipping invalid event_id=%s: %s",
                            flat.get("event_id"),
                            exc,
                        )

            if not event_rows:
                if log:
                    log.warning("migration: no valid rows for sport=%s; skipping write", sport_name)
                report.skipped.append(
                    SportResult(
                        sport_name, "skipped", total_rows=len(sport_rows), failed_rows=failed
                    )
                )
                continue

            df = pd.DataFrame(event_rows)
            schema.validate(df)

            out_path = out_dir / sport_name / run_date / f"migration_{batch_ts}.parquet"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = out_path.with_suffix(".tmp")
            df.to_parquet(tmp, index=False)
            tmp.replace(out_path)

            if log:
                log.info(
                    "migration: wrote %d rows for sport=%s to %s (skipped %d)",
                    len(df),
                    sport_name,
                    out_path,
                    failed,
                )

            report.written.append(
                SportResult(
                    sport_name,
                    "written",
                    out_path=out_path,
                    total_rows=len(sport_rows),
                    valid_rows=len(event_rows),
                    failed_rows=failed,
                )
            )

        except Exception as exc:  # noqa: BLE001 — per-sport isolation
            if log:
                log.error("migration: failed for sport=%s: %s", sport_name, exc)
            report.failed.append(SportResult(sport_name, "failed", error=str(exc)))

    return report


__all__ = [
    "SPORT_ID_MAP",
    "SportResult",
    "MigrationReport",
    "run_matchbook_postgres_migration",
]
