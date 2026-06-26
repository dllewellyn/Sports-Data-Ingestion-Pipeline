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

    # Medallion layout
    data_dir: Path = Path("data")
    duckdb_path: Path = Path("data/warehouse.duckdb")

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


settings = Settings()
