---
id: "006"
title: Matchbook & ESPN Conform Layer — Implementation Plan
slug: matchbook-espn-conform
status: draft
created: 2026-06-29
specification: 006-matchbook-espn-conform-specification.md
user_stories: []
---

# Matchbook & ESPN Conform Layer — Implementation Plan

## 1. Summary

This plan implements Spec 006 in 14 ordered steps. The work falls into four
tracks — (A) pure-Python conform engines and their unit tests, (B) dbt models
that read the conform-produced Parquet files and write into DuckLake, (C) Dagster
asset wiring and job definition, and (D) the Streamlit exceptions UI plus Docker
service definition. A setup step (S0) lands the new `pyproject.toml` dependencies
and `Settings` fields before any asset module is written; subsequent steps follow
the repo's established bronze→silver→gold ordering and never open DuckLake from
Python.

Each step is independently testable (pytest for pure-Python engines, dbt tests
for warehouse models, artifact-existence checks for end-to-end paths) and ends
with a read-only self-review sub-agent before the next step begins.

---

## 2. Skills to use

Phase 1 skill-discovery summary. Skills are matched from the session-surfaced
inventory; no sub-agent is spawned because the inventory is already visible.

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| Pure-Python conform engine (fuzzy match, parser, override loader) | `bronze-ingest-source` (pattern reference only — no network call here) | available (pattern ref) |
| New dbt silver model (`matchbook_event_link`, `canonical_*_export`, updated `match.sql`) | No dedicated dbt-model skill exists | MISSING — proceed using existing dbt patterns from `dbt/data_platform/models/silver/canonical/`; capture in `self-learn` post-build |
| Dagster asset wiring, job/schedule definition, `BronzeAwareTranslator` extension | No dedicated orchestration-wiring skill | MISSING — follow `definitions.py` + `assets/matchbook_events.py` pattern; capture in `self-learn` |
| Config field addition | No dedicated skill — add typed fields to `config.py` directly (pattern from existing `Settings`) | available via pattern |
| Per-step architecture conformance check | `code-architecture-review` | available |
| Per-step code-quality / diff review | `simplify` (post-step cleanup) | available |
| Post-build learnings capture | `self-learn` | available |
| Convention gaps | `create-rule` (if gaps found in §3) | available |

---

## 3. Convention & rule audit (resolved before implementation)

Every artifact type this plan touches, its governing convention, and resolution
status. No implementation step below depends on a row still marked **gap**.

| Artifact type | Governing convention | Status | Note |
|---------------|----------------------|--------|------|
| New pure-Python engine module (`matchbook/conform.py`, `matchbook/t60.py`) | CLAUDE.md: Dagster-free module, `from __future__ import annotations` allowed, `pathlib.Path`, no ad-hoc `os.getenv`; mirrors `matchbook/ingest.py` pattern | **exists** | |
| New Dagster asset module (`assets/matchbook_conform.py`, `assets/matchbook_t60.py`) | CLAUDE.md: no `from __future__ import annotations`; type-annotate public functions; config from `settings`; `pathlib.Path`; mirrors `assets/matchbook_events.py` | **exists** | |
| `config.py` new Settings fields | CLAUDE.md: typed `Path` properties in `Settings`, must precede asset module that reads them | **exists** | |
| `pyproject.toml` new dependencies (`rapidfuzz`, `streamlit`) | CLAUDE.md: add via `uv` to `pyproject.toml [project]dependencies`; `uv sync` to update lock | **exists** | |
| New dbt silver external-export model (`canonical_team_export.sql`, `canonical_match_export.sql`) | Mirrors `gold/users_by_city_export.sql` pattern — `materialized = 'external'`, `location = env_var(...)`, `format = 'parquet'`; lives under `models/silver/canonical/` (because it reads silver entities); `+database: lake` inherited | **exists** | |
| Updated dbt silver model (`matchbook_event_link.sql` — replace empty scaffold) | Mirrors `espn_match_link.sql` pattern: reads an external source Parquet, computes `md5()` surrogate PK, full-rebuild `+materialized: table` | **exists** | |
| Updated `match.sql` (UNION ALL of `matchbook_canonical_additions.parquet` + LEFT JOIN T-60) | CLAUDE.md: derive Parquet inside dbt (`read_parquet()` inline or external source); Python reads the resulting file, never opens DuckLake. Existing `match.sql` uses `qualify row_number()` dedup — extend, don't replace | **exists** | |
| New dbt `_sources.yml` entry (`matchbook_resolved_links`, `matchbook_canonical_additions`, `matchbook_t60_enrichment`) | Mirrors existing `_sources.yml` entries for `espn_events` and `matchbook_odds` — `external_location: read_parquet(...)` under `sources: - name: bronze` | **exists** (pattern) | |
| `_schema.yml` extension for `matchbook_event_link` (add `match_method`, `confidence`, `review_status`, `relationships` test) | Mirrors `espn_match_link` columns in the same file | **exists** | |
| `BronzeAwareTranslator` extension (new `_SOURCE_ASSET_KEYS` entry) | CLAUDE.md: `"matchbook_resolved_links": AssetKey(["matchbook_conform"])` — mirrors `"espn_events": AssetKey(["espn_bronze"])` pattern in `assets/dbt.py` | **exists** | |
| `definitions.py` new job/schedule + exclusion from `AssetSelection.all()` | CLAUDE.md: subtract new asset group from `medallion_hello_world`; add dedicated job and schedule; mirrors `espn_assets` / `espn_job` pattern | **exists** | |
| pytest unit tests for pure-Python engines | `pyproject.toml` `[tool.pytest.ini_options]` is already configured (`pythonpath = ["src"]`, `testpaths = ["tests"]`, importlib mode); `tests/matchbook/` directory exists with `conftest.py` and test files; `pytest` is in `dev` dependency group | **exists** | |
| Streamlit app module (`streamlit_app/matchbook_exceptions.py`) | No existing Streamlit module in `src/data_platform/`; the Streamlit app is a standalone UI script (not a Dagster asset, not imported by `definitions.py`); should live at `streamlit_app/matchbook_exceptions.py` (project-root-level directory, separate from `src/data_platform/`) per spec. Convention: reads/writes only `./data`, atomic temp-file + rename writes, `pathlib.Path`, no ad-hoc `os.getenv` | **exists** (derived from CLAUDE.md write-atomicity + path conventions) | |
| Docker Compose Streamlit service | CLAUDE.md overlay pattern: base `docker-compose.yml` for services without telemetry dependency; mounts `./data`; mirrors `jupyter` service shape | **exists** | |
| ERD.md update in same commit as `matchbook_event_link` schema change | CLAUDE.md: "Update ERD.md in the same commit that implements schema changes" | **exists** | |
| `canonical_match_id` macro for new canonical entity minting | CLAUDE.md: always use the macro logic (`md5(concat_ws('|', league_id, season_id, date, home_team_id, away_team_id))`); Python conform replicates this in pure Python (hashlib.md5) | **exists** | |
| `match.sql` UNION ALL schema column compatibility | CLAUDE.md: dbt models must be schema-stable; UNION ALL branches must emit identical column lists | **exists** | The `matchbook_canonical_additions.parquet` CTE must emit all columns that the ESPN CTE emits, including `status_completed` (stub `false`) and `ht_score` (stub `null`). |
| Atomic Parquet write (temp-file + rename) | CLAUDE.md: all Parquet writes; mirrors `matchbook/ingest.py` | **exists** | |
| Per-source failure isolation (accumulate failures, re-raise at end) | CLAUDE.md: mirrors `espn/ingest.py` and `matchbook/ingest.py` patterns | **exists** | |

**Gate status: all rows are "exists". No conventions need to be created before
implementation can proceed.**

---

## 4. Testable units (BDD → tests)

