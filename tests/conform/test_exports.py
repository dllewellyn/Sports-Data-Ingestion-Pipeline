"""Contract test for the canonical league/season Parquet export models (US1, FR-011, U15).

The Python conform layer must RESOLVE existing canonical leagues/seasons from
Parquet files (never DuckLake). Two dbt external models produce those files,
mirroring the existing `canonical_team_export`:
  * canonical_league_export -> $DATA_DIR/silver/canonical/league.parquet
  * canonical_season_export -> $DATA_DIR/silver/canonical/season.parquet

Rather than open the (down) Postgres catalog, this test builds a fully
self-contained dbt harness in a pytest ``tmp_path`` — a scratch file-backed
DuckLake catalog plus a schema-correct ESPN bronze fixture and a scratch
``profiles.yml`` — then drives the real `dbt build` via subprocess and reads the
two Parquet files with pandas to assert their columns. No dependency on any
session-specific path, so it runs from a clean checkout / CI.

It genuinely runs and FAILS before the export models exist (or if they are
broken/removed): `dbt build` on a missing/broken model errors, and the files are
never written.
"""

import os
import subprocess
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DBT_DIR = REPO_ROOT / "dbt" / "data_platform"

# Upstream models the two exports depend on, plus the two export models themselves.
BUILD_SELECT = [
    "team_aliases",
    "stg_espn_events",
    "int_team",
    "int_league",
    "int_season",
    "canonical_league_export",
    "canonical_season_export",
]

LEAGUE_COLS = ["league_id", "name", "is_tournament"]
SEASON_COLS = ["season_id", "league_id", "name", "start_date", "end_date"]

# Two schema-correct ESPN bronze events (one completed, one scheduled) — enough to
# mint an int_league / int_season row so the exports have real content to write.
_ESPN_EVENTS = [
    {
        "espn_event_id": "401001",
        "league_slug": "eng.1",
        "season_year": 2025,
        "kickoff_time": "2025-08-16T14:00:00Z",
        "home_team_id": "359",
        "home_team_name": "Arsenal",
        "away_team_id": "363",
        "away_team_name": "Chelsea",
        "status_name": "STATUS_FULL_TIME",
        "status_state": "post",
        "status_completed": True,
        "home_score": 2,
        "away_score": 1,
        "raw_event": '{"season": {"displayName": "2025-26"}}',
    },
    {
        "espn_event_id": "401002",
        "league_slug": "eng.1",
        "season_year": 2025,
        "kickoff_time": "2025-08-17T16:30:00Z",
        "home_team_id": "364",
        "home_team_name": "Liverpool",
        "away_team_id": "368",
        "away_team_name": "Everton",
        "status_name": "STATUS_SCHEDULED",
        "status_state": "pre",
        "status_completed": False,
        "home_score": 0,
        "away_score": 0,
        "raw_event": '{"season": {"displayName": "2025-26"}}',
    },
]

# The int_league / int_season / int_team models UNION-in provider `*_additions`
# Parquet files via read_parquet, which ERRORS if the file is absent. The conform
# assets bootstrap-write these empty in production; the harness does the same so
# an un-minted provider contributes zero rows. Schema = the cast(...) column set
# each int model projects from these files.
_ADDITIONS_SCHEMAS = {
    "canonical_league_additions": pa.schema(
        [("league_id", pa.string()), ("name", pa.string()), ("is_tournament", pa.bool_())]
    ),
    "canonical_season_additions": pa.schema(
        [
            ("season_id", pa.string()),
            ("league_id", pa.string()),
            ("name", pa.string()),
            ("start_date", pa.date32()),
            ("end_date", pa.date32()),
        ]
    ),
    "canonical_team_additions": pa.schema(
        [
            ("team_id", pa.string()),
            ("name", pa.string()),
            ("similar_names", pa.list_(pa.string())),
        ]
    ),
}


