"""Behaviour of the shared migration helpers extracted into `migrate/base.py`.

`validate_records` must pass valid rows through and skip-and-count invalid ones
without aborting the batch; `write_frame_atomic` must Pandera-validate the frame and
write it via a temp file + rename (no partial file left behind on success).
"""

from pathlib import Path

from data_platform.migrate.base import validate_records, write_frame_atomic
from data_platform.models.schemas import MatchbookEventRecord
from data_platform.models.validation import matchbook_events_bronze_schema


def _valid_row(event_id: str = "1") -> dict:
    return {
        "event_id": event_id,
        "event_name": "A vs B",
        "sport_id": 15,
        "status": "open",
        "start_utc": "2026-01-01T12:00:00+00:00",
        "volume": 100.0,
        "ingested_at": "2026-01-01T00:00:00Z",
        "raw_event": "{}",
    }


def test_validate_records_keeps_valid_and_counts_invalid() -> None:
    good = _valid_row("1")
    bad = _valid_row("2")
    del bad["status"]  # missing required core field → Pydantic failure

    valid, failed = validate_records(
        [good, bad], MatchbookEventRecord, log=None, context="football"
    )

    assert valid == [good]
    assert failed == 1


def test_validate_records_all_valid_reports_zero_failures() -> None:
    rows = [_valid_row("1"), _valid_row("2")]
    valid, failed = validate_records(rows, MatchbookEventRecord, log=None, context="football")
    assert len(valid) == 2
    assert failed == 0


def test_write_frame_atomic_writes_file_and_returns_count(tmp_path: Path) -> None:
    rows = [_valid_row("1"), _valid_row("2")]
    out_path = tmp_path / "football" / "2026-01-01" / "migration.parquet"

    written = write_frame_atomic(rows, matchbook_events_bronze_schema, out_path)

    assert written == 2
    assert out_path.exists()
    # No stray temp file remains after a successful atomic write.
    assert not out_path.with_suffix(".tmp").exists()
