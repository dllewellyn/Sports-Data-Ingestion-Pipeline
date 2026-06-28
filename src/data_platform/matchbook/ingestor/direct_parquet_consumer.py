"""
Direct Parquet Lakehouse Ingestor
==================================
Reads the ``matchbook_odds_stream`` Redis channel and writes Silver-grade
Parquet files to the local NVMe lakehouse at ``/app/data/lake/silver/matchbook_odds/``.

Runs as a long-lived daemon alongside the existing Kotlin JSONL pipeline — both
consumers subscribe to the same Redis channel so there is no data loss during
the parallel-run phase.

Deduplication strategy
-----------------------
An in-memory dict keyed by ``(event_id, market_id, runner_id)`` tracks the last
published state for each runner.  A tick is buffered only when **any** of the
following change:

  - best_back_price / best_lay_price
  - best_back_available / best_lay_available
  - back_available_2/3, lay_available_2/3  (queue depth changes = fills / cancels)
  - runner_volume                          (total matched: fill detection)
  - market_volume
  - in_running / market_status

Flush triggers
--------------
The buffer is flushed to a ZSTD-compressed Parquet file whenever:
  - 5 000 state-change ticks have accumulated, OR
  - 60 seconds have elapsed since the last flush (and the buffer is non-empty)

On SIGTERM / SIGINT the buffer is flushed before exit so no ticks are lost.
"""

import json
import logging
import os
import signal
import time
from datetime import UTC, datetime
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import redis

try:
    from .schema import SCHEMA
except ImportError:
    # Fallback for direct execution: python -m ingestor.direct_parquet_consumer
    from schema import SCHEMA  # type: ignore[no-redef]

logger = logging.getLogger("ingestor.parquet")

FLUSH_TICK_THRESHOLD = 5_000
FLUSH_INTERVAL_S = 60


