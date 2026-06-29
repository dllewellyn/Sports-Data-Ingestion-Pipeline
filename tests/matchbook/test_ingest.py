"""S2 — Matchbook events ingest engine tests.

Tests for authenticate(), fetch_events(), ingest_sport(), run_matchbook_events_ingest().
All HTTP is mocked; no live network calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data_platform.matchbook.ingest import (
    IngestionReport,
    authenticate,
    fetch_events,
    flatten_event,
    ingest_sport,
    run_matchbook_events_ingest,
)
from data_platform.models.validation import matchbook_events_bronze_schema

# ── Helpers ────────────────────────────────────────────────────────────────────

BASE_URL = "https://api.matchbook.com"
BATCH_TS = "20260629T120000Z"
RUN_DATE = "2026-06-29"


def _mock_auth_response(token: str = "test-token-abc") -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"session-token": token}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_events_response(events: list[dict], total: int | None = None) -> MagicMock:
    resp = MagicMock()
    payload: dict = {"events": events}
    if total is not None:
        payload["total"] = total
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _valid_event(event_id: str = "123456", sport_id: int = 15) -> dict:
    """A minimal well-formed Matchbook event dict from the API."""
    return {
        "id": event_id,
        "name": f"Arsenal vs Chelsea ({event_id})",
        "sport-id": sport_id,
        "status": "open",
        "start": "2026-06-29T15:00:00Z",
        "volume": 50000.0,
        "markets": [{"id": 1, "name": "Match Odds"}],
        "venue": "Emirates Stadium",
    }


# ── authenticate() ─────────────────────────────────────────────────────────────


def test_authenticate_returns_token() -> None:
    """Successful auth returns the session token string (AC11)."""
    with patch("requests.Session.post", return_value=_mock_auth_response("tok123")):
        token = authenticate("user", "pass", base_url=BASE_URL, timeout=10)
    assert token == "tok123"


def test_authenticate_raises_on_missing_token() -> None:
    """Auth response with no session-token raises ValueError (E3, AC16)."""
    resp = MagicMock()
    resp.json.return_value = {}
    resp.raise_for_status = MagicMock()
    with patch("requests.Session.post", return_value=resp):
        with pytest.raises(ValueError, match="session-token"):
            authenticate("user", "pass", base_url=BASE_URL, timeout=10)


def test_authenticate_raises_on_non_2xx() -> None:
    """Non-2xx auth response raises (E1, AC16)."""
    resp = MagicMock()
    resp.raise_for_status.side_effect = Exception("401 Unauthorized")
    with patch("requests.Session.post", return_value=resp):
        with pytest.raises(Exception):
            authenticate("user", "pass", base_url=BASE_URL, timeout=10)


def test_authenticate_raises_on_empty_username() -> None:
    """Empty username raises ValueError before any HTTP call (E2, AC6)."""
    with patch("requests.Session.post") as mock_post:
        with pytest.raises(ValueError, match="credentials"):
            authenticate("", "pass", base_url=BASE_URL, timeout=10)
        mock_post.assert_not_called()


def test_authenticate_raises_on_empty_password() -> None:
    """Empty password raises ValueError before any HTTP call (E2, AC6)."""
    with patch("requests.Session.post") as mock_post:
        with pytest.raises(ValueError, match="credentials"):
            authenticate("user", "", base_url=BASE_URL, timeout=10)
        mock_post.assert_not_called()


# ── fetch_events() ─────────────────────────────────────────────────────────────


def test_fetch_events_paginates_all_pages() -> None:
    """fetch_events accumulates events across pages when total > per_page."""
    page1 = [_valid_event(str(i)) for i in range(20)]
    page2 = [_valid_event(str(i)) for i in range(20, 25)]
    responses = [
        _mock_events_response(page1, total=25),
        _mock_events_response(page2, total=25),
    ]
    with patch("requests.Session.get", side_effect=responses):
        events = fetch_events("tok", 15, base_url=BASE_URL, per_page=20, timeout=10)
    assert len(events) == 25


def test_fetch_events_returns_empty_list_for_zero_events() -> None:
    """Zero total returns empty list without error (E7)."""
    with patch("requests.Session.get", return_value=_mock_events_response([], total=0)):
        events = fetch_events("tok", 15, base_url=BASE_URL, per_page=20, timeout=10)
    assert events == []


def test_fetch_events_raises_on_non_2xx() -> None:
    """Non-2xx response from events endpoint raises (E4)."""
    resp = MagicMock()
    resp.raise_for_status.side_effect = Exception("503 Service Unavailable")
    with patch("requests.Session.get", return_value=resp):
        with pytest.raises(Exception):
            fetch_events("tok", 15, base_url=BASE_URL, per_page=20, timeout=10)


def test_fetch_events_treats_absent_total_as_single_page(caplog) -> None:
    """If total is absent, treat as single page and log a warning (E13)."""
    events = [_valid_event("1")]
    with patch("requests.Session.get", return_value=_mock_events_response(events)):
        result = fetch_events("tok", 15, base_url=BASE_URL, per_page=20, timeout=10)
    assert len(result) == 1


# ── flatten_event() ────────────────────────────────────────────────────────────


def test_flatten_event_projects_required_columns() -> None:
    """flatten_event produces all required structured columns (AC4)."""
    raw = _valid_event("999")
    row = flatten_event(raw, ingested_at="2026-06-29T12:00:00Z")
    assert row["event_id"] == "999"
    assert row["event_name"] == "Arsenal vs Chelsea (999)"
    assert row["sport_id"] == 15
    assert row["status"] == "open"
    assert row["start_utc"] == "2026-06-29T15:00:00Z"
    assert row["volume"] == 50000.0
    assert row["ingested_at"] == "2026-06-29T12:00:00Z"


def test_flatten_event_raw_event_contains_full_dict() -> None:
    """raw_event round-trips to original dict including non-projected fields (AC3)."""
    raw = _valid_event("999")
    row = flatten_event(raw, ingested_at="2026-06-29T12:00:00Z")
    recovered = json.loads(row["raw_event"])
    # Non-projected fields must be recoverable
    assert "markets" in recovered
    assert "venue" in recovered
    assert recovered["venue"] == "Emirates Stadium"
    assert recovered["markets"][0]["name"] == "Match Odds"


# ── ingest_sport() ─────────────────────────────────────────────────────────────


def test_ingest_sport_writes_parquet_at_correct_path(tmp_path: Path) -> None:
    """ingest_sport writes Parquet at out_dir/sport_name/YYYY-MM-DD/batch_ts.parquet (AC1, AC2)."""
    events = [_valid_event("1"), _valid_event("2")]
    with patch("requests.Session.get", return_value=_mock_events_response(events, total=2)):
        result, _failures = ingest_sport(
            sport_id=15,
            sport_name="football",
            session_token="tok",
            base_url=BASE_URL,
            per_page=20,
            timeout=10,
            out_dir=tmp_path,
            batch_ts=BATCH_TS,
            run_date=RUN_DATE,
            log=None,
            schema=matchbook_events_bronze_schema,
        )
    assert result is not None
    assert result.exists()
    expected = tmp_path / "football" / "2026-06-29" / f"{BATCH_TS}.parquet"
    assert result == expected


def test_ingest_sport_parquet_has_all_columns(tmp_path: Path) -> None:
    """Parquet rows contain all structured columns (AC4)."""
    events = [_valid_event("1")]
    with patch("requests.Session.get", return_value=_mock_events_response(events, total=1)):
        result, _ = ingest_sport(
            sport_id=15,
            sport_name="football",
            session_token="tok",
            base_url=BASE_URL,
            per_page=20,
            timeout=10,
            out_dir=tmp_path,
            batch_ts=BATCH_TS,
            run_date=RUN_DATE,
            log=None,
            schema=matchbook_events_bronze_schema,
        )
    df = pd.read_parquet(result)
    for col in ["event_id", "event_name", "sport_id", "status", "start_utc", "volume", "ingested_at", "raw_event"]:
        assert col in df.columns, f"missing column: {col}"


def test_ingest_sport_raw_event_preserves_non_projected_fields(tmp_path: Path) -> None:
    """raw_event in Parquet contains the full original dict (AC3 faithful-bronze test)."""
    events = [_valid_event("1")]
    with patch("requests.Session.get", return_value=_mock_events_response(events, total=1)):
        result, _ = ingest_sport(
            sport_id=15,
            sport_name="football",
            session_token="tok",
            base_url=BASE_URL,
            per_page=20,
            timeout=10,
            out_dir=tmp_path,
            batch_ts=BATCH_TS,
            run_date=RUN_DATE,
            log=None,
            schema=matchbook_events_bronze_schema,
        )
    df = pd.read_parquet(result)
    recovered = json.loads(df.iloc[0]["raw_event"])
    assert "venue" in recovered  # non-projected field
    assert "markets" in recovered  # non-projected nested data


def test_ingest_sport_returns_none_for_zero_events(tmp_path: Path) -> None:
    """Zero events returns (None, 0), no Parquet written (E7)."""
    with patch("requests.Session.get", return_value=_mock_events_response([], total=0)):
        result, failures = ingest_sport(
            sport_id=15,
            sport_name="football",
            session_token="tok",
            base_url=BASE_URL,
            per_page=20,
            timeout=10,
            out_dir=tmp_path,
            batch_ts=BATCH_TS,
            run_date=RUN_DATE,
            log=None,
            schema=matchbook_events_bronze_schema,
        )
    assert result is None
    assert failures == 0
    assert not list(tmp_path.rglob("*.parquet"))


def test_ingest_sport_creates_directory_on_first_run(tmp_path: Path) -> None:
    """Directory is created if it doesn't exist on first run."""
    events = [_valid_event("1")]
    out_dir = tmp_path / "new_dir"
    assert not out_dir.exists()
    with patch("requests.Session.get", return_value=_mock_events_response(events, total=1)):
        ingest_sport(
            sport_id=15,
            sport_name="football",
            session_token="tok",
            base_url=BASE_URL,
            per_page=20,
            timeout=10,
            out_dir=out_dir,
            batch_ts=BATCH_TS,
            run_date=RUN_DATE,
            log=None,
            schema=matchbook_events_bronze_schema,
        )
    assert (out_dir / "football" / "2026-06-29").exists()


