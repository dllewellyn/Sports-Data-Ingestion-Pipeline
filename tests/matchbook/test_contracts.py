"""S1 — Matchbook bronze data contracts (Pydantic + Pandera).

Tests for MatchbookEventRecord (per-record Pydantic boundary) and
matchbook_events_bronze_schema (per-frame Pandera boundary).
"""

import pandas as pd
import pandera.errors
import pytest
from pydantic import ValidationError

from data_platform.models.schemas import MatchbookEventRecord
from data_platform.models.validation import matchbook_events_bronze_schema

# ── Helpers ────────────────────────────────────────────────────────────────────


def _valid_record() -> dict:
    """Minimal well-formed event dict (all required fields present)."""
    return {
        "event_id": "1234567",
        "event_name": "Arsenal vs Chelsea",
        "sport_id": 15,
        "status": "open",
        "start_utc": "2026-06-29T15:00:00Z",
        "volume": 50000.0,
        "ingested_at": "2026-06-29T12:00:00Z",
        "raw_event": '{"id": 1234567, "name": "Arsenal vs Chelsea", "markets": []}',
    }


def _valid_frame() -> pd.DataFrame:
    """Minimal well-typed DataFrame (two rows, all required columns)."""
    return pd.DataFrame(
        [
            {
                "event_id": "1234567",
                "event_name": "Arsenal vs Chelsea",
                "sport_id": 15,
                "status": "open",
                "start_utc": "2026-06-29T15:00:00Z",
                "volume": 50000.0,
                "ingested_at": "2026-06-29T12:00:00Z",
                "raw_event": '{"id": 1234567}',
            },
            {
                "event_id": "7654321",
                "event_name": "Bath vs Sale",
                "sport_id": 2,
                "status": "open",
                "start_utc": "2026-06-29T16:00:00Z",
                "volume": None,
                "ingested_at": "2026-06-29T12:00:00Z",
                "raw_event": '{"id": 7654321}',
            },
        ]
    )


# ── MatchbookEventRecord (Pydantic) ────────────────────────────────────────────


def test_valid_record_validates() -> None:
    """Well-formed event dict passes Pydantic validation (AC4)."""
    record = MatchbookEventRecord.model_validate(_valid_record())
    assert record.event_id == "1234567"
    assert record.event_name == "Arsenal vs Chelsea"
    assert record.sport_id == 15
    assert record.status == "open"
    assert record.volume == 50000.0


def test_valid_record_nullable_volume() -> None:
    """volume may be None (A7 — not all events have liquidity)."""
    data = {**_valid_record(), "volume": None}
    record = MatchbookEventRecord.model_validate(data)
    assert record.volume is None


def test_valid_record_extra_fields_ignored() -> None:
    """extra='ignore' — extra keys from the API don't cause a validation error."""
    data = {**_valid_record(), "venue": "Emirates Stadium", "markets": []}
    record = MatchbookEventRecord.model_validate(data)
    assert record.event_id == "1234567"


def test_missing_event_id_raises() -> None:
    """Missing event_id raises ValidationError (E5, E11)."""
    data = {k: v for k, v in _valid_record().items() if k != "event_id"}
    with pytest.raises(ValidationError):
        MatchbookEventRecord.model_validate(data)


def test_empty_event_id_raises() -> None:
    """Blank event_id raises ValidationError (E11)."""
    data = {**_valid_record(), "event_id": "  "}
    with pytest.raises(ValidationError):
        MatchbookEventRecord.model_validate(data)


def test_missing_start_utc_raises() -> None:
    """Missing start_utc raises ValidationError (E12)."""
    data = {k: v for k, v in _valid_record().items() if k != "start_utc"}
    with pytest.raises(ValidationError):
        MatchbookEventRecord.model_validate(data)


def test_none_start_utc_raises() -> None:
    """None start_utc raises ValidationError (E12)."""
    data = {**_valid_record(), "start_utc": None}
    with pytest.raises(ValidationError):
        MatchbookEventRecord.model_validate(data)


def test_missing_sport_id_raises() -> None:
    """Missing sport_id raises ValidationError (E11)."""
    data = {k: v for k, v in _valid_record().items() if k != "sport_id"}
    with pytest.raises(ValidationError):
        MatchbookEventRecord.model_validate(data)


def test_sport_id_coerced_from_string() -> None:
    """sport_id coerced from string to int."""
    data = {**_valid_record(), "sport_id": "15"}
    record = MatchbookEventRecord.model_validate(data)
    assert record.sport_id == 15


def test_raw_event_required() -> None:
    """raw_event is required and non-empty (AC3)."""
    data = {k: v for k, v in _valid_record().items() if k != "raw_event"}
    with pytest.raises(ValidationError):
        MatchbookEventRecord.model_validate(data)


def test_empty_raw_event_raises() -> None:
    """Blank raw_event raises ValidationError (AC3)."""
    data = {**_valid_record(), "raw_event": ""}
    with pytest.raises(ValidationError):
        MatchbookEventRecord.model_validate(data)


# ── matchbook_events_bronze_schema (Pandera) ───────────────────────────────────


def test_valid_frame_passes_schema() -> None:
    """Well-typed frame with all required columns passes Pandera schema (AC4)."""
    df = _valid_frame()
    validated = matchbook_events_bronze_schema.validate(df)
    assert len(validated) == 2


def test_frame_missing_raw_event_raises() -> None:
    """Frame without raw_event column raises SchemaError (AC3)."""
    df = _valid_frame().drop(columns=["raw_event"])
    with pytest.raises(pandera.errors.SchemaError):
        matchbook_events_bronze_schema.validate(df)


def test_frame_missing_event_id_raises() -> None:
    """Frame without event_id column raises SchemaError."""
    df = _valid_frame().drop(columns=["event_id"])
    with pytest.raises(pandera.errors.SchemaError):
        matchbook_events_bronze_schema.validate(df)


def test_frame_with_extra_columns_passes() -> None:
    """strict=False: extra columns ride along without failing schema."""
    df = _valid_frame()
    df["venue"] = "Emirates Stadium"
    validated = matchbook_events_bronze_schema.validate(df)
    assert "venue" in validated.columns
