"""Typed runtime configuration, sourced from environment variables / .env.

pydantic-settings is the modern, validated replacement for hand-rolled
os.getenv() config or plain dataclasses.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root, derived from this file's location (src/data_platform/config.py) so
# repo-tree assets (dbt seeds) resolve regardless of the process CWD.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Matchbook Redis ingestion (odds ticks via pub/sub)
    matchbook_redis_host: str = "redis"
    matchbook_redis_port: int = 6379

    # Matchbook Events REST API ingestion (bronze Parquet, Spec 004)
    matchbook_username: str = ""
    matchbook_password: str = ""
    matchbook_throttle_seconds: float = 0.0  # declared for future use; not wired in this spec
    matchbook_events_base_url: str = "https://api.matchbook.com"

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

    # MCP
    dbt_manifest_path: Path = Path("dbt/data_platform/target/manifest.json")

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
    def matchbook_bronze_dir(self) -> Path:
        """Bronze partition root for Matchbook odds ticks (matchbook_odds/...)."""
        return self.bronze_dir / "matchbook_odds"

    @property
    def matchbook_events_bronze_dir(self) -> Path:
        """Bronze partition root for Matchbook Events REST API ingestion (matchbook_events/...)."""
        return self.bronze_dir / "matchbook_events"

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

    # ── Matchbook conform layer (Spec 006) ──────────────────────────────────

    @property
    def matchbook_conform_canonical_dir(self) -> Path:
        """Silver canonical Parquet exports (team.parquet, match.parquet) — written by dbt."""
        return self.silver_dir / "canonical"

    @property
    def matchbook_conform_dir(self) -> Path:
        """Resolved conform links Parquet output dir (matchbook_resolved_links.parquet)."""
        return self.silver_dir

    @property
    def matchbook_canonical_additions_dir(self) -> Path:
        """New-canonical additions Parquet dir (matchbook_canonical_match_additions.parquet)."""
        return self.silver_dir

    @property
    def matchbook_exceptions_dir(self) -> Path:
        """Exceptions Parquet dir (matchbook_unresolved.parquet)."""
        return self.data_dir / "exceptions"

    @property
    def matchbook_overrides_dir(self) -> Path:
        """Human override decisions Parquet dir (matchbook_overrides.parquet)."""
        return self.data_dir / "manual_links"

    @property
    def matchbook_t60_dir(self) -> Path:
        """T-60 enrichment Parquet dir (matchbook_t60_enrichment.parquet)."""
        return self.silver_dir

    @property
    def team_aliases_seed_path(self) -> Path:
        """dbt team_aliases seed CSV (team_id, canonical_name, alias) the mint reads.

        Anchored to the repo root — a seed lives in the repo tree, not under
        DATA_DIR — so it resolves regardless of the process CWD.
        """
        return _REPO_ROOT / "dbt" / "data_platform" / "seeds" / "team_aliases.csv"

    @property
    def league_aliases_seed_path(self) -> Path:
        """dbt league_aliases seed CSV (league_id, canonical_name, provider, provider_key).

        Anchored to the repo root — a seed lives in the repo tree, not under
        DATA_DIR — so it resolves regardless of the process CWD.
        """
        return _REPO_ROOT / "dbt" / "data_platform" / "seeds" / "league_aliases.csv"


settings = Settings()