| Unit | Spec trace (scenario / AC) | Test facility | Failing-first assertion |
|------|----------------------------|---------------|-------------------------|
| U1: `parse_event_name("Arsenal v Chelsea")` → `("Arsenal", "Chelsea")` | Scenario A1 / AC1 | pytest | `assert parse_event_name("Arsenal v Chelsea") == ("Arsenal", "Chelsea")` fails because function doesn't exist |
| U2: `parse_event_name("Rugby event")` → raises / returns sentinel for missing ` v ` | Scenario A2 / AC1 | pytest | Parsing non-` v ` name returns `None` or raises; event enters exceptions path |
| U3: `parse_event_name("Real Madrid v FC v Barcelona")` splits on FIRST ` v ` | Edge case E4 / AC1 | pytest | `assert parse_event_name("Real Madrid v FC v Barcelona") == ("Real Madrid", "FC v Barcelona")` |
| U4: `load_overrides(path)` returns empty DataFrame when file absent (E9/B2) | Scenario B2 / AC5 | pytest | `assert load_overrides(nonexistent_path).empty` fails because function doesn't exist |
| U5: `load_overrides(path)` returns override rows when file present | Scenario B1 / AC5 | pytest | DataFrame has expected columns and one row for known event_id |
| U6: Conform engine routes override events before fuzzy matching | Scenario B1 / AC5 | pytest | Override event receives `confidence=1.0`, `match_method='human_override'`, fuzzy mock not called |
| U7: HIGH confidence path → `confidence=0.95`, `review_status='auto_confirmed'` | Scenario C1 / AC2 | pytest | With mocked canonical data and score ≥ 0.85 both teams + ≤ 90 min, link row has exact `confidence=0.95`. Uses a `tmp_path` pytest fixture to write a minimal `match.parquet` (one row with known `match_id`, `home_team_name`, `away_team_name`, `kickoff_time`) and points `settings.matchbook_conform_canonical_dir` at `tmp_path`. Test is self-contained; does not require dbt to have run. |
| U8: HIGH confidence path blocked when kickoff diff > 90 min | Scenario C2 / AC2 | pytest | Same scores but kickoff delta > 90 min → HIGH path NOT taken |
| U9: MEDIUM confidence path → `confidence=0.75`, `review_status='needs_review'` | Scenario D1 / AC3 | pytest | Scores 0.70–0.84, unique candidate, link row has exact `confidence=0.75` |
| U10: Multiple MEDIUM candidates → exceptions queue with `unresolved_reason='multiple_candidates'` | Scenario D2 / AC4 | pytest | Two candidates at MEDIUM threshold → no link row, exceptions row written |
| U11: No match → exceptions row with `candidates` JSON (top 5) | Scenario E1 / AC4 | pytest | No candidate at MEDIUM → exceptions row with `unresolved_reason='no_match'` and `candidates` list |
| U12: Football-only filter (sport-id 15); rugby silently skipped | Scenario E7 / AC12 | pytest | Rugby events (sport_id=2) absent from both resolved-links and exceptions output |
| U13: Idempotency — same bronze input produces identical resolved-links output | Scenario E5, G2 / AC6 | pytest (artifact compare) | Run conform engine twice on same input; assert output Parquet bytes identical |
| U14: Exceptions Parquet rebuild: resolved events removed, new events added | Scenario E2 / AC4 | pytest | Prior exceptions with 2 rows; 1 gets a human override; output exceptions has 1 old (minus resolved) + new |
| U15: `new_canonical` action writes row to `matchbook_canonical_additions.parquet` | Scenario F1 / AC7 | pytest | Override with `action='new_canonical'` → additions Parquet gets a row; resolved-links gets `confidence=1.0` |
| U16: Python-side canonical_match_id replication (md5 over pipe-separated key) | Scenario F1 / AC7 | pytest | `compute_canonical_match_id(league_id, season_id, date, home_id, away_id)` produces known md5 value |
| U17: `matchbook_event_link` dbt model produces typed table with all spec columns | Scenario G1 / AC7 | dbt test (`dbt build --select silver.canonical.matchbook_event_link`) | Model missing → `dbt build` fails; model implemented → `not_null`, `unique` on `link_id`, `relationships` on `match_id` pass |
| U18: `matchbook_event_link` re-run idempotency | Scenario G2 / AC6 | dbt test | `dbt build` twice → same row count, same content |
| U19: T-60 window filter: `[kickoff_ms − 4500000, kickoff_ms − 2700000]` | Scenario H1 / AC8 | pytest | `filter_t60_ticks(ticks_df, kickoff_ms)` returns only ticks in window; ticks outside excluded |
| U20: Favourite = runner with minimum `best_back_price` in T-60 window | Scenario H1 / AC8 | pytest | `find_favourite_runner(ticks)` returns runner_id with lowest price; NULL-price ticks skipped |
| U21: No T-60 tick → no row in enrichment Parquet | Scenario H2 / AC8 | pytest | Empty ticks for event → output Parquet has no row for that event |
| U22: Runner-to-team fuzzy resolution via `raw_event["runners"]` JSON | Scenario H1, AC9 | pytest | `resolve_runner_to_team(runners_json, home_name, away_name)` maps runner to home/away; < 0.70 → None |
| U23: `canonical_match_export` dbt model writes `data/silver/canonical/match.parquet` | Spec §8 constraint / AC8 | artifact assertion | File absent before step; present and readable with pandas after dbt build |
| U24: `canonical_team_export` dbt model writes `data/silver/canonical/team.parquet` | Spec §8 constraint / AC8 | artifact assertion | File absent before step; present and readable after dbt build |
| U25: `match.favourite_team_id` populated after T-60 enrichment + dbt build | Scenario H3 / AC9 | dbt test + artifact | Before: `favourite_team_id` all NULL; after: at least one non-NULL where T-60 data exists |
| U26: Streamlit app starts without error when exceptions Parquet absent | Scenario J5 / AC10 | pytest (via `streamlit.testing.v1` or subprocess smoke) | App process exits 0 / renders "No unresolved events" when file absent |
| U27: Streamlit "Confirm" action writes `action='link'` row to overrides Parquet | Scenario J2 / AC11 | pytest | Simulate form submission; overrides Parquet gets row with `action='link'`, `match_id` populated |
| U28: Streamlit "New Canonical Record" writes `action='new_canonical'` row | Scenario J3 / AC11 | pytest | overrides Parquet gets row with `action='new_canonical'`, `match_id=None` |
| U29: Streamlit "Merge Duplicates" writes `action='merge'` row with `merge_source_match_id` | Scenario J4 / AC11 | pytest | overrides Parquet gets row with `action='merge'` and both match_id fields populated |
| U30: `matchbook_conform_job` registered; subtracted from `medallion_hello_world` | AC13 | pytest (`test_definitions.py` pattern) | Assert asset IS in `AssetSelection.all()` keys AND NOT in `medallion_hello_world` keys (two-part test per CLAUDE.md) |
| U31: `matchbook_conform` asset depends on `AssetKey(["matchbook_events_bronze"])` | AC14 | pytest | Inspect asset deps; `AssetKey(["matchbook_events_bronze"])` present in conform asset's deps |
| U32: Streamlit Docker service defined in base `docker-compose.yml`, port 8501, mounts `./data` | AC15 | artifact assertion (parse YAML) | docker-compose.yml contains `streamlit` service with port 8501 and `./data:/app/data` volume |
| U33: ESPN score enrichment: `match.ft_score` non-NULL after ESPN run with `status_completed=true` | Scenario I1 / AC16 | dbt test | Documented existing behavior; `dbt build --select silver.canonical.match` with ESPN bronze having completed event → `ft_score` not null for that row |
| U34: No asset module uses `from __future__ import annotations` | AC17 | pytest (AST scan) | Scan all `assets/*.py` for the import; test fails if found |

---

## 5. Guardrail register

| Guardrail | How verified in place | Covered by step |
|-----------|------------------------|-----------------|
| ruff check + format (pre-commit) | `uv run pre-commit run --all-files` clean at each step | All steps |
| pytest harness green | `PYTHONPATH=src uv run pytest` on new test files | S1, S4, S5, S6, S7, S8, S9, S12, S13 |
| dbt tests run via `dbt build` | `cd dbt/data_platform && uv run --project ../.. dbt build --select <model>` green | S3, S5, S9, S10, S11 |
| Pydantic/Pandera boundary validation | Conform engine validates input rows from Matchbook bronze Parquet; enrichment validates T-60 ticks | S4, S8 |
| Idempotency / re-run safety | U13 test (identical output from two runs on same input); dbt full-rebuild materialization | S4, S5, S9 |
| OTel span emitted | Conform asset and T-60 asset open spans via `get_tracer()` (pattern from `matchbook/ingest.py`) | S7, S10 |
| Repo: no `from __future__ import annotations` in asset modules | U34 test; self-review check on every asset step | S7, S10, S12 |
| Repo: prefixed dbt asset keys (`AssetKey(["silver","matchbook_event_link"])`) | Unit test U31; self-review; `definitions.py` review | S7, S9, S12 |
| Repo: single-writer DuckLake — Python never opens DuckLake | Architecture review: no `duckdb.connect()` in conform/t60/streamlit modules | All Python steps |
| Repo: config via `pydantic-settings` — no ad-hoc `os.getenv` | ruff + self-review; all new Settings fields added in S0 | S0, all |
| Repo: `pathlib.Path` for all filesystem paths | ruff (B007/UP) + self-review | All steps |
| Repo: atomic temp-file + rename Parquet writes | Code review; pattern matches `matchbook/ingest.py` | S4, S8 |
| Repo: per-source failure isolation, accumulate + re-raise | Code review; test that partial failures still write valid files | S4, S8 |
| `BronzeAwareTranslator` mapping wired | Unit test U31; `dbt parse` manifest check | S9 |
| ERD.md updated same commit as schema change | Self-review checkpoint on S9 | S9 |
| `rapidfuzz` and `streamlit` in `pyproject.toml` | `uv sync` succeeds; import in test | S0 |
| Dagster queued-run ordering (daemon/webserver same workspace) | Verify `matchbook_conform_job` launches via queued path after S12; `dagster definitions validate -w workspace.yaml` | S12 |

