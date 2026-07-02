"""Shared helpers for the one-off PostgreSQL → bronze Parquet migration engines.

Both provider engines (`espn.py`, `matchbook.py`) follow the same boundary-
validation and write flow: validate each candidate row against a Pydantic record
model (counting per-record failures without aborting the batch), validate the
resulting frame against a Pandera schema, then write it atomically (temp file +
rename). Those two steps are the genuinely-shared piece and live here.

The report shapes differ per provider — ESPN reports per (league, season)
`UnitResult`, Matchbook per-sport `SportResult` — so each engine keeps its own
report; only the validate/write flow is shared.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import pandera.pandas as pa
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


def validate_records(
    candidates: list[dict],
    record_model: type[BaseModel],
    *,
    log: Any | None,
    context: str,
) -> tuple[list[dict], int]:
    """Validate each candidate row against the Pydantic record model.

    Returns the rows that passed and the count that failed. A per-record failure is
    logged and counted, never raised, so one bad row does not abort the batch.
    ``context`` labels the batch in warning logs (e.g. ``"epl/2023"`` or ``"football"``).
    """
    valid: list[dict] = []
    failed = 0
    for row in candidates:
        try:
            record_model.model_validate(row)
            valid.append(row)
        except ValidationError as exc:
            failed += 1
            if log:
                log.warning("migration: skipping invalid row in %s: %s", context, exc)
    return valid, failed


def write_frame_atomic(rows: list[dict], schema: pa.DataFrameSchema, out_path: Path) -> int:
    """Validate the rows as a frame and write it atomically to ``out_path``.

    Builds a DataFrame, validates it against the Pandera schema, then writes via a
    temp file + rename so a partial file is never left behind. Returns the row count
    written. The caller creates the parent directory as needed.
    """
    df = pd.DataFrame(rows)
    schema.validate(df)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(out_path)
    return len(df)
