"""Matchbook Events REST API bronze ingest engine (Dagster-free).

One Parquet per sport per run under
``data/bronze/matchbook_events/<sport>/<YYYY-MM-DD>/<batch_ts>.parquet``.
Flow per sport: authenticate (once per run) → paginated GET of open events →
flatten each event to a bronze row → row-level Pydantic validation
(skip-and-count invalid) → frame-level Pandera validation → atomic write
(temp + rename). Per-sport failures are isolated; the outer loop accumulates
them and re-raises at the end so the run is marked failed while valid Parquet
files are still persisted.

Auth convention (CLAUDE.md): standalone ``authenticate()`` function,
raise_for_status() first, ValueError on missing token, one token per run,
auth raises before any Parquet write.

This module is intentionally free of Dagster so it is unit-testable; the thin
``assets/matchbook_events.py`` wrapper reads settings and calls
``run_matchbook_events_ingest()``.
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
import requests
from pydantic import ValidationError

from ..models.schemas import MatchbookEventRecord
from ..otel import get_tracer

logger = logging.getLogger(__name__)

# Sports to ingest each run. sport_id is the Matchbook API id.
SPORTS: list[dict] = [
    {"sport_id": 15, "name": "football"},
    {"sport_id": 2, "name": "rugby_union"},
]


@dataclass(frozen=True)
class SportResult:
    sport_name: str
    status: str  # "written" | "skipped" | "failed"
    out_path: Path | None = None
    raw_count: int = 0
    valid_count: int = 0
    failure_count: int = 0
    error: str | None = None


@dataclass
class IngestionReport:
    written: list[SportResult] = field(default_factory=list)
    skipped: list[SportResult] = field(default_factory=list)
    failed: list[SportResult] = field(default_factory=list)

    @property
    def attempted(self) -> int:
        return len(self.written) + len(self.skipped) + len(self.failed)

    @property
    def total_failures(self) -> int:
        return sum(r.failure_count for r in self.written + self.skipped) + len(self.failed)


def authenticate(
    username: str,
    password: str,
    *,
    base_url: str,
    timeout: float,
) -> str:
    """POST credentials to the Matchbook auth endpoint and return the session token.

    Raises ValueError immediately if credentials are empty (before any HTTP call).
    Calls raise_for_status() before inspecting the body; raises ValueError if
    session-token is absent from the response (AC16).
    """
    if not username or not password:
        raise ValueError(
            "credentials missing: MATCHBOOK_USERNAME and MATCHBOOK_PASSWORD must be set"
        )

    session = requests.Session()
    response = session.post(
        f"{base_url}/bpapi/rest/security/session",
        json={"username": username, "password": password},
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    token = body.get("session-token")
    if not token:
        raise ValueError("session-token not present in auth response")
    return token


def fetch_events(
    session_token: str,
    sport_id: int,
    *,
    base_url: str,
    per_page: int,
    timeout: float,
) -> list[dict]:
    """Paginated GET of open events for one sport.

    Continues until all events are fetched (len(events) >= total) or the page
    is shorter than per_page (sentinel). If total is absent from the response,
    treats as a single page and logs a warning (E13).
    """
    session = requests.Session()
    session.headers["session-token"] = session_token

    events: list[dict] = []
    offset = 0

    while True:
        response = session.get(
            f"{base_url}/edge/rest/events",
            params={
                "sport-ids": sport_id,
                "status": "open",
                "include-markets": "true",
                "include-runners": "true",
                "per-page": per_page,
                "offset": offset,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        batch: list[dict] = payload.get("events", [])
        total: int | None = payload.get("total")

        events.extend(batch)

        if total is None:
            logger.warning(
                "matchbook fetch_events: 'total' absent from response for sport_id=%s; "
                "treating as single page",
                sport_id,
            )
            break

        if len(events) >= total or len(batch) < per_page:
            break

        offset += len(batch)

    return events


def flatten_event(raw: dict, *, ingested_at: str) -> dict:
    """Project structured columns from a raw Matchbook event dict.

    The complete original dict is serialised verbatim into ``raw_event`` so
    every API field (markets, runners, venue, ...) is recoverable from bronze
    without re-fetching (faithful-to-source, AC3).
    """
    return {
        "event_id": str(raw.get("id", "")),
        "event_name": str(raw.get("name", "")),
        "sport_id": raw.get("sport-id"),
        "status": str(raw.get("status", "")),
        "start_utc": str(raw.get("start", "")),
        "volume": raw.get("volume"),
        "ingested_at": ingested_at,
        "raw_event": json.dumps(raw, separators=(",", ":"), sort_keys=True),
    }


def ingest_sport(
    sport_id: int,
    sport_name: str,
    session_token: str,
    *,
    base_url: str,
    per_page: int,
    timeout: float,
    out_dir: Path,
    batch_ts: str,
    run_date: str,
    log: Any | None,
    schema: pa.DataFrameSchema,
) -> tuple[Path | None, int]:
    """Ingest one sport's open events into one bronze Parquet.

    Per-record Pydantic failures are skip-and-counted (NOT raised here). Returns
    ``(path_written_or_None, failure_count)``. The caller
    (run_matchbook_events_ingest) re-raises if the total failure count across all
    sports is > 0 (AC7). Returns (None, failure_count) if zero events or zero
    valid records.
    """
    ingested_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw_events = fetch_events(
        session_token, sport_id, base_url=base_url, per_page=per_page, timeout=timeout
    )

    if not raw_events:
        if log is not None:
            log.info("matchbook: no open events for sport_id=%s (%s)", sport_id, sport_name)
        return None, 0

    rows: list[dict] = []
    failure_count = 0
    for raw in raw_events:
        flat = flatten_event(raw, ingested_at=ingested_at)
        try:
            MatchbookEventRecord.model_validate(flat)
            rows.append(flat)
        except ValidationError as exc:
            failure_count += 1
            if log is not None:
                log.warning(
                    "matchbook: skipping invalid record (sport_id=%s, event_id=%s): %s",
                    sport_id,
                    raw.get("id"),
                    exc,
                )

    if not rows:
        if log is not None:
            log.warning(
                "matchbook: zero valid records for sport_id=%s (%s); skipping write",
                sport_id,
                sport_name,
            )
        return None, failure_count

    df = pd.DataFrame(rows)
    schema.validate(df)

    out_path = out_dir / sport_name / run_date / f"{batch_ts}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp")
    df.to_parquet(tmp_path, index=False)
    tmp_path.replace(out_path)

    if log is not None:
        log.info(
            "matchbook: wrote %d rows to %s (skipped %d invalid)",
            len(df),
            out_path,
            failure_count,
        )

    return out_path, failure_count


def run_matchbook_events_ingest(
    username: str,
    password: str,
    *,
    base_url: str,
    per_page: int,
    timeout: float,
    out_dir: Path,
    log: Any | None,
    schema: pa.DataFrameSchema,
) -> IngestionReport:
    """Authenticate once and ingest all configured sports, isolating per-sport failures.

    Re-raises RuntimeError at the end if any per-record validation failures or
    per-sport exceptions occurred (AC7: run marked failed while valid Parquet
    files are still persisted). Auth failure raises immediately before any
    Parquet write (AC16).
    """
    tracer = get_tracer()
    batch_ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_date = datetime.now(UTC).strftime("%Y-%m-%d")

    with tracer.start_as_current_span("ingest.matchbook_events") as span:
        token = authenticate(username, password, base_url=base_url, timeout=timeout)
        span.set_attribute("ingest.sports", [s["name"] for s in SPORTS])

        report = IngestionReport()
        total_failures = 0

        for sport in SPORTS:
            try:
                out_path, failure_count = ingest_sport(
                    sport_id=sport["sport_id"],
                    sport_name=sport["name"],
                    session_token=token,
                    base_url=base_url,
                    per_page=per_page,
                    timeout=timeout,
                    out_dir=out_dir,
                    batch_ts=batch_ts,
                    run_date=run_date,
                    log=log,
                    schema=schema,
                )
                total_failures += failure_count
                if out_path is None:
                    report.skipped.append(
                        SportResult(sport["name"], "skipped", failure_count=failure_count)
                    )
                else:
                    report.written.append(
                        SportResult(
                            sport["name"],
                            "written",
                            out_path=out_path,
                            failure_count=failure_count,
                        )
                    )
            except Exception as exc:  # noqa: BLE001 — per-sport isolation
                if log is not None:
                    log.error("matchbook: ingest failed for %s: %s", sport["name"], exc)
                report.failed.append(SportResult(sport["name"], "failed", error=str(exc)))
                total_failures += 1

        span.set_attribute("ingest.written", len(report.written))
        span.set_attribute("ingest.skipped", len(report.skipped))
        span.set_attribute("ingest.failed", len(report.failed))

    if total_failures > 0:
        raise RuntimeError(
            f"matchbook ingest completed with {total_failures} failures"
            f" (written={len(report.written)}, skipped={len(report.skipped)},"
            f" failed={len(report.failed)})"
        )

    return report


__all__ = [
    "SPORTS",
    "SportResult",
    "IngestionReport",
    "authenticate",
    "fetch_events",
    "flatten_event",
    "ingest_sport",
    "run_matchbook_events_ingest",
]
