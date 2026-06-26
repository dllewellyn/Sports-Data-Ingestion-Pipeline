"""S7 — main-family ingestor asset wiring (discovery + latin-1 + deterministic path)."""

from datetime import date

import pandas as pd

from data_platform.assets.football_main import run_main_backfill
from data_platform.config import settings
from data_platform.football.registry import MainLeague

RUN_DATE = date(2026, 6, 26)
ENGLAND = MainLeague("england", "englandm.php")

MAIN_CSV_LATIN1 = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H\n"
    "E0,14/08/93,Arsenal,Coventry,0,3,A,2.10\n"
    "E0,14/08/93,Málaga,Sheffield,2,0,H,1.80\n"
    ",,,,,,\n"
).encode("latin-1")


def _content(base: str) -> dict[str, bytes]:
    return {
        f"{base}englandm.php": b'<a href="mmz4281/9394/E0.csv">E0</a>',
        f"{base}mmz4281/9394/E0.csv": MAIN_CSV_LATIN1,
    }


def test_run_main_backfill_lands_parquet_at_deterministic_path(
    tmp_path, monkeypatch, fetcher_factory
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    base = settings.football_base_url
    fetcher, session = fetcher_factory(_content(base))

    report = run_main_backfill(fetcher, RUN_DATE, leagues=[ENGLAND], log=None)

    expected = tmp_path / "bronze" / "football_main" / "england" / "9394" / "E0.parquet"
    assert expected.exists()
    assert len(report.written) == 1 and not report.failed
    assert report.written[0].valid_count == 2
    landed = pd.read_parquet(expected)
    assert "Málaga" in landed["HomeTeam"].to_numpy(), "latin-1 decoded without mojibake"
    assert f"{base}mmz4281/9394/E0.csv" in session.calls


def test_run_main_backfill_isolates_unreachable_file(
    tmp_path, monkeypatch, fetcher_factory
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    base = settings.football_base_url
    # Landing page links a file that the session does not serve (→ 404 → FootballFetchError).
    content = {f"{base}englandm.php": b'<a href="mmz4281/9394/E0.csv">missing</a>'}
    fetcher, _ = fetcher_factory(content)

    report = run_main_backfill(fetcher, RUN_DATE, leagues=[ENGLAND], log=None)

    assert len(report.failed) == 1 and len(report.written) == 0
    assert not (tmp_path / "bronze" / "football_main" / "england" / "9394" / "E0.parquet").exists()