---

## 6. Implementation steps

### Step S0 — Setup: dependencies and Settings fields

- **Goal:** Land `rapidfuzz` and `streamlit` in `pyproject.toml` and all new
  `Settings` fields in `config.py` before any asset module reads them. Verify
  `uv sync` succeeds and the fields are importable.
- **Spec trace:** AC18, AC19; Spec §8 non-functional constraints
- **Red (failing test first):**
  ```python
  # tests/test_config_matchbook.py (existing file — extend it)
  from data_platform.config import settings
  assert hasattr(settings, "matchbook_conform_canonical_dir")  # fails: attr missing
  assert hasattr(settings, "matchbook_conform_dir")
  assert hasattr(settings, "matchbook_exceptions_dir")
  assert hasattr(settings, "matchbook_overrides_dir")
  assert hasattr(settings, "matchbook_t60_dir")
  assert hasattr(settings, "matchbook_canonical_additions_dir")
  ```
  Also: `import rapidfuzz` and `import streamlit` fail before deps are added.
- **Implementation:**
  1. Add to `pyproject.toml` `[project]dependencies`: `"rapidfuzz>=3.0"` and `"streamlit>=1.35"`.
  2. Run `uv sync` to update `uv.lock`.
  3. Add to `config.py` `Settings`:
     ```python
     @property
     def matchbook_conform_canonical_dir(self) -> Path:
         """Silver canonical Parquet exports (team.parquet, match.parquet) — written by dbt."""
         return self.silver_dir / "canonical"

     @property
     def matchbook_conform_dir(self) -> Path:
         """Resolved conform links Parquet output dir (matchbook_resolved_links.parquet)."""
         return self.silver_dir

     @property
     def matchbook_canonical_additions_dir(self) -> Path:
         """New-canonical additions Parquet dir (matchbook_canonical_additions.parquet)."""
         return self.silver_dir

     @property
     def matchbook_exceptions_dir(self) -> Path:
         """Exceptions Parquet dir (matchbook_unresolved.parquet)."""
         return self.data_dir / "exceptions"

     @property
     def matchbook_overrides_dir(self) -> Path:
         """Human override decisions Parquet dir (matchbook_overrides.parquet)."""
         return self.data_dir / "manual_links"

     @property
     def matchbook_t60_dir(self) -> Path:
         """T-60 enrichment Parquet dir (matchbook_t60_enrichment.parquet)."""
         return self.silver_dir
     ```
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/test_config_matchbook.py` passes; `uv run python -c "import rapidfuzz, streamlit"` exits 0.
- **Guardrails to satisfy:** ruff clean on `config.py`; `uv run pre-commit run --all-files` clean.
- **Note:** The spec §8 lists five Settings fields; `matchbook_canonical_additions_dir` is required by the UNION ALL design (OQ1 resolution) and is added to `config.py` in S0 as the sixth field.
- **Self-review checkpoint:** Reviewer confirms: (1) all six property names match spec §8 exactly (`matchbook_conform_canonical_dir`, `matchbook_conform_dir`, `matchbook_exceptions_dir`, `matchbook_overrides_dir`, `matchbook_t60_dir`, `matchbook_canonical_additions_dir`); (2) property return types are `Path`; (3) no `os.getenv` introduced; (4) `rapidfuzz` and `streamlit` in `pyproject.toml` with version bounds; (5) `uv.lock` updated; (6) no `from __future__ import annotations` violation (config.py already has it — allowed, it is not an asset module).

---

### Step S1 — Pure-Python event-name parser (`matchbook/conform.py` — parsing unit)

- **Goal:** Implement `parse_event_name(event_name: str) -> tuple[str, str] | None`
  in a new `src/data_platform/matchbook/conform.py` engine module. Returns `(home, away)` on success, `None` when no ` v ` separator or result is empty after strip.
- **Spec trace:** Scenarios A1, A2; Edge case E4; AC1
- **Red (failing test first):**
  ```python
  # tests/matchbook/test_conform.py  (new file)
  from data_platform.matchbook.conform import parse_event_name
  assert parse_event_name("Arsenal v Chelsea") == ("Arsenal", "Chelsea")
  # ImportError / AttributeError fails before implementation
  ```
- **Implementation:** Create `src/data_platform/matchbook/conform.py` with `parse_event_name`. Split on first ` v ` (use `str.split(" v ", maxsplit=1)`); strip both parts; return `None` if either part is empty or no ` v ` found.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/matchbook/test_conform.py::test_parse_event_name` (and edge-case variants U1–U3) all pass.
- **Guardrails to satisfy:** `from __future__ import annotations` is ALLOWED (pure engine, no Dagster decorators); ruff clean; `pathlib.Path` where applicable (not needed for this function); function is pure with no I/O.
- **Self-review checkpoint:** Reviewer checks: (1) `parse_event_name("A v B v C")` returns `("A", "B v C")` (first split); (2) `parse_event_name("no sep")` returns `None`; (3) `parse_event_name(" v ")` returns `None` (empty parts); (4) test is non-trivial (fails without implementation); (5) no Dagster import in `conform.py`.

---

### Step S2 — Override loader (`matchbook/conform.py` — override unit)

- **Goal:** Add `load_overrides(path: Path) -> pd.DataFrame` to `matchbook/conform.py`.
  Returns an empty DataFrame (with correct columns) when the file is absent; returns
  the full override DataFrame when present.
- **Spec trace:** Scenarios B1, B2; Edge case E9; AC5
- **Red (failing test first):**
  ```python
  from data_platform.matchbook.conform import load_overrides
  assert load_overrides(Path("/nonexistent/path.parquet")).empty  # fails before function exists
  ```
- **Implementation:** Add to `conform.py`. Check `path.exists()`; if not, return an empty DataFrame with columns `["matchbook_event_id", "action", "match_id", "merge_source_match_id", "decided_at", "decided_by"]`. If exists, `pd.read_parquet(path)`.
- **Green criterion:** U4 and U5 tests pass.
- **Guardrails to satisfy:** No `os.path` usage; `pathlib.Path`; ruff clean.
- **Self-review checkpoint:** Reviewer confirms: (1) absent-file path returns empty DF with correct columns (not raises); (2) present-file path returns data; (3) no DuckLake connection in this function.

---

### Step S3 — Canonical export dbt models (`canonical_team_export`, `canonical_match_export`)

- **Goal:** Two new dbt external-Parquet models that export the silver canonical
  `team` and `match` tables to files Python can read without touching DuckLake.
  Writes `data/silver/canonical/team.parquet` and `data/silver/canonical/match.parquet`.
- **Spec trace:** Spec §8 constraint ("Python conform assets read canonical entity Parquet exports produced by dbt"); AC8, AC9, AC14
- **Red (failing test first):** Artifact assertion — the Parquet files do not exist before this step:
  ```bash
  python -c "import pandas as pd; pd.read_parquet('data/silver/canonical/team.parquet')"
  # FileNotFoundError before model exists
  ```
- **Implementation:**
  1. Create `dbt/data_platform/models/silver/canonical/canonical_team_export.sql`:
     ```sql
     {{
       config(
         materialized = 'external',
         location = env_var('DATA_DIR', '/app/data') ~ '/silver/canonical/team.parquet',
         format = 'parquet'
       )
     }}
     select team_id, name, similar_names from {{ ref('team') }}
     ```
  2. Create `dbt/data_platform/models/silver/canonical/canonical_match_export.sql`:
     ```sql
     {{
       config(
         materialized = 'external',
         location = env_var('DATA_DIR', '/app/data') ~ '/silver/canonical/match.parquet',
         format = 'parquet'
       )
     }}
     select
         match_id,
         season_id,
         home_team_id,
         away_team_id,
         favourite_team_id,
         kickoff_time
     from {{ ref('match') }}
     ```
     Note: also export home/away team names by joining `team` on `home_team_id`/`away_team_id` — the T-60 runner resolution needs `home_team_name` and `away_team_name` from this Parquet (per AC9). Add those join columns.
  3. Run `dbt parse` first, then `dbt build --select silver.canonical.canonical_team_export silver.canonical.canonical_match_export`.
