"""The ``BronzeAwareTranslator`` maps each dbt bronze source onto its upstream
Dagster ingest asset so the bronze -> silver lineage edges form."""

from dagster import AssetKey

from data_platform.assets.dbt import BronzeAwareTranslator


def test_espn_source_maps_to_espn_bronze_asset_key() -> None:
    translator = BronzeAwareTranslator()
    key = translator.get_asset_key({"resource_type": "source", "name": "espn_events"})
    assert key == AssetKey(["espn_bronze"])


def test_users_source_still_maps_to_raw_users() -> None:
    translator = BronzeAwareTranslator()
    key = translator.get_asset_key({"resource_type": "source", "name": "users"})
    assert key == AssetKey(["raw_users"])
