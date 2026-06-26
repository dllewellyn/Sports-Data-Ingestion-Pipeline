"""Shared bronze ingest engine for both football-data families (Dagster-free).

One source CSV → one bronze Parquet. The flow per file is: fetch (honouring the
client's cache/skip policy) → decode with the family's mandated encoding → row-level
core validation (Pydantic, skip-and-count invalid rows) → frame-level validation
(Pandera, open contract) → write **one** Parquet at a deterministic path, inside an
OTel span. Failures are **isolated per file** (A5): a fetch error, a zero-valid file
(E8), a schema failure, or any unexpected error is recorded and the run continues —
and crucially **no partial or empty Parquet is written** for a failed file.

This module is intentionally free of Dagster so it is unit-testable; the thin
`assets/football_main.py` / `assets/football_extra.py` wrappers supply the resource,
discovery, run date, and Dagster metadata/run-status surfacing.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
import pandera.pandas as pa
from pydantic import BaseModel, ValidationError

from ..otel import get_tracer
from .discovery import DiscoveredFile
from .registry import Family


class ZeroValidRowsError(RuntimeError):
    """A file parsed but produced no rows that pass core validation (E8)."""


class SourceFetcher(Protocol):
    """The slice of the throttled client this engine needs (eases faking in tests)."""

    def fetch_source(
        self,
        *,
        url: str,
        family: Family,
        season_token: str | None,
        run_date: date,
        artifact_path: Path | None,
    ) -> bytes | None: ...


@dataclass(frozen=True)
class FileResult:
    file: DiscoveredFile
    status: str  # "written" | "skipped" | "failed"
    out_path: Path | None = None
    raw_count: int = 0
    valid_count: int = 0
    reject_count: int = 0
    error: str | None = None


@dataclass
class IngestionReport:
    written: list[FileResult] = field(default_factory=list)
    skipped: list[FileResult] = field(default_factory=list)
    failed: list[FileResult] = field(default_factory=list)

    @property
    def attempted(self) -> int:
        return len(self.written) + len(self.skipped) + len(self.failed)


def decode_csv(raw: bytes, encoding: str) -> pd.DataFrame:
    """Decode CSV bytes with the family's mandated encoding (main=latin-1, extra=utf-8-sig).

    Trailing fully-empty ``Unnamed`` columns (common in these files) are dropped;
    everything else rides along faithfully (bronze is faithful-to-source).
    """
    df = pd.read_csv(io.BytesIO(raw), encoding=encoding, on_bad_lines="skip")
    keep = [c for c in df.columns if not (str(c).startswith("Unnamed") and df[c].isna().all())]
    return df.loc[:, keep]


def validate_rows(
    df: pd.DataFrame, model: type[BaseModel], core: list[str]
) -> tuple[pd.DataFrame, int, int, int]:
    """Row-level core validation: keep rows passing the Pydantic core, count rejects.

    Invalid rows (blank/footer/incomplete, or any row when a core column is absent)
    are dropped — never raised out — so one bad row can't lose a whole file. Returns
    (valid_frame, raw_count, valid_count, reject_count).
    """
    raw_count = len(df)
    records = df.to_dict("records")
    keep_mask: list[bool] = []
    for rec in records:
        try:
            model.model_validate(rec)
            keep_mask.append(True)
        except ValidationError:
            keep_mask.append(False)
    valid_df = df.loc[keep_mask].reset_index(drop=True)
    valid_count = len(valid_df)
    return valid_df, raw_count, valid_count, raw_count - valid_count


def ingest_file(
    file: DiscoveredFile,
    fetcher: SourceFetcher,
    run_date: date,
    *,
    encoding: str,
    model: type[BaseModel],
    schema: pa.DataFrameSchema,
    core: list[str],
    out_path: Path,
) -> FileResult:
    """Ingest one source file into one bronze Parquet, or report it skipped.

    Raises on any failure (fetch, zero-valid, schema) *before* writing, so a failed
    file never leaves a partial/empty Parquet behind. The write itself is atomic
    (temp file + rename) so an interrupted write also leaves no partial artifact.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(f"ingest.football_{file.family.value}") as span:
        span.set_attribute("source.url", file.url)
        span.set_attribute("source.family", file.family.value)

        raw = fetcher.fetch_source(
            url=file.url,
            family=file.family,
            season_token=file.season,
            run_date=run_date,
            artifact_path=out_path,
        )
        if raw is None:
            span.set_attribute("ingest.skipped", True)
            return FileResult(file, "skipped", out_path)

        df = decode_csv(raw, encoding)
        valid_df, raw_count, valid_count, reject_count = validate_rows(df, model, core)
        span.set_attribute("ingest.raw_rows", raw_count)
        span.set_attribute("ingest.valid_rows", valid_count)
        span.set_attribute("ingest.reject_rows", reject_count)

        if valid_count == 0:
            raise ZeroValidRowsError(f"{file.url}: 0 valid rows of {raw_count}")

        validated = schema.validate(valid_df)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_name(out_path.name + ".tmp")
        validated.to_parquet(tmp_path, index=False)
        tmp_path.replace(out_path)  # atomic: no partial Parquet on interruption
        span.set_attribute("output.path", str(out_path))
        span.set_attribute("output.rows", len(validated))

        return FileResult(file, "written", out_path, raw_count, valid_count, reject_count)


def ingest_family(
    files: list[DiscoveredFile],
    fetcher: SourceFetcher,
    run_date: date,
    *,
    log: Any | None,
    encoding: str,
    model: type[BaseModel],
    schema: pa.DataFrameSchema,
    core: list[str],
    out_path_for: Callable[[DiscoveredFile], Path],
) -> IngestionReport:
    """Ingest every discovered file, isolating per-file failures (A5).

    Each file lands a Parquet, is skipped (already-landed historical), or fails —
    failures are logged and recorded but never abort the run, and never leave a
    partial/empty Parquet. The caller decides how to surface ``report.failed`` in
    the asset's run status.
    """
    report = IngestionReport()
    for file in files:
        out_path = out_path_for(file)
        try:
            result = ingest_file(
                file,
                fetcher,
                run_date,
                encoding=encoding,
                model=model,
                schema=schema,
                core=core,
                out_path=out_path,
            )
        except Exception as exc:  # noqa: BLE001 — per-file isolation is the design (A5)
            if log is not None:
                log.error("football ingest failed for %s: %s", file.url, exc)
            report.failed.append(FileResult(file, "failed", None, error=str(exc)))
            continue
        (report.written if result.status == "written" else report.skipped).append(result)
    return report


__all__ = [
    "ZeroValidRowsError",
    "SourceFetcher",
    "FileResult",
    "IngestionReport",
    "decode_csv",
    "validate_rows",
    "ingest_file",
    "ingest_family",
]
