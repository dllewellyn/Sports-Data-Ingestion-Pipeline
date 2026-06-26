"""S6 — main-family record (Pydantic) + frame (Pandera, strict=False) contracts.

Core = Div, Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR. Blank/footer rows fail the
record contract (skip-and-count); the open frame contract requires the core but
tolerates the wide optional-odds column sprawl (7 → 106 columns across eras).
"""

import math

import pandas as pd
import pytest
from pandera.errors import SchemaError, SchemaErrors
from pydantic import ValidationError

from data_platform.models.schemas import MainMatchRecord
from data_platform.models.validation import main_bronze_schema

VALID_ROW = {
    "Div": "E0",
    "Date": "14/08/93",
    "HomeTeam": "Arsenal",
    "AwayTeam": "Coventry",
    "FTHG": 0,
    "FTAG": 3,
    "FTR": "A",
}


def test_valid_main_row_parses() -> None:
    rec = MainMatchRecord.model_validate(VALID_ROW)
    assert rec.HomeTeam == "Arsenal"
    assert rec.FTHG == 0 and rec.FTAG == 3
    assert rec.FTR == "A"


def test_blank_footer_row_rejected() -> None:
    # A trailing blank row from 9394/E0.csv: all-empty / NaN.
    blank = {k: ("" if isinstance(v, str) else math.nan) for k, v in VALID_ROW.items()}
    with pytest.raises(ValidationError):
        MainMatchRecord.model_validate(blank)


def test_row_missing_goals_rejected() -> None:
    bad = {**VALID_ROW, "FTHG": math.nan}
    with pytest.raises(ValidationError):
        MainMatchRecord.model_validate(bad)


def test_invalid_result_code_rejected() -> None:
    with pytest.raises(ValidationError):
        MainMatchRecord.model_validate({**VALID_ROW, "FTR": "X"})


def test_goals_coerced_from_float_strings() -> None:
    rec = MainMatchRecord.model_validate({**VALID_ROW, "FTHG": "2", "FTAG": 1.0})
    assert rec.FTHG == 2 and rec.FTAG == 1


def test_frame_with_optional_odds_columns_passes() -> None:
    frame = pd.DataFrame(
        [
            {**VALID_ROW, "B365H": 2.1, "B365D": 3.2, "B365A": 3.5},
            {
                "Div": "E0",
                "Date": "14/08/93",
                "HomeTeam": "Liverpool",
                "AwayTeam": "Sheffield Weds",
                "FTHG": 2,
                "FTAG": 0,
                "FTR": "H",
                "B365H": 1.8,
                "B365D": 3.4,
                "B365A": 4.0,
            },
        ]
    )
    validated = main_bronze_schema.validate(frame)
    assert "B365H" in validated.columns, "optional odds columns ride along"


def test_frame_missing_core_column_fails() -> None:
    frame = pd.DataFrame([{k: v for k, v in VALID_ROW.items() if k != "FTR"}])
    with pytest.raises((SchemaError, SchemaErrors)):
        main_bronze_schema.validate(frame)