class DirectParquetConsumer:
    def __init__(
        self,
        redis_host: str = "redis",
        redis_port: int = 6379,
        lake_root: str = "/app/data/lake",
    ) -> None:
        self._redis = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self._lake_root = lake_root
        self._buffer: list[dict[str, Any]] = []
        self._dedup: dict[tuple[int, int, int], tuple] = {}
        self._last_flush = time.monotonic()
        self._running = True

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, _signum: int, _frame: Any) -> None:
        logger.info("Shutdown signal received — flushing buffer before exit")
        self._running = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Block forever, consuming the Redis pub/sub channel and writing Parquet files."""
        logger.info(
            "Starting Parquet consumer",
            extra={"lake_root": self._lake_root},
        )
        pubsub = self._redis.pubsub()
        pubsub.subscribe("matchbook_odds_stream")

        while self._running:
            # get_message is non-blocking; sleep briefly to avoid CPU spin.
            raw = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if raw and raw.get("type") == "message":
                try:
                    msg = json.loads(raw["data"])
                except (json.JSONDecodeError, KeyError):
                    logger.warning("Dropping unparseable message")
                else:
                    self._process_json_message(msg)

            elapsed = time.monotonic() - self._last_flush
            if len(self._buffer) >= FLUSH_TICK_THRESHOLD or (
                elapsed >= FLUSH_INTERVAL_S and self._buffer
            ):
                self._flush()

        # Final flush on clean shutdown
        pubsub.close()
        self._flush()
        logger.info("Parquet consumer stopped")

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _process_json_message(self, msg: dict[str, Any]) -> None:
        """Process a message parsed from JSON (pub/sub path).

        Unlike ``_process_message`` which expects string values (the XREAD /
        XADD wire format), this path receives native Python types from
        ``json.loads``: bools, ints, floats, and ``None`` for JSON null.
        """
        try:
            event_id = int(msg["event_id"])
            market_id = int(msg["market_id"])
            runner_id = int(msg["runner_id"])
        except (KeyError, ValueError, TypeError):
            logger.warning("Dropping malformed message: missing IDs")
            return

        key = (event_id, market_id, runner_id)
        state = (
            msg.get("best_back_price"),
            msg.get("best_lay_price"),
            msg.get("best_back_available"),
            msg.get("best_lay_available"),
            msg.get("back_available_2"),
            msg.get("back_available_3"),
            msg.get("lay_available_2"),
            msg.get("lay_available_3"),
            msg.get("market_volume"),
            msg.get("runner_volume"),
            msg.get("in_running"),
            msg.get("market_status"),
        )
        if self._dedup.get(key) == state:
            return
        self._dedup[key] = state

        ts_ns = msg.get("timestamp_ns")
        ingested_at = int(ts_ns) // 1_000_000 if ts_ns is not None else int(time.time() * 1000)

        self._buffer.append(
            {
                "event_id": event_id,
                "market_id": market_id,
                "runner_id": runner_id,
                "ingested_at": ingested_at,
                "sport_id": _coerce_int(msg.get("sport_id")),
                "market_type": msg.get("market_type"),
                "market_status": msg.get("market_status"),
                "in_running": bool(msg.get("in_running")),
                "best_back_price": _coerce_float(msg.get("best_back_price")),
                "best_back_available": _coerce_float(msg.get("best_back_available")),
                "best_lay_price": _coerce_float(msg.get("best_lay_price")),
                "best_lay_available": _coerce_float(msg.get("best_lay_available")),
                "back_price_2": _coerce_float(msg.get("back_price_2")),
                "back_available_2": _coerce_float(msg.get("back_available_2")),
                "back_price_3": _coerce_float(msg.get("back_price_3")),
                "back_available_3": _coerce_float(msg.get("back_available_3")),
                "lay_price_2": _coerce_float(msg.get("lay_price_2")),
                "lay_available_2": _coerce_float(msg.get("lay_available_2")),
                "lay_price_3": _coerce_float(msg.get("lay_price_3")),
                "lay_available_3": _coerce_float(msg.get("lay_available_3")),
                "back_depth": _coerce_float(msg.get("back_depth")),
                "lay_depth": _coerce_float(msg.get("lay_depth")),
                "wom": _coerce_float(msg.get("wom")),
                "market_volume": _coerce_float(msg.get("market_volume")),
                "runner_volume": _coerce_float(msg.get("runner_volume")),
                "handicap_line": _coerce_float(msg.get("handicap_line")),  # None if JSON null
                "event_participant_id": _coerce_int(msg.get("event_participant_id")),
                "kickoff_ms": _coerce_int(msg.get("kickoff_ms")),
            }
        )

    def _build_dedup_state(self, msg: dict[str, str]) -> tuple:
        return (
            _float(msg, "best_back_price"),
            _float(msg, "best_lay_price"),
            _float(msg, "best_back_available"),
            _float(msg, "best_lay_available"),
            _float(msg, "back_available_2"),
            _float(msg, "back_available_3"),
            _float(msg, "lay_available_2"),
            _float(msg, "lay_available_3"),
            _float(msg, "market_volume"),
            _float(msg, "runner_volume"),
            msg.get("in_running"),
            msg.get("market_status"),
        )

    def _process_message(self, msg: dict[str, str]) -> None:
        try:
            event_id = int(msg["event_id"])
            market_id = int(msg["market_id"])
            runner_id = int(msg["runner_id"])
        except (KeyError, ValueError):
            logger.warning("Dropping malformed message: missing IDs")
            return

        key = (event_id, market_id, runner_id)
        state = self._build_dedup_state(msg)
        if self._dedup.get(key) == state:
            return
        self._dedup[key] = state

        ts_ns = msg.get("timestamp_ns")
        ingested_at = (
            int(ts_ns) // 1_000_000  # ns → ms
            if ts_ns is not None
            else int(time.time() * 1000)
        )

        self._buffer.append(
            {
                "event_id": event_id,
                "market_id": market_id,
                "runner_id": runner_id,
                "ingested_at": ingested_at,
                "sport_id": _int(msg, "sport_id"),
                "market_type": msg.get("market_type"),
                "market_status": msg.get("market_status"),
                "in_running": msg.get("in_running") in ("true", "True", True),
                "best_back_price": _float(msg, "best_back_price"),
                "best_back_available": _float(msg, "best_back_available"),
                "best_lay_price": _float(msg, "best_lay_price"),
                "best_lay_available": _float(msg, "best_lay_available"),
                "back_price_2": _float(msg, "back_price_2"),
                "back_available_2": _float(msg, "back_available_2"),
                "back_price_3": _float(msg, "back_price_3"),
                "back_available_3": _float(msg, "back_available_3"),
                "lay_price_2": _float(msg, "lay_price_2"),
                "lay_available_2": _float(msg, "lay_available_2"),
                "lay_price_3": _float(msg, "lay_price_3"),
                "lay_available_3": _float(msg, "lay_available_3"),
                "back_depth": _float(msg, "back_depth"),
                "lay_depth": _float(msg, "lay_depth"),
                "wom": _float(msg, "wom"),
                "market_volume": _float(msg, "market_volume"),
                "runner_volume": _float(msg, "runner_volume"),
                "handicap_line": _optional_float(msg, "handicap_line"),
                "event_participant_id": _int(msg, "event_participant_id"),
                "kickoff_ms": _int(msg, "kickoff_ms"),
            }
        )

    def _flush(self) -> None:
        if not self._buffer:
            return

        rows = self._buffer
        self._buffer = []
        self._last_flush = time.monotonic()

        table = _rows_to_arrow(rows)
        _write_parquet(table, self._lake_root)
        logger.info("Flushed %d ticks to Parquet", len(rows))


# ── Arrow helpers ──────────────────────────────────────────────────────────────


def _rows_to_arrow(rows: list[dict[str, Any]]) -> pa.Table:
    columns: dict[str, list] = {field.name: [] for field in SCHEMA}
    for row in rows:
        for field in SCHEMA:
            columns[field.name].append(row.get(field.name))

    arrays = []
    for field in SCHEMA:
        col = columns[field.name]
        if pa.types.is_timestamp(field.type):
            arrays.append(pa.array(col, type=field.type))
        else:
            arrays.append(pa.array(col, type=field.type))

    return pa.table(arrays, schema=SCHEMA)


def _write_parquet(table: pa.Table, lake_root: str) -> None:
    now = datetime.now(tz=UTC)
    dest_dir = os.path.join(
        lake_root,
        "silver",
        "matchbook_odds",
        f"year={now.year}",
        f"month={now.month:02d}",
        f"day={now.day:02d}",
    )
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, f"part-{int(time.time() * 1000)}.parquet")
    pq.write_table(table, path, compression="zstd")


# ── Parsing helpers ────────────────────────────────────────────────────────────


def _coerce_float(v: Any) -> float | None:
    """Coerce a native Python value (from JSON) to float, or None."""
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _coerce_int(v: Any) -> int | None:
    """Coerce a native Python value (from JSON) to int, or None."""
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _float(msg: dict[str, str], key: str) -> float | None:
    v = msg.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _optional_float(msg: dict[str, str], key: str) -> float | None:
    """Returns None for missing keys and for JSON null values."""
    v = msg.get(key)
    if v is None or v == "null":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _int(msg: dict[str, str], key: str) -> int | None:
    v = msg.get(key)
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


# ── Entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(description="Direct Parquet lakehouse ingestor")
    parser.add_argument("--redis-host", default=os.getenv("REDIS_HOST", "redis"))
    parser.add_argument("--redis-port", type=int, default=int(os.getenv("REDIS_PORT", "6379")))
    parser.add_argument("--lake-root", default=os.getenv("LAKE_ROOT", "/app/data/lake"))
    args = parser.parse_args()

    DirectParquetConsumer(
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        lake_root=args.lake_root,
    ).run()
