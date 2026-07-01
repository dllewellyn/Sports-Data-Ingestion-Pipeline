"""Bronze ingestor for ESPN soccer scoreboards (the network edge).

One Parquet per league×season under ``data/bronze/espn/<league>/<season>.parquet``,
overwritten with the latest scoreboard each run. Network access stays in the bronze
layer (ARCHITECTURE rule #1): the season-resolution GETs and scoreboard GETs both
flow through the shared throttled client. Per-unit failures are isolated; the asset
then re-raises so the run status reflects them.

No ``from __future__ import annotations`` — Dagster introspects the annotations.
"""

from datetime import date

from dagster import AssetKey, MaterializeResult, asset

from ...config import settings
from ...espn.asset_results import to_materialize_result
from ...espn.discovery import discover_units
from ...espn.http_client import ThrottledFetcher, ThrottledHttpClient
from ...espn.ingest import IngestionReport, ingest_units
from ...espn.registry import SOCCER_LEAGUES, EspnLeague
from ...models.validation import espn_bronze_schema


def run_espn_ingest(
    fetcher: ThrottledFetcher,
    run_date: date,
    *,
    leagues: list[EspnLeague] | tuple[EspnLeague, ...] = SOCCER_LEAGUES,
    log=None,
) -> IngestionReport:
    """Discover + ingest every allowlisted ESPN unit. Pure of Dagster (testable)."""
    units = discover_units(
        fetcher.get_json,
        leagues,
        run_date=run_date,
        horizon_days=settings.espn_fetch_horizon_days,
        core_base_url=settings.espn_core_base_url,
        site_base_url=settings.espn_site_base_url,
    )
    if log is not None:
        log.info("discovered %d espn units", len(units))
    return ingest_units(units, fetcher, log=log, schema=espn_bronze_schema)


@asset(
    key=AssetKey(["espn_bronze"]),
    group_name="bronze",
    compute_kind="python",
    description="ESPN soccer scoreboards → one bronze Parquet per league×season (overwrite).",
)
def espn_bronze(context, espn_http: ThrottledHttpClient) -> MaterializeResult:
    fetcher = espn_http.build_fetcher()
    report = run_espn_ingest(fetcher, date.today(), log=context.log)
    return to_materialize_result(report, context.log, "espn_bronze")
