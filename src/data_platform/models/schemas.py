"""Pydantic v2 models for the source API payload.

This is the "validate data as it comes in" layer at the edge of the system:
every record from the API is parsed/validated here before it is allowed any
further. Invalid records raise immediately rather than silently corrupting bronze.

(Plain dataclasses are still part of stdlib, but they do no validation or
coercion — Pydantic v2 is the current best-in-class choice for this boundary.)
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Geo(BaseModel):
    lat: float
    lng: float


class Address(BaseModel):
    street: str
    suite: str = ""
    city: str
    zipcode: str
    geo: Geo


class Company(BaseModel):
    name: str


class User(BaseModel):
    """One user record as returned by the source API."""

    id: int = Field(ge=1)
    name: str
    username: str
    email: str  # source data is not RFC-strict; keep as str, dbt asserts shape
    phone: str = ""
    website: str = ""
    address: Address
    company: Company

    def to_flat(self) -> dict:
        """Flatten the nested record into a single bronze row."""
        return {
            "id": self.id,
            "name": self.name,
            "username": self.username,
            "email": self.email,
            "phone": self.phone,
            "website": self.website,
            "company_name": self.company.name,
            "city": self.address.city,
            "zipcode": self.address.zipcode,
            "lat": self.address.geo.lat,
            "lng": self.address.geo.lng,
        }


def _missing(v: object) -> bool:
    """True for the empty/footer/blank values that pepper football-data CSVs."""
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return isinstance(v, str) and v.strip() == ""


# --- football-data.co.uk bronze record contracts (D4, D5) ----------------------
# Two families, two cores. `extra="ignore"` lets the wide optional odds/stat
# columns ride along at the frame level (Pandera) without bloating the record.


class MainMatchRecord(BaseModel):
    """One main-family (`mmz4281/<season>/<div>.csv`) record — mandatory 7-field core.

    Blank/footer/incomplete rows fail here and are skipped-and-counted by the
    ingestor (E1, E4). Goals are coerced from the float/str shapes pandas produces.
    """

    model_config = ConfigDict(extra="ignore")

    Div: str
    Date: str
    HomeTeam: str
    AwayTeam: str
    FTHG: int
    FTAG: int
    FTR: str

    @field_validator("Div", "Date", "HomeTeam", "AwayTeam", "FTR", mode="before")
    @classmethod
    def _required_text(cls, v: object) -> str:
        if _missing(v):
            raise ValueError("required core field empty")
        return str(v).strip()

    @field_validator("FTHG", "FTAG", mode="before")
    @classmethod
    def _required_goals(cls, v: object) -> int:
        if _missing(v):
            raise ValueError("required goal count missing")
        return int(float(v))

    @field_validator("FTR")
    @classmethod
    def _result_domain(cls, v: str) -> str:
        if v not in {"H", "D", "A"}:
            raise ValueError("FTR must be one of H/D/A")
        return v


class ExtraMatchRecord(BaseModel):
    """One extra-family (`new/<CODE>.csv`) record — mandatory 9-field core.

    A DIFFERENT core/keys from the main family (D5): country/league/season
    provenance is carried in-file. Goals are coerced; blank rows are rejected
    deterministically (same input → same rejects).
    """

    model_config = ConfigDict(extra="ignore")

    Country: str
    League: str
    Season: str
    Date: str
    Home: str
    Away: str
    HG: int
    AG: int
    Res: str

    @field_validator("Country", "League", "Season", "Date", "Home", "Away", "Res", mode="before")
    @classmethod
    def _required_text(cls, v: object) -> str:
        if _missing(v):
            raise ValueError("required core field empty")
        return str(v).strip()

    @field_validator("HG", "AG", mode="before")
    @classmethod
    def _required_goals(cls, v: object) -> int:
        if _missing(v):
            raise ValueError("required goal count missing")
        return int(float(v))

    @field_validator("Res")
    @classmethod
    def _result_domain(cls, v: str) -> str:
        if v not in {"H", "D", "A"}:
            raise ValueError("Res must be one of H/D/A")
        return v


class MatchbookOddsRecord(BaseModel):
    """One Matchbook odds tick — validated at the Redis pub/sub boundary.

    Required fields (non-nullable in bronze): event_id, market_id, runner_id,
    ingested_at, in_running. All price/volume/depth fields are nullable.
    ingested_at is epoch milliseconds (int); Arrow casts to timestamp[ms, UTC].
    """

    model_config = ConfigDict(extra="ignore")

    event_id: int
    market_id: int
    runner_id: int
    ingested_at: int
    in_running: bool
    sport_id: int | None = None
    market_type: str | None = None
    market_status: str | None = None
    best_back_price: float | None = None
    best_back_available: float | None = None
    best_lay_price: float | None = None
    best_lay_available: float | None = None
    back_price_2: float | None = None
    back_available_2: float | None = None
    back_price_3: float | None = None
    back_available_3: float | None = None
    lay_price_2: float | None = None
    lay_available_2: float | None = None
    lay_price_3: float | None = None
    lay_available_3: float | None = None
    back_depth: float | None = None
    lay_depth: float | None = None
    wom: float | None = None
    market_volume: float | None = None
    runner_volume: float | None = None
    handicap_line: float | None = None
    event_participant_id: int | None = None
    kickoff_ms: int | None = None


__all__ = [
    "User",
    "Address",
    "Company",
    "Geo",
    "MainMatchRecord",
    "ExtraMatchRecord",
    "MatchbookOddsRecord",
]
