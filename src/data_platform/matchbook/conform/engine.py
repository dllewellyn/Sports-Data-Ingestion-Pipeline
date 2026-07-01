"""Matchbook conform engine orchestrator."""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .overrides import load_overrides
from .reversal import parse_event_name
from .scoring import (
    HIGH_CONFIDENCE,
    HIGH_THRESHOLD,
    KICKOFF_TOLERANCE_MINUTES,
    MEDIUM_CONFIDENCE,
    MEDIUM_THRESHOLD,
    _parse_start_utc,
    _score_candidate,
)

logger = logging.getLogger(__name__)

FOOTBALL_SPORT_ID = 15


@dataclass
class ConformReport:
    resolved_count: int = 0
    exceptions_count: int = 0
    overrides_applied: int = 0
    additions_count: int = 0
    failures: list[str] = field(default_factory=list)


def compute_canonical_match_id(
    league_id: str, season_id: str, date_str: str, home_team_id: str, away_team_id: str
) -> str:
    """Replicate the dbt canonical_match_id macro in Python.

    md5(concat_ws('|', league_id, season_id, date, home, away))
    """
    key = "|".join([league_id, season_id, date_str, home_team_id, away_team_id])
    return hashlib.md5(key.encode()).hexdigest()


def _write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to Parquet atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    df.to_parquet(tmp_path, index=False)
    tmp_path.replace(path)


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
    if log is None:
        log = logger
    report = ConformReport()

    # ── Load bronze events ──────────────────────────────────────────────
    event_files = sorted(events_dir.glob("**/*.parquet")) if events_dir.exists() else []
    if not event_files:
        log.warning("No bronze event Parquet files found in %s", events_dir)
        _write_parquet_atomic(
            pd.DataFrame(
                columns=[
                    "matchbook_event_id",
                    "match_id",
                    "match_method",
                    "confidence",
                    "review_status",
                ]
            ),
            conform_dir / "matchbook_resolved_links.parquet",
        )
        _write_parquet_atomic(
            pd.DataFrame(
                columns=[
                    "matchbook_event_id",
                    "event_name",
                    "home_team_parsed",
                    "away_team_parsed",
                    "start_utc",
                    "unresolved_reason",
                    "candidates",
                ]
            ),
            exceptions_dir / "matchbook_unresolved.parquet",
        )
        return report

    events_df = pd.concat([pd.read_parquet(f) for f in event_files], ignore_index=True)

    # Deduplicate by event_id, keeping latest ingested_at (E15)
    if "ingested_at" in events_df.columns:
        events_df = events_df.sort_values("ingested_at", ascending=False)
    events_df = events_df.drop_duplicates(subset=["event_id"], keep="first")

    # Filter to football only (E7)
    if "sport_id" in events_df.columns:
        events_df = events_df[events_df["sport_id"] == FOOTBALL_SPORT_ID]

    # ── Load canonical data ─────────────────────────────────────────────
    match_parquet = canonical_dir / "match.parquet"
    canonical_matches: list[dict] = []
    if match_parquet.exists():
        matches_df = pd.read_parquet(match_parquet)
        canonical_matches = matches_df.to_dict("records")

    # ── Load overrides ──────────────────────────────────────────────────
    overrides = load_overrides(overrides_path)
    overrides_by_event: dict[str, dict] = {}
    if not overrides.empty:
        for _, row in overrides.iterrows():
            overrides_by_event[str(row["matchbook_event_id"])] = row.to_dict()

    # ── Process events ──────────────────────────────────────────────────
    resolved_rows: list[dict] = []
    exception_rows: list[dict] = []
    addition_rows: list[dict] = []

    for _, event in events_df.iterrows():
        event_id = str(event["event_id"])
        event_name = str(event.get("event_name", ""))

        # Check override first
        if event_id in overrides_by_event:
            override = overrides_by_event[event_id]
            resolved_rows.append(
                {
                    "matchbook_event_id": event_id,
                    "match_id": override.get("match_id", ""),
                    "match_method": "human_override",
                    "confidence": 1.0,
                    "review_status": "human_confirmed",
                }
            )
            report.overrides_applied += 1

            # new_canonical action: write to additions
            if override.get("action") == "new_canonical":
                parsed = parse_event_name(event_name)
                if parsed:
                    home_parsed, away_parsed = parsed
                else:
                    home_parsed, away_parsed = event_name, ""

                start_utc_str = str(event.get("start_utc", ""))
                start_dt = _parse_start_utc(start_utc_str)
                date_str = start_dt.strftime("%Y-%m-%d") if start_dt else "unknown"

                # Best-effort surrogate ids
                league_id = hashlib.md5(b"matchbook_football").hexdigest()
                year = start_dt.year if start_dt else 2026
                season_id = hashlib.md5(f"{league_id}|{year}".encode()).hexdigest()
                home_team_id = hashlib.md5(home_parsed.lower().encode()).hexdigest()
                away_team_id = hashlib.md5(away_parsed.lower().encode()).hexdigest()

                match_id = compute_canonical_match_id(
                    league_id, season_id, date_str, home_team_id, away_team_id
                )
                # Update the resolved row with the minted match_id
                resolved_rows[-1]["match_id"] = match_id

                addition_rows.append(
                    {
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
                )

            continue

        # Parse event name
        parsed = parse_event_name(event_name)
        if parsed is None:
            exception_rows.append(
                {
                    "matchbook_event_id": event_id,
                    "event_name": event_name,
                    "home_team_parsed": None,
                    "away_team_parsed": None,
                    "start_utc": str(event.get("start_utc", "")),
                    "unresolved_reason": "unparseable_event_name",
                    "candidates": "[]",
                }
            )
            continue

        home_parsed, away_parsed = parsed

        # Parse start_utc
        start_utc_str = str(event.get("start_utc", ""))
        start_utc = _parse_start_utc(start_utc_str)
        if start_utc is None:
            exception_rows.append(
                {
                    "matchbook_event_id": event_id,
                    "event_name": event_name,
                    "home_team_parsed": home_parsed,
                    "away_team_parsed": away_parsed,
                    "start_utc": start_utc_str,
                    "unresolved_reason": "invalid_start_utc",
                    "candidates": "[]",
                }
            )
            continue

        # Score all canonical candidates
        candidates = []
        for match_row in canonical_matches:
            scored = _score_candidate(home_parsed, away_parsed, start_utc, match_row)
            if scored is not None:
                candidates.append(scored)

        # Sort by combined_score descending
        candidates.sort(key=lambda c: c["combined_score"], reverse=True)

        # HIGH confidence path
        high_candidates = [
            c
            for c in candidates
            if c["home_score"] >= HIGH_THRESHOLD
            and c["away_score"] >= HIGH_THRESHOLD
            and c["kickoff_diff_minutes"] <= KICKOFF_TOLERANCE_MINUTES
        ]
        if len(high_candidates) == 1:
            resolved_rows.append(
                {
                    "matchbook_event_id": event_id,
                    "match_id": high_candidates[0]["match_id"],
                    "match_method": "fuzzy_high",
                    "confidence": HIGH_CONFIDENCE,
                    "review_status": "auto_confirmed",
                }
            )
            continue

        # MEDIUM confidence path
        medium_candidates = [
            c
            for c in candidates
            if c["home_score"] >= MEDIUM_THRESHOLD
            and c["away_score"] >= MEDIUM_THRESHOLD
            and c["kickoff_diff_minutes"] <= KICKOFF_TOLERANCE_MINUTES
        ]
        if len(medium_candidates) == 1:
            resolved_rows.append(
                {
                    "matchbook_event_id": event_id,
                    "match_id": medium_candidates[0]["match_id"],
                    "match_method": "fuzzy_medium",
                    "confidence": MEDIUM_CONFIDENCE,
                    "review_status": "needs_review",
                }
            )
            continue

        # Multiple candidates or no match -> exceptions
        reason = "multiple_candidates" if len(medium_candidates) > 1 else "no_match"

        top_5 = candidates[:5]
        candidates_json = json.dumps(
            [
                {
                    "match_id": c["match_id"],
                    "home_team": c["home_team_name"],
                    "away_team": c["away_team_name"],
                    "kickoff_time": c["kickoff_time"],
                    "score": round(c["combined_score"], 4),
                }
                for c in top_5
            ]
        )
        exception_rows.append(
            {
                "matchbook_event_id": event_id,
                "event_name": event_name,
                "home_team_parsed": home_parsed,
                "away_team_parsed": away_parsed,
                "start_utc": start_utc_str,
                "unresolved_reason": reason,
                "candidates": candidates_json,
            }
        )

    # ── Write outputs ───────────────────────────────────────────────────
    resolved_df = pd.DataFrame(
        resolved_rows,
        columns=["matchbook_event_id", "match_id", "match_method", "confidence", "review_status"],
    )
    _write_parquet_atomic(resolved_df, conform_dir / "matchbook_resolved_links.parquet")
    report.resolved_count = len(resolved_df)

    exceptions_df = pd.DataFrame(
        exception_rows,
        columns=[
            "matchbook_event_id",
            "event_name",
            "home_team_parsed",
            "away_team_parsed",
            "start_utc",
            "unresolved_reason",
            "candidates",
        ],
    )
    _write_parquet_atomic(exceptions_df, exceptions_dir / "matchbook_unresolved.parquet")
    report.exceptions_count = len(exceptions_df)

    # Always write, even if empty — read_parquet in int_match.sql requires the file to exist.
    additions_df = (
        pd.DataFrame(addition_rows)
        if addition_rows
        else pd.DataFrame(
            columns=["match_id", "season_id", "home_team_id", "away_team_id", "kickoff_time"]
        )
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
    return report
