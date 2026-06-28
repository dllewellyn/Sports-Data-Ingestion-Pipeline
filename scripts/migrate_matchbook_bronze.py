#!/usr/bin/env python3
"""Migrate Matchbook bronze Parquet from sports-gaming-engine lakehouse to this project.

Usage
-----
    python scripts/migrate_matchbook_bronze.py \\
        --source-dir /path/to/extracted/lake/silver/matchbook_odds \\
        [--dest-dir data/bronze] \\
        [--dry-run]

macOS / Docker Desktop — volume extraction prerequisite
-------------------------------------------------------
The lakehouse_data Docker volume is not directly accessible on the macOS host.
Extract it first:

    docker run --rm \\
        -v lakehouse_data:/data \\
        -v $(pwd):/out \\
        alpine tar cf /out/lake.tar -C /data .
    mkdir -p /tmp/lake && tar xf lake.tar -C /tmp/lake

Then run this script with --source-dir /tmp/lake/silver/matchbook_odds.

Source layout expected
----------------------
    <source-dir>/year=YYYY/month=MM/day=DD/<filename>.parquet

Destination layout produced
---------------------------
    <dest-dir>/matchbook_odds/year=YYYY/month=MM/day=DD/part-<filename>.parquet
"""

import argparse
import contextlib
import shutil
import sys
from pathlib import Path


def _extract_partition(source: Path) -> tuple[int, int, int] | None:
    """Walk path components to extract year/month/day Hive partition tokens.

    Returns (year, month, day) if all three tokens are found, else None.
    """
    year = month = day = None
    for part in source.parts:
        if part.startswith("year="):
            with contextlib.suppress(ValueError):
                year = int(part[5:])
        elif part.startswith("month="):
            with contextlib.suppress(ValueError):
                month = int(part[6:])
        elif part.startswith("day="):
            with contextlib.suppress(ValueError):
                day = int(part[4:])
    if year is not None and month is not None and day is not None:
        return year, month, day
    return None


def _derive_date_from_parquet(source: Path) -> tuple[int, int, int]:
    """Read ingested_at minimum from Parquet to derive date as fallback."""
    import pyarrow.parquet as pq

    table = pq.read_table(source, columns=["ingested_at"])
    ts = table.column("ingested_at")[0].as_py()
    return ts.year, ts.month, ts.day


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source-dir",
        required=True,
        help="Path to the locally accessible matchbook_odds Parquet directory.",
    )
    parser.add_argument(
        "--dest-dir",
        default="data/bronze",
        help="Destination bronze root (default: data/bronze).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be copied without writing any files.",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    dest_dir = Path(args.dest_dir)

    if not source_dir.exists():
        print(f"ERROR: source-dir does not exist: {source_dir}", file=sys.stderr)
        sys.exit(1)

    sources = sorted(source_dir.rglob("*.parquet"))
    if not sources:
        print(f"No .parquet files found under {source_dir}", file=sys.stderr)
        sys.exit(1)

    copied = skipped = 0

    for src in sources:
        partition = _extract_partition(src)
        if partition is None:
            try:
                partition = _derive_date_from_parquet(src)
            except Exception as exc:
                print(f"SKIP {src} (could not determine date: {exc})")
                skipped += 1
                continue

        y, m, d = partition
        dest = (
            dest_dir / "matchbook_odds" / f"year={y}" / f"month={m:02d}" / f"day={d:02d}" / src.name
        )

        if dest.exists():
            print(f"SKIP {dest}")
            skipped += 1
            continue

        if args.dry_run:
            print(f"WOULD COPY {src} -> {dest}")
            copied += 1
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"COPY {src} -> {dest}")
        copied += 1

    print(f"\nCopied: {copied}  Skipped: {skipped}")


if __name__ == "__main__":
    main()
