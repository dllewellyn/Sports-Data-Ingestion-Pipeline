"""Bronze ingestor for the football-data.co.uk EXTRA family (`new/<CODE>`, utf-8-sig).

One Parquet per league code under ``data/bronze/football_extra/<code>.parquet``
(one file holds every season; season is carried in-file). Read with utf-8-sig so
the UTF-8 BOM header is normalised (`Country`, not `ï»¿Country`) — reading these as
latin-1 is a defect (E2). Network access stays in the bronze layer; per-file
failures are isolated then re-raised so the run status reflects them.

No ``from __future__ import annotations`` — Dagster introspects the annotations.
"""

from datetime import date

from dagster import AssetKey, MaterializeResult, asset

from ...config import settings
from ...football.asset_results import to_materialize_result
from ...football.discovery import DiscoveredFile, discover_files
from ...football.http_client import ThrottledFetcher, ThrottledHttpClient
from ...football.ingest import IngestionReport, ingest_family
from ...football.registry import EXTRA_LEAGUES, ExtraLeague
from ...models.schemas import ExtraMatchRecord
from ...models.validation import extra_bronze_schema

EXTRA_CORE = ["Country", "League", "Season", "Date", "Home", "Away", "HG", "AG", "Res"]


def extra_out_path(file: DiscoveredFile):
    """Deterministic bronze path for one extra-family file (A6)."""
    return settings.football_extra_dir / f"{file.code}.parquet"


def run_extra_backfill(
    fetcher: ThrottledFetcher,
    run_date: date,
    *,
    leagues: list[ExtraLeague] | tuple[ExtraLeague, ...] = EXTRA_LEAGUES,
    log=None,
) -> IngestionReport:
    """Discover + ingest every whitelisted extra file. Pure of Dagster (testable)."""
    files = discover_files(fetcher.get_text, main_leagues=[], extra_leagues=leagues)
    if log is not None:
        log.info("discovered %d extra-family files", len(files))
    return ingest_family(
        files,
        fetcher,
        run_date,
        log=log,
        encoding="utf-8-sig",
        model=ExtraMatchRecord,
        schema=extra_bronze_schema,
        core=EXTRA_CORE,
        out_path_for=extra_out_path,
    )


@asset(
    key=AssetKey(["football_extra"]),
    group_name="bronze",
    compute_kind="python",
    description="football-data.co.uk extra family (new/<CODE>, utf-8-sig) → one Parquet per code.",
)
def football_extra(context, football_http: ThrottledHttpClient) -> MaterializeResult:
    fetcher = football_http.build_fetcher()
    report = run_extra_backfill(fetcher, date.today(), log=context.log)
    return to_materialize_result(report, context.log, "football_extra")