def test_ingest_sport_replay_appends_new_file(tmp_path: Path) -> None:
    """Two runs on the same date create two distinct files (E10, AC5)."""
    events = [_valid_event("1")]
    shared_args = dict(
        sport_id=15,
        sport_name="football",
        session_token="tok",
        base_url=BASE_URL,
        per_page=20,
        timeout=10,
        out_dir=tmp_path,
        run_date=RUN_DATE,
        log=None,
        schema=matchbook_events_bronze_schema,
    )
    with patch("requests.Session.get", return_value=_mock_events_response(events, total=1)):
        r1, _ = ingest_sport(**shared_args, batch_ts="20260629T120000Z")
    with patch("requests.Session.get", return_value=_mock_events_response(events, total=1)):
        r2, _ = ingest_sport(**shared_args, batch_ts="20260629T180000Z")
    assert r1 != r2
    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert len(parquet_files) == 2


def test_ingest_sport_per_record_failures_counted_not_raised(tmp_path: Path) -> None:
    """Per-record Pydantic failures are counted; valid records written; no raise (AC7, E5)."""
    good_event = _valid_event("1")
    bad_event = {"id": "", "name": "Bad", "sport-id": 15, "status": "open", "start": "bad"}  # invalid event_id
    events = [good_event, bad_event]
    with patch("requests.Session.get", return_value=_mock_events_response(events, total=2)):
        result, failure_count = ingest_sport(
            sport_id=15,
            sport_name="football",
            session_token="tok",
            base_url=BASE_URL,
            per_page=20,
            timeout=10,
            out_dir=tmp_path,
            batch_ts=BATCH_TS,
            run_date=RUN_DATE,
            log=None,
            schema=matchbook_events_bronze_schema,
        )
    # ingest_sport should return the path (not raise) and write 1 valid row
    assert result is not None
    assert failure_count == 1
    df = pd.read_parquet(result)
    assert len(df) == 1


