"""S4 — Matchbook events Dagster asset wrapper tests (Spec 004 AC9, AC10, AC13, AC14)."""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest
from dagster import AssetKey, MaterializeResult

from data_platform.assets.ingestion.matchbook_events import matchbook_events_bronze


def test_asset_key_is_correct() -> None:
    """matchbook_events_bronze asset key is ['matchbook_events_bronze'] (AC9)."""
    assert matchbook_events_bronze.key == AssetKey(["matchbook_events_bronze"])


def test_asset_group_is_bronze() -> None:
    """matchbook_events_bronze is in the 'bronze' group (AC9)."""
    assert (
        matchbook_events_bronze.group_names_by_key.get(AssetKey(["matchbook_events_bronze"]))
        == "bronze"
    )


def test_no_future_annotations_in_asset_module() -> None:
    """Asset module must NOT have 'from __future__ import annotations' as a code line (AC13).

    Dagster introspects context/return annotations at runtime; stringized
    annotations cause DagsterInvalidDefinitionError. We check stripped source lines
    (not the raw string) to avoid false positives from docstrings mentioning the import.
    """
    import data_platform.assets.ingestion.matchbook_events as mod

    lines = inspect.getsource(mod).splitlines()
    # An actual import line (stripped) would be exactly this string
    assert "from __future__ import annotations" not in [line.strip() for line in lines]


def test_asset_returns_materialize_result_on_success(tmp_path) -> None:
    """matchbook_events_bronze returns MaterializeResult on a successful run."""
    from dagster import build_asset_context

    from data_platform.matchbook.ingest import IngestionReport, SportResult

    mock_report = IngestionReport(
        written=[SportResult("football", "written", out_path=tmp_path / "f.parquet")]
    )

    with (
        patch(
            "data_platform.assets.ingestion.matchbook_events.run_matchbook_events_ingest",
            return_value=mock_report,
        ),
        build_asset_context() as ctx,
    ):
        result = matchbook_events_bronze(ctx)

    assert isinstance(result, MaterializeResult)


def test_asset_reraises_on_ingest_failure(tmp_path) -> None:
    """matchbook_events_bronze re-raises when run_matchbook_events_ingest raises."""
    from dagster import build_asset_context

    with (
        patch(
            "data_platform.assets.ingestion.matchbook_events.run_matchbook_events_ingest",
            side_effect=RuntimeError("matchbook ingest failed: 1 failures"),
        ),
        pytest.raises(RuntimeError, match="failures"),
        build_asset_context() as ctx,
    ):
        matchbook_events_bronze(ctx)
