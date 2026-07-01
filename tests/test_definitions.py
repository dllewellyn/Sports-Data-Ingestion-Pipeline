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


# The ESPN end-to-end selection: bronze + the verified dbt keys (staging + intermediate)
# plus the `team_aliases` seed (an ESPN-conform input in the staging schema).
ESPN_KEYS = {
    "espn_bronze",
    "staging/stg_espn_events",
    "intermediate/int_league",
    "intermediate/int_season",
    "intermediate/int_team",
    "intermediate/int_match",
    "intermediate/int_espn_match_link",
    "staging/team_aliases",
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


# ── Matchbook events wiring tests (Spec 004 S5 — AC9, AC10) ───────────────────


def test_matchbook_events_job_registered() -> None:
    """matchbook_events_ingestion job is registered (AC10)."""
    defs = _load_defs()

    job_names = {job.name for job in defs.jobs}
    assert "matchbook_events_ingestion" in job_names

    job_keys = _job_keys(defs, "matchbook_events_ingestion")
    assert job_keys == {"matchbook_events_bronze"}


def test_matchbook_events_schedule_six_hourly() -> None:
    """matchbook_events_schedule cron is '0 */6 * * *' targeting the job (AC10)."""
    defs = _load_defs()

    schedules = {s.name: s for s in defs.schedules}
    assert "matchbook_events_schedule" in schedules
    schedule = schedules["matchbook_events_schedule"]
    assert schedule.cron_schedule == "0 */6 * * *"
    assert schedule.job.name == "matchbook_events_ingestion"


# ── Matchbook conform wiring tests (Spec 006 S12 — AC13) ─────────────────────


def test_matchbook_conform_job_registered() -> None:
    """matchbook_conform_job is registered in defs (AC13)."""
    defs = _load_defs()

    job_names = {job.name for job in defs.jobs}
    assert "matchbook_conform_job" in job_names


def test_matchbook_conform_schedule_registered() -> None:
    """matchbook_conform_schedule is registered with correct cron (AC13)."""
    defs = _load_defs()

    schedules = {s.name: s for s in defs.schedules}
    assert "matchbook_conform_schedule" in schedules
    schedule = schedules["matchbook_conform_schedule"]
    assert schedule.cron_schedule == "0 1,7,13,19 * * *"
    assert schedule.job.name == "matchbook_conform_job"


def test_matchbook_conform_asset_deps_include_events_bronze() -> None:
    """U31 / AC14 — matchbook_conform depends on AssetKey(['matchbook_events_bronze'])."""
    from data_platform.assets.intermediate.matchbook_conform import (
        matchbook_conform as conform_asset,
    )

    dep_keys = set(conform_asset.dependency_keys)
    assert AssetKey(["matchbook_events_bronze"]) in dep_keys, (
        "matchbook_conform must depend on matchbook_events_bronze"
    )
