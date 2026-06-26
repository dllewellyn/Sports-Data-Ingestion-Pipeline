"""S7/S9 core — the shared, Dagster-free ingest engine.

Covers decode (latin-1 main, utf-8-sig extra/BOM), row skip-and-count, frame
validation, deterministic one-Parquet-per-file landing, per-file failure
isolation (E7/E8 — no partial/empty Parquet), and per-file span emission.
"""

from datetime import date

import pandas as pd

from data_platform.football.discovery import DiscoveredFile
from data_platform.football.http_client import FootballFetchError
from data_platform.football.ingest import decode_csv, ingest_family, validate_rows
from data_platform.football.registry import Family
from data_platform.models.schemas import ExtraMatchRecord, MainMatchRecord
from data_platform.models.validation import extra_bronze_schema, main_bronze_schema

RUN_DATE = date(2026, 6, 26)
MAIN_CORE = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
EXTRA_CORE = ["Country", "League", "Season", "Date", "Home", "Away", "HG", "AG", "Res"]

# A latin-1 main CSV with a real row carrying a latin-1 char, a blank row, and a
# footer row — mirrors the 9394/E0.csv blank/footer noise (E1).
MAIN_CSV_LATIN1 = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H\n"
    "E0,14/08/93,Arsenal,Coventry,0,3,A,2.10\n"
    "E0,14/08/93,Málaga,Sheffield,2,0,H,1.80\n"
    ",,,,,,\n"
    "Note: data provided by football-data,,,,,,\n"
).encode("latin-1")

# An extra CSV that is UTF-8 WITH BOM (E2/AC11).
EXTRA_CSV_BOM = (
    "﻿Country,League,Season,Date,Home,Away,HG,AG,Res,PSH\n"
    "Argentina,Liga Profesional,2024,26/01/2024,Boca,River,1,0,H,2.1\n"
    "Argentina,Liga Profesional,2024,27/01/2024,Racing,Independiente,2,2,D,3.0\n"
).encode()


class FakeFetcher:
    """Returns scripted bytes per URL; raises for URLs in `fail_urls`."""

    def __init__(self, content_by_url: dict[str, bytes], fail_urls: set[str] | None = None) -> None:
        self.content_by_url = content_by_url
        self.fail_urls = fail_urls or set()
        self.fetched: list[str] = []

    def fetch_source(self, *, url, family, season_token, run_date, artifact_path):
        self.fetched.append(url)
        if url in self.fail_urls:
            raise FootballFetchError(url, 3)
        return self.content_by_url[url]


def _main_file(season="9394", div="E0", league="england") -> DiscoveredFile:
    return DiscoveredFile(
        family=Family.MAIN,
        league=league,
        url=f"https://www.football-data.co.uk/mmz4281/{season}/{div}.csv",
        source_path=f"mmz4281/{season}/{div}.csv",
        season=season,
        division=div,
    )


def _extra_file(code="ARG", league="argentina") -> DiscoveredFile:
    return DiscoveredFile(
        family=Family.EXTRA,
        league=league,
        url=f"https://www.football-data.co.uk/new/{code}.csv",
        source_path=f"new/{code}.csv",
        code=code,
    )


# --- decode + row validation ---------------------------------------------------


def test_latin1_decodes_without_mojibake() -> None:
    df = decode_csv(MAIN_CSV_LATIN1, "latin-1")
    assert "Málaga" in df["HomeTeam"].to_numpy()


def test_utf8sig_normalizes_bom_header() -> None:
    df = decode_csv(EXTRA_CSV_BOM, "utf-8-sig")
    assert "Country" in df.columns
    assert "﻿Country" not in df.columns


def test_skip_and_count_drops_invalid_rows() -> None:
    df = decode_csv(MAIN_CSV_LATIN1, "latin-1")
    valid_df, raw, valid, reject = validate_rows(df, MainMatchRecord, MAIN_CORE)
    assert raw == 4 and valid == 2 and reject == 2
    assert list(valid_df["HomeTeam"]) == ["Arsenal", "Málaga"]


# --- main family ingest --------------------------------------------------------


def test_main_lands_one_parquet_at_deterministic_path(tmp_path) -> None:
    file = _main_file()
    fetcher = FakeFetcher({file.url: MAIN_CSV_LATIN1})

    def out_for(f: DiscoveredFile):
        return tmp_path / "football_main" / f.league / f.season / f"{f.division}.parquet"

    report = ingest_family(
        [file],
        fetcher,
        RUN_DATE,
        log=None,
        encoding="latin-1",
        model=MainMatchRecord,
        schema=main_bronze_schema,
        core=MAIN_CORE,
        out_path_for=out_for,
    )
    expected = tmp_path / "football_main" / "england" / "9394" / "E0.parquet"
    assert expected.exists()
    assert len(report.written) == 1
    res = report.written[0]
    assert (res.raw_count, res.valid_count, res.reject_count) == (4, 2, 2)
    landed = pd.read_parquet(expected)
    assert list(landed.columns)[:7] == MAIN_CORE
    assert "B365H" in landed.columns  # optional odds ride along