def test_ingest_sport_atomic_no_partial_file_on_failure(tmp_path: Path) -> None:
    """If the rename fails, no partial file is left at the final path (AC8, E9)."""
    events = [_valid_event("1")]
    final_path = tmp_path / "football" / "2026-06-29" / f"{BATCH_TS}.parquet"

    def _failing_replace(self, target):
        raise OSError("disk full")

    with patch("requests.Session.get", return_value=_mock_events_response(events, total=1)):
        with patch("pathlib.Path.replace", _failing_replace):
            with pytest.raises(OSError):
                ingest_sport(
                    sport_id=15,
                    sport_name="football",
                    session_token="tok",
                    base_url=BASE_URL,
                    per_page=20,
                    timeout=10,
                    out_dir=tmp_path,
                    batch_ts=BATCH_TS,
                    run_date=RUN_DATE,
                    log=None,
                    schema=matchbook_events_bronze_schema,
                )
    assert not final_path.exists()


# ── run_matchbook_events_ingest() ──────────────────────────────────────────────


def test_run_ingest_writes_both_sports(tmp_path: Path) -> None:
    """Both football and rugby_union Parquets written on a successful run (AC1, AC2)."""
    football_events = [_valid_event("1", sport_id=15)]
    rugby_events = [_valid_event("2", sport_id=2)]

    # Each sport makes one GET (1 page each); football first, then rugby
    responses = [
        _mock_events_response(football_events, total=1),
        _mock_events_response(rugby_events, total=1),
    ]
    with patch("requests.Session.post", return_value=_mock_auth_response()):
        with patch("requests.Session.get", side_effect=responses):
            report = run_matchbook_events_ingest(
                username="user",
                password="pass",
                base_url=BASE_URL,
                per_page=20,
                timeout=10,
                out_dir=tmp_path,
                log=None,
                schema=matchbook_events_bronze_schema,
            )
    assert len(report.written) == 2
    assert len(report.failed) == 0


