"""Matchbook conform engine orchestrator.

Links Matchbook bronze events to canonical (ESPN-derived) matches. Each event is
either resolved (to a canonical ``match_id``) or sent to an exceptions queue for
human review; human overrides can also mint a brand-new canonical match. The
engine reads Parquet and writes three Parquet files — it never touches DuckLake
(dbt owns the catalog).
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .matchbook_event_name import parse_event_name
from .matchbook_overrides import load_overrides
from .matchbook_scoring import (
    HIGH_CONFIDENCE,
    HIGH_THRESHOLD,
    KICKOFF_TOLERANCE_MINUTES,
    MEDIUM_CONFIDENCE,
    MEDIUM_THRESHOLD,
    _parse_start_utc,
    _score_candidate,
)
from .resolve import compute_canonical_match_id

logger = logging.getLogger(__name__)

FOOTBALL_SPORT_ID = 15

RESOLVED_COLUMNS = [
    "matchbook_event_id",
    "match_id",
    "match_method",
    "confidence",
    "review_status",
]
EXCEPTION_COLUMNS = [
    "matchbook_event_id",
    "event_name",
    "home_team_parsed",
    "away_team_parsed",
    "start_utc",
    "unresolved_reason",
    "candidates",
]
# Columns for the additions file when there are no rows to write; a populated
# frame carries the full set of columns inferred from the addition row dicts.
ADDITION_EMPTY_COLUMNS = ["match_id", "season_id", "home_team_id", "away_team_id", "kickoff_time"]


@dataclass
class ConformReport:
    resolved_count: int = 0
    exceptions_count: int = 0
    overrides_applied: int = 0
    additions_count: int = 0
    failures: list[str] = field(default_factory=list)


@dataclass
class _EventOutcome:
    """The result of conforming a single event: at most one row of each kind."""

    resolved: dict | None = None
    exception: dict | None = None
    addition: dict | None = None
    override_applied: bool = False


def run_conform(
    events_dir: Path,
    canonical_dir: Path,
    overrides_path: Path,
    exceptions_dir: Path,
    conform_dir: Path,
    additions_dir: Path,
    log: logging.Logger | None = None,
) -> ConformReport:
    """Run the Matchbook conform engine.

    Reads bronze events, loads canonical match/team data, applies overrides,
    then fuzzy-matches remaining events. Writes three output Parquet files
    atomically: resolved-links, exceptions, and canonical additions.
    """
    log = log or logger
    report = ConformReport()

    events = _load_football_events(events_dir, log)
    canonical_matches = _load_canonical_matches(canonical_dir)
    overrides_by_event = _index_overrides(overrides_path)

    resolved_rows: list[dict] = []
    exception_rows: list[dict] = []
    addition_rows: list[dict] = []
    for _, event in events.iterrows():
        outcome = _resolve_event(event, canonical_matches, overrides_by_event)
        if outcome.resolved is not None:
            resolved_rows.append(outcome.resolved)
        if outcome.exception is not None:
            exception_rows.append(outcome.exception)
        if outcome.addition is not None:
            addition_rows.append(outcome.addition)
        if outcome.override_applied:
            report.overrides_applied += 1

    _write_conform_outputs(
        resolved_rows,
        exception_rows,
        addition_rows,
        conform_dir=conform_dir,
        exceptions_dir=exceptions_dir,
        additions_dir=additions_dir,
        report=report,
        log=log,
    )
    return report


# ── Load ────────────────────────────────────────────────────────────────────


def _load_football_events(events_dir: Path, log: logging.Logger) -> pd.DataFrame:
    """Read bronze event Parquet, dedup by latest ingested_at, keep football only.

    Returns an empty frame when no bronze files exist (E7/E15).
    """
    event_files = sorted(events_dir.glob("**/*.parquet")) if events_dir.exists() else []
    if not event_files:
        log.warning("No bronze event Parquet files found in %s", events_dir)
        return pd.DataFrame()

    events = pd.concat([pd.read_parquet(f) for f in event_files], ignore_index=True)

    # Deduplicate by event_id, keeping latest ingested_at (E15).
    if "ingested_at" in events.columns:
        events = events.sort_values("ingested_at", ascending=False)
    events = events.drop_duplicates(subset=["event_id"], keep="first")

    # Filter to football only (E7).
    if "sport_id" in events.columns:
        events = events[events["sport_id"] == FOOTBALL_SPORT_ID]

    return events


def _load_canonical_matches(canonical_dir: Path) -> list[dict]:
    """Load canonical match rows (team names, kickoff times, match_ids)."""
    match_parquet = canonical_dir / "match.parquet"
    if not match_parquet.exists():
        return []
    return pd.read_parquet(match_parquet).to_dict("records")


def _index_overrides(overrides_path: Path) -> dict[str, dict]:
    """Index human-override decisions by Matchbook event id."""
    overrides = load_overrides(overrides_path)
    if overrides.empty:
        return {}
    return {str(row["matchbook_event_id"]): row.to_dict() for _, row in overrides.iterrows()}


# ── Resolve one event ─────────────────────────────────────────────────────────


def _resolve_event(
    event: pd.Series, canonical_matches: list[dict], overrides_by_event: dict[str, dict]
) -> _EventOutcome:
    """Conform a single event: a human override wins, otherwise fuzzy-match."""
    event_id = str(event["event_id"])
    event_name = str(event.get("event_name", ""))

    override = overrides_by_event.get(event_id)
    if override is not None:
        return _resolve_via_override(event_id, event_name, event, override)

    return _resolve_via_fuzzy(event_id, event_name, event, canonical_matches)


def _resolve_via_override(
    event_id: str, event_name: str, event: pd.Series, override: dict
) -> _EventOutcome:
    """Apply a human override. ``new_canonical`` mints and links a fresh match."""
    resolved = _link_row(
        event_id, override.get("match_id", ""), "human_override", 1.0, "human_confirmed"
    )
    if override.get("action") == "new_canonical":
        match_id, addition = _mint_canonical_addition(event_name, event)
        resolved["match_id"] = match_id
        return _EventOutcome(resolved=resolved, addition=addition, override_applied=True)
    return _EventOutcome(resolved=resolved, override_applied=True)


def _mint_canonical_addition(event_name: str, event: pd.Series) -> tuple[str, dict]:
    """Mint a new canonical match from a Matchbook event with best-effort ids.

    Returns ``(match_id, addition_row)`` — the caller stamps the same match_id
    onto the resolved link so the two stay in lock-step.
    """
    parsed = parse_event_name(event_name)
    home_parsed, away_parsed = parsed if parsed else (event_name, "")

    start_utc_str = str(event.get("start_utc", ""))
    start_dt = _parse_start_utc(start_utc_str)
    date_str = start_dt.strftime("%Y-%m-%d") if start_dt else "unknown"

    league_id = hashlib.md5(b"matchbook_football").hexdigest()
    year = start_dt.year if start_dt else 2026
    season_id = hashlib.md5(f"{league_id}|{year}".encode()).hexdigest()
    home_team_id = hashlib.md5(home_parsed.lower().encode()).hexdigest()
    away_team_id = hashlib.md5(away_parsed.lower().encode()).hexdigest()

    match_id = compute_canonical_match_id(
        league_id, season_id, date_str, home_team_id, away_team_id
    )
    addition = {
        "match_id": match_id,
        "season_id": season_id,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "favourite_team_id": None,
        "kickoff_time": start_utc_str or None,
        "ht_score": None,
        "ft_score": None,
        "status_completed": False,
    }
    return match_id, addition


def _resolve_via_fuzzy(
    event_id: str, event_name: str, event: pd.Series, canonical_matches: list[dict]
) -> _EventOutcome:
    """Fuzzy-match an event against canonical matches into HIGH/MEDIUM/exception."""
    parsed = parse_event_name(event_name)
    start_utc_str = str(event.get("start_utc", ""))
    if parsed is None:
        return _EventOutcome(
            exception=_exception_row(
                event_id, event_name, None, None, start_utc_str, "unparseable_event_name", "[]"
            )
        )

    home_parsed, away_parsed = parsed
    start_utc = _parse_start_utc(start_utc_str)
    if start_utc is None:
        return _EventOutcome(
            exception=_exception_row(
                event_id,
                event_name,
                home_parsed,
                away_parsed,
                start_utc_str,
                "invalid_start_utc",
                "[]",
            )
        )

    candidates = _score_candidates(home_parsed, away_parsed, start_utc, canonical_matches)

    high = _candidates_within_tolerance(candidates, HIGH_THRESHOLD)
    if len(high) == 1:
        return _EventOutcome(
            resolved=_link_row(
                event_id, high[0]["match_id"], "fuzzy_high", HIGH_CONFIDENCE, "auto_confirmed"
            )
        )

    medium = _candidates_within_tolerance(candidates, MEDIUM_THRESHOLD)
    if len(medium) == 1:
        return _EventOutcome(
            resolved=_link_row(
                event_id, medium[0]["match_id"], "fuzzy_medium", MEDIUM_CONFIDENCE, "needs_review"
            )
        )

    reason = "multiple_candidates" if len(medium) > 1 else "no_match"
    return _EventOutcome(
        exception=_exception_row(
            event_id,
            event_name,
            home_parsed,
            away_parsed,
            start_utc_str,
            reason,
            _candidates_json(candidates[:5]),
        )
    )


def _score_candidates(
    home_parsed: str, away_parsed: str, start_utc, canonical_matches: list[dict]
) -> list[dict]:
    """Score every canonical match, dropping unscorable ones, best score first."""
    scored = [
        candidate
        for match_row in canonical_matches
        if (candidate := _score_candidate(home_parsed, away_parsed, start_utc, match_row))
        is not None
    ]
    scored.sort(key=lambda c: c["combined_score"], reverse=True)
    return scored


def _candidates_within_tolerance(candidates: list[dict], threshold: float) -> list[dict]:
    """Candidates where both team scores clear ``threshold`` and kickoff is close."""
    return [
        c
        for c in candidates
        if c["home_score"] >= threshold
        and c["away_score"] >= threshold
        and c["kickoff_diff_minutes"] <= KICKOFF_TOLERANCE_MINUTES
    ]


# ── Row builders ──────────────────────────────────────────────────────────────


def _link_row(
    event_id: str, match_id: str, match_method: str, confidence: float, review_status: str
) -> dict:
    return {
        "matchbook_event_id": event_id,
        "match_id": match_id,
        "match_method": match_method,
        "confidence": confidence,
        "review_status": review_status,
    }


def _exception_row(
    event_id: str,
    event_name: str,
    home_parsed: str | None,
    away_parsed: str | None,
    start_utc_str: str,
    reason: str,
    candidates_json: str,
) -> dict:
    return {
        "matchbook_event_id": event_id,
        "event_name": event_name,
        "home_team_parsed": home_parsed,
        "away_team_parsed": away_parsed,
        "start_utc": start_utc_str,
        "unresolved_reason": reason,
        "candidates": candidates_json,
    }


def _candidates_json(candidates: list[dict]) -> str:
    """Serialize the top candidates for the exceptions review queue."""
    return json.dumps(
        [
            {
                "match_id": c["match_id"],
                "home_team": c["home_team_name"],
                "away_team": c["away_team_name"],
                "kickoff_time": c["kickoff_time"],
                "score": round(c["combined_score"], 4),
            }
            for c in candidates
        ]
    )


# ── Write ─────────────────────────────────────────────────────────────────────


def _write_conform_outputs(
    resolved_rows: list[dict],
    exception_rows: list[dict],
    addition_rows: list[dict],
    *,
    conform_dir: Path,
    exceptions_dir: Path,
    additions_dir: Path,
    report: ConformReport,
    log: logging.Logger,
) -> None:
    """Write resolved-links, exceptions, and additions Parquet files atomically.

    All three files are always written (even empty) — ``int_match.sql`` reads the
    additions file and requires it to exist.
    """
    resolved_df = pd.DataFrame(resolved_rows, columns=RESOLVED_COLUMNS)
    _write_parquet_atomic(resolved_df, conform_dir / "matchbook_resolved_links.parquet")
    report.resolved_count = len(resolved_df)

    exceptions_df = pd.DataFrame(exception_rows, columns=EXCEPTION_COLUMNS)
    _write_parquet_atomic(exceptions_df, exceptions_dir / "matchbook_unresolved.parquet")
    report.exceptions_count = len(exceptions_df)

    additions_df = (
        pd.DataFrame(addition_rows)
        if addition_rows
        else pd.DataFrame(columns=ADDITION_EMPTY_COLUMNS)
    )
    _write_parquet_atomic(additions_df, additions_dir / "matchbook_canonical_additions.parquet")
    report.additions_count = len(additions_df)

    log.info(
        "conform: resolved=%d, exceptions=%d, overrides=%d, additions=%d",
        report.resolved_count,
        report.exceptions_count,
        report.overrides_applied,
        report.additions_count,
    )


def _write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to Parquet atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    df.to_parquet(tmp_path, index=False)
    tmp_path.replace(path)
