"""Matchbook conform engine orchestrator.

Links Matchbook bronze events to canonical (ESPN-derived) matches. Each event is
either resolved (to a canonical ``match_id``) or sent to an exceptions queue for
human review; human overrides can also mint a brand-new canonical match. A mint
resolves the FULL season→league→team chain through the shared resolver + seeds
and emits four additions frames (match/team/league/season). The engine reads
Parquet and writes Parquet — it never touches DuckLake (dbt owns the catalog).
"""

from __future__ import annotations

import contextlib
import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..models.validation import (
    league_additions_schema,
    match_additions_schema,
    season_additions_schema,
    team_additions_schema,
)
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
from .resolve import (
    compute_canonical_match_id,
    derive_season_id,
    is_mintable_name,
    resolve_league_id,
    resolve_team_id,
)

logger = logging.getLogger(__name__)

FOOTBALL_SPORT_ID = 15
MATCHBOOK_PROVIDER = "matchbook"

# Column orders for the four canonical-additions frames (data-model.md). An empty
# frame is written with these columns so dbt's read_parquet finds the file typed.
MATCH_ADDITION_COLUMNS = [
    "match_id",
    "season_id",
    "home_team_id",
    "away_team_id",
    "kickoff_time",
    "ht_score",
    "ft_score",
    "status_completed",
]
TEAM_ADDITION_COLUMNS = ["team_id", "name", "similar_names"]
LEAGUE_ADDITION_COLUMNS = ["league_id", "name", "is_tournament"]
SEASON_ADDITION_COLUMNS = ["season_id", "league_id", "name", "start_date", "end_date"]

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


@dataclass
class ConformReport:
    resolved_count: int = 0
    exceptions_count: int = 0
    overrides_applied: int = 0
    additions_count: int = 0
    failures: list[str] = field(default_factory=list)


@dataclass
class MintResult:
    """The chain members a mint produced. Only UN-resolved members are carried.

    ``exception`` is set instead of any addition when the parsed team names are
    blank (E5) — in that case NO additions are emitted and the caller routes the
    event to the exceptions queue.
    """

    match_addition: dict | None = None
    team_additions: list[dict] = field(default_factory=list)
    league_additions: list[dict] = field(default_factory=list)
    season_additions: list[dict] = field(default_factory=list)
    exception: dict | None = None


@dataclass
class _EventOutcome:
    """The result of conforming a single event."""

    resolved: dict | None = None
    exception: dict | None = None
    mint: MintResult | None = None
    override_applied: bool = False