def test_run_ingest_zero_events_all_sports_succeeds(tmp_path: Path) -> None:
    """Zero events for all sports: run succeeds, no Parquet written (E8)."""
    with patch("requests.Session.post", return_value=_mock_auth_response()):
        with patch("requests.Session.get", return_value=_mock_events_response([], total=0)):
            report = run_matchbook_events_ingest(
                username="user",
                password="pass",
                base_url=BASE_URL,
                per_page=20,
                timeout=10,
                out_dir=tmp_path,
                log=None,
                schema=matchbook_events_bronze_schema,
            )
    assert not list(tmp_path.rglob("*.parquet"))
    assert len(report.written) == 0


def test_run_ingest_zero_events_one_sport_continues(tmp_path: Path) -> None:
    """Zero football, 1 rugby — no football Parquet, rugby Parquet written (E7)."""
    rugby_events = [_valid_event("2", sport_id=2)]

    # football GET returns 0 events, rugby GET returns 1
    responses = [
        _mock_events_response([], total=0),
        _mock_events_response(rugby_events, total=1),
    ]
    with patch("requests.Session.post", return_value=_mock_auth_response()):
        with patch("requests.Session.get", side_effect=responses):
            report = run_matchbook_events_ingest(
                username="user",
                password="pass",
                base_url=BASE_URL,
                per_page=20,
                timeout=10,
                out_dir=tmp_path,
                log=None,
                schema=matchbook_events_bronze_schema,
            )
    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert len(parquet_files) == 1
    assert "rugby_union" in str(parquet_files[0])
    assert len(report.written) == 1


def test_run_ingest_reraises_on_failures(tmp_path: Path) -> None:
    """run_matchbook_events_ingest re-raises at end when any sport had per-record failures (AC7)."""
    # One valid + one invalid event for football; zero events for rugby.
    # failure_count=1 should trigger re-raise even though one valid row was written.
    good_event = _valid_event("1")
    bad_event = {"id": "", "name": "x", "sport-id": 15, "status": "open", "start": "bad"}

    responses = [
        _mock_events_response([good_event, bad_event], total=2),  # football: 1 valid + 1 bad
        _mock_events_response([], total=0),  # rugby: no events
    ]
    with patch("requests.Session.post", return_value=_mock_auth_response()):
        with patch("requests.Session.get", side_effect=responses):
            with pytest.raises(RuntimeError, match="failures"):
                run_matchbook_events_ingest(
                    username="user",
                    password="pass",
                    base_url=BASE_URL,
                    per_page=20,
                    timeout=10,
                    out_dir=tmp_path,
                    log=None,
                    schema=matchbook_events_bronze_schema,
                )


# ── OTel span ──────────────────────────────────────────────────────────────────


def test_otel_span_emitted(tmp_path: Path) -> None:
    """OTel span 'ingest.matchbook_events' emitted during ingest (telemetry convention)."""
    events = [_valid_event("1")]
    spans_started: list[str] = []

    class _TrackingSpan:
        def set_attribute(self, *a, **k) -> None: ...

        def __enter__(self) -> "_TrackingSpan":
            return self

        def __exit__(self, *a) -> bool:
            return False

    class _TrackingTracer:
        def start_as_current_span(self, name: str, **kwargs) -> _TrackingSpan:
            spans_started.append(name)
            return _TrackingSpan()

    with patch(
        "data_platform.matchbook.ingest.get_tracer", return_value=_TrackingTracer()
    ):
        with patch("requests.Session.post", return_value=_mock_auth_response()):
            with patch(
                "requests.Session.get",
                return_value=_mock_events_response(events, total=1),
            ):
                run_matchbook_events_ingest(
                    username="user",
                    password="pass",
                    base_url=BASE_URL,
                    per_page=20,
                    timeout=10,
                    out_dir=tmp_path,
                    log=None,
                    schema=matchbook_events_bronze_schema,
                )

    assert "ingest.matchbook_events" in spans_started
