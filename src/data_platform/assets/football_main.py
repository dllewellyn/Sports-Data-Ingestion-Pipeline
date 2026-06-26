"""Bronze ingestor for the football-data.co.uk MAIN family (`mmz4281`, latin-1).

One Parquet per season×division file under
``data/bronze/football_main/<league>/<season>/<div>.parquet`` (season from the URL
path). Network access stays in the bronze layer (ARCHITECTURE rule #1): discovery
page GETs and file GETs both flow through the shared throttled client. Per-file
failures are isolated; the asset then re-raises so the run status reflects them.

No ``from __future__ import annotations`` — Dagster introspects the annotations.
"""

from datetime import date

from dagster import AssetKey, MaterializeResult, MetadataValue, asset

from ..config import settings
from ..football.discovery import DiscoveredFile, discover_files
from ..football.http_client import ThrottledFetcher, ThrottledHttpClient
from ..football.ingest import IngestionReport, ingest_family
from ..football.registry import MAIN_LEAGUES, MainLeague
from ..models.schemas import MainMatchRecord
from ..models.validation import main_bronze_schema

MAIN_CORE = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]


def main_out_path(file: DiscoveredFile):
    """Deterministic bronze path for one main-family file (A6)."""
    return settings.football_main_dir / file.league / file.season / f"{file.division}.parquet"


def run_main_backfill(
    fetcher: ThrottledFetcher,
    run_date: date,
    *,
    leagues: list[MainLeague] | tuple[MainLeague, ...] = MAIN_LEAGUES,
    log=None,
) -> IngestionReport:
    """Discover + ingest every whitelisted main file. Pure of Dagster (testable)."""
    files = discover_files(fetcher.get_text, main_leagues=leagues, extra_leagues=[])
    if log is not None:
        log.info("discovered %d main-family files", len(files))
    return ingest_family(
        files,
        fetcher,
        run_date,
        log=log,
        encoding="latin-1",
        model=MainMatchRecord,
        schema=main_bronze_schema,
        core=MAIN_CORE,
        out_path_for=main_out_path,
    )


def _to_result(report: IngestionReport, context, label: str) -> MaterializeResult:
    valid = sum(r.valid_count for r in report.written)
    reject = sum(r.reject_count for r in report.written)
    metadata = {
        "files_written": MetadataValue.int(len(report.written)),
        "files_skipped": MetadataValue.int(len(report.skipped)),
        "files_failed": MetadataValue.int(len(report.failed)),
        "valid_rows": MetadataValue.int(valid),
        "reject_rows": MetadataValue.int(reject),
    }
    if report.failed:
        failed_urls = [r.file.url for r in report.failed]
        context.log.error("%s: %d file(s) failed: %s", label, len(failed_urls), failed_urls[:20])
        # Surface in run status: successful Parquet files persist, but the run fails.
        raise RuntimeError(
            f"{label}: {len(failed_urls)} file(s) failed to ingest; see logs. "
            f"first: {failed_urls[:5]}"
        )
    return MaterializeResult(metadata=metadata)


@asset(
    key=AssetKey(["football_main"]),
    group_name="bronze",
    compute_kind="python",
    description="football-data.co.uk main family (mmz4281, latin-1) → one bronze Parquet per file.",
)
def football_main(context, football_http: ThrottledHttpClient) -> MaterializeResult:
    fetcher = football_http.build_fetcher()
    report = run_main_backfill(fetcher, date.today(), log=context.log)
    return _to_result(report, context, "football_main")