def run_conform(
    events_dir: Path,
    canonical_dir: Path,
    overrides_path: Path,
    exceptions_dir: Path,
    conform_dir: Path,
    additions_dir: Path,
    team_aliases_path: Path | None = None,
    league_aliases_path: Path | None = None,
    log: logging.Logger | None = None,
) -> ConformReport:
    """Run the Matchbook conform engine.

    Reads bronze events, loads canonical match/team/league/season data, applies
    overrides, then fuzzy-matches remaining events. A ``new_canonical`` mint
    resolves the full season→league→team chain through the shared resolver +
    seeds and emits FOUR additions frames (match/team/league/season). Writes the
    resolved-links, exceptions, and four additions Parquet files atomically.
    """
    log = log or logger
    report = ConformReport()

    events = _load_football_events(events_dir, log)
    canonical_matches = _load_canonical_matches(canonical_dir)
    overrides_by_event = _index_overrides(overrides_path)

    team_aliases_df = _load_seed(team_aliases_path, ["team_id", "canonical_name", "alias"])
    league_aliases_df = _load_seed(
        league_aliases_path, ["league_id", "canonical_name", "provider", "provider_key"]
    )
    existing_team_ids = _load_canonical_ids(canonical_dir / "team.parquet", "team_id")
    existing_league_ids = _load_canonical_ids(canonical_dir / "league.parquet", "league_id")
    existing_season_ids = _load_canonical_ids(canonical_dir / "season.parquet", "season_id")

    resolved_rows: list[dict] = []
    exception_rows: list[dict] = []
    match_rows: list[dict] = []
    team_rows: list[dict] = []
    league_rows: list[dict] = []
    season_rows: list[dict] = []
    # Track ids emitted THIS run so two minted matches sharing a league/season/team
    # don't emit duplicate additions (dbt keep-one is the backstop).
    emitted_team_ids: set[str] = set()
    emitted_league_ids: set[str] = set()
    emitted_season_ids: set[str] = set()

    for _, event in events.iterrows():
        outcome = _resolve_event(
            event,
            canonical_matches,
            overrides_by_event,
            team_aliases_df,
            league_aliases_df,
            existing_team_ids | emitted_team_ids,
            existing_league_ids | emitted_league_ids,
            existing_season_ids | emitted_season_ids,
        )
        if outcome.resolved is not None:
            resolved_rows.append(outcome.resolved)
        if outcome.exception is not None:
            exception_rows.append(outcome.exception)
        if outcome.override_applied:
            report.overrides_applied += 1
        if outcome.mint is not None:
            mint = outcome.mint
            if mint.match_addition is not None:
                match_rows.append(mint.match_addition)
            for row in mint.team_additions:
                team_rows.append(row)
                emitted_team_ids.add(row["team_id"])
            for row in mint.league_additions:
                league_rows.append(row)
                emitted_league_ids.add(row["league_id"])
            for row in mint.season_additions:
                season_rows.append(row)
                emitted_season_ids.add(row["season_id"])

    _write_conform_outputs(
        resolved_rows,
        exception_rows,
        match_rows,
        team_rows,
        league_rows,
        season_rows,
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


def _load_seed(path: Path | None, columns: list[str]) -> pd.DataFrame:
    """Read a seed CSV, or return an empty frame with the given columns if absent."""
    if path is None or not path.exists():
        return pd.DataFrame(columns=columns)
    return pd.read_csv(path, dtype=str)


def _load_canonical_ids(path: Path, column: str) -> set[str]:
    """Read a canonical export Parquet's id column into a set, empty if absent."""
    if not path.exists():
        return set()
    frame = pd.read_parquet(path, columns=[column])
    return {str(v) for v in frame[column].dropna()}


# ── Resolve one event ─────────────────────────────────────────────────────────


def _resolve_event(
    event: pd.Series,
    canonical_matches: list[dict],
    overrides_by_event: dict[str, dict],
    team_aliases_df: pd.DataFrame,
    league_aliases_df: pd.DataFrame,
    existing_team_ids: set[str],
    existing_league_ids: set[str],
    existing_season_ids: set[str],
) -> _EventOutcome:
    """Conform a single event: a human override wins, otherwise fuzzy-match."""
    event_id = str(event["event_id"])
    event_name = str(event.get("event_name", ""))

    override = overrides_by_event.get(event_id)
    if override is not None:
        return _resolve_via_override(
            event_id,
            event_name,
            event,
            override,
            team_aliases_df,
            league_aliases_df,
            existing_team_ids,
            existing_league_ids,
            existing_season_ids,
        )

    return _resolve_via_fuzzy(event_id, event_name, event, canonical_matches)


def _resolve_via_override(
    event_id: str,
    event_name: str,
    event: pd.Series,
    override: dict,
    team_aliases_df: pd.DataFrame,
    league_aliases_df: pd.DataFrame,
    existing_team_ids: set[str],
    existing_league_ids: set[str],
    existing_season_ids: set[str],
) -> _EventOutcome:
    """Apply a human override. ``new_canonical`` mints and links a fresh match."""
    if override.get("action") == "new_canonical":
        match_id, mint = _mint_canonical_chain(
            event_name,
            event,
            team_aliases_df,
            league_aliases_df,
            existing_league_ids,
            existing_season_ids,
            existing_team_ids,
        )
        if mint.exception is not None:
            return _EventOutcome(exception=mint.exception, override_applied=True)
        resolved = _link_row(event_id, match_id, "human_override", 1.0, "human_confirmed")
        return _EventOutcome(resolved=resolved, mint=mint, override_applied=True)

    resolved = _link_row(
        event_id, override.get("match_id", ""), "human_override", 1.0, "human_confirmed"
    )
    return _EventOutcome(resolved=resolved, override_applied=True)


def _matchbook_provider_key(event: pd.Series) -> str:
    """Build the Matchbook league provider_key ``"<sport_id>|<category_id>"``.

    sport_id defaults to 15 (football); category_id comes from the ``raw_event``
    JSON's ``category-id`` field, falling back to a top-level ``category_id`` or
    ``"unknown"``. This is the key ``league_aliases`` maps onto the ESPN league id.
    """
    sport_id = event.get("sport_id", FOOTBALL_SPORT_ID)
    category_id = event.get("category_id")
    raw_event = event.get("raw_event")
    if isinstance(raw_event, str) and raw_event:
        with contextlib.suppress(ValueError, TypeError):
            category_id = json.loads(raw_event).get("category-id", category_id)
    return f"{sport_id}|{category_id if category_id else 'unknown'}"


def _mint_canonical_chain(
    event_name: str,
    event: pd.Series,
    team_aliases_df: pd.DataFrame,
    league_aliases_df: pd.DataFrame,
    existing_league_ids: set[str],
    existing_season_ids: set[str],
    existing_team_ids: set[str],
) -> tuple[str | None, MintResult]:
    """Mint a canonical match plus its full season→league→team chain.

    Resolves every id through the shared resolver + seeds (ESPN-anchored dedup for
    a mapped league; provider-scoped mint otherwise). Emits a chain-member addition
    only for members NOT already canonical (``existing_*_ids``). A blank/unparseable
    team name (E5) returns ``(None, MintResult(exception=...))`` with no additions.
    """
    parsed = parse_event_name(event_name)
    home_parsed, away_parsed = parsed if parsed else (event_name, "")

    start_utc_str = str(event.get("start_utc", ""))
    start_dt = _parse_start_utc(start_utc_str)
    date_str = start_dt.strftime("%Y-%m-%d") if start_dt else "unknown"
    year = start_dt.year if start_dt else 2026

    if not is_mintable_name(home_parsed) or not is_mintable_name(away_parsed):
        exception = _exception_row(
            str(event["event_id"]),
            event_name,
            home_parsed or None,
            away_parsed or None,
            start_utc_str,
            "blank_team_name",
            "[]",
        )
        return None, MintResult(exception=exception)

    provider_key = _matchbook_provider_key(event)
    league_id = resolve_league_id(MATCHBOOK_PROVIDER, provider_key, league_aliases_df)
    season_id = derive_season_id(league_id, year)
    home_team_id = resolve_team_id(home_parsed, team_aliases_df)
    away_team_id = resolve_team_id(away_parsed, team_aliases_df)
    match_id = compute_canonical_match_id(
        league_id, season_id, date_str, home_team_id, away_team_id
    )

    result = MintResult(
        match_addition={
            "match_id": match_id,
            "season_id": season_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "kickoff_time": start_utc_str or None,
            "ht_score": None,
            "ft_score": None,
            "status_completed": False,
        }
    )

    for team_id, name in ((home_team_id, home_parsed), (away_team_id, away_parsed)):
        if team_id not in existing_team_ids:
            result.team_additions.append(
                {"team_id": team_id, "name": name, "similar_names": [name]}
            )
    if league_id not in existing_league_ids:
        result.league_additions.append(
            {"league_id": league_id, "name": provider_key, "is_tournament": False}
        )
    if season_id not in existing_season_ids:
        result.season_additions.append(
            {
                "season_id": season_id,
                "league_id": league_id,
                "name": str(year),
                "start_date": None,
                "end_date": None,
            }
        )
    return match_id, result


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
    match_rows: list[dict],
    team_rows: list[dict],
    league_rows: list[dict],
    season_rows: list[dict],
    *,
    conform_dir: Path,
    exceptions_dir: Path,
    additions_dir: Path,
    report: ConformReport,
    log: logging.Logger,
) -> None:
    """Write resolved-links, exceptions, and the four additions files atomically.

    Every file is always written (even empty) — the intermediate dbt models read
    them via ``read_parquet`` and require them to exist. Each additions frame is
    Pandera-validated before it is written (a blank team/league name raises).
    """
    resolved_df = pd.DataFrame(resolved_rows, columns=RESOLVED_COLUMNS)
    _write_parquet_atomic(resolved_df, conform_dir / "matchbook_resolved_links.parquet")
    report.resolved_count = len(resolved_df)

    exceptions_df = pd.DataFrame(exception_rows, columns=EXCEPTION_COLUMNS)
    _write_parquet_atomic(exceptions_df, exceptions_dir / "matchbook_unresolved.parquet")
    report.exceptions_count = len(exceptions_df)

    match_df = _validated_frame(match_rows, MATCH_ADDITION_COLUMNS, match_additions_schema)
    _write_parquet_atomic(match_df, additions_dir / "matchbook_canonical_match_additions.parquet")
    report.additions_count = len(match_df)

    team_df = _validated_frame(team_rows, TEAM_ADDITION_COLUMNS, team_additions_schema)
    _write_parquet_atomic(team_df, additions_dir / "matchbook_canonical_team_additions.parquet")

    league_df = _validated_frame(league_rows, LEAGUE_ADDITION_COLUMNS, league_additions_schema)
    _write_parquet_atomic(league_df, additions_dir / "matchbook_canonical_league_additions.parquet")

    season_df = _validated_frame(season_rows, SEASON_ADDITION_COLUMNS, season_additions_schema)
    _write_parquet_atomic(season_df, additions_dir / "matchbook_canonical_season_additions.parquet")

    log.info(
        "conform: resolved=%d, exceptions=%d, overrides=%d, additions=%d "
        "(team=%d, league=%d, season=%d)",
        report.resolved_count,
        report.exceptions_count,
        report.overrides_applied,
        report.additions_count,
        len(team_df),
        len(league_df),
        len(season_df),
    )


def _validated_frame(rows: list[dict], columns: list[str], schema) -> pd.DataFrame:
    """Build a column-ordered frame and validate it against its Pandera schema.

    An empty frame carries the declared columns so dbt's ``read_parquet`` finds a
    typed file; a populated frame is Pandera-validated (rejecting e.g. a blank
    team/league name) before it is written.
    """
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return frame
    return schema.validate(frame)


def _write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to Parquet atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    df.to_parquet(tmp_path, index=False)
    tmp_path.replace(path)
