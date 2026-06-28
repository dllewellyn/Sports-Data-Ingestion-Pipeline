"""
matchbook_odds schema loader
============================
Loads ``matchbook_odds_schema.json`` (the single source of truth) and
exposes a PyArrow ``Schema`` and the dedup field list for use by any
Python service that reads or writes these Parquet files.
"""

import json
from pathlib import Path

import pyarrow as pa

_SCHEMA_PATH = Path(__file__).with_name("matchbook_odds_schema.json")

_ARROW_TYPE_MAP: dict[str, pa.DataType] = {
    "int64":              pa.int64(),
    "float64":            pa.float64(),
    "string":             pa.string(),
    "bool":               pa.bool_(),
    "timestamp[ms, UTC]": pa.timestamp("ms", tz="UTC"),
}


def _load_raw() -> dict:
    with _SCHEMA_PATH.open() as fh:
        return json.load(fh)


def build_arrow_schema() -> pa.Schema:
    """Return a ``pa.Schema`` derived from ``matchbook_odds_schema.json``."""
    raw = _load_raw()
    fields = []
    for f in raw["fields"]:
        arrow_type = _ARROW_TYPE_MAP[f["type"]]
        fields.append(pa.field(f["name"], arrow_type))
    return pa.schema(fields)


def dedup_fields() -> list[str]:
    """Return the ordered list of field names used for tick deduplication."""
    return _load_raw()["dedup_fields"]


# Module-level singletons — loaded once on import.
SCHEMA: pa.Schema = build_arrow_schema()
DEDUP_FIELDS: tuple[str, ...] = tuple(dedup_fields())