- **Green criterion:** Both Parquet files exist and are readable with pandas; `dbt build` exits 0.
- **Guardrails to satisfy:** `+database: lake` inherited from `dbt_project.yml`; single-writer DuckLake (dbt writes, Python reads only); no dbt test failures on existing models.
- **Self-review checkpoint:** Reviewer checks: (1) files produced at correct paths; (2) `match.parquet` includes `home_team_name`, `away_team_name` for runner resolution; (3) no new dbt test failures; (4) `external` materialization pattern matches `users_by_city_export.sql`.

---

### Step S4 — Conform engine — fuzzy matching, exceptions, and Parquet writer

- **Goal:** Implement the full conform engine in `matchbook/conform.py`:
  `run_conform(events_dir, canonical_dir, overrides_dir, exceptions_dir, conform_dir, additions_dir, log)`.
  This is the core of Capabilities B–F: override lookup → HIGH/MEDIUM fuzzy match → exceptions queue → new-canonical additions. Atomic Parquet writes throughout.
- **Spec trace:** Scenarios B1, B2, C1, C2, D1, D2, E1, E2, F1; Edge cases E1, E4, E5, E7, E8, E12, E13, E14, E15; AC1–AC6, AC12
- **Red (failing test first):**
  ```python
  # tests/matchbook/test_conform.py — add:
  from data_platform.matchbook.conform import run_conform
  # Call with empty events_dir → produces empty resolved-links Parquet, no error
  result = run_conform(events_dir=tmp_path / "events", ...)
  assert result.resolved_count == 0
  # Fails: AttributeError / ImportError before implementation
  ```
- **Implementation outline:**
  1. `run_conform(...)` signature takes all directories as `Path`.
  2. Glob and read all bronze Parquet files from `events_dir` (using `union_by_name`-style `pd.read_parquet` with concat); deduplicate by `event_id` (latest `ingested_at` wins, per E15).
  3. Filter to football only (`sport_id == 15`, per E7).
  4. Parse `event_name` with `parse_event_name()`; events failing parse → exceptions with `unresolved_reason='unparseable_event_name'`.
  5. Parse `start_utc`; events with invalid datetime → exceptions with `unresolved_reason='invalid_start_utc'` (E14).
  6. Load overrides from `overrides_dir / "matchbook_overrides.parquet"` via `load_overrides()`.
  7. Load canonical match/team Parquet from `canonical_dir`.
  8. For each event:
     - If override exists (by `matchbook_event_id`): route with `confidence=1.0`, `review_status='human_confirmed'`, `match_method='human_override'`. If `action='new_canonical'`, also write to additions Parquet.
     - Otherwise: compute `token_sort_ratio` for all canonical matches; find HIGH candidates (both teams ≥ 0.85, kickoff diff ≤ 90 min). If exactly one, HIGH link (`confidence=0.95`). Else find MEDIUM (both ≥ 0.70, kickoff ≤ 90 min). If exactly one, MEDIUM link (`confidence=0.75`). If multiple at MEDIUM → exceptions `multiple_candidates`. If none → exceptions `no_match` with top-5 candidates JSON.
  9. Write resolved-links Parquet atomically to `conform_dir / "matchbook_resolved_links.parquet"`.
  10. Write exceptions Parquet atomically to `exceptions_dir / "matchbook_unresolved.parquet"` (built from scratch each run from current unresolved set, minus events now in overrides, per E5 + Scenario E2).
  11. Write additions Parquet atomically to `additions_dir / "matchbook_canonical_additions.parquet"` (only `new_canonical` rows).
  12. Return a `ConformReport` dataclass (resolved_count, exceptions_count, overrides_applied, failures).
  - `HIGH_CONFIDENCE = 0.95` and `MEDIUM_CONFIDENCE = 0.75` are module-level constants (exact values from spec).
  - `compute_canonical_match_id(league_id, season_id, date, home_id, away_id)` helper using `hashlib.md5` replicating the dbt macro.
- **Green criterion:** U6–U16, U12, U13, U14, U15, U16 pytest tests pass. `PYTHONPATH=src uv run pytest tests/matchbook/test_conform.py` green.
- **Guardrails to satisfy:** Atomic writes (temp-file + rename); accumulate failures in `ConformReport` not raise; idempotency tested; ruff clean; no DuckLake connection; `pathlib.Path` throughout; `rapidfuzz.fuzz.token_sort_ratio` used.
- **Self-review checkpoint:** Reviewer checks: (1) `HIGH_CONFIDENCE = 0.95` is exactly `0.95` (not computed from fuzzy scores); (2) `MEDIUM_CONFIDENCE = 0.75` is exactly `0.75`; (3) rugby events not in exceptions (silently skipped); (4) idempotency test is non-trivial (actually compares Parquet bytes); (5) tie-score events go to exceptions (E8); (6) `new_canonical` writes to additions Parquet; (7) exceptions Parquet rebuilt from scratch each run (not appended); (8) no reward-hacking (no mock that always passes regardless of input).

---

### Step S5 — T-60 engine (`matchbook/t60.py`)

- **Goal:** Implement the T-60 enrichment engine in a new
  `src/data_platform/matchbook/t60.py` module.
  Functions: `filter_t60_ticks(ticks_df, kickoff_ms)`, `find_favourite_runner(ticks_in_window)`,
  `resolve_runner_to_team(runners_json, home_team_name, away_team_name)`,
  `run_t60_enrichment(resolved_links_path, odds_dir, canonical_dir, out_path)`.
- **Spec trace:** Scenarios H1, H2; Edge cases E2, E3; AC8, AC9
- **Red (failing test first):**
  ```python
  # tests/matchbook/test_t60.py  (new file)
  from data_platform.matchbook.t60 import filter_t60_ticks
  import pandas as pd
  kickoff_ms = 1_000_000_000_000  # arbitrary
  df = pd.DataFrame({"ingested_at": [kickoff_ms - 4_000_000, kickoff_ms - 5_000_000, kickoff_ms - 1_000_000], ...})
  result = filter_t60_ticks(df, kickoff_ms)
  assert len(result) == 1  # only the tick at -4_000_000 is in [T-75, T-45]
  # ImportError fails before implementation
  ```
- **Implementation outline:**
  1. `filter_t60_ticks`: keep rows where `kickoff_ms - 4_500_000 <= ingested_at <= kickoff_ms - 2_700_000`; drop rows with NULL `kickoff_ms` (E3).
  2. `find_favourite_runner`: among ticks in window, skip NULL `best_back_price`; return `runner_id` with minimum `best_back_price`; return `None` if no valid ticks.
  3. `resolve_runner_to_team(runners_json: list[dict], home_team_name: str, away_team_name: str)`: for each runner `{"id": ..., "name": ...}`, compute `token_sort_ratio(runner["name"], home_team_name)` and `token_sort_ratio(runner["name"], away_team_name)`; assign best match ≥ 0.70; return `{"home_runner_id": ..., "away_runner_id": ...}` (None if no match ≥ 0.70).
  4. `run_t60_enrichment`: read resolved-links Parquet; read odds Parquet (glob); read canonical match Parquet; for each linked event, filter odds to `market_type == 'match_odds'`, apply T-60 window, find favourite runner, resolve runner to team; write enrichment rows to `out_path` atomically.
- **Green criterion:** U19–U22 pytest tests pass. `PYTHONPATH=src uv run pytest tests/matchbook/test_t60.py` green.
- **Guardrails to satisfy:** Atomic write; NULL `kickoff_ms` excluded (E3); runner with NULL `best_back_price` skipped; `pathlib.Path`; ruff clean; no DuckLake connection.
- **Self-review checkpoint:** Reviewer checks: (1) T-60 window is `[kickoff_ms − 4500000, kickoff_ms − 2700000]` inclusive (75–45 min); (2) NULL `kickoff_ms` ticks excluded; (3) NULL `best_back_price` skipped; (4) runner-to-team returns `None` (not raises) when score < 0.70; (5) no event row written when no valid ticks in window (H2).

---

### Step S6 — Streamlit exceptions UI (`streamlit_app/matchbook_exceptions.py`)

