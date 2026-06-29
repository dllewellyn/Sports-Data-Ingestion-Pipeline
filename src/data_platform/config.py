"""Typed runtime configuration, sourced from environment variables / .env.

pydantic-settings is the modern, validated replacement for hand-rolled
os.getenv() config or plain dataclasses.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Source
    api_base_url: str = "https://jsonplaceholder.typicode.com"

    # Matchbook Redis ingestion
    matchbook_redis_host: str = "redis"
    matchbook_redis_port: int = 6379

    # football-data.co.uk ingestion (bronze source)
    football_base_url: str = "https://www.football-data.co.uk/"
    football_throttle_seconds: float = 0.4  # polite pacing between outbound requests
    football_request_timeout: float = 60.0
    football_max_retries: int = 3  # bounded retry for transient errors (then surface)
    football_user_agent: str = "data-platform/0.1 (+football-data ingestion)"

    # ESPN soccer ingestion (bronze source)
    espn_core_base_url: str = "https://sports.core.api.espn.com"
    espn_site_base_url: str = "https://site.api.espn.com"
    espn_fetch_horizon_days: int = 30  # today ± horizon → which season windows to fetch
    espn_throttle_seconds: float = 0.1  # polite pacing between outbound requests
    espn_request_timeout: float = 30.0
    espn_max_retries: int = 3  # bounded retry for transient errors (then surface)
    # ESPN requires a browser User-Agent or it rejects/throttles requests.
    espn_user_agent: str = "Mozilla/5.0 (compatible; data-platform/0.1; +espn ingestion)"

    # Medallion layout
    data_dir: Path = Path("data")
    duckdb_path: Path = Path("data/warehouse.duckdb")

    # DuckLake catalog
    postgres_catalog_url: str = (
        "postgres:dbname=ducklake user=ducklake password=ducklake host=ducklake-catalog port=5432"
    )
    ducklake_data_path: Path = Path("data/lake")

    # OpenTelemetry
    otel_service_name: str = "data-platform"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    deployment_environment: str = "dev"

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"

    @property
    def silver_dir(self) -> Path:
        return self.data_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        return self.data_dir / "gold"

    @property
    def matchbook_bronze_dir(self) -> Path:
        """Bronze partition root for Matchbook odds ticks (matchbook_odds/...)."""
        return self.bronze_dir / "matchbook_odds"

    @property
    def football_main_dir(self) -> Path:
        """Bronze partition root for the main family (football_main/<league>/...)."""
        return self.bronze_dir / "football_main"

    @property
    def football_extra_dir(self) -> Path:
        """Bronze partition root for the extra family (football_extra/<code>.parquet)."""
        return self.bronze_dir / "football_extra"

    @property
    def espn_bronze_dir(self) -> Path:
        """Bronze partition root for ESPN soccer ingestion (espn/...)."""
        return self.bronze_dir / "espn"


settings = Settings()
