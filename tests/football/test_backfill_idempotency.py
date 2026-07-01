"""S10 — full coverage + idempotent re-runs (AC15, AC16, E9, E10).

Uses a small fixture registry (one league, one current + one historical file) and a
REAL ThrottledFetcher over a fake session, so skip-existing / always-refresh are
exercised end-to-end across two runs.
"""

from datetime import date

import pandas as pd

from data_platform.assets.football_main import run_main_backfill
from data_platform.config import settings
from data_platform.football.registry import MainLeague

RUN_DATE = date(2026, 6, 26)  # current main season token = "2526"
ENGLAND = MainLeague("england", "englandm.php")

LANDING = b'<a href="mmz4281/9394/E0.csv">hist</a><a href="mmz4281/2526/E0.csv">current</a>'

HIST_CSV = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
    "E0,14/08/93,Arsenal,Coventry,0,3,A\n"
    "E0,14/08/93,Liverpool,Sheffield,2,0,H\n"
).encode("latin-1")

CURRENT_V1 = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
    "E0,12/08/25,Arsenal,Wolves,2,0,H\n"
    "E0,12/08/25,Chelsea,Palace,1,1,D\n"
).encode("latin-1")

# Same current file updated in place at source with a third fixture (E10).
CURRENT_V2 = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
    "E0,12/08/25,Arsenal,Wolves,2,0,H\n"
    "E0,12/08/25,Chelsea,Palace,1,1,D\n"
    "E0,19/08/25,Spurs,Everton,3,1,H\n"
).encode("latin-1")


def _urls() -> tuple[str, str]:
    base = settings.football_base_url
    return f"{base}mmz4281/9394/E0.csv", f"{base}mmz4281/2526/E0.csv"


def test_full_coverage_then_idempotent_rerun(tmp_path, monkeypatch, fetcher_factory) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    base = settings.football_base_url
    hist_url, cur_url = _urls()

    content1 = {f"{base}englandm.php": LANDING, hist_url: HIST_CSV, cur_url: CURRENT_V1}
    fetcher1, session1 = fetcher_factory(content1)
    report1 = run_main_backfill(fetcher1, RUN_DATE, leagues=[ENGLAND], log=None)

    # AC15: every discovered file landed; full coverage.
    assert len(report1.written) == 2 and not report1.failed
    assert hist_url in session1.calls and cur_url in session1.calls
    hist_path = tmp_path / "bronze" / "football_main" / "england" / "9394" / "E0.parquet"
    cur_path = tmp_path / "bronze" / "football_main" / "england" / "2526" / "E0.parquet"
    assert hist_path.exists() and cur_path.exists()
    hist_mtime = hist_path.stat().st_mtime_ns
    assert pd.read_parquet(cur_path).shape[0] == 2

    # Second run: source current file changed in place (V2).
    content2 = {f"{base}englandm.php": LANDING, hist_url: HIST_CSV, cur_url: CURRENT_V2}
    fetcher2, session2 = fetcher_factory(content2)
    report2 = run_main_backfill(fetcher2, RUN_DATE, leagues=[ENGLAND], log=None)

    # AC16/E9: historical skipped — no GET, artifact untouched.
    assert hist_url not in session2.calls, "historical file not re-fetched"
    assert hist_path.stat().st_mtime_ns == hist_mtime, "historical artifact unchanged"
    assert any(r.file.season == "9394" for r in report2.skipped)

    # AC16/E10: current re-fetched and overwritten with the new fixtures.
    assert cur_url in session2.calls, "current-season file re-fetched"
    assert pd.read_parquet(cur_path).shape[0] == 3, "current Parquet refreshed"
    assert report2.attempted == 2, "every registry entry accounted for (none silently dropped)"


def test_definitions_registers_football_assets_resource_and_job() -> None:
    import pytest
    from dagster import AssetKey

    # Importing the code location reads the dbt manifest (CLAUDE.md: `dbt parse`
    # first). Skip gracefully if it isn't built, but still surface real wiring
    # breakage (e.g. an import error in the football assets).
    try:
        from data_platform.definitions import defs
    except Exception as exc:  # noqa: BLE001
        if "Manifest" in type(exc).__name__ or "JSONDecode" in type(exc).__name__:
            pytest.skip("dbt manifest not built; run `dbt parse` first (see CLAUDE.md)")
        raise

    asset_keys: set[AssetKey] = set()
    for assets_def in defs.assets:
        asset_keys |= set(assets_def.keys)
    assert AssetKey(["football_main"]) in asset_keys
    assert AssetKey(["football_extra"]) in asset_keys

    assert "football_http" in defs.resources

    job_names = {job.name for job in defs.jobs}
    assert "football_backfill" in job_names

    # The football assets must be their own job and EXCLUDED from the all()-based
    # hello-world job (and thus its schedule), or running the demo would trigger the
    # ~705-file backfill.
    def _keys(job_name: str) -> set[str]:
        job = defs.get_job_def(job_name)
        return {"/".join(k.path) for k in job.asset_layer.executable_asset_keys}

    football = {"football_main", "football_extra"}
    assert _keys("football_backfill") == football
