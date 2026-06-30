"""Verify MCP config fields in Settings (Spec 007)."""

from pathlib import Path

from data_platform.config import Settings, settings


def test_dbt_manifest_path():
    assert isinstance(settings.dbt_manifest_path, Path)
    assert settings.dbt_manifest_path == Path("dbt/data_platform/target/manifest.json")

    s = Settings()
    assert isinstance(s.dbt_manifest_path, Path)
    assert s.dbt_manifest_path == Path("dbt/data_platform/target/manifest.json")
