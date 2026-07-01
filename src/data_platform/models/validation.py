"""Pandera schemas for bronze DataFrames.

Pydantic validates individual records at ingest; Pandera validates the assembled
DataFrame (column presence, dtypes, nullability, value ranges) before it is
written to Parquet. Two complementary gates before data ever lands in bronze.
"""

from __future__ import annotations

import pandera.pandas as pa

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

extra_bronze_schema = pa.DataFrameSchema(
    {
        "Country": pa.Column(str, nullable=False),
        "League": pa.Column(str, nullable=False),
        "Season": pa.Column(str, nullable=False, coerce=True),
        "Date": pa.Column(str, nullable=False),
        "Home": pa.Column(str, nullable=False),
        "Away": pa.Column(str, nullable=False),
        "HG": pa.Column(int, pa.Check.ge(0), nullable=False, coerce=True),
        "AG": pa.Column(int, pa.Check.ge(0), nullable=False, coerce=True),
        "Res": pa.Column(str, pa.Check.isin(["H", "D", "A"]), nullable=False),
    },
    strict=False,
    coerce=True,
)


# --- ESPN scoreboard bronze frame contract (S3) --------------------------------
# Same OPEN (`strict=False`) pattern as the football families: only the mandatory
# flattened-event core is declared, so the wide ESPN payload (scores, season
# fields, venue, ...) rides along untouched while a frame MISSING a core column
# still fails. The per-record core is enforced upstream by Pydantic (schemas.py).

espn_bronze_schema = pa.DataFrameSchema(
    {
        "espn_event_id": pa.Column(str, nullable=False),
        "kickoff_time": pa.Column(str, nullable=False),
        "home_team_id": pa.Column(str, nullable=False),
        "home_team_name": pa.Column(str, nullable=False),
        "away_team_id": pa.Column(str, nullable=False),
        "away_team_name": pa.Column(str, nullable=False),
        "status_name": pa.Column(str, nullable=False),
        # faithful bronze: the complete original event JSON rides along as a
        # required core column so the full payload is always persisted verbatim.
        "raw_event": pa.Column(str, nullable=False),
    },
    strict=False,
    coerce=True,
)


# --- Matchbook Events REST API bronze frame contract (Spec 004) ----------------
# OPEN (`strict=False`): only the mandatory event core is declared; the wide API
# payload (markets, runners, ...) rides along in ``raw_event``. ``volume`` is
# nullable since not all events have matched liquidity. The per-record core is
# enforced upstream by Pydantic (schemas.py).

matchbook_events_bronze_schema = pa.DataFrameSchema(
    {
        "event_id": pa.Column(str, nullable=False),
        "event_name": pa.Column(str, nullable=False),
        "sport_id": pa.Column(int, nullable=False, coerce=True),
        "status": pa.Column(str, nullable=False),
        "start_utc": pa.Column(str, nullable=False),
        "volume": pa.Column(float, nullable=True),
        "ingested_at": pa.Column(str, nullable=False),
        # faithful bronze: the complete original event JSON preserved verbatim.
        "raw_event": pa.Column(str, nullable=False),
    },
    strict=False,
    coerce=True,
)
