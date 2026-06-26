"""Pandera schema for the bronze DataFrame.

Pydantic validates individual records at ingest; Pandera validates the assembled
DataFrame (column presence, dtypes, nullability, value ranges) before it is
written to Parquet. Two complementary gates before data ever lands in bronze.
"""

from __future__ import annotations

import pandera.pandas as pa

bronze_users_schema = pa.DataFrameSchema(
    {
        "id": pa.Column(int, pa.Check.ge(1), unique=True, nullable=False),
        "name": pa.Column(str, nullable=False),
        "username": pa.Column(str, nullable=False),
        "email": pa.Column(str, pa.Check.str_contains("@"), nullable=False),
        "phone": pa.Column(str, nullable=True),
        "website": pa.Column(str, nullable=True),
        "company_name": pa.Column(str, nullable=False),
        "city": pa.Column(str, nullable=False),
        "zipcode": pa.Column(str, nullable=True),
        "lat": pa.Column(float, nullable=False),
        "lng": pa.Column(float, nullable=False),
    },
    strict=True,
    coerce=True,
)


# --- football-data.co.uk bronze frame contracts (D4, D5) -----------------------
# These are deliberately OPEN (`strict=False`): they enforce only the mandatory
# per-family core and let the wide, drift-prone optional odds/stat columns ride
# along untouched (main-family E0 grows 7 → 106 columns across 30 years; a strict
# wide schema is impossible). A frame MISSING a core column still fails. The
# matching per-record cores are enforced upstream by Pydantic (schemas.py).

main_bronze_schema = pa.DataFrameSchema(
    {
        "Div": pa.Column(str, nullable=False),
        "Date": pa.Column(str, nullable=False),
        "HomeTeam": pa.Column(str, nullable=False),
        "AwayTeam": pa.Column(str, nullable=False),
        "FTHG": pa.Column(int, pa.Check.ge(0), nullable=False, coerce=True),
        "FTAG": pa.Column(int, pa.Check.ge(0), nullable=False, coerce=True),
        "FTR": pa.Column(str, pa.Check.isin(["H", "D", "A"]), nullable=False),
    },
    strict=False,
    coerce=True,
)
