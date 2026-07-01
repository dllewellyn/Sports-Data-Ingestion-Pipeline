"""S4 — the thin ESPN bronze asset wiring.

Asserts the asset is defined with the expected key/group and that the asset
module carries NO ``from __future__ import annotations`` (a hard CLAUDE.md rule —
Dagster introspects the annotations at runtime).
"""

import inspect
from datetime import date

import pytest
from dagster import AssetKey

import data_platform.assets.ingestion.espn as espn_asset_module
from data_platform.espn.asset_results import to_materialize_result
from data_platform.espn.discovery import EspnUnit
from data_platform.espn.ingest import IngestionReport, UnitResult, espn_out_path


def _sample_unit() -> EspnUnit:
    return EspnUnit(
        league_slug="eng.1",
        league_name="English Premier League",
        season_year=2025,
        start_date=date(2025, 8, 1),
        end_date=date(2026, 5, 31),
        scoreboard_url="https://example/scoreboard",
    )


def test_asset_key_and_group() -> None:
    assert espn_asset_module.espn_bronze.key == AssetKey(["espn_bronze"])
    assert espn_asset_module.espn_bronze.group_names_by_key[AssetKey(["espn_bronze"])] == "bronze"


def test_asset_module_has_no_future_annotations() -> None:
    # A real import statement starts at column 0; the rule's mention inside the
    # module docstring must not count, so match on a line-anchored import.
    lines = inspect.getsource(espn_asset_module).splitlines()
    assert "from __future__ import annotations" not in lines


def test_out_path_is_deterministic(monkeypatch, tmp_path) -> None:
    from data_platform.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    assert espn_out_path(_sample_unit()) == tmp_path / "bronze" / "espn" / "eng.1" / "2025.parquet"


def test_to_materialize_result_reraises_when_a_unit_failed() -> None:
    # E1: a failed unit must surface as a run failure. The engine isolates per
    # unit (successful Parquet already on disk); the summary RAISES so the run
    # status reflects the failure rather than reporting success.
    report = IngestionReport(
        written=[], failed=[UnitResult(_sample_unit(), "failed", error="boom")]
    )
    with pytest.raises(RuntimeError, match="unit"):
        to_materialize_result(report, None, "espn")


def test_to_materialize_result_succeeds_when_all_units_written() -> None:
    report = IngestionReport(
        written=[UnitResult(_sample_unit(), "written", valid_count=3)], failed=[]
    )
    result = to_materialize_result(report, None, "espn")
    assert result is not None
