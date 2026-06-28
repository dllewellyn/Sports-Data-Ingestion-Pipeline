"""S9 — ESPN orchestration wiring (AC9, AC10).

Mirrors ``tests/football/test_backfill_idempotency.py``'s defs test: importing the
code location reads the dbt manifest (CLAUDE.md: run ``dbt parse`` first), so we skip
gracefully when the manifest is absent while still surfacing real wiring breakage.
"""

import pytest
from dagster import AssetKey


def _load_defs():
    try:
        from data_platform.definitions import defs
    except Exception as exc:  # noqa: BLE001
        if "Manifest" in type(exc).__name__ or "JSONDecode" in type(exc).__name__:
            pytest.skip("dbt manifest not built; run `dbt parse` first (see CLAUDE.md)")
        raise
    return defs


# The ESPN end-to-end selection: bronze + the verified `["silver","<model>"]` dbt keys
# (NOT `["silver","canonical",...]`) plus the `team_aliases` seed (an ESPN-conform input).
ESPN_KEYS = {
    "espn_bronze",
    "silver/stg_espn_events",
    "silver/league",
    "silver/season",
    "silver/team",
    "silver/match",
    "silver/espn_match_link",
    "silver/team_aliases",
}


def _job_keys(defs, job_name: str) -> set[str]:
    job = defs.get_job_def(job_name)
    return {"/".join(k.path) for k in job.asset_layer.executable_asset_keys}


def test_espn_bronze_asset_and_resource_registered() -> None:
    defs = _load_defs()

    asset_keys: set[AssetKey] = set()
    for assets_def in defs.assets:
        asset_keys |= set(assets_def.keys)
    assert AssetKey(["espn_bronze"]) in asset_keys

    assert "espn_http" in defs.resources


def test_espn_job_selects_exactly_the_espn_assets() -> None:
    defs = _load_defs()

    job_names = {job.name for job in defs.jobs}
    assert "espn_ingestion" in job_names

    # End-to-end: bronze + the ESPN dbt models (staging, conform, link) + the seed.
    assert _job_keys(defs, "espn_ingestion") == ESPN_KEYS


def test_espn_schedule_is_six_hourly_targeting_the_job() -> None:
    defs = _load_defs()

    schedules = {s.name: s for s in defs.schedules}
    assert "espn_every_6h" in schedules
    schedule = schedules["espn_every_6h"]
    assert schedule.cron_schedule == "0 */6 * * *"
    assert schedule.job.name == "espn_ingestion"


def test_espn_excluded_from_hello_world_job() -> None:
    """AC10 — ESPN is its own job, subtracted from the all()-based demo job (and thus
    its daily schedule), or the demo would trigger the full ESPN flow."""
    defs = _load_defs()

    assert not (_job_keys(defs, "medallion_hello_world") & ESPN_KEYS), (
        "ESPN excluded from hello-world"
    )
