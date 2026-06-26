"""S8 — extra-family record (Pydantic) + frame (Pandera, strict=False) contracts.

Core = Country, League, Season, Date, Home, Away, HG, AG, Res — a DIFFERENT core
from the main family (D5): season/country provenance is carried in-file. Rejections
are deterministic (same input → same rejects).
"""

import math

import pandas as pd
import pytest
from pandera.errors import SchemaError, SchemaErrors
from pydantic import ValidationError

from data_platform.models.schemas import ExtraMatchRecord
from data_platform.models.validation import extra_bronze_schema

VALID_ROW = {
    "Country": "Argentina",
    "League": "Argentina Liga Profesional",
    "Season": "2024",
    "Date": "26/01/2024",
    "Home": "Boca Juniors",
    "Away": "River Plate",
    "HG": 1,
    "AG": 0,
    "Res": "H",
}


def test_valid_extra_row_parses() -> None:
    rec = ExtraMatchRecord.model_validate(VALID_ROW)
    assert rec.Country == "Argentina"
    assert rec.Season == "2024"
    assert rec.HG == 1 and rec.AG == 0 and rec.Res == "H"


def test_blank_row_rejected() -> None:
    blank = {k: ("" if isinstance(v, str) else math.nan) for k, v in VALID_ROW.items()}
    with pytest.raises(ValidationError):
        ExtraMatchRecord.model_validate(blank)


def test_missing_required_field_rejected() -> None:
    bad = {**VALID_ROW, "HG": math.nan}
    with pytest.raises(ValidationError):
        ExtraMatchRecord.model_validate(bad)


def test_rejection_is_deterministic() -> None:
    rows = [VALID_ROW, {**VALID_ROW, "Home": ""}, {**VALID_ROW, "Res": "Z"}]

    def reject_indices() -> list[int]:
        out = []
        for i, row in enumerate(rows):
            try:
                ExtraMatchRecord.model_validate(row)
            except ValidationError:
                out.append(i)
        return out

    assert reject_indices() == reject_indices() == [1, 2]


def test_frame_with_optionals_passes() -> None:
    frame = pd.DataFrame(
        [
            {**VALID_ROW, "PSH": 2.1, "PSD": 3.4, "PSA": 3.8},
            {
                **VALID_ROW,
                "Home": "Racing Club",
                "Away": "Independiente",
                "Res": "D",
                "HG": 2,
                "AG": 2,
            },
        ]
    )
    validated = extra_bronze_schema.validate(frame)
    assert "PSH" in validated.columns


def test_frame_missing_core_column_fails() -> None:
    frame = pd.DataFrame([{k: v for k, v in VALID_ROW.items() if k != "Season"}])
    with pytest.raises((SchemaError, SchemaErrors)):
        extra_bronze_schema.validate(frame)
