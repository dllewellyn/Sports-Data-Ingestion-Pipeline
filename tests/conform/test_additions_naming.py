"""T012: the match-additions Parquet is named matchbook_canonical_match_additions.

Spec 010 / US2 / FR-003: the conform engine writes its minted-canonical additions
to ``matchbook_canonical_match_additions.parquet`` (renamed from the older bare
``matchbook_canonical_additions.parquet``). This is a clean replace — the old name
must not survive anywhere in the source tree (no dual-read, no shim).
"""

import subprocess
from pathlib import Path

import pandas as pd

from data_platform.conform.matchbook import run_conform

OLD_NAME = "matchbook_canonical_additions.parquet"
NEW_NAME = "matchbook_canonical_match_additions.parquet"


def test_conform_writes_renamed_additions_file(tmp_path: Path) -> None:
    """run_conform over a new_canonical mint writes the renamed additions file."""
    events_dir = tmp_path / "events"
    canonical_dir = tmp_path / "canonical"
    exceptions_dir = tmp_path / "exceptions"
    conform_dir = tmp_path / "conform"
    additions_dir = tmp_path / "additions"
    overrides_path = tmp_path / "overrides" / "matchbook_overrides.parquet"

    events = [
        {
            "event_id": "900",
            "event_name": "New FC v Fresh United",
            "start_utc": "2026-08-10T15:00:00Z",
            "sport_id": 15,
            "ingested_at": 1,
        }
    ]
    overrides = [
        {
            "matchbook_event_id": "900",
            "action": "new_canonical",
            "match_id": None,
            "merge_source_match_id": None,
            "decided_at": "2026-06-29",
            "decided_by": "human_ui",
        }
    ]

    (events_dir / "football").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(events).to_parquet(events_dir / "football" / "batch.parquet")
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(overrides).to_parquet(overrides_path)

    report = run_conform(
        events_dir=events_dir,
        canonical_dir=canonical_dir,
        overrides_path=overrides_path,
        exceptions_dir=exceptions_dir,
        conform_dir=conform_dir,
        additions_dir=additions_dir,
    )

    assert report.additions_count == 1
    assert (additions_dir / NEW_NAME).exists()
    assert not (additions_dir / OLD_NAME).exists()


def test_old_additions_filename_gone_from_sources() -> None:
    """No source file references the bare old filename (clean replace, no shim)."""
    repo_root = Path(__file__).resolve().parents[2]
    out = subprocess.run(
        ["grep", "-rn", OLD_NAME, "src", "dbt/data_platform/models"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    ).stdout
    stale = [
        line
        for line in out.splitlines()
        if OLD_NAME in line
        and NEW_NAME not in line
        and "__pycache__" not in line
        and not line.split(":", 1)[0].endswith(".pyc")
    ]
    assert stale == [], f"stale references to {OLD_NAME}:\n" + "\n".join(stale)