- **Goal:** Implement the Streamlit exceptions UI. Reads `data/exceptions/matchbook_unresolved.parquet`; displays unresolved events with candidates; writes decisions to `data/manual_links/matchbook_overrides.parquet` atomically. Handles absent file gracefully (shows "No unresolved events").
- **Spec trace:** Scenarios J1–J5; AC10, AC11, AC15
- **Red (failing test first):**
  ```python
  # tests/test_streamlit_ui.py  (new file — uses streamlit.testing.v1 or subprocess)
  from streamlit.testing.v1 import AppTest
  at = AppTest.from_file("streamlit_app/matchbook_exceptions.py")
  at.run()
  assert not at.exception  # fails: ImportError / FileNotFoundError before implementation
  assert "No unresolved events" in at.markdown[0].value
  ```
  Note: if `streamlit.testing.v1` is not available in this version, use subprocess smoke-test; record as a blocker note if so.
- **Implementation outline:**
  1. Create `streamlit_app/` directory at project root.
  2. Create `streamlit_app/matchbook_exceptions.py`:
     - Import `streamlit as st`, `pandas as pd`, `pathlib.Path`, `json`, `datetime`.
     - Read paths from environment (via `config.settings`) or hardcode defaults (`Path("data/exceptions/matchbook_unresolved.parquet")`, `Path("data/manual_links/matchbook_overrides.parquet")`).
     - If exceptions file absent or empty: `st.info("No unresolved events")`.
     - Otherwise: for each row, `st.expander(event_name)` → show parsed home/away, start_utc, reason, candidates table sorted by score descending.
     - Three action buttons per event: "Confirm" (select candidate → `action='link'`), "New Canonical Record" (`action='new_canonical'`), "Merge Duplicates" (select two → `action='merge'`).
     - On submit: read existing overrides (if present), append new row, write atomically (temp-file + rename). Each override row includes `matchbook_event_id`, `action`, `match_id`, `merge_source_match_id` (if merge), `decided_at=datetime.now(UTC).isoformat()`, `decided_by='human_ui'`.
  3. Create `streamlit_app/__init__.py` (empty) to satisfy any tooling.
- **Green criterion:** U26–U29 tests pass (or subprocess `python -m streamlit run streamlit_app/matchbook_exceptions.py --server.headless true` exits without import error); U26 (absent file → "No unresolved events") confirmed.
- **Guardrails to satisfy:** Atomic write; `pathlib.Path`; no `os.getenv` (use `settings` or literal defaults); ruff clean on `streamlit_app/`.
- **Self-review checkpoint:** Reviewer confirms: (1) absent exceptions file → no error, info message displayed; (2) atomic overrides write (temp-file + rename); (3) `decided_at` is a UTC ISO timestamp; (4) merge action populates `merge_source_match_id`; (5) no DuckLake connection; (6) `streamlit` is in `pyproject.toml` (S0 pre-condition satisfied).

---

### Step S7 — Dagster `matchbook_conform` asset (`assets/matchbook_conform.py`)

- **Goal:** Thin Dagster wrapper asset that calls `run_conform()`. Asset key
  `AssetKey(["matchbook_conform"])`. Depends on `AssetKey(["matchbook_events_bronze"])`.
  Emits `MaterializeResult` with metadata. No `from __future__ import annotations`.
- **Spec trace:** AC13, AC14; Capabilities A–F
- **Red (failing test first):**
  ```python
  # tests/matchbook/test_conform.py — engine tests (new assertions added here):
  from data_platform.matchbook.conform import run_conform
  # Call with empty events_dir → produces empty resolved-links Parquet, no error
  result = run_conform(events_dir=tmp_path / "events", ...)
  assert result.resolved_count == 0
  # Fails: AttributeError / ImportError before implementation
  ```
  Note: `definitions.py` is NOT modified in S7 — asset registration in `definitions.py` happens in S12. The red criterion here is that the engine tests pass and the asset file exists, not that the asset appears in the Dagster graph.
- **Implementation:**
  1. Create `src/data_platform/assets/matchbook_conform.py` with the `matchbook_conform` `@asset`.
  2. ```python
     deps=[
         AssetKey(["matchbook_events_bronze"]),
         AssetKey(["silver", "canonical_match_export"]),
         AssetKey(["silver", "canonical_team_export"]),
     ]
     ```
     This enforces that the canonical Parquet exports are current before the conform engine runs. S7 dep on canonical exports enforces ordering — the conform engine reads `canonical_match_export` and `canonical_team_export` Parquet files produced by dbt; without this dep, those files could be stale.
  3. Calls `run_conform(...)` from `..matchbook.conform`; passes `settings.*` paths.
  4. No `from __future__ import annotations`.
  5. Add OTel span via `get_tracer()` (pattern from existing assets).
- **Green criterion:** Engine tests in `tests/matchbook/test_conform.py` pass (`pytest tests/matchbook/test_conform.py`). The asset file exists. `definitions.py` is NOT yet modified in S7.
- **Guardrails to satisfy:** No `from __future__ import annotations`; `pathlib.Path`; config from `settings`; ruff clean.
- **Self-review checkpoint:** Reviewer checks: (1) no `from __future__ import annotations`; (2) deps include `AssetKey(["matchbook_events_bronze"])`, `AssetKey(["silver", "canonical_match_export"])`, `AssetKey(["silver", "canonical_team_export"])`; (3) `group_name="silver"` or appropriate; (4) OTel span opened; (5) function signature has no non-runtime type annotations (Dagster-safe); (6) `definitions.py` has NOT been modified in this step — that happens in S12.

---

### Step S8 — Dagster `matchbook_t60_enrichment` asset (`assets/matchbook_t60.py`)

- **Goal:** Thin Dagster wrapper for `run_t60_enrichment()`. Asset key
  `AssetKey(["matchbook_t60_enrichment"])`. Depends on
  `AssetKey(["silver", "matchbook_event_link"])` (the dbt-produced link table,
  per OQ3 resolution) and `AssetKey(["matchbook_events_bronze"])`.
  No `from __future__ import annotations`.
- **Spec trace:** Scenarios H1, H2, H3; AC8, AC9; Spec §9 assumption 3
- **Red (failing test first):**
  ```python
  from dagster import AssetKey, AssetSelection
  from data_platform.definitions import defs
  keys = {k for k in AssetSelection.all().resolve(defs.get_asset_graph())}
  assert AssetKey(["matchbook_t60_enrichment"]) in keys  # fails before asset registered
  ```
- **Implementation:**
  1. Create `src/data_platform/assets/matchbook_t60.py`.
  2. `deps=[AssetKey(["silver", "matchbook_event_link"]), AssetKey(["matchbook_events_bronze"])]` — enforces correct ordering (dbt FK validation before T-60 runs). The T-60 ordering through `matchbook_event_link` already transitively covers `matchbook_conform` → canonical exports; no explicit dep on `canonical_match_export` is needed here.
  3. Calls `run_t60_enrichment(...)`.
  4. No `from __future__ import annotations`.
- **Green criterion:** Asset registered in definitions; deps present; ruff clean.
- **Guardrails to satisfy:** No `from __future__ import annotations`; deps on dbt models (not on Parquet file existence alone); ruff clean.
- **Self-review checkpoint:** Reviewer checks: (1) deps include `AssetKey(["silver", "matchbook_event_link"])` (dbt key, not a Python asset); (2) no `from __future__ import annotations`; (3) OTel span present.

---

### Step S9 — dbt `matchbook_event_link` model (replace empty scaffold) + `_schema.yml` + `_sources.yml` + `BronzeAwareTranslator`

- **Goal:** Replace the empty scaffold `matchbook_event_link.sql` with a real
  model. Update `_schema.yml` with full column tests. Update `_sources.yml` with
  three new source entries. Extend `BronzeAwareTranslator` in `assets/dbt.py` with
  the `matchbook_resolved_links` mapping. Update ERD.md in the same commit.
- **Spec trace:** Scenarios G1, G2; AC7, AC20
- **Red (failing test first):**
  ```bash
  cd dbt/data_platform && uv run --project ../.. dbt build --select silver.canonical.matchbook_event_link
  # Fails: empty scaffold returns 0 rows, not_null/unique tests on link_id pass trivially against nothing
  # (or: test_dbt_translator.py checks BronzeAwareTranslator mapping and fails)
  ```
  Also: write a pytest that asserts `"matchbook_resolved_links" in BronzeAwareTranslator._SOURCE_ASSET_KEYS` — fails before this step.
