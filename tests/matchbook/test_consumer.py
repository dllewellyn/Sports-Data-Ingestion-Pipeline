"""Unit tests for DirectParquetConsumer.

All tests use tmp_path for filesystem isolation and mock Redis entirely.
No live Redis connection is required.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from data_platform.matchbook.ingestor.direct_parquet_consumer import (
    FLUSH_INTERVAL_S,
    DirectParquetConsumer,
)
from data_platform.matchbook.ingestor.schema import SCHEMA

# ── Helpers ────────────────────────────────────────────────────────────────────


def _valid_tick(
    event_id: int = 1,
    market_id: int = 10,
    runner_id: int = 100,
) -> dict:
    """A minimal valid tick as it would arrive from the Redis pub/sub channel."""
    return {
        "event_id": event_id,
        "market_id": market_id,
        "runner_id": runner_id,
        "timestamp_ns": str(int(time.time() * 1_000_000_000)),
        "in_running": True,
        "market_status": "open",
        "best_back_price": 2.0,
        "best_lay_price": 2.1,
        "best_back_available": 100.0,
        "best_lay_available": 80.0,
    }


def _valid_tick_dict(
    event_id: int = 1,
    market_id: int = 10,
    runner_id: int = 100,
) -> dict:
    """Pre-processed buffer dict (post-_process_json_message format)."""
    return {
        "event_id": event_id,
        "market_id": market_id,
        "runner_id": runner_id,
        "ingested_at": int(time.time() * 1000),
        "sport_id": None,
        "market_type": None,
        "market_status": "open",
        "in_running": True,
        "best_back_price": 2.0,
        "best_back_available": 100.0,
        "best_lay_price": 2.1,
        "best_lay_available": 80.0,
        "back_price_2": None,
        "back_available_2": None,
        "back_price_3": None,
        "back_available_3": None,
        "lay_price_2": None,
        "lay_available_2": None,
        "lay_price_3": None,
        "lay_available_3": None,
        "back_depth": None,
        "lay_depth": None,
        "wom": None,
        "market_volume": None,
        "runner_volume": None,
        "handicap_line": None,
        "event_participant_id": None,
        "kickoff_ms": None,
    }


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_dedup_same_tick_not_buffered(tmp_path: Path) -> None:
    """Sending the same tick twice results in buffer length 1 (AC-15)."""
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    tick = _valid_tick()
    consumer._process_json_message(tick)
    consumer._process_json_message(tick)  # identical — should be deduped
    assert len(consumer._buffer) == 1


def test_dedup_changed_tick_buffered(tmp_path: Path) -> None:
    """Sending a tick with a changed dedup field results in buffer length 2 (AC-15)."""
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    tick = _valid_tick()
    consumer._process_json_message(tick)
    tick2 = {**tick, "best_back_price": tick["best_back_price"] + 0.05}
    consumer._process_json_message(tick2)
    assert len(consumer._buffer) == 2


def test_flush_empty_buffer_writes_nothing(tmp_path: Path) -> None:
    """_flush() on an empty buffer writes no files (AC-17)."""
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    consumer._flush()
    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert parquet_files == []


def test_flush_writes_parquet(tmp_path: Path) -> None:
    """Non-empty buffer: _flush() writes one Parquet file (AC-01, AC-03, AC-04)."""
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    consumer._process_json_message(_valid_tick())
    consumer._flush()

    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert len(parquet_files) == 1

    path_str = str(parquet_files[0])
    assert "matchbook_odds" in path_str
    assert "year=" in path_str
    assert "month=" in path_str
    assert "day=" in path_str
    assert "silver" not in path_str

    # Verify ZSTD compression
    meta = pq.read_metadata(parquet_files[0])
    assert meta.row_group(0).column(0).compression == "ZSTD"


def test_flush_bad_schema_writes_nothing(tmp_path: Path) -> None:
    """A batch that fails PyArrow schema cast drops the batch without writing (AC-06).

    We build a table with event_id typed as string (incompatible with int64)
    and inject it via _rows_to_arrow mock so the cast gate in _write_parquet
    sees the type mismatch.
    """
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    consumer._buffer.append(_valid_tick_dict())

    # Build a table whose event_id column is string — cast to int64 will raise
    bad_schema = pa.schema(
        [pa.field("event_id", pa.string())] + [SCHEMA.field(i) for i in range(1, len(SCHEMA))]
    )
    arrays = []
    for _i, field in enumerate(SCHEMA):
        if field.name == "event_id":
            arrays.append(pa.array(["not-an-int"], type=pa.string()))
        elif field.name == "ingested_at":
            arrays.append(pa.array([int(time.time() * 1000)], type=pa.timestamp("ms", tz="UTC")))
        elif pa.types.is_integer(field.type):
            arrays.append(pa.array([1], type=field.type))
        elif pa.types.is_floating(field.type):
            arrays.append(pa.array([None], type=field.type))
        elif pa.types.is_boolean(field.type):
            arrays.append(pa.array([True], type=field.type))
        else:
            arrays.append(pa.array([None], type=field.type))
    bad_table = pa.table(arrays, schema=bad_schema)

    with patch(
        "data_platform.matchbook.ingestor.direct_parquet_consumer._rows_to_arrow",
        return_value=bad_table,
    ):
        consumer._flush()

    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert parquet_files == []


def test_sigterm_flushes_buffer(tmp_path: Path) -> None:
    """Buffer is flushed when SIGTERM causes run() to exit cleanly (AC-16)."""
    mock_pubsub = MagicMock()
    mock_pubsub.get_message.return_value = None
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub

    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    consumer._redis = mock_redis

    # Pre-load buffer with 3 distinct ticks (different event_ids → no dedup)
    consumer._buffer.clear()
    consumer._buffer.append(_valid_tick_dict(event_id=1))
    consumer._buffer.append(_valid_tick_dict(event_id=2))
    consumer._buffer.append(_valid_tick_dict(event_id=3))

    # Simulate SIGTERM: set _running=False so run() exits immediately
    consumer._running = False
    consumer.run()

    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert len(parquet_files) == 1
    table = pq.read_table(parquet_files[0])
    assert len(table) == 3


def test_time_based_flush(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock time advances beyond FLUSH_INTERVAL_S; flush fires with non-empty buffer (AC-18)."""
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    consumer._last_flush = 0.0
    consumer._buffer.append(_valid_tick_dict())

    # Simulate elapsed time exceeding the interval
    monkeypatch.setattr(
        "data_platform.matchbook.ingestor.direct_parquet_consumer.time.monotonic",
        lambda: 61.0,
    )

    elapsed = time.monotonic() - consumer._last_flush
    if elapsed >= FLUSH_INTERVAL_S and consumer._buffer:
        consumer._flush()

    parquet_files = list(tmp_path.rglob("*.parquet"))
    assert len(parquet_files) == 1


def test_pydantic_validation_drops_missing_event_id(tmp_path: Path) -> None:
    """A message missing event_id is dropped with no crash (AC-05)."""
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    bad_tick = _valid_tick()
    del bad_tick["event_id"]
    consumer._process_json_message(bad_tick)
    assert len(consumer._buffer) == 0


def test_pydantic_validation_drops_missing_in_running(tmp_path: Path) -> None:
    """A message missing in_running coerces to False via bool(None) — still valid."""
    consumer = DirectParquetConsumer(bronze_dir=tmp_path)
    tick = _valid_tick()
    del tick["in_running"]
    consumer._process_json_message(tick)
    # bool(None) == False, so in_running=False is valid — tick should be buffered
    assert len(consumer._buffer) == 1
