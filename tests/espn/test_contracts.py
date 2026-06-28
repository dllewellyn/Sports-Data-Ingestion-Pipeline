"""S3 — ESPN bronze record (Pydantic) + frame (Pandera, strict=False) contracts.

These validate the FLATTENED bronze row (one dict per event with the mandatory
core keys), NOT the raw nested ESPN scoreboard JSON. Core = espn_event_id,
kickoff_time, home_team_id, home_team_name, away_team_id, away_team_name,
status_name. Events missing a core field fail the record contract (skip-and-count,
E3); the open frame contract requires the core but lets the wide ESPN payload
(scores, season fields, venue, ...) ride along.
"""

import pandas as pd
import pytest
from pandera.errors import SchemaError, SchemaErrors
from pydantic import ValidationError

from data_platform.models.schemas import EspnEventRecord
from data_platform.models.validation import espn_bronze_schema

VALID_ROW = {
    "espn_event_id": "401547438",
    "kickoff_time": "2024-08-16T19:00Z",
    "home_team_id": "359",
    "home_team_name": "Arsenal",
    "away_team_id": "360",
    "away_team_name": "Wolverhampton Wanderers",
    "status_name": "STATUS_SCHEDULED",
}


def test_valid_core_record_parses() -> None:
    rec = EspnEventRecord.model_validate(VALID_ROW)
    assert rec.espn_event_id == "401547438"
    assert rec.home_team_name == "Arsenal"
    assert rec.status_name == "STATUS_SCHEDULED"


def test_numeric_ids_coerced_to_str() -> None:
    rec = EspnEventRecord.model_validate(
        {**VALID_ROW, "espn_event_id": 401547438, "home_team_id": 359, "away_team_id": 360}
    )
    assert rec.espn_event_id == "401547438"
    assert rec.home_team_id == "359"
    assert rec.away_team_id == "360"


def test_record_missing_event_id_rejected() -> None:
    bad = {k: v for k, v in VALID_ROW.items() if k != "espn_event_id"}
    with pytest.raises(ValidationError):
        EspnEventRecord.model_validate(bad)


def test_record_missing_home_competitor_rejected() -> None:
    bad = {k: v for k, v in VALID_ROW.items() if k not in {"home_team_id", "home_team_name"}}
    with pytest.raises(ValidationError):
        EspnEventRecord.model_validate(bad)


def test_record_missing_away_competitor_rejected() -> None:
    bad = {k: v for k, v in VALID_ROW.items() if k not in {"away_team_id", "away_team_name"}}
    with pytest.raises(ValidationError):
        EspnEventRecord.model_validate(bad)


def test_record_missing_status_rejected() -> None:
    bad = {k: v for k, v in VALID_ROW.items() if k != "status_name"}
    with pytest.raises(ValidationError):
        EspnEventRecord.model_validate(bad)


def test_record_blank_core_field_rejected() -> None:
    with pytest.raises(ValidationError):
        EspnEventRecord.model_validate({**VALID_ROW, "home_team_name": "  "})


def test_frame_missing_core_column_fails() -> None:
    frame = pd.DataFrame([{k: v for k, v in VALID_ROW.items() if k != "home_team_id"}])
    with pytest.raises((SchemaError, SchemaErrors)):
        espn_bronze_schema.validate(frame)


def test_wide_frame_extra_columns_ride_along() -> None:
    frame = pd.DataFrame(
        [
            {
                **VALID_ROW,
                "home_score": 2,
                "away_score": 1,
                "season_year": 2024,
                "venue": "Emirates Stadium",
            },
            {
                "espn_event_id": "401547439",
                "kickoff_time": "2024-08-17T14:00Z",
                "home_team_id": "364",
                "home_team_name": "Liverpool",
                "away_team_id": "331",
                "away_team_name": "Brentford",
                "status_name": "STATUS_FINAL",
                "home_score": 2,
                "away_score": 0,
                "season_year": 2024,
                "venue": "Anfield",
            },
        ]
    )
    validated = espn_bronze_schema.validate(frame)
    for col in ("home_score", "away_score", "season_year", "venue"):
        assert col in validated.columns, "extra ESPN columns ride along"
