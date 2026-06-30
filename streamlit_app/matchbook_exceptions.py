"""Streamlit exceptions UI for Matchbook unresolved events (Spec 006 S6).

Reads data/exceptions/matchbook_unresolved.parquet, displays each unresolved
Matchbook football event with candidate canonical matches, and records human
decisions (link / new_canonical / merge) to
data/manual_links/matchbook_overrides.parquet.

Run with:
    PYTHONPATH=src streamlit run streamlit_app/matchbook_exceptions.py
"""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Paths (config-driven where available, else sensible defaults) ────────────

try:
    import sys

    sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
    from data_platform.config import settings

    EXCEPTIONS_PATH = settings.matchbook_exceptions_dir / "matchbook_unresolved.parquet"
    OVERRIDES_PATH = settings.matchbook_overrides_dir / "matchbook_overrides.parquet"
except Exception:
    EXCEPTIONS_PATH = Path("data/exceptions/matchbook_unresolved.parquet")
    OVERRIDES_PATH = Path("data/manual_links/matchbook_overrides.parquet")

OVERRIDE_COLUMNS = [
    "matchbook_event_id",
    "action",
    "match_id",
    "merge_source_match_id",
    "decided_at",
    "decided_by",
]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_exceptions() -> pd.DataFrame:
    """Load exceptions Parquet; return empty DataFrame if absent."""
    if not EXCEPTIONS_PATH.exists():
        return pd.DataFrame()
    return pd.read_parquet(EXCEPTIONS_PATH)


def _load_overrides() -> pd.DataFrame:
    """Load existing overrides; return empty DataFrame if absent."""
    if not OVERRIDES_PATH.exists():
        return pd.DataFrame(columns=OVERRIDE_COLUMNS)
    return pd.read_parquet(OVERRIDES_PATH)


def _write_override(new_row: dict) -> None:
    """Append (or create) an override decision atomically (temp + rename)."""
    existing = _load_overrides()
    new_df = pd.DataFrame([new_row], columns=OVERRIDE_COLUMNS)
    # Remove any prior decision for this event_id so it's not duplicated
    if not existing.empty:
        existing = existing[existing["matchbook_event_id"] != new_row["matchbook_event_id"]]
    combined = pd.concat([existing, new_df], ignore_index=True)

    OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=OVERRIDES_PATH.parent, suffix=".tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    combined.to_parquet(tmp_path, index=False)
    tmp_path.replace(OVERRIDES_PATH)


def _parse_candidates(candidates_json: str) -> list[dict]:
    """Parse candidates JSON column safely."""
    try:
        return json.loads(candidates_json) if candidates_json else []
    except (json.JSONDecodeError, TypeError):
        return []


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Main UI ──────────────────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(
        page_title="Matchbook Exceptions Review",
        layout="wide",
    )
    st.title("Matchbook Unresolved Events")

    exceptions = _load_exceptions()
    overrides = _load_overrides()

    if exceptions.empty:
        st.info("No unresolved events")
        return

    # Exclude events that already have a human override in this session
    override_ids: set[str] = set()
    if not overrides.empty:
        override_ids = set(overrides["matchbook_event_id"].astype(str))

    pending = exceptions[~exceptions["matchbook_event_id"].astype(str).isin(override_ids)]

    if pending.empty:
        st.success("All unresolved events have been reviewed.")
        return

    st.write(f"**{len(pending)} unresolved events** awaiting review.")

    for _, row in pending.iterrows():
        event_id = str(row["matchbook_event_id"])
        event_name = str(row.get("event_name", ""))
        home_parsed = str(row.get("home_team_parsed", ""))
        away_parsed = str(row.get("away_team_parsed", ""))
        start_utc = str(row.get("start_utc", ""))
        reason = str(row.get("unresolved_reason", ""))
        candidates = _parse_candidates(str(row.get("candidates", "[]")))

        with st.expander(f"{event_name}  (id: {event_id})", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Home:** {home_parsed}")
                st.markdown(f"**Away:** {away_parsed}")
            with col2:
                st.markdown(f"**Start UTC:** {start_utc}")
                st.markdown(f"**Reason:** {reason}")

            if candidates:
                st.markdown("**Candidate canonical matches:**")
                cand_df = pd.DataFrame(candidates)
                if not cand_df.empty:
                    cand_df = cand_df.sort_values("score", ascending=False)
                    st.dataframe(cand_df, use_container_width=True, hide_index=True)

            # ── Action: Confirm link ──────────────────────────────────────
            st.markdown("---")
            if candidates:
                candidate_options = {
                    f"{c.get('home_team', '')} v {c.get('away_team', '')} "
                    f"({c.get('kickoff_time', '')}) [score: {c.get('score', '')}]": c["match_id"]
                    for c in candidates
                }
                selected_label = st.selectbox(
                    "Select candidate to confirm",
                    options=list(candidate_options.keys()),
                    key=f"select_{event_id}",
                )
                if st.button("✓ Confirm Link", key=f"confirm_{event_id}"):
                    match_id = candidate_options[selected_label]
                    _write_override(
                        {
                            "matchbook_event_id": event_id,
                            "action": "link",
                            "match_id": match_id,
                            "merge_source_match_id": None,
                            "decided_at": _utc_now_iso(),
                            "decided_by": "human_ui",
                        }
                    )
                    st.success(f"Saved: linked to match_id={match_id}")
                    st.rerun()

            # ── Action: New canonical record ──────────────────────────────
            if st.button("+ New Canonical Record", key=f"new_canonical_{event_id}"):
                _write_override(
                    {
                        "matchbook_event_id": event_id,
                        "action": "new_canonical",
                        "match_id": None,
                        "merge_source_match_id": None,
                        "decided_at": _utc_now_iso(),
                        "decided_by": "human_ui",
                    }
                )
                st.success("Saved: marked as new canonical record")
                st.rerun()

            # ── Action: Merge duplicates ──────────────────────────────────
            if len(candidates) >= 2:
                st.markdown("**Merge duplicates:**")
                merge_options = {
                    f"{c.get('home_team', '')} v {c.get('away_team', '')} "
                    f"[{c.get('match_id', '')}]": c["match_id"]
                    for c in candidates
                }
                surviving_label = st.selectbox(
                    "Surviving record",
                    options=list(merge_options.keys()),
                    key=f"merge_keep_{event_id}",
                )
                retiring_options = {k: v for k, v in merge_options.items() if k != surviving_label}
                retiring_label = st.selectbox(
                    "Record to retire",
                    options=list(retiring_options.keys()),
                    key=f"merge_retire_{event_id}",
                )
                if st.button("⚡ Merge Duplicates", key=f"merge_{event_id}"):
                    surviving_id = merge_options[surviving_label]
                    retiring_id = retiring_options[retiring_label]
                    _write_override(
                        {
                            "matchbook_event_id": event_id,
                            "action": "merge",
                            "match_id": surviving_id,
                            "merge_source_match_id": retiring_id,
                            "decided_at": _utc_now_iso(),
                            "decided_by": "human_ui",
                        }
                    )
                    st.success(f"Saved: merge {retiring_id} → {surviving_id}")
                    st.rerun()


if __name__ == "__main__":
    main()
