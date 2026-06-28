"""S4 — Dagster-free ESPN ingest engine.

Covers flatten → row validation → frame validation → one-Parquet-per-unit at a
deterministic path, overwrite-not-append on re-fetch (AC2), per-unit failure
isolation + re-raise (E1/AC11), zero-event empty window (E2), null scores when
STATUS_FINAL with no scores yet (E11), and per-unit span emission.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from data_platform.espn.discovery import EspnUnit
from data_platform.espn.http_client import EspnFetchError
from data_platform.espn.ingest import (
    EspnZeroEventsError,
    flatten_events,
    ingest_units,
)
from data_platform.models.validation import espn_bronze_schema

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _unit(slug: str = "eng.1", season_year: int = 2025) -> EspnUnit:
    return EspnUnit(
        league_slug=slug,
        league_name="English Premier League",
        season_year=season_year,
        start_date=date(2025, 8, 1),
        end_date=date(2026, 5, 31),
        scoreboard_url=f"https://site.api.espn.com/{slug}/{season_year}/scoreboard",
    )


class FakeFetcher:
    """Returns scripted JSON per URL; raises for URLs in ``fail_urls``."""

    def __init__(self, json_by_url: dict[str, dict], fail_urls: set[str] | None = None) -> None:
        self.json_by_url = json_by_url
        self.fail_urls = fail_urls or set()
        self.fetched: list[str] = []

    def get_json(self, url: str) -> dict:
        self.fetched.append(url)
        if url in self.fail_urls:
            raise EspnFetchError(url, 3)
        return self.json_by_url[url]


# --- flatten -------------------------------------------------------------------


def test_flatten_maps_core_and_ride_along_columns() -> None:
    rows = flatten_events(_load("scoreboard_eng1_2025_prematch.json"))
    assert len(rows) == 3
    first = rows[0]
    assert first["espn_event_id"] == "704946"
    assert first["kickoff_time"] == "2025-08-16T11:30Z"
    assert first["home_team_id"] == "364"
    assert first["home_team_name"] == "Liverpool"
    assert first["away_team_id"] == "349"
    assert first["away_team_name"] == "AFC Bournemouth"
    assert first["status_name"] == "STATUS_SCHEDULED"
    # ride-along
    assert first["season_year"] == 2025
    assert first["season_display"] == "2025-26"
    assert first["status_state"] == "pre"
    assert first["status_completed"] is False
    assert first["home_score"] == "0"
    assert first["away_score"] == "0"


def test_flatten_drops_events_missing_competition_or_competitor() -> None:
    payload = {
        "events": [
            {"id": "1", "date": "2025-08-16T11:30Z", "competitions": []},
            {
                "id": "2",
                "date": "2025-08-16T11:30Z",
                "competitions": [
                    {
                        "status": {"type": {"name": "STATUS_SCHEDULED"}},
                        "competitors": [
                            {"homeAway": "home", "team": {"id": "1", "displayName": "A"}}
                        ],
                    }
                ],
            },
        ]
    }
    assert flatten_events(payload) == []


# --- ingest --------------------------------------------------------------------


def test_one_parquet_at_deterministic_path(tmp_path, monkeypatch) -> None:
    from data_platform.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    unit = _unit()
    fetcher = FakeFetcher({unit.scoreboard_url: _load("scoreboard_eng1_2025_prematch.json")})

    report = ingest_units([unit], fetcher, log=None, schema=espn_bronze_schema)

    expected = tmp_path / "bronze" / "espn" / "eng.1" / "2025.parquet"
    assert expected.exists()
    assert len(report.written) == 1 and not report.failed
    landed = pd.read_parquet(expected)
    assert len(landed) == 3
    assert list(landed.columns)[:7] == [
        "espn_event_id",
        "kickoff_time",
        "home_team_id",
        "home_team_name",
        "away_team_id",
        "away_team_name",
        "status_name",
    ]


def test_refetch_overwrites_with_richer_payload(tmp_path, monkeypatch) -> None:
    from data_platform.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    unit = _unit()
    out = tmp_path / "bronze" / "espn" / "eng.1" / "2025.parquet"

    # Run 1: scheduled, no scores.
    f1 = FakeFetcher({unit.scoreboard_url: _load("scoreboard_eng1_2025_prematch.json")})
    ingest_units([unit], f1, log=None, schema=espn_bronze_schema)
    run1 = pd.read_parquet(out)
    assert run1.loc[run1["espn_event_id"] == "704946", "status_name"].iloc[0] == "STATUS_SCHEDULED"

    # Run 2: same unit, now FINAL with scores.
    f2 = FakeFetcher({unit.scoreboard_url: _load("scoreboard_eng1_2025_postmatch.json")})
    ingest_units([unit], f2, log=None, schema=espn_bronze_schema)
    run2 = pd.read_parquet(out)

    row = run2.loc[run2["espn_event_id"] == "704946"].iloc[0]
    assert row["status_name"] == "STATUS_FINAL"
    assert row["home_score"] == "4"
    assert row["away_score"] == "2"
    # OVERWRITE, not append: postmatch fixture has 4 events; run1 had 3.
    assert len(run2) == 4
    assert len(run2["espn_event_id"]) == run2["espn_event_id"].nunique()


def test_fetch_error_isolated_and_reraised_other_units_land(tmp_path, monkeypatch) -> None:
    from data_platform.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    good = _unit("eng.1", 2025)
    bad = _unit("esp.1", 2025)
    fetcher = FakeFetcher(
        {good.scoreboard_url: _load("scoreboard_eng1_2025_prematch.json")},
        fail_urls={bad.scoreboard_url},
    )

    report = ingest_units([good, bad], fetcher, log=None, schema=espn_bronze_schema)

    assert len(report.written) == 1 and len(report.failed) == 1
    assert report.failed[0].unit.league_slug == "esp.1"
    assert (tmp_path / "bronze" / "espn" / "eng.1" / "2025.parquet").exists()
    assert not (tmp_path / "bronze" / "espn" / "esp.1" / "2025.parquet").exists(), "no partial"


def test_zero_events_writes_no_parquet_recorded(tmp_path, monkeypatch) -> None:
    from data_platform.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    unit = _unit()
    fetcher = FakeFetcher({unit.scoreboard_url: {"events": []}})

    report = ingest_units([unit], fetcher, log=None, schema=espn_bronze_schema)

    assert len(report.failed) == 1 and len(report.written) == 0
    assert isinstance(EspnZeroEventsError("x"), RuntimeError)
    assert not (tmp_path / "bronze" / "espn" / "eng.1" / "2025.parquet").exists()


def test_final_without_scores_keeps_scores_null(tmp_path, monkeypatch) -> None:
    from data_platform.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    unit = _unit()
    payload = {
        "events": [
            {
                "id": "999",
                "date": "2025-08-16T11:30Z",
                "season": {"year": 2025, "displayName": "2025-26"},
                "competitions": [
                    {
                        "status": {
                            "type": {"name": "STATUS_FINAL", "state": "post", "completed": True}
                        },
                        "competitors": [
                            {"homeAway": "home", "team": {"id": "1", "displayName": "Home FC"}},
                            {"homeAway": "away", "team": {"id": "2", "displayName": "Away FC"}},
                        ],
                    }
                ],
            }
        ]
    }
    fetcher = FakeFetcher({unit.scoreboard_url: payload})
    report = ingest_units([unit], fetcher, log=None, schema=espn_bronze_schema)

    assert len(report.written) == 1
    landed = pd.read_parquet(tmp_path / "bronze" / "espn" / "eng.1" / "2025.parquet")
    assert landed.loc[0, "status_name"] == "STATUS_FINAL"
    assert pd.isna(landed.loc[0, "home_score"])
    assert pd.isna(landed.loc[0, "away_score"])


def test_span_emitted_per_unit(tmp_path, monkeypatch) -> None:
    from data_platform.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    spans: list[str] = []

    class FakeSpan:
        def set_attribute(self, *a, **k): ...
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeTracer:
        def start_as_current_span(self, name, *a, **k):
            spans.append(name)
            return FakeSpan()

    monkeypatch.setattr("data_platform.espn.ingest.get_tracer", lambda *a, **k: FakeTracer())
    unit = _unit()
    fetcher = FakeFetcher({unit.scoreboard_url: _load("scoreboard_eng1_2025_prematch.json")})
    ingest_units([unit], fetcher, log=None, schema=espn_bronze_schema)
    assert spans == ["ingest.espn"]
