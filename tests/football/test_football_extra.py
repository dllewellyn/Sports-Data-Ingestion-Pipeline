"""S9 — extra-family ingestor asset wiring (discovery + utf-8-sig/BOM + path)."""

from datetime import date

import pandas as pd

from data_platform.assets.ingestion.football_extra import run_extra_backfill
from data_platform.config import settings
from data_platform.football.registry import ExtraLeague

RUN_DATE = date(2026, 6, 26)
ARGENTINA = ExtraLeague("argentina", "argentina.php", "ARG")

# UTF-8 WITH BOM (E2 / AC11).
EXTRA_CSV_BOM = (
    "﻿Country,League,Season,Date,Home,Away,HG,AG,Res,PSH\n"
    "Argentina,Liga Profesional,2024,26/01/2024,Boca,River,1,0,H,2.1\n"
    "Argentina,Liga Profesional,2024,27/01/2024,Racing,Independiente,2,2,D,3.0\n"
).encode()


def test_run_extra_backfill_lands_parquet_with_normalized_bom(
    tmp_path, monkeypatch, fetcher_factory
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    base = settings.football_base_url
    content = {
        f"{base}argentina.php": b'<a href="new/ARG.csv">Argentina</a>',
        f"{base}new/ARG.csv": EXTRA_CSV_BOM,
    }
    fetcher, session = fetcher_factory(content)

    report = run_extra_backfill(fetcher, RUN_DATE, leagues=[ARGENTINA], log=None)

    expected = tmp_path / "bronze" / "football_extra" / "ARG.parquet"
    assert expected.exists()
    assert len(report.written) == 1 and not report.failed
    assert report.written[0].valid_count == 2
    landed = pd.read_parquet(expected)
    assert "Country" in landed.columns, "utf-8-sig normalises the BOM header"
    assert "﻿Country" not in landed.columns


def test_extra_always_refetched_on_rerun(tmp_path, monkeypatch, fetcher_factory) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    base = settings.football_base_url
    arg_url = f"{base}new/ARG.csv"
    content = {
        f"{base}argentina.php": b'<a href="new/ARG.csv">Argentina</a>',
        arg_url: EXTRA_CSV_BOM,
    }

    # First run lands the file.
    fetcher1, _ = fetcher_factory(content)
    run_extra_backfill(fetcher1, RUN_DATE, leagues=[ARGENTINA], log=None)
    # Second run (fresh fetcher, same on-disk artifact): extra files always re-fetch.
    fetcher2, session2 = fetcher_factory(content)
    report2 = run_extra_backfill(fetcher2, RUN_DATE, leagues=[ARGENTINA], log=None)
    assert arg_url in session2.calls, "extra file re-fetched on re-run (never skipped)"
    assert len(report2.written) == 1
