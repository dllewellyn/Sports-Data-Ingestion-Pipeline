"""Map an ESPN IngestionReport onto a Dagster MaterializeResult.

Kept out of the asset module (mirroring ``football/asset_results.py``) so the
Dagster-aware summary helper sits beside the engine it summarises. Raises if any
unit failed so the run status reflects it (per-unit isolation already let every
unit be attempted; successful Parquet files are already on disk).
"""

from __future__ import annotations

from dagster import MaterializeResult, MetadataValue

from .ingest import IngestionReport


def to_materialize_result(report: IngestionReport, log, label: str) -> MaterializeResult:
    """Summarise the run; raise if any unit failed so the run status reflects it."""
    valid = sum(r.valid_count for r in report.written)
    reject = sum(r.reject_count for r in report.written)
    metadata = {
        "units_written": MetadataValue.int(len(report.written)),
        "units_failed": MetadataValue.int(len(report.failed)),
        "valid_rows": MetadataValue.int(valid),
        "reject_rows": MetadataValue.int(reject),
    }
    if report.failed:
        failed = [r.unit.scoreboard_url for r in report.failed]
        if log is not None:
            log.error("%s: %d unit(s) failed: %s", label, len(failed), failed[:20])
        raise RuntimeError(
            f"{label}: {len(failed)} unit(s) failed to ingest; see logs. first: {failed[:5]}"
        )
    return MaterializeResult(metadata=metadata)


__all__ = ["to_materialize_result"]
