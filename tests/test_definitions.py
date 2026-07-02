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
    "marts/canonical_match_export",
    "marts/canonical_team_export",
    "marts/canonical_league_export",
    "marts/canonical_season_export",
}


def _job_keys(defs, job_name: str) -> set[str]:
    job = defs.get_job_def(job_name)
    return {"/".join(k.path) for k in job.asset_layer.executable_asset_keys}


def test_espn_bronze_asset_and_resource_registered() -> None:
    defs = _load_defs()

    asset_keys: set[AssetKey] = set()
    for assets_def in defs.assets:
        # AssetsDefinition exposes `.keys`; SourceAsset (e.g. matchbook_odds_bronze)
        # exposes a single `.key`.
        if hasattr(assets_def, "keys"):
            asset_keys |= set(assets_def.keys)
        else:
            asset_keys.add(assets_def.key)
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


# ── Matchbook end-to-end wiring tests (definitions.py merge: ingest + conform +
# T-60 + canonical/link rebuild all in one job, replacing the old separately-
# scheduled matchbook_events_ingestion / matchbook_conform_job pair) ──────────

MATCHBOOK_KEYS = {
    "matchbook_events_bronze",
    "matchbook_conform",
    "matchbook_t60_enrichment",
    "intermediate/int_league",
    "intermediate/int_season",
    "intermediate/int_team",
    "intermediate/int_match",
    "intermediate/int_matchbook_event_link",
    "intermediate/int_matchbook_team_link",
    "intermediate/int_matchbook_league_link",
}


def test_matchbook_job_selects_exactly_the_matchbook_assets() -> None:
    """matchbook_ingestion job registered with the full end-to-end selection."""
    defs = _load_defs()

    job_names = {job.name for job in defs.jobs}
    assert "matchbook_ingestion" in job_names
    assert _job_keys(defs, "matchbook_ingestion") == MATCHBOOK_KEYS


def test_matchbook_schedule_is_six_hourly_offset_from_espn() -> None:
    """matchbook_every_6h targets matchbook_ingestion, offset from espn_every_6h."""
    defs = _load_defs()

    schedules = {s.name: s for s in defs.schedules}
    assert "matchbook_every_6h" in schedules
    schedule = schedules["matchbook_every_6h"]
    assert schedule.cron_schedule == "15 */6 * * *"
    assert schedule.job.name == "matchbook_ingestion"

    # No longer two separate jobs/schedules for events vs. conform.
    job_names = {job.name for job in defs.jobs}
    assert "matchbook_events_ingestion" not in job_names
    assert "matchbook_conform_job" not in job_names
    assert "matchbook_events_schedule" not in schedules
    assert "matchbook_conform_schedule" not in schedules


def test_matchbook_conform_asset_deps_include_events_bronze() -> None:
    """U31 / AC14 — matchbook_conform depends on AssetKey(['matchbook_events_bronze'])."""
    from data_platform.assets.intermediate.matchbook_conform import (
        matchbook_conform as conform_asset,
    )

    dep_keys = set(conform_asset.dependency_keys)
    assert AssetKey(["matchbook_events_bronze"]) in dep_keys, (
        "matchbook_conform must depend on matchbook_events_bronze"
    )