def _write_harness(tmp_path: Path) -> tuple[Path, Path]:
    """Materialize a self-contained dbt harness under ``tmp_path``.

    Returns ``(profiles_dir, data_dir)`` — a scratch ``profiles.yml`` whose
    DuckLake catalog is a local file (not Postgres), and a DATA_DIR holding the
    ESPN bronze fixture + empty provider-additions Parquet files.
    """
    data_dir = tmp_path / "data"
    profiles_dir = tmp_path / "dbtprofile"
    profiles_dir.mkdir(parents=True)

    warehouse = tmp_path / "warehouse.duckdb"
    catalog = tmp_path / "catalog.ducklake"
    lake_data = tmp_path / "lake_data"

    # Scratch profile: DuckDB primary + a file-backed DuckLake catalog attached as
    # `lake` (mirrors the real profiles.yml, but the catalog is a local FILE so no
    # Postgres is needed). +database: lake in dbt_project.yml routes models here.
    profiles = f"""\
data_platform:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "{warehouse}"
      threads: 1
      extensions:
        - parquet
        - postgres
        - ducklake
      attach:
        - path: "ducklake:{catalog}"
          alias: lake
          options:
            data_path: "{lake_data}"
"""
    (profiles_dir / "profiles.yml").write_text(profiles)

    # ESPN bronze fixture at the source glob path: bronze/espn/<slug>/<year>.parquet
    espn_dir = data_dir / "bronze" / "espn" / "eng.1"
    espn_dir.mkdir(parents=True)
    events = pd.DataFrame(_ESPN_EVENTS)
    events["ingested_at"] = pd.Timestamp("2025-08-18", tz="UTC")
    events.to_parquet(espn_dir / "2025.parquet", index=False)

    # Empty provider-additions files (matchbook + football_data) the int models read.
    silver_dir = data_dir / "silver"
    silver_dir.mkdir(parents=True)
    # The `external` materialization writes the export Parquet directly; it does NOT
    # create the parent directory, so make it up-front.
    (silver_dir / "canonical").mkdir()
    for provider in ("matchbook", "football_data"):
        for name, schema in _ADDITIONS_SCHEMAS.items():
            pq.write_table(schema.empty_table(), silver_dir / f"{provider}_{name}.parquet")

    return profiles_dir, data_dir


@pytest.fixture(scope="module")
def built_exports(tmp_path_factory):
    """Build the upstream + two export models against a self-contained harness."""
    tmp_path = tmp_path_factory.mktemp("export_harness")
    profiles_dir, data_dir = _write_harness(tmp_path)

    env = dict(os.environ)
    env["DATA_DIR"] = str(data_dir)

    proc = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            "../..",
            "dbt",
            "build",
            "--select",
            *BUILD_SELECT,
            # Build exactly the selected nodes; do not pull in relationships tests
            # that reference *unselected* neighbor models (int_match, the link
            # tables) — those aren't part of this export contract and error on a
            # partial graph. This is a graph-scoping choice, not a test bypass.
            "--indirect-selection=empty",
            # Force single-threaded build: threads > 1 triggers a nondeterministic
            # __dbt_tmp catalog-qualification race in the file-backed DuckLake
            # catalog, making this test flaky. Single-threaded is deterministic.
            "--threads",
            "1",
            "--profiles-dir",
            str(profiles_dir),
        ],
        cwd=DBT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"dbt build of the export models failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    return data_dir / "silver" / "canonical"


def test_league_export_written_with_columns(built_exports):
    path = built_exports / "league.parquet"
    assert path.exists(), f"expected league export at {path}"
    df = pd.read_parquet(path)
    assert list(df.columns) == LEAGUE_COLS


def test_season_export_written_with_columns(built_exports):
    path = built_exports / "season.parquet"
    assert path.exists(), f"expected season export at {path}"
    df = pd.read_parquet(path)
    assert list(df.columns) == SEASON_COLS