def test_main_unreachable_file_isolated_no_parquet(tmp_path) -> None:
    good, bad = _main_file(div="E0"), _main_file(div="E1")
    fetcher = FakeFetcher({good.url: MAIN_CSV_LATIN1}, fail_urls={bad.url})

    def out_for(f: DiscoveredFile):
        return tmp_path / f.league / f.season / f"{f.division}.parquet"

    report = ingest_family(
        [good, bad],
        fetcher,
        RUN_DATE,
        log=None,
        encoding="latin-1",
        model=MainMatchRecord,
        schema=main_bronze_schema,
        core=MAIN_CORE,
        out_path_for=out_for,
    )
    assert len(report.written) == 1 and len(report.failed) == 1
    assert report.failed[0].file.division == "E1"
    assert not (tmp_path / "england" / "9394" / "E1.parquet").exists(), "no partial Parquet"
    assert (tmp_path / "england" / "9394" / "E0.parquet").exists(), "other files continue"


def test_zero_valid_rows_surfaced_no_empty_parquet(tmp_path) -> None:
    all_blank = ("Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n,,,,,,\n,,,,,,\n").encode("latin-1")
    file = _main_file()
    fetcher = FakeFetcher({file.url: all_blank})

    def out_for(f: DiscoveredFile):
        return tmp_path / f"{f.division}.parquet"

    report = ingest_family(
        [file],
        fetcher,
        RUN_DATE,
        log=None,
        encoding="latin-1",
        model=MainMatchRecord,
        schema=main_bronze_schema,
        core=MAIN_CORE,
        out_path_for=out_for,
    )
    assert len(report.failed) == 1 and len(report.written) == 0
    assert not (tmp_path / "E0.parquet").exists(), "no empty Parquet for zero-valid file"


def test_span_emitted_per_written_file(tmp_path, monkeypatch) -> None:
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

    monkeypatch.setattr("data_platform.football.ingest.get_tracer", lambda *a, **k: FakeTracer())
    file = _main_file()
    fetcher = FakeFetcher({file.url: MAIN_CSV_LATIN1})
    ingest_family(
        [file],
        fetcher,
        RUN_DATE,
        log=None,
        encoding="latin-1",
        model=MainMatchRecord,
        schema=main_bronze_schema,
        core=MAIN_CORE,
        out_path_for=lambda f: tmp_path / f"{f.division}.parquet",
    )
    assert spans, "a span must be opened per ingested file"


# --- extra family ingest -------------------------------------------------------


def test_extra_lands_one_parquet_with_normalized_bom(tmp_path) -> None:
    file = _extra_file()
    fetcher = FakeFetcher({file.url: EXTRA_CSV_BOM})

    def out_for(f: DiscoveredFile):
        return tmp_path / "football_extra" / f"{f.code}.parquet"

    report = ingest_family(
        [file],
        fetcher,
        RUN_DATE,
        log=None,
        encoding="utf-8-sig",
        model=ExtraMatchRecord,
        schema=extra_bronze_schema,
        core=EXTRA_CORE,
        out_path_for=out_for,
    )
    expected = tmp_path / "football_extra" / "ARG.parquet"
    assert expected.exists()
    assert report.written[0].valid_count == 2
    landed = pd.read_parquet(expected)
    assert "Country" in landed.columns and "﻿Country" not in landed.columns


def test_skipped_file_recorded_not_written(tmp_path) -> None:
    file = _main_file()

    class SkipFetcher:
        fetched: list[str] = []

        def fetch_source(self, **kwargs):
            return None  # simulate skip-existing

    report = ingest_family(
        [file],
        SkipFetcher(),
        RUN_DATE,
        log=None,
        encoding="latin-1",
        model=MainMatchRecord,
        schema=main_bronze_schema,
        core=MAIN_CORE,
        out_path_for=lambda f: tmp_path / f"{f.division}.parquet",
    )
    assert len(report.skipped) == 1 and len(report.written) == 0
    assert not (tmp_path / "E0.parquet").exists()


def test_unexpected_exception_isolated(tmp_path) -> None:
    file = _main_file()

    class BoomFetcher:
        def fetch_source(self, **kwargs):
            raise RuntimeError("unexpected boom")

    report = ingest_family(
        [file],
        BoomFetcher(),
        RUN_DATE,
        log=None,
        encoding="latin-1",
        model=MainMatchRecord,
        schema=main_bronze_schema,
        core=MAIN_CORE,
        out_path_for=lambda f: tmp_path / f"{f.division}.parquet",
    )
    assert len(report.failed) == 1, "any per-file error is isolated, not propagated"
