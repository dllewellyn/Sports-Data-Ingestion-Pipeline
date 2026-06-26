"""Map an IngestionReport onto a Dagster MaterializeResult (shared by both assets).

Kept out of the asset modules so the two family ingestors don't import each other
(ARCHITECTURE rule #4). The football package already depends on Dagster (the
ConfigurableResource in `http_client`), so a Dagster-aware helper belongs here
rather than duplicated per asset.
"""

from __future__ import annotations

from dagster import MaterializeResult, MetadataValue

from .ingest import IngestionReport


def to_materialize_result(report: IngestionReport, log, label: str) -> MaterializeResult:
    """Summarise the run; raise if any file failed so the run status reflects it.

    Successful Parquet files are already on disk; raising only marks the run failed
    (per-file isolation already let every file be attempted). Skipped = already-landed
    immutable historical files (idempotent re-run).
    """
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
        if log is not None:
            log.error("%s: %d file(s) failed: %s", label, len(failed_urls), failed_urls[:20])
        raise RuntimeError(
            f"{label}: {len(failed_urls)} file(s) failed to ingest; see logs. "
            f"first: {failed_urls[:5]}"
        )
    return MaterializeResult(metadata=metadata)


__all__ = ["to_materialize_result"]
