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
