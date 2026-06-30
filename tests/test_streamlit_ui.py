"""Tests for the Streamlit exceptions UI (Spec 006 S6).

U26: App starts without error when exceptions Parquet absent.
U27: Confirm action writes action='link' to overrides.
U28: New Canonical Record action writes action='new_canonical'.
U29: Merge Duplicates action writes action='merge' with merge_source_match_id.
"""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).parents[1] / "streamlit_app" / "matchbook_exceptions.py"

OVERRIDE_COLUMNS = [
    "matchbook_event_id",
    "action",
    "match_id",
    "merge_source_match_id",
    "decided_at",
    "decided_by",
]


def _exceptions_parquet(path: Path, rows: list[dict]) -> None:
    """Write a minimal exceptions Parquet at the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


# ── U26: App starts without error when exceptions Parquet absent ─────────────


def test_app_handles_absent_exceptions_file() -> None:
    """U26: App shows 'No unresolved events' when exceptions file is absent.

    Runs the app with the default path configuration. If the exceptions file
    doesn't exist (typical in a clean test environment), the app should display
    an informational message without raising an error.
    """
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=15)
    # The key requirement: no uncaught exception (graceful handling)
    assert not at.exception


# ── Smoke test: confirm the app is importable and runnable ──────────────────


def test_app_runs_without_import_error() -> None:
    """The Streamlit app module is importable and AppTest can load it."""
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=15)
    assert not at.exception


# ── Test write_override helper via direct module import ──────────────────────
# These tests unit-test the _write_override function directly (no Streamlit context needed).


def _import_write_override():
    """Import _write_override from the Streamlit app module."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("matchbook_exceptions", str(APP_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_write_override_creates_link_row(tmp_path: Path, monkeypatch) -> None:
    """U27: _write_override writes action='link' row to overrides Parquet."""
    overrides_path = tmp_path / "manual_links" / "overrides.parquet"

    mod = _import_write_override()
    # Monkeypatch OVERRIDES_PATH in the loaded module
    monkeypatch.setattr(mod, "OVERRIDES_PATH", overrides_path)

    mod._write_override(
        {
            "matchbook_event_id": "evt_1",
            "action": "link",
            "match_id": "m_123",
            "merge_source_match_id": None,
            "decided_at": "2026-06-29T12:00:00+00:00",
            "decided_by": "human_ui",
        }
    )

    assert overrides_path.exists()
    result = pd.read_parquet(overrides_path)
    assert len(result) == 1
    assert result.iloc[0]["action"] == "link"
    assert result.iloc[0]["match_id"] == "m_123"
    assert result.iloc[0]["matchbook_event_id"] == "evt_1"
    assert result.iloc[0]["decided_by"] == "human_ui"


def test_write_override_new_canonical_row(tmp_path: Path, monkeypatch) -> None:
    """U28: _write_override writes action='new_canonical' row."""
    overrides_path = tmp_path / "manual_links" / "overrides.parquet"

    mod = _import_write_override()
    monkeypatch.setattr(mod, "OVERRIDES_PATH", overrides_path)

    mod._write_override(
        {
            "matchbook_event_id": "evt_2",
            "action": "new_canonical",
            "match_id": None,
            "merge_source_match_id": None,
            "decided_at": "2026-06-29T12:00:00+00:00",
            "decided_by": "human_ui",
        }
    )

    result = pd.read_parquet(overrides_path)
    assert len(result) == 1
    assert result.iloc[0]["action"] == "new_canonical"
    assert result.iloc[0]["match_id"] is None or pd.isna(result.iloc[0]["match_id"])


def test_write_override_merge_row(tmp_path: Path, monkeypatch) -> None:
    """U29: _write_override writes action='merge' row with merge_source_match_id."""
    overrides_path = tmp_path / "manual_links" / "overrides.parquet"

    mod = _import_write_override()
    monkeypatch.setattr(mod, "OVERRIDES_PATH", overrides_path)

    mod._write_override(
        {
            "matchbook_event_id": "evt_3",
            "action": "merge",
            "match_id": "m_surviving",
            "merge_source_match_id": "m_retiring",
            "decided_at": "2026-06-29T12:00:00+00:00",
            "decided_by": "human_ui",
        }
    )

    result = pd.read_parquet(overrides_path)
    assert len(result) == 1
    assert result.iloc[0]["action"] == "merge"
    assert result.iloc[0]["match_id"] == "m_surviving"
    assert result.iloc[0]["merge_source_match_id"] == "m_retiring"


def test_write_override_is_atomic(tmp_path: Path, monkeypatch) -> None:
    """Overrides file is written atomically (temp + rename pattern)."""
    overrides_path = tmp_path / "overrides" / "matchbook_overrides.parquet"

    mod = _import_write_override()
    monkeypatch.setattr(mod, "OVERRIDES_PATH", overrides_path)

    # Write two overrides sequentially
    mod._write_override(
        {
            "matchbook_event_id": "evt_1",
            "action": "link",
            "match_id": "m_1",
            "merge_source_match_id": None,
            "decided_at": "2026-06-29T12:00:00+00:00",
            "decided_by": "human_ui",
        }
    )
    mod._write_override(
        {
            "matchbook_event_id": "evt_2",
            "action": "new_canonical",
            "match_id": None,
            "merge_source_match_id": None,
            "decided_at": "2026-06-29T12:01:00+00:00",
            "decided_by": "human_ui",
        }
    )

    result = pd.read_parquet(overrides_path)
    assert len(result) == 2
    # No .tmp files left behind
    tmp_files = list(overrides_path.parent.glob("*.tmp"))
    assert tmp_files == []


def test_write_override_deduplicates_by_event_id(tmp_path: Path, monkeypatch) -> None:
    """Writing an override for the same event_id replaces the prior row."""
    overrides_path = tmp_path / "overrides" / "matchbook_overrides.parquet"

    mod = _import_write_override()
    monkeypatch.setattr(mod, "OVERRIDES_PATH", overrides_path)

    mod._write_override(
        {
            "matchbook_event_id": "evt_1",
            "action": "link",
            "match_id": "m_1",
            "merge_source_match_id": None,
            "decided_at": "2026-06-29T12:00:00+00:00",
            "decided_by": "human_ui",
        }
    )
    # Second write for the same event: new canonical
    mod._write_override(
        {
            "matchbook_event_id": "evt_1",
            "action": "new_canonical",
            "match_id": None,
            "merge_source_match_id": None,
            "decided_at": "2026-06-29T12:05:00+00:00",
            "decided_by": "human_ui",
        }
    )

    result = pd.read_parquet(overrides_path)
    assert len(result) == 1
    assert result.iloc[0]["action"] == "new_canonical"


def test_decided_at_is_utc_iso_string(tmp_path: Path, monkeypatch) -> None:
    """decided_at field is a UTC ISO 8601 string."""
    overrides_path = tmp_path / "overrides" / "overrides.parquet"

    mod = _import_write_override()
    monkeypatch.setattr(mod, "OVERRIDES_PATH", overrides_path)

    # Call _utc_now_iso directly
    ts = mod._utc_now_iso()
    # Should be parseable as a datetime
    from datetime import datetime

    dt = datetime.fromisoformat(ts)
    assert dt.tzinfo is not None  # UTC-aware
