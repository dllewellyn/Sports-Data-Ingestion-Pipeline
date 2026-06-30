"""Pydantic v2 models for bronze ingest validation.

This is the "validate data as it comes in" layer at the edge of the system:
every record from the API is parsed/validated here before it is allowed any
further. Invalid records raise immediately rather than silently corrupting bronze.

(Plain dataclasses are still part of stdlib, but they do no validation or
coercion — Pydantic v2 is the current best-in-class choice for this boundary.)
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _missing(v: object) -> bool:
    """True for the empty/footer/blank values that pepper football-data CSVs."""
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return isinstance(v, str) and v.strip() == ""


# --- football-data.co.uk bronze record contracts (D4, D5) ----------------------


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


# --- ESPN scoreboard bronze record contract (S3) -------------------------------
# Validates the FLATTENED bronze row (one dict per event), NOT the raw nested
# scoreboard JSON (the ingest engine does the flattening). The mandatory core is
# enforced per record; `extra="ignore"` lets the wide ESPN payload (scores, season
# fields, venue, ...) ride along at the frame level (Pandera) without bloating the
# record. ESPN ids are numeric — coerced to str so the bronze layer stores strings.


class EspnEventRecord(BaseModel):
    """One flattened ESPN scoreboard event — mandatory core enforced per record.

    Events missing a core field (event id, kickoff date, or a home/away
    competitor) fail here and are skipped-and-counted by the ingestor (E3).
    """

    model_config = ConfigDict(extra="ignore")

    espn_event_id: str
    kickoff_time: str
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str
    status_name: str
    # The complete original event JSON, preserved verbatim (faithful bronze): every
    # field ESPN sent is recoverable from this string without re-fetching. Required
    # and non-empty so a row can never silently drop the source payload.
    raw_event: str

    @field_validator(
        "espn_event_id",
        "kickoff_time",
        "home_team_id",
        "home_team_name",
        "away_team_id",
        "away_team_name",
        "status_name",
        "raw_event",
        mode="before",
    )
    @classmethod
    def _required_text(cls, v: object) -> str:
        if _missing(v):
            raise ValueError("required core field empty")
        return str(v).strip()


class MatchbookEventRecord(BaseModel):
    """One Matchbook open event — mandatory core enforced per record.

    Events missing a core field (event id, name, status, start time) fail here
    and are skipped-and-counted by the ingestor (E5, E11, E12). volume is nullable
    since not all events have matched liquidity. The complete original event JSON
    is preserved verbatim in ``raw_event`` so bronze stays faithful to source.
    """

    model_config = ConfigDict(extra="ignore")

    event_id: str
    event_name: str
    sport_id: int
    status: str
    start_utc: str
    volume: float | None = None
    ingested_at: str
    # The complete original event JSON, preserved verbatim (faithful bronze).
    raw_event: str

    @field_validator(
        "event_id",
        "event_name",
        "status",
        "start_utc",
        "ingested_at",
        "raw_event",
        mode="before",
    )
    @classmethod
    def _required_text(cls, v: object) -> str:
        if _missing(v):
            raise ValueError("required core field empty")
        return str(v).strip()

    @field_validator("sport_id", mode="before")
    @classmethod
    def _coerce_sport_id(cls, v: object) -> int:
        if _missing(v):
            raise ValueError("sport_id required")
        return int(v)


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
    "EspnEventRecord",
    "MatchbookEventRecord",
    "MatchbookOddsRecord",
]