- **Implementation:**
  1. Replace `matchbook_event_link.sql`:
     ```sql
     -- Reads the Python conform asset output and materializes as a typed DuckLake table.
     with resolved as (
         select * from read_parquet(
             env_var('DATA_DIR', '/app/data') ~ '/silver/matchbook_resolved_links.parquet'
         )
     )
     select
         md5(cast(matchbook_event_id as varchar))  as link_id,
         match_id,
         cast(matchbook_event_id as varchar)        as matchbook_event_id,
         match_method,
         cast(confidence as double)                as confidence,
         review_status
     from resolved
     ```
     Note: if `matchbook_resolved_links.parquet` is absent (first run before conform), the model produces zero rows (same as scaffold). Add a conditional `try_read_parquet` or handle via external source in `_sources.yml`.
  2. Update `_schema.yml` for `matchbook_event_link`: add `match_method` (accepted_values: `['fuzzy_high','fuzzy_medium','human_override']`), `confidence` (not_null), `review_status` (accepted_values: `['auto_confirmed','needs_review','human_confirmed']`), and `relationships` test on `match_id → ref('match')`. Update `matchbook_event_id` column with `not_null` + `unique`.
  3. Update `_sources.yml`: add three new source tables `matchbook_resolved_links`, `matchbook_canonical_additions`, `matchbook_t60_enrichment` under the `bronze` source with their `external_location` paths.
  4. Extend `BronzeAwareTranslator._SOURCE_ASSET_KEYS`: add `"matchbook_resolved_links": AssetKey(["matchbook_conform"])`.
  5. Update `ERD.md`: update `matchbook_event_link` table description to include `match_method`, `confidence`, `review_status`; update `favourite_team_id` label from "T-45m" to "T-60 minute window (kickoff − 75 min to kickoff − 45 min)"; update `matchbook_event_link` scaffold note to "physical table, populated by Spec 006".
- **Green criterion:** `cd dbt/data_platform && uv run --project ../.. dbt build --select silver.canonical.matchbook_event_link` green (with resolved-links Parquet present from S4 engine tests); `not_null`, `unique` on `link_id` pass; `relationships` test passes for rows where canonical `match_id` exists. `PYTHONPATH=src uv run pytest tests/test_dbt_translator.py` passes (BronzeAwareTranslator mapping present).
- **Guardrails to satisfy:** ERD.md updated in same commit (CLAUDE.md requirement); single-writer DuckLake; `+database: lake` inherited; dbt node selector `silver.canonical.matchbook_event_link` (not `silver.matchbook_event_link`); AssetKey is `["silver","matchbook_event_link"]`.
- **Self-review checkpoint:** Reviewer checks: (1) ERD.md updated in same commit; (2) accepted_values tests cover all three `match_method` values; (3) `BronzeAwareTranslator` mapping key is `"matchbook_resolved_links"` (exact dbt source name); (4) AssetKey derivation is `["silver","matchbook_event_link"]` (no `canonical` prefix); (5) `relationships` test on `match_id → ref('match')` present; (6) scaffold `limit 0` clause removed.

---

### Step S10 — `match.sql` extension: UNION ALL canonical additions + LEFT JOIN T-60

- **Goal:** Extend `match.sql` to (1) UNION ALL `matchbook_canonical_additions.parquet`
  (only when file exists) so Matchbook-minted `match_id` values appear in `match`,
  and (2) LEFT JOIN `matchbook_t60_enrichment.parquet` on `match_id` to populate
  `favourite_team_id`.
- **Spec trace:** Scenario F1, H3; AC7, AC9, AC21; Edge case E11
- **Red (failing test first):**
  ```bash
  # Before: match.favourite_team_id is always NULL
  # dbt test: custom singular test that checks favourite_team_id is non-null for a known match_id
  # (set up using fixture data in dbt seeds or a test Parquet)
  cd dbt/data_platform && uv run --project ../.. dbt build --select silver.canonical.match
  # Model builds but favourite_team_id is NULL — fails the post-step assertion
  ```
