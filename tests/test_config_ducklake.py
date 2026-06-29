"""Verify DuckLake config fields have correct defaults (Spec 002)."""

from pathlib import Path

from data_platform.config import Settings


def test_postgres_catalog_url_default():
    s = Settings()
    assert s.postgres_catalog_url == (
        "postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake"
    )


def test_ducklake_data_path_default():
    s = Settings()
    assert s.ducklake_data_path == Path("data/lake")


def test_postgres_catalog_url_env_override(monkeypatch):
    monkeypatch.setenv("POSTGRES_CATALOG_URL", "postgresql://x:y@host/db")
    s = Settings()
    assert s.postgres_catalog_url == "postgresql://x:y@host/db"
