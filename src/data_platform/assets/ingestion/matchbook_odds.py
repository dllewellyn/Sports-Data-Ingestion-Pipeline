"""Observable source asset for the Matchbook odds-tick bronze layer.

The odds ticks are produced **outside Dagster** by a long-lived streaming daemon
(``matchbook.ingestor.direct_parquet_consumer``, the ``matchbook-ingestor``
compose service): it subscribes to the Redis ``matchbook_odds_stream`` pub/sub
channel and flushes ZSTD Parquet to ``bronze/matchbook_odds/`` every 5 000 ticks
or 60 s.

A continuous consumer is deliberately **not** a materializing asset — a
materialization run must terminate, and micro-batching a fire-and-forget pub/sub
stream would drop ticks (Redis pub/sub has no replay). So we model the daemon's
*output* as an ``@observable_source_asset``: it gives the asset graph a real
upstream node for ``stg_matchbook_odds`` to descend from (wired via
``BronzeAwareTranslator``), and each observation records how fresh the newest
Parquet file is, so the lineage view shows whether ticks are still flowing.

No ``from __future__ import annotations`` — Dagster introspects annotations.
"""

from datetime import UTC, datetime

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetKey,
    DataVersion,
    ObserveResult,
    asset_check,
    observable_source_asset,
)

from ...config import settings

# Odds ticks only stream while markets are live; overnight the newest file is
# legitimately stale. This threshold is intentionally generous and the check
# WARNs rather than fails, so a dead daemon / dry Redis stream during trading
# hours is visible without paging on every quiet off-market period.
STALE_AFTER_SECONDS = 60 * 60  # 1 hour


def _newest_parquet_mtime() -> float | None:
    """mtime (epoch seconds) of the most recent odds Parquet, or None if none exist."""
    root = settings.matchbook_bronze_dir
    if not root.exists():
        return None
    mtimes = [p.stat().st_mtime for p in root.rglob("*.parquet")]
    return max(mtimes) if mtimes else None


@observable_source_asset(
    key=AssetKey(["matchbook_odds_bronze"]),
    group_name="bronze",
    description=(
        "Matchbook odds ticks (bronze Parquet), produced out-of-band by the "
        "matchbook-ingestor daemon from the Redis odds stream. Observed for "
        "freshness by Dagster, never materialized by it."
    ),
)
def matchbook_odds_bronze() -> ObserveResult:
    newest = _newest_parquet_mtime()
    if newest is None:
        return ObserveResult(
            data_version=DataVersion("no-data"),
            metadata={"newest_file_epoch_s": 0, "seconds_since_last_tick_file": -1},
        )
    age_s = round(datetime.now(tz=UTC).timestamp() - newest)
    return ObserveResult(
        data_version=DataVersion(str(int(newest))),
        metadata={
            "newest_file_epoch_s": int(newest),
            "seconds_since_last_tick_file": age_s,
        },
    )


@asset_check(
    asset=matchbook_odds_bronze,
    name="odds_stream_fresh",
    description=(
        "WARNs when no odds Parquet has been written for over an hour — a dead "
        "ingestor daemon or a dry Redis stream. Expected to warn outside live "
        "market hours, when no ticks are published."
    ),
)
def odds_stream_fresh() -> AssetCheckResult:
    newest = _newest_parquet_mtime()
    if newest is None:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"reason": "no matchbook_odds Parquet files found"},
        )
    age_s = round(datetime.now(tz=UTC).timestamp() - newest)
    return AssetCheckResult(
        passed=age_s <= STALE_AFTER_SECONDS,
        severity=AssetCheckSeverity.WARN,
        metadata={
            "seconds_since_last_tick_file": age_s,
            "newest_file_epoch_s": int(newest),
            "stale_after_seconds": STALE_AFTER_SECONDS,
        },
    )