- **Implementation:**
  1. In `match.sql`, add a second CTE `canonical_additions` that reads `matchbook_canonical_additions.parquet` via `read_parquet(...)` (use `CASE WHEN file_exists THEN read_parquet(...) ELSE empty_select END` or DuckDB's `try_read_parquet` — prefer `try_read_parquet` to handle absent file gracefully, per E11 pattern).
  2. UNION ALL the `canonical_additions` CTE into `final` before the `qualify` dedup.
  3. Add a `t60_enrichment` CTE reading `matchbook_t60_enrichment.parquet` via `try_read_parquet(...)`.
  4. In the final SELECT, replace `cast(null as varchar) as favourite_team_id` with `coalesce(t60.favourite_team_id, null) as favourite_team_id` via LEFT JOIN on `match_id`.
  5. Update ERD.md `favourite_team_id` description to "T-60 minute window (kickoff − 75 min to kickoff − 45 min)" (AC21 — already done in S9; confirm).
- **Green criterion:** `dbt build --select silver.canonical.match` green with no regressions on existing tests (`match_id not_null`, `unique`, FK tests). With `matchbook_t60_enrichment.parquet` present, `favourite_team_id` is non-NULL for enriched matches.
- **Guardrails to satisfy:** Single-writer DuckLake (dbt writes match table; Python reads Parquet only); `try_read_parquet` handles absent Parquet gracefully (E11 — `favourite_team_id=NULL` when file absent, no error); `qualify row_number()` dedup preserved; `+database: lake` inherited; `+materialized: table` inherited.
- **Self-review checkpoint:** Reviewer checks: (1) absent `matchbook_canonical_additions.parquet` produces no error (try_read_parquet or conditional); (2) absent `matchbook_t60_enrichment.parquet` produces `favourite_team_id=NULL` (not error); (3) existing `match` tests (`match_id` unique, FK tests) still pass; (4) UNION ALL only for `new_canonical` action rows (not all overrides); (5) dedup `qualify` clause still present and correct.

---

### Step S11 — `stg_matchbook_odds.sql` check and T-60 source wiring

- **Goal:** Verify that `stg_matchbook_odds.sql` and its companion `yml` correctly
  expose `event_id`, `market_type`, `runner_id`, `best_back_price`, `kickoff_ms`,
  `ingested_at` — the columns the T-60 engine reads from the odds bronze Parquet.
  No model change needed if already correct; document the verification.
- **Spec trace:** Scenario H1; AC8
- **Red:** `dbt build --select silver.stg_matchbook_odds` passes but T-60 engine
  test (S5) fails if expected columns are absent from the Parquet output.
- **Implementation:** Read `stg_matchbook_odds.sql` and `stg_matchbook_odds.yml`; confirm columns `event_id`, `market_type`, `runner_id`, `best_back_price`, `kickoff_ms`, `ingested_at` are present and tested with `not_null` where appropriate. If any are missing, add `coalesce` or cast in the staging view and update the yml. No new file needed if columns are already present.
- **Green criterion:** `dbt build --select silver.stg_matchbook_odds` green; T-60 engine tests (S5) that read from the odds Parquet pass.
- **Guardrails to satisfy:** No regressions on existing `stg_matchbook_odds` tests.
- **Self-review checkpoint:** Reviewer confirms required columns are present in staging view and verifiable.

---

### Step S12 — `definitions.py` wiring: new assets, job, schedule, exclusion

- **Goal:** Register `matchbook_conform` and `matchbook_t60_enrichment` assets in
  `Definitions`. Define `matchbook_conform_job` (selection: conform + t60 +
  `AssetKey(["silver","matchbook_event_link"])` + `AssetKey(["silver","match"])`).
  Subtract `matchbook_conform_assets` from `medallion_hello_world`. Add schedule
  `matchbook_conform_schedule` at suggested cron `0 1,7,13,19 * * *`. Register
  the Streamlit service in `docker-compose.yml`.
- **Spec trace:** AC13, AC15; Spec §3 Goal 9
- **Red (failing test first):**
  ```python
  # tests/test_definitions.py — two-part exclusion test (CLAUDE.md pattern, U30):
  from dagster import AssetKey, AssetSelection
  from data_platform.definitions import defs

  all_keys = {k for k in AssetSelection.all().resolve(defs.get_asset_graph())}
  hello_world_keys = {k for k in defs.get_job_def("medallion_hello_world").selection.resolve(defs.get_asset_graph())}

  # Part 1: asset IS registered (in AssetSelection.all())
  assert AssetKey(["matchbook_conform"]) in all_keys
  # Part 2: asset NOT in medallion_hello_world (heavy job, excluded via subtraction)
  assert AssetKey(["matchbook_conform"]) not in hello_world_keys
  ```
  Note: `matchbook_conform` SHOULD appear in `matchbook_conform_job` — the two-part test is about exclusion from `medallion_hello_world`, not from its own dedicated job. Both assertions fail before this step because S7/S8 created the asset files but `definitions.py` has not yet been updated to import them.
- **Implementation:**
  1. Import `matchbook_conform` from `assets/matchbook_conform.py` and `matchbook_t60_enrichment` from `assets/matchbook_t60.py` in `definitions.py`. This is the first and only place these assets are added to `definitions.py`.
  2. Create `matchbook_conform_assets` selection (conform asset + t60 asset + dbt keys for `matchbook_event_link` + `match` + `canonical_match_export` + `canonical_team_export`).
  3. Subtract from `medallion_hello_world`: `AssetSelection.all() - football_assets - espn_assets - matchbook_events_assets - matchbook_conform_assets`.
  4. Define `matchbook_conform_job` and `matchbook_conform_schedule`.
  5. Add new assets to `Definitions(assets=[..., matchbook_conform, matchbook_t60_enrichment])`.
  6. Add `matchbook_conform_job` to `jobs=[...]` and `matchbook_conform_schedule` to `schedules=[...]`.
  7. Add Streamlit service to `docker-compose.yml`:
     ```yaml
     streamlit:
       <<: *app
       command: >
         sh -c "streamlit run streamlit_app/matchbook_exceptions.py
                --server.address 0.0.0.0 --server.port 8501"
       ports:
         - "${STREAMLIT_PORT:-8501}:8501"
       volumes:
         - ./data:/app/data
     ```
- **Green criterion:** U30 two-part test passes; `PYTHONPATH=src uv run pytest tests/test_definitions.py` green; `dagster definitions validate -w workspace.yaml` exits 0.
- **Guardrails to satisfy:** Two-part exclusion test (CLAUDE.md: "assert IS in all() AND NOT in job keys"); `workspace.yaml` used for validate (not just `-m`); no `from __future__ import annotations` in `definitions.py` (already true — it's already excluded); Docker service has `./data:/app/data` volume.
- **Self-review checkpoint:** Reviewer checks: (1) two-part test is truly two assertions (not one); (2) `matchbook_conform_job` selection does NOT include football/espn/hello-world assets; (3) `dagster definitions validate -w workspace.yaml` exits 0; (4) Streamlit service in docker-compose has `restart: unless-stopped`; (5) no new import of `matchbook_conform` into `definitions.py` breaks `from __future__ import annotations` ban (verify `definitions.py` itself has no Dagster annotations that would be broken).

---

### Step S13 — `from __future__ import annotations` guard test (AC17)

- **Goal:** Add an AST-scan pytest that asserts no file under `src/data_platform/assets/`
  contains `from __future__ import annotations`. This is the AC17 enforcement test.
- **Spec trace:** AC17
- **Red (failing test first):** Write the test; it passes immediately if assets/ is clean
  (but serves as a regression guard). Verify it fails when a `from __future__` import is
  artificially injected into one asset file.
- **Implementation:**
  ```python
  # tests/test_no_future_annotations.py  (new file)
  import ast
  from pathlib import Path

  ASSETS_DIR = Path(__file__).parents[1] / "src" / "data_platform" / "assets"

  def test_no_from_future_annotations_in_assets():
      violations = []
      for f in ASSETS_DIR.glob("*.py"):
          tree = ast.parse(f.read_text())
          for node in ast.walk(tree):
              if (
                  isinstance(node, ast.ImportFrom)
                  and node.module == "__future__"
                  and any(alias.name == "annotations" for alias in node.names)
              ):
                  violations.append(f.name)
      assert violations == [], f"Found 'from __future__ import annotations' in: {violations}"
  ```
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/test_no_future_annotations.py` passes with all current asset files; fails if any asset file gets the import added.
- **Guardrails to satisfy:** ruff clean; pure ast scan (no imports of asset modules, no side-effects).
- **Self-review checkpoint:** Reviewer confirms: (1) test fails when `from __future__ import annotations` is inserted into any `assets/*.py` file; (2) test passes on clean tree; (3) test is in `tests/` root (not in `tests/matchbook/`), basename is unique.

---

### Step S14 — End-to-end smoke + pre-commit gate

- **Goal:** Run the full test suite and pre-commit gate; verify the end-to-end
  Parquet artifact chain works (conform produces resolved-links → dbt reads it →
  match.sql includes T-60 enrichment); confirm ESPN score enrichment (I1 / AC16)
  is documented to be working (no new code needed).
- **Spec trace:** AC6, AC16, AC19; all guardrails
- **Red:** Any failing test or pre-commit violation at this step is a regression
  from a prior step and must be fixed before shipping.
- **Implementation:**
  1. Run `PYTHONPATH=src uv run pytest` — all tests green.
  2. Run `uv run pre-commit run --all-files` — clean.
  3. Run `cd dbt/data_platform && uv run --project ../.. dbt build` with test Parquet fixtures in place — green.
  4. Verify AC16 documentation: `match.sql` `status_completed` path is unchanged and the `espn_ingestion` job already rebuilds `match` — no code change needed, confirm by reading `match.sql` and the ESPN job definition.
- **Green criterion:** All commands above exit 0. `dagster definitions validate -w workspace.yaml` exits 0.
- **Guardrails to satisfy:** All guardrails from §5.
- **Self-review checkpoint:** Reviewer checks: (1) all tests pass; (2) pre-commit clean; (3) dbt build green; (4) no reward-hacking anywhere in the changeset (no skipped tests, no blanket `# noqa`, no `xfail`); (5) AC16 confirmed by reading `match.sql` (no code needed).

---

## 7. Sequencing & dependencies

The ordering below respects (a) bronze→silver→gold data flow, (b) the CLAUDE.md
constraint that `Settings` fields must precede asset modules, and (c) that dbt
canonical exports must exist before the conform Python asset runs in production:

```
S0  (deps + Settings)
│
├─ S1  (parse_event_name — pure Python)
├─ S2  (load_overrides — pure Python)
├─ S3  (canonical_team_export / canonical_match_export dbt models)
│
├─ S4  (conform engine — depends on S1, S2, S3 pattern; reads canonical Parquet)
├─ S5  (T-60 engine — depends on S3 canonical match Parquet pattern)
│
├─ S6  (Streamlit UI — independent of S4/S5 for code; reads their output at runtime)
├─ S7  (matchbook_conform Dagster asset — depends on S0 Settings, S4 engine)
├─ S8  (matchbook_t60_enrichment Dagster asset — depends on S0 Settings, S5 engine)
│
├─ S9  (matchbook_event_link dbt model + BronzeAwareTranslator + ERD.md)
├─ S10 (match.sql extension — depends on S9 matchbook_event_link + S5 T-60 Parquet)
├─ S11 (stg_matchbook_odds check — independent, but confirms T-60 column availability)
│
├─ S12 (definitions.py wiring + Docker Compose — depends on S7, S8, S9)
└─ S13 (from __future__ guard test — after all assets created)
    └─ S14 (end-to-end smoke + pre-commit gate — last)
```

Key ordering gotchas:
- **S0 before S7/S8**: `Settings` fields must exist before asset modules are
  imported (CLAUDE.md: "Config fields must precede the asset wrapper").
- **S3 before S4/S5 in production**: the canonical Parquet exports must be run by
  dbt before the Python conform engine runs. In the asset graph, this is enforced
  by S7's dep on `AssetKey(["silver","canonical_match_export"])` and
  `AssetKey(["silver","canonical_team_export"])` — these deps are declared in the
  `matchbook_conform` asset file created in S7.
- **S7 creates asset files; S12 registers them in definitions.py**: S7 and S8
  create `assets/matchbook_conform.py` and `assets/matchbook_t60.py` respectively,
  but do NOT modify `definitions.py`. S12 is the single step that imports both
  assets into `definitions.py`, adds them to `Definitions`, and wires the job and
  schedule. This eliminates the S7/S12 contradiction: S7's green criterion is
  passing engine tests + asset file existence; S12's green criterion is the
  two-part `test_definitions.py` assertion (asset in `AssetSelection.all()`, NOT in
  `medallion_hello_world`).
- **S9 before S10**: `match.sql` UNION requires `matchbook_event_link` to be real
  (the relationships test depends on `match` including all `new_canonical` rows).
- **S9 (BronzeAwareTranslator) before S12 (definitions.py)**: the translator must
  know the `matchbook_resolved_links` source before the full `dbt_models` asset
  is re-validated in definitions.
- **ERD.md in S9 commit**: CLAUDE.md hard requirement — schema change and ERD
  update must be atomic.

---

## 8. Assumptions

1. `rapidfuzz.fuzz.token_sort_ratio` is the correct ratio function (spec §9 assumption 1). Thresholds 0.85 (HIGH) and 0.70 (MEDIUM) are calibrated to this function.
2. `canonical_match_export.sql` should include `home_team_name` and `away_team_name` columns (from a join onto `team`). The spec references "home_team_name/away_team_name from canonical_match_export Parquet" for runner resolution (AC9, Scenario H1). The `match` table itself stores `home_team_id`/`away_team_id` not names — the export model must join `team` to expose names.
3. The `canonical_team_export` and `canonical_match_export` dbt models live under `models/silver/canonical/` (not `models/gold/`) because they export silver entities. The `+materialized: external` config is NOT blocked by `canonical: +materialized: table` — the local `config()` block in the model file overrides the `dbt_project.yml` default.
4. `try_read_parquet` is available in the DuckDB version used (>=1.5.2, required for DuckLake). If not, a conditional `{% if env_var('...', '') != '' %}` dbt macro pattern is used as fallback.
5. The Streamlit testing library (`streamlit.testing.v1`) is available in the `streamlit>=1.35` version added in S0. If not available, the smoke test uses subprocess.
6. OQ3 is resolved as: T-60 asset deps on `AssetKey(["silver","matchbook_event_link"])` (the dbt model key) — NOT on the resolved-links Parquet file key. This enforces dbt FK validation ordering.
7. OQ4 resolved: `matchbook_conform_job` scope is `matchbook_conform_assets` which includes `matchbook_event_link` and `match` dbt models but not the full ESPN canonical suite.
8. OQ5 resolved: Streamlit service in base `docker-compose.yml` (mirrors `jupyter`).
9. The `matchbook_conform_canonical_dir` property points to `data/silver/canonical/` — the directory where `canonical_team_export` and `canonical_match_export` write their Parquet files. The path `data/silver/canonical/match.parquet` is where `canonical_match_export.sql`'s `location` resolves at runtime.
10. The `matchbook_t60_dir` property is the parent of `matchbook_t60_enrichment.parquet` (`data/silver/`); similarly `matchbook_conform_dir` is the parent of `matchbook_resolved_links.parquet` (`data/silver/`).
11. Python's `canonical_match_id` replication uses `hashlib.md5("|".join([league_id, season_id, date_str, home_team_id, away_team_id]).encode()).hexdigest()` — same field order as the SQL macro.
12. The `matchbook_canonical_additions_dir` is `data/silver/` (same level as `matchbook_resolved_links.parquet`). Both are silver-layer artifacts.

---

## 9. Open questions

| # | Question | Blocker? | Notes |
|---|----------|----------|-------|
| Q1 | `canonical_match_export.sql` — should the join onto `team` use `home_team_id`/`away_team_id` to fetch names, or should team names be sourced from ESPN staging directly? | Non-blocker | Assumption 2 above: join `team` in the export. This keeps the export self-contained and avoids re-reading ESPN staging. If team.name is the canonical display name (per `_schema.yml`), this is correct. |
| Q2 | `streamlit.testing.v1` availability in `streamlit>=1.35` | Non-blocker | If unavailable, use subprocess smoke-test. Document in S6 if workaround used. |
| Q3 | `try_read_parquet` availability in DuckDB >=1.5.2 | Non-blocker | If unavailable, use `read_parquet(glob_path, union_by_name=true)` where glob matches the file if present, and wrap in a CTE that returns empty when no files match. Document in S10. |
| Q4 | Exact cron for `matchbook_conform_schedule` | Non-blocker | Spec §9 assumption 7 suggests `0 1,7,13,19 * * *`. Implementer may adjust; must be documented in `definitions.py`. |
| Q5 | Streamlit `settings` import — should the Streamlit app import `data_platform.config.settings`? | Non-blocker | Preferred approach: import `settings` so paths are config-driven. The Streamlit app must then be run with `PYTHONPATH=src` (same as rest of the project). Document in `docker-compose.yml` command. |

**No blockers.** All spec open questions are resolved. Remaining questions above are implementation-choice decisions delegated to the implementer.

---

## 10. Traceability

Every spec scenario and acceptance criterion maps to at least one unit and one step.

| Spec scenario / AC | Unit(s) | Step(s) | Guardrail(s) |
|--------------------|---------|---------|--------------|
| A1: parse "Team A v Team B" | U1 | S1 | pytest, ruff |
| A2: missing ` v ` → exceptions | U2 | S1, S4 | pytest, ruff |
| B1: override exists → human_confirmed | U5, U6 | S2, S4 | pytest, atomic write |
| B2: override file absent → no error | U4 | S2, S4 | pytest |
| C1: HIGH confidence auto-link (0.95) | U7 | S4 | pytest (U7), ruff |
| C2: HIGH blocked by kickoff > 90 min | U8 | S4 | pytest |
| D1: MEDIUM confidence unique (0.75) | U9 | S4 | pytest (U9), ruff |
| D2: MEDIUM multiple candidates → exceptions | U10 | S4 | pytest |
| E1: no match → exceptions with candidates | U11 | S4 | pytest |
| E2: exceptions rebuilt across runs | U14 | S4 | pytest (idempotency) |
| E4: first ` v ` split only | U3 | S1 | pytest |
| E7: rugby silently skipped | U12 | S4 | pytest |
| E8: tie-score → exceptions | U10 (extended) | S4 | pytest |
| E14: invalid start_utc → exceptions | S4 engine | S4 | pytest |
| E15: dedup by latest ingested_at | S4 engine | S4 | pytest |
| F1: new_canonical → additions Parquet | U15, U16 | S4 | pytest, dbt test (relationships) |
| G1: matchbook_event_link typed table | U17 | S9 | dbt build, ruff |
| G2: re-run idempotent | U18 | S9, S10 | dbt build |
| H1: T-60 window → favourite runner | U19, U20, U22 | S5 | pytest |
| H2: no T-60 tick → no row | U21 | S5 | pytest |
| H3: match.favourite_team_id populated | U25 | S10 | dbt build |
| I1: ESPN score enrichment (existing) | U33 | S14 | dbt build (AC16 verification) |
| J1: Streamlit displays unresolved events | U26 | S6 | pytest/smoke |
| J2: Confirm → action='link' | U27 | S6 | pytest |
| J3: New Canonical → action='new_canonical' | U28 | S6 | pytest |
| J4: Merge → action='merge' | U29 | S6 | pytest |
| J5: absent exceptions file → no error | U26 | S6 | pytest |
| AC1: parse + fuzzy on football events | U1, U2, U12 | S1, S4 | pytest |
| AC2: confidence=0.95 exact constant | U7 | S4 | pytest (exact value assert) |
| AC3: confidence=0.75 exact constant | U9 | S4 | pytest (exact value assert) |
| AC4: exceptions Parquet + candidates JSON | U11, U14 | S4 | pytest |
| AC5: override → confidence=1.0 | U5, U6 | S2, S4 | pytest |
| AC6: idempotent runs | U13 | S4, S9 | pytest, dbt tests |
| AC7: matchbook_event_link + relationships test | U17 | S9 | dbt build |
| AC8: T-60 enrichment Parquet | U19–U21 | S5 | pytest |
| AC9: favourite_team_id populated | U22, U25 | S5, S10 | pytest, dbt build |
| AC10: Streamlit handles absent exceptions file | U26 | S6 | pytest/smoke |
| AC11: three action types written correctly | U27–U29 | S6 | pytest |
| AC12: rugby not in exceptions | U12 | S4 | pytest |
| AC13: matchbook_conform_job registered + excluded | U30 | S12 | pytest (two-part) |
| AC14: matchbook_conform deps on events_bronze | U31 | S7, S12 | pytest |
| AC15: Streamlit Docker service on port 8501 | U32 | S12 | YAML parse test |
| AC16: ESPN ft_score populated (existing) | U33 | S14 | dbt build |
| AC17: no from __future__ in asset modules | U34 | S13 | pytest (AST scan) |
| AC18: all Settings fields before asset modules | S0 | S0 | pytest (config test) |
| AC19: pure-Python units testable without DuckLake | U1–U22 | S1–S5 | pytest (no live catalog) |
| AC20: ERD.md updated with matchbook_event_link schema | — | S9 | self-review (same commit) |
| AC21: ERD.md favourite_team_id → T-60 label | — | S9/S10 | self-review (same commit) |
