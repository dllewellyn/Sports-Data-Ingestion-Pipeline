---
id: "004"
title: Matchbook Events Bronze Ingestion — Implementation Plan
slug: matchbook-events-bronze-ingestion
status: draft
created: 2026-06-29
specification: 004-matchbook-events-bronze-specification.md
user_stories: []
---

# Matchbook Events Bronze Ingestion — Implementation Plan

## 1. Summary

We are adding a new bronze-layer ingest source: Matchbook open events (football
sport-id 15, rugby union sport-id 2). The implementation follows the established
ESPN pattern exactly: a Dagster-free pure-Python engine in
`src/data_platform/matchbook/ingest.py` handles auth, paginated fetch, per-record
Pydantic validation, per-frame Pandera validation, and atomic Parquet write; a thin
Dagster wrapper in `src/data_platform/assets/matchbook_events.py` wires the engine
into a dedicated `matchbook_events_ingestion` job and `matchbook_events_schedule`
(cron `0 */6 * * *`). New config fields (`matchbook_username`, `matchbook_password`,
`matchbook_throttle_seconds`) are added to `config.py` alongside the existing Redis
fields; a new `matchbook_events_bronze_dir` property is added. Schemas live in
`models/schemas.py` (Pydantic) and `models/validation.py` (Pandera), following the
existing multi-schema pattern. The asset is explicitly excluded from
`medallion_hello_world`. No DuckDB or DuckLake writes occur; bronze is Parquet-only.
Steps are ordered: contracts → engine → asset wrapper → config+dir → definitions
wiring (always last).

---

## 2. Skills to use

The available skills from the session system-reminder are used below. This spec is
a data-ingestion pipeline; there is no dedicated "create data ingestion pipeline"
skill — the repo's `ARCHITECTURE.md §6` "add a new data source" guide is the
equivalent document, and the existing `espn/ingest.py` pattern is the living
reference. The plan proceeds from those patterns; `self-learn` is scheduled after
the build to codify learnings.

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| Architecture conformance review of the changeset | `code-architecture-review` | available |
| Per-step diff review | (general code review — no dedicated skill found) | — |
| Creating missing rules (if needed) | `create-rule` (command) | available |
| Capturing learnings after build | `self-learn` | available |
| Create data-ingestion pipeline (new bronze source) | — | MISSING — proceed from `espn/ingest.py` pattern + `ARCHITECTURE.md §6`; run `self-learn` after to codify into a skill |
| Dagster definitions validation | `dagster definitions validate` (CLI) | available (CLI, not a skill) |

---

## 3. Convention & rule audit (resolved before implementation)

All artifact types introduced by this plan are audited against their governing
conventions. Sources: `CLAUDE.md` (Python conventions + Non-obvious constraints),
`ARCHITECTURE.md` (layering/dependency rules + §6 extension guide), `pyproject.toml`
(ruff lint set, pytest layout), and nearest existing code of the same type.

| Artifact type | Governing convention | Status |
|---------------|----------------------|--------|
| New Python ingestion module (`matchbook/ingest.py`) | `CLAUDE.md`: pydantic-settings config; `pathlib.Path`; atomic write (temp+rename); `raw_event` JSON column; no `os.getenv`; OTel span via `get_tracer()`. `ARCHITECTURE.md §6`: network edge in bronze only; contracts-first. Mirror: `espn/ingest.py` | **exists** |
| API / network code (session-token auth + paginated HTTP) | `CLAUDE.md`: `requests` auto-instrumented; config via `pydantic-settings`; raise on error, no silent fallbacks; no ad-hoc `os.getenv`. Mirror: `espn/http_client.py`, `espn/ingest.py`. No separate rule for auth patterns — see blocker below | **gap — BLOCKER** |
| New Dagster asset module (`assets/matchbook_events.py`) | `CLAUDE.md`: NO `from __future__ import annotations`; thin wrapper over pure-Python engine; `AssetKey`, `group_name`, `compute_kind`; use `MaterializeResult`. Mirror: `assets/espn.py` | **exists** |
| New Pydantic record schema (`MatchbookEventRecord`) | `CLAUDE.md`: Pydantic v2 `BaseModel`, `ConfigDict(extra="ignore")`; `field_validator` for required-non-empty core fields; `raw_event: str` required. Mirror: `EspnEventRecord` in `models/schemas.py` | **exists** |
| New Pandera frame schema (`matchbook_events_bronze_schema`) | `CLAUDE.md`: `strict=False`; enforce core columns only; `coerce=True`; `nullable=False` for required columns. Mirror: `espn_bronze_schema` in `models/validation.py` | **exists** |
| New `Settings` fields + property (`matchbook_username`, `matchbook_password`, `matchbook_events_bronze_dir`) | `CLAUDE.md`: typed fields in `config.py`; property for derived paths; no rename of existing Redis fields. Mirror: existing `matchbook_redis_host`, `espn_bronze_dir` | **exists** |
| New pytest test files (`tests/matchbook/test_ingest.py`, `test_asset.py`) | `CLAUDE.md`: `tests/` mirrors `src/data_platform/`; `pyproject.toml`: `pythonpath=["src"]`, `importlib` mode, unique basenames; `conftest.py` for OTel silencing per-package. Mirror: `tests/espn/` | **exists** |
| `definitions.py` wiring (new asset, job, schedule + `AssetSelection.all()` subtraction) | `CLAUDE.md`: `definitions.py` is the sole composition root; `AssetSelection.all()` must subtract new heavy/standalone sources; dedicated job required; edits to `definitions.py` must be the LAST step. Mirror: existing `espn_assets` exclusion pattern | **exists** |
| `.env.example` additions | `CLAUDE.md`: document new settings; placeholder values only; never commit real credentials | **exists** |
| OTel span | `CLAUDE.md`: `get_tracer()` from `otel.py`; span per ingest run; best-effort (no `depends_on`). Mirror: `espn/ingest.py` `ingest.espn` span | **exists** |

### Gap — BLOCKER (convention-audit hard gate)

**Auth pattern rule is absent.** The spec introduces a session-token authentication
flow (POST credentials → extract token → pass as header) that no existing rule
document covers explicitly. The existing sources (ESPN, football-data) use either
unauthenticated HTTP or an API key. The auth module pattern (where auth lives, how
errors propagate, token lifecycle) is not written down.

**Resolution approach (non-interactive mode — recorded as a blocker needing
approval):** The plan proposes the following convention, to be adopted before S2
(the engine step), either by appending to `CLAUDE.md` or by creating a dedicated
rule:

> **Session-token auth pattern:** POST credentials to the auth endpoint, extract
> the session token from the response, raise immediately (`ValueError`) if the
> response has no token field. Implement auth as a standalone function
> `authenticate(username, password, *, base_url, timeout) -> str` so it is
> unit-testable without Dagster. Acquire exactly one token per asset run; do not
> refresh mid-run. Raise before any Parquet write if auth fails (AC16).

This convention documents exactly what the spec requires (Scenarios: "Auth endpoint
returns error or no token"; AC16; E1–E3). Approval required before implementation
begins.

---

## 4. Testable units (BDD → tests)

| Unit | Spec trace (scenario / AC) | Test facility | Failing-first assertion |
|------|----------------------------|---------------|-------------------------|
| `authenticate()` returns a session token string from a mock 200 response | Auth — "Successful session token acquisition" / AC11 | pytest (`tests/matchbook/test_ingest.py`) | Call with mocked `requests.post` returning `{"session-token":"tok"}` → returns `"tok"` (fails before function exists) |
| `authenticate()` raises `ValueError` when response has no `session-token` | Auth — "Auth endpoint returns error or no token" / AC16, E3 | pytest | Mocked 200 with `{}` → `ValueError` raised (fails before guard exists) |
| `authenticate()` raises on non-2xx response | Auth — "Auth endpoint returns error or no token" / AC16, E1 | pytest | Mocked 401 → raises (fails before `raise_for_status()` call exists) |
| Missing credentials raises before any HTTP call | Auth — "Missing credentials" / AC6, E2 | pytest | Pass `username=""` → raises with descriptive message; no HTTP call made |
| `fetch_events()` paginates until all events retrieved | Event fetching — "Paginated fetch…" | pytest | Mock responses: page 1 returns `total=25`, 20 events; page 2 returns 5 events → accumulate 25 (fails before loop logic exists) |
| `fetch_events()` returns empty list when API returns zero events | Event fetching — "Empty result for a sport" / E7 | pytest | Mock `total=0, events=[]` → returns `[]` (fails before zero-check exists) |
| `fetch_events()` raises on non-2xx response from events endpoint | Edge case E4 | pytest | Mocked 503 → raises |
| `fetch_events()` treats absent `total` as single page | Edge case E13 | pytest | Mock response with no `total` key → returns page-1 events only, logs warning (fails before guard exists) |
| `MatchbookEventRecord` validates a well-formed event dict | Record validation — "Well-formed events pass validation" / AC4 | Pydantic (`models/schemas.py`) | Feed dict with all required fields → validates without error (fails before model exists) |
| `MatchbookEventRecord` rejects a dict missing `event_id` | Record validation — E5, E11 | Pydantic | Feed dict without `event_id` → `ValidationError` raised (fails before required-field validator exists) |
| `MatchbookEventRecord` rejects a dict with absent or unparseable `start` | Record validation — E12 | Pydantic | Feed dict with `start=None` → `ValidationError` raised |
| `matchbook_events_bronze_schema` validates a minimal well-typed frame | Frame validation — "Well-formed events pass…" / AC4 | Pandera (`models/validation.py`) | Pass a 2-row DataFrame with required columns → validates (fails before schema exists) |
| `matchbook_events_bronze_schema` rejects frame missing `raw_event` column | Frame validation — "Frame fails Pandera schema" / AC3 | Pandera | Drop `raw_event` column → raises `SchemaError` (fails before schema exists) |
| Ingest function writes Parquet at correct partitioned path | Parquet write — "Successful atomic write" / AC1, AC2 | pytest (artifact assertion) | Call `ingest_sport(...)` with mocked HTTP → `data/bronze/matchbook_events/football/<YYYY-MM-DD>/<ts>.parquet` exists (fails before write logic exists) |
| Parquet rows contain `raw_event` with full original dict including non-projected fields | Parquet write — "`raw_event` column…" / AC3 | pytest (artifact assertion) | Mock raw dict includes a `venue` key NOT in projected columns; read Parquet, deserialise `raw_event`, assert `venue` key present and `markets` key present (fails before `raw_event` is serialised with the full original dict — a faithful-bronze test, not a projected-columns test) |
| Parquet rows contain all structured columns at correct types | Parquet write — "Successful atomic write" / AC4 | pytest (artifact assertion) | Read Parquet columns and assert `event_id`, `event_name`, `sport_id`, `status`, `start_utc`, `volume`, `ingested_at`, `raw_event` all present (fails before columns projected) |
| Atomic write: no partial file left on disk after write-time failure | Parquet write — "Successful atomic write" / AC8 | pytest | Mock `tmp_path.replace(final_path)` to raise → assert final path absent (fails before temp+rename pattern) |
| Directory created on first run | Parquet write — "Output path created on first run" | pytest (artifact assertion) | `matchbook_events_bronze_dir / "football"` does not pre-exist → ingest creates it (fails before `mkdir(parents=True, exist_ok=True)`) |
| Replay (same date) appends new file, does not overwrite | Parquet write — E10 / AC5 | pytest | Run ingest twice same date → two distinct files under same partition dir (fails before batch-timestamp path scheme exists) |
| Zero events for one sport: no Parquet, continues to other sport | Edge case E7 / "Empty result for a sport" | pytest | Mock football=0 events, rugby=3 events → no football Parquet, rugby Parquet written (fails before zero-events guard) |
| Zero events all sports: run succeeds, no Parquet written | Edge case E8 | pytest | Mock both sports zero → no Parquet, no exception raised (fails before zero-all guard) |
| Per-record failures accumulate in `ingest_sport`: valid records written, failure count returned (NOT raised) | "Individual malformed record skipped…" / AC7, E5 | pytest | `ingest_sport(...)` with mix 1 bad + 2 good → returns result with `failure_count=1`, Parquet has 2 rows, function does NOT raise (fails before skip-and-count logic) |
| `run_matchbook_events_ingest` re-raises at end if any failures accumulated | "Individual malformed record skipped…" / AC7, E5 | pytest | Mock `ingest_sport` to return failure_count=1 → `run_matchbook_events_ingest` raises at end (fails before re-raise logic) |
| OTel span emitted for each sport ingest | "Successful atomic write" + telemetry convention | pytest | Monkeypatch `get_tracer`; call ingest; assert span name `"ingest.matchbook_events"` emitted (fails before `get_tracer()` call exists) |
| `matchbook_events_bronze_dir` property returns correct path | AC12 | pytest | `settings.matchbook_events_bronze_dir == settings.bronze_dir / "matchbook_events"` (fails before property exists) |
| Asset module has no `from __future__ import annotations` | AC13 | pytest (inspect) | `"from __future__ import annotations"` not in `inspect.getsource(matchbook_events_asset_module).splitlines()` (fails if import present) |
| Asset key is `["matchbook_events_bronze"]`, group is `"bronze"` | AC9, AC10 | pytest | `matchbook_events_bronze.key == AssetKey(["matchbook_events_bronze"])` (fails before asset exists) |
| `matchbook_events_ingestion` job registered; fires only `matchbook_events_bronze` | AC10 | pytest (definitions test) | `defs.get_job_def("matchbook_events_ingestion")` exists; asset keys contain only `matchbook_events_bronze` (fails before job registered) |
| `matchbook_events_schedule` fires at `0 */6 * * *`, targets the job | AC10 | pytest (definitions test) | Schedule cron and job name match (fails before schedule registered) |
| `matchbook_events_bronze` excluded from `medallion_hello_world` | AC9 | pytest (definitions test) | `"matchbook_events_bronze"` not in `medallion_hello_world` asset keys (fails before exclusion subtracted) |
| `MATCHBOOK_USERNAME` and `MATCHBOOK_PASSWORD` declared in `config.py` | AC11 | pytest | Instantiate `Settings(matchbook_username="u", matchbook_password="p")` → no error (fails before fields added) |
| `matchbook_events_base_url` declared in `config.py` with correct default | A9 | pytest | `Settings().matchbook_events_base_url == "https://api.matchbook.com"` (fails before field added) |

---

## 5. Guardrail register

| Guardrail | How verified in place | Covered by step |
|-----------|------------------------|-----------------|
| ruff check + format (pre-commit) | `uv run ruff check src/data_platform/matchbook/ingest.py src/data_platform/assets/matchbook_events.py src/data_platform/config.py src/data_platform/models/schemas.py src/data_platform/models/validation.py` clean; `uv run pre-commit run --all-files` clean | Every step |
| pytest unit tests pass | `PYTHONPATH=src uv run pytest tests/matchbook/` green | S1–S5 |
| Pydantic per-record boundary validation | `MatchbookEventRecord` rejects malformed records; bad-record test passes | S1 |
| Pandera per-frame boundary validation | `matchbook_events_bronze_schema` rejects frames missing core columns; schema test passes | S1 |
| Atomic Parquet write (temp + rename) | No partial file test passes; write uses `tmp_path = out_path.with_suffix(".tmp"); tmp_path.replace(out_path)` | S2 |
| `raw_event` column faithfulness | Parquet row `raw_event` round-trips to original dict including `markets`; test asserts non-projected field recovery | S2 |
| Idempotency / re-run safety (append, not overwrite) | Run-twice test: two distinct files at same partition date; no file deleted | S2 |
| OTel span emitted per sport run | Span-emission test passes for `"ingest.matchbook_events"` | S2 |
| No `from __future__ import annotations` in asset module | `inspect.getsource` test in `test_asset.py` | S3 |
| Config via pydantic-settings only | All new config in `config.py`; no `os.getenv` in new code; `ruff` and code review | S3 |
| `matchbook_events_bronze` excluded from `medallion_hello_world` | Definitions test asserts exclusion; `dagster definitions validate` exits 0 | S5 |
| `matchbook_events_ingestion` job + `matchbook_events_schedule` registered | Definitions test asserts job and schedule present with correct cron | S5 |
| No DuckDB / DuckLake writes | Code review: no DuckDB import or connection in new files | all |
| Single-writer DuckDB constraint respected | No DuckDB connection opened in new code (not applicable — bronze is Parquet-only) | all |
| Repo non-obvious constraints | prefixed dbt asset keys (N/A — no new dbt models); no `from __future__`; `pathlib.Path` for paths; `pydantic-settings` for config | all |
| Auth fails before Parquet write (AC16) | `authenticate()` raises tests pass; Parquet absent after auth failure | S2 |
| `dagster definitions validate` exits 0 | Run `PYTHONPATH=src DUCKDB_PATH=/tmp/wh.duckdb dagster definitions validate -w workspace.yaml` after S5 | S5 |

---

## 6. Implementation steps

### Step S0 — Establish auth convention (hard gate)

- **Goal:** Close the convention gap for session-token auth before any implementation code is written. Add a concise ALWAYS/NEVER rule for the pattern to `CLAUDE.md` under "Non-obvious constraints" or as a new "Matchbook events auth pattern" bullet under Python conventions.
- **Spec trace:** Auth scenarios (all three) / AC11, AC16 — this convention governs how the auth function must behave.
- **Red (failing test first):** No test — this is a pure documentation step. The gate is: the rule does not yet exist. After this step, the rule exists in a committed `docs:` or `chore:` commit. The self-review confirms the rule text covers: standalone function, raise on missing token, raise on non-2xx, no side effects, one token per run, raise before any Parquet write.
- **Implementation:** Append to `CLAUDE.md` under "Non-obvious constraints":
  > **Matchbook session-token auth:** Auth lives in a standalone `authenticate(username, password, *, base_url, timeout) -> str` function in the ingest module so it is unit-testable. POST credentials to the auth endpoint; call `response.raise_for_status()` before inspecting the body; raise `ValueError("session-token not present in auth response")` if the key is absent. Acquire exactly one token per asset run — do not refresh mid-run. Auth failure raises before any Parquet write is attempted (AC16).
- **Green criterion:** Rule text present in `CLAUDE.md`, committed as `docs: add matchbook session-token auth convention`. No test to run — the gate is "committed convention exists".
- **Guardrails to satisfy:** The convention must be written before S1 and S2 can proceed.
- **Self-review checkpoint:** Reviewer confirms: rule exists in `CLAUDE.md`; rule covers all four obligations (standalone function, raise-for-status, ValueError on missing token, one token per run, raises before Parquet write); no implementation code added in this step; commit is `docs:` type.

---

### Step S1 — Data contracts: Pydantic record schema + Pandera frame schema

- **Goal:** Define `MatchbookEventRecord` (Pydantic) in `models/schemas.py` and `matchbook_events_bronze_schema` (Pandera) in `models/validation.py`, with tests in `tests/matchbook/test_contracts.py`.
- **Spec trace:** Record validation — "Well-formed events pass validation"; "Individual malformed record skipped"; "Frame fails Pandera schema" / AC3, AC4, E5, E11, E12.
- **Red (failing test first):** Create `tests/matchbook/__init__.py` (empty) and `tests/matchbook/test_contracts.py`. Write tests that import `MatchbookEventRecord` and `matchbook_events_bronze_schema` (both absent). Run `uv run pytest tests/matchbook/test_contracts.py` — fails with `ImportError`.
- **Implementation:**
  1. Add `MatchbookEventRecord` to `models/schemas.py` following `EspnEventRecord`'s pattern: `ConfigDict(extra="ignore")`; required fields `event_id: str`, `event_name: str`, `sport_id: int`, `status: str`, `start_utc: str`, `volume: float | None = None`, `ingested_at: str`, `raw_event: str`; `_required_text` validator on all `str` required fields; coerce `sport_id` to `int` in a `field_validator`.
  2. Add `matchbook_events_bronze_schema` to `models/validation.py` following `espn_bronze_schema`'s pattern: `strict=False`, `coerce=True`; columns `event_id`, `event_name`, `sport_id` (int), `status`, `start_utc`, `volume` (float, nullable=True), `ingested_at`, `raw_event` all required (nullable=False except `volume`).
  3. Add a `conftest.py` to `tests/matchbook/` that silences the matchbook OTel tracer (mirrors `tests/espn/conftest.py`).
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/matchbook/test_contracts.py` passes. All contract tests green (valid dict validates; missing `event_id` raises; missing `start` raises; frame missing `raw_event` raises SchemaError; well-typed frame passes).
- **Guardrails to satisfy:** ruff clean on `models/schemas.py`, `models/validation.py`; no I/O or orchestration in the models; `extra="ignore"` pattern respected.
- **Self-review checkpoint:** Reviewer confirms: `MatchbookEventRecord` and `matchbook_events_bronze_schema` exist in the correct files; tests were failing before the schemas existed (confirm by tracing the `ImportError`); `extra="ignore"` present; `raw_event: str` required and non-nullable; `strict=False, coerce=True` on Pandera schema; no `from __future__ import annotations` added to `models/schemas.py` or `models/validation.py` (they already have it — leave as-is, these are not Dagster asset modules); ruff clean; no reward-hacking (no test narrowed to pass against absent implementation).

---

### Step S2 — Pure-Python ingest engine (`matchbook/ingest.py`)

- **Goal:** Implement `src/data_platform/matchbook/ingest.py` — `authenticate()`, `fetch_events()`, `flatten_event()`, `ingest_sport()` (validate + atomic write), `run_matchbook_events_ingest()` (outer loop over sports). Dagster-free and fully unit-tested.
- **Spec trace:** All Auth scenarios; all Event-fetching scenarios; all Parquet-write scenarios; all edge cases E1–E13 / AC1–AC8, AC12, AC14, AC16.
- **Red (failing test first):** Create `tests/matchbook/test_ingest.py`. Write tests that import `authenticate`, `fetch_events`, `ingest_sport`, `run_matchbook_events_ingest` (all absent). Run — fails with `ImportError`.
- **Implementation outline:**
  1. `authenticate(username, password, *, base_url, timeout) -> str` — POST to `{base_url}/bpapi/rest/security/session`, `raise_for_status()`, extract `session-token`, raise `ValueError` if absent. Raise `ValueError("credentials missing")` immediately if `username` or `password` is empty before any HTTP call.
  2. `fetch_events(session_token, sport_id, *, base_url, per_page, timeout) -> list[dict]` — paginated GET to `{base_url}/edge/rest/events?sport-ids={sport_id}&status=open&include-markets=true&include-runners=true&per-page={per_page}&offset={offset}`. Loop while `len(events) < total` (or `len(batch) < per_page` as sentinel). If `total` absent, treat as single page (log warning). Raise on non-2xx.
  3. `flatten_event(raw: dict, *, ingested_at: str) -> dict` — project structured columns from the raw dict; include `raw_event = json.dumps(raw, ...)` (full dict including `markets`). Columns: `event_id`, `event_name`, `sport_id`, `status`, `start_utc`, `volume`, `ingested_at`, `raw_event`.
  4. `ingest_sport(sport_id, sport_name, session_token, *, base_url, per_page, timeout, out_dir, batch_ts, log, schema) -> Path | None` — call `fetch_events`; if zero events, log and return None. Flatten and per-record Pydantic validate (skip-and-count invalid); if zero valid records, return None. Pandera validate frame. Atomic write: `tmp = out_path.with_suffix(".tmp")`, write Parquet, `tmp.replace(out_path)`. Return path.
  5. `run_matchbook_events_ingest(username, password, *, base_url, per_page, timeout, out_dir, log, schema) -> IngestionReport` — authenticate; loop over `SPORTS` (`[{"sport_id": 15, "name": "football"}, {"sport_id": 2, "name": "rugby_union"}]`); call `ingest_sport` for each (catching per-sport exceptions, per the ESPN outer-loop pattern); accumulate results; re-raise at the end of the full loop if `report.failed > 0`. **`ingest_sport` does NOT re-raise on per-record Pydantic failures** — it records the failure count in a return value (`IngestionReport` or a tuple); `run_matchbook_events_ingest` re-raises once all sports have been attempted. A Pandera frame failure or zero-valid-records condition returns early from `ingest_sport` without writing a Parquet and without raising — the outer loop accumulates it as a skipped/failed sport.
  6. `IngestionReport` dataclass (written/skipped/failed counts and paths) mirroring ESPN pattern.
  7. OTel span `"ingest.matchbook_events"` wrapping the main ingest call.
  - Path scheme: `out_dir / sport_name / YYYY-MM-DD / {batch_ts}.parquet` (batch_ts = UTC ISO-8601 like `20260629T120000Z`).
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/matchbook/test_ingest.py` passes. All units green: authenticate happy path, ValueError on missing token, 401 raises, empty credentials raises before HTTP call, pagination accumulates all pages, zero events returns None, non-2xx on events endpoint raises, absent `total` handled, Parquet at correct path, `raw_event` round-trips with `markets`, all structured columns present, atomic write (no partial on failure), replay appends new file, zero-one-sport continues, zero-all-sports succeeds, per-record failures counted and re-raised, OTel span emitted.
- **Guardrails to satisfy:** ruff clean; no Dagster imports; no `os.getenv`; `pathlib.Path` for all paths; temp+rename atomic write; `raw_event` faithfulness; `config.py` not imported directly in the engine (settings passed as arguments so the function is testable without `monkeypatch`); auth convention from S0 honoured; `ingest_sport` does NOT re-raise on per-record failures — it returns a failure count; re-raise is in `run_matchbook_events_ingest` only.
- **Self-review checkpoint:** Reviewer confirms: all tests fail before the engine exists (verify by checking the ImportError on a clean run); `authenticate` raises before any HTTP call when credentials are empty; `fetch_events` makes no second GET when total is absent; Parquet path matches spec scheme; `raw_event` contains full original dict including a non-projected field (check the `venue`-key round-trip test); atomic write test actually confirms no partial file; no Dagster imports; ruff clean; `matchbook/ingest.py` may include `from __future__ import annotations` (it is a pure-Python module, not an asset module — the prohibition applies only to Dagster asset modules per CLAUDE.md); `ingest_sport` returns a result object, not raises, when only some records fail; `run_matchbook_events_ingest` re-raises at end; no reward-hacking (no hardcoded responses, no `pass`-body validators).

---

### Step S3 — Config, directory property, and `.env.example`

- **Goal:** Add `matchbook_username`, `matchbook_password`, and `matchbook_throttle_seconds` fields to `Settings` in `config.py`; add `matchbook_events_bronze_dir` property; document in `.env.example`. Tests assert the fields and property.
- **Spec trace:** AC11, AC12 / "Missing credentials" scenario (credentials absent → raise before HTTP call is part of ingest, but the config fields must exist first).
- **Red (failing test first):** Extend `tests/matchbook/test_contracts.py` (or add `tests/test_config_matchbook.py`) with: `Settings(matchbook_username="u", matchbook_password="p")` validates; `settings.matchbook_events_bronze_dir == settings.bronze_dir / "matchbook_events"`; `matchbook_events_bronze_dir != matchbook_bronze_dir`. These fail before fields/property added.
- **Implementation:**
  1. Add to `config.py` alongside existing `matchbook_redis_host`:
     ```python
     matchbook_username: str = ""
     matchbook_password: str = ""
     matchbook_throttle_seconds: float = 0.0
     ```
  2. Add property:
     ```python
     @property
     def matchbook_events_bronze_dir(self) -> Path:
         """Bronze partition root for Matchbook events REST API ingestion."""
         return self.bronze_dir / "matchbook_events"
     ```
  3. Append to `.env.example`:
     ```
     # --- Matchbook Events REST API (bronze ingest) ---
     # Credentials from the sports-gaming-engine .env. Required for matchbook_events_ingestion.
     MATCHBOOK_USERNAME=your-matchbook-username
     MATCHBOOK_PASSWORD=your-matchbook-password
     ```
- **Green criterion:** Config tests pass: `PYTHONPATH=src uv run pytest tests/test_config_matchbook.py` (or the extended test file) green. Verify `matchbook_events_bronze_dir` is distinct from `matchbook_bronze_dir`.
- **Guardrails to satisfy:** Do NOT rename or remove `matchbook_redis_host` / `matchbook_redis_port`; do NOT commit real credentials; ruff clean on `config.py`.
- **Self-review checkpoint:** Reviewer confirms: existing `matchbook_redis_host` / `matchbook_redis_port` / `matchbook_bronze_dir` untouched; new fields default to `""` (not a hard error at import time — credentials validated at runtime in `authenticate()`); `matchbook_events_bronze_dir` returns `bronze_dir / "matchbook_events"` not `bronze_dir / "matchbook_odds"`; `.env.example` has placeholder values not real credentials; `matchbook_events_base_url` field present with default `"https://api.matchbook.com"`; ruff clean.

---

### Step S4 — Thin Dagster asset wrapper (`assets/matchbook_events.py`)

- **Goal:** Implement `src/data_platform/assets/matchbook_events.py` — the `matchbook_events_bronze` asset that calls `run_matchbook_events_ingest` and returns a `MaterializeResult`. Tests in `tests/matchbook/test_asset.py`. (S3 must complete first so credentials fields exist in `Settings`.)
- **Spec trace:** Scheduling — "6-hourly schedule fires the asset"; "Manual job launch" / AC9, AC10, AC13, AC14.
- **Red (failing test first):** Create `tests/matchbook/test_asset.py`. Write tests that import `matchbook_events_bronze` from `data_platform.assets.matchbook_events` (absent). Run — fails with `ImportError: cannot import name 'matchbook_events_bronze'`.
- **Implementation outline:**
  1. `from data_platform.matchbook.ingest import run_matchbook_events_ingest, IngestionReport` (and other needed imports).
  2. `@asset(key=AssetKey(["matchbook_events_bronze"]), group_name="bronze", compute_kind="python")` decorator. No `from __future__ import annotations`.
  3. Asset function signature: `def matchbook_events_bronze(context) -> MaterializeResult:` — no resource injection (credentials come from `settings` directly in the thin wrapper).
  4. Body: read `settings.matchbook_username`, `settings.matchbook_password`, `settings.matchbook_events_bronze_dir`, `settings.matchbook_events_base_url` from config; call `run_matchbook_events_ingest(...)`; surface `IngestionReport` metadata via `MaterializeResult`; re-raise if any failures (mirrors ESPN `to_materialize_result` pattern).
  5. Tests in `test_asset.py`: asset key and group correct; `from __future__ import annotations` absent (via `inspect.getsource`); `MaterializeResult` returned on success (mock the ingest function); re-raises on failure.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/matchbook/test_asset.py` passes. Key/group test, no-future-annotations test, success-returns-result test, failure-re-raises test all green.
- **Guardrails to satisfy:** No `from __future__ import annotations`; thin wrapper (no ingest logic in the asset module); `AssetKey(["matchbook_events_bronze"])`; ruff clean; S3 config fields must already exist.
- **Self-review checkpoint:** Reviewer confirms: `from __future__ import annotations` not in source lines (not just not in the docstring — use `inspect.getsource`); asset key is `["matchbook_events_bronze"]` (not a deeper path); no ingest logic in the asset file (only calls the engine); tests fail before the module exists (`ImportError`, not attribute errors on missing config); ruff clean; no reward-hacking.

---

### Step S5 — Dagster definitions wiring (`definitions.py`) — LAST STEP

- **Goal:** Register `matchbook_events_bronze` asset, `matchbook_events_ingestion` job, `matchbook_events_schedule` schedule in `definitions.py`. Subtract `matchbook_events_bronze` from `AssetSelection.all()` (via `medallion_job`'s selection subtraction). Run definitions validation. Tests in `tests/test_definitions.py` (extend existing file).
- **Spec trace:** Scheduling — "6-hourly schedule fires the asset"; "Manual job launch" / AC9, AC10 / AC15.
- **Red (failing test first):** Add tests to `tests/test_definitions.py`:
  - `test_matchbook_events_job_registered()` — `defs.get_job_def("matchbook_events_ingestion")` exists; job asset keys = `{"matchbook_events_bronze"}`.
  - `test_matchbook_events_schedule_six_hourly()` — schedule cron `"0 */6 * * *"`, job name `"matchbook_events_ingestion"`.
  - `test_matchbook_events_excluded_from_hello_world()` — assert `"matchbook_events_bronze"` IS in `AssetSelection.all()` resolved keys (i.e. it IS registered) AND is NOT in `medallion_hello_world` asset keys. This two-part assertion is the correct red-first test: before S5 wiring, the first part fails (asset not registered); after S5 with a missing subtraction, the second part fails.
  These fail before the wiring is added.
- **Implementation:**
  1. Import `matchbook_events_bronze` from `assets.matchbook_events`.
  2. Build `matchbook_events_assets = AssetSelection.assets(matchbook_events_bronze)`.
  3. Extend `medallion_job` selection: `AssetSelection.all() - football_assets - espn_assets - matchbook_events_assets`.
  4. Add `matchbook_events_job = define_asset_job(name="matchbook_events_ingestion", selection=matchbook_events_assets, description="...")`.
  5. Add `matchbook_events_schedule = ScheduleDefinition(name="matchbook_events_schedule", job=matchbook_events_job, cron_schedule="0 */6 * * *")`.
  6. Add `matchbook_events_bronze` to `Definitions(assets=[...])`.
  7. Add `matchbook_events_job` to `Definitions(jobs=[...])`.
  8. Add `matchbook_events_schedule` to `Definitions(schedules=[...])`.
- **Green criterion:**
  1. `PYTHONPATH=src uv run pytest tests/test_definitions.py` passes (all three new tests green).
  2. `PYTHONPATH=src DUCKDB_PATH=/tmp/wh.duckdb dagster definitions validate -w workspace.yaml` exits 0.
  3. `uv run pre-commit run --all-files` clean.
- **Guardrails to satisfy:** `definitions.py` is the last step (after all other steps are complete and tested); `AssetSelection.all()` subtraction updated; no ingest logic in `definitions.py`; ruff clean; `dagster definitions validate` exits 0 (NOT merely `import defs`).
- **Self-review checkpoint:** Reviewer confirms: `matchbook_events_bronze` does NOT appear in `medallion_hello_world` asset keys; `matchbook_events_ingestion` job contains only `matchbook_events_bronze`; cron is `"0 */6 * * *"`; `dagster definitions validate -w workspace.yaml` exits 0 (reviewer runs this); definitions tests genuinely fail before the wiring is present; no reward-hacking (no `@pytest.mark.skip`, no permissive `AssetSelection.all()` without subtraction).

---

## 7. Sequencing & dependencies

```
S0 (convention — docs gate)
  └─▶ S1 (contracts: Pydantic + Pandera schemas)
        └─▶ S2 (ingest engine — imports from models/)
              └─▶ S3 (config fields + dir property)
                    └─▶ S4 (asset wrapper — reads from settings)
                          └─▶ S5 (definitions wiring — ALWAYS LAST)
```

Rationale for ordering:
- **S0 before S1:** The auth convention must be established (committed) before any
  auth code is written, per the hard gate.
- **S1 before S2:** The ingest engine imports `MatchbookEventRecord` and
  `matchbook_events_bronze_schema` — these must exist first.
- **S2 before S3:** Config fields can be added independently, but S4 (asset wrapper)
  reads `settings.matchbook_username`, `settings.matchbook_password`,
  `settings.matchbook_events_bronze_dir`, and `settings.matchbook_events_base_url`.
  S3 (config) must precede S4 (asset wrapper) so the config fields exist when the
  asset module is imported and tested. Placing S3 here keeps the chain linear and
  avoids attribute errors at import time.
- **S3 before S4:** The asset wrapper reads settings fields that S3 adds — these
  must exist before the asset module can be imported by S4's tests.
- **S5 always last:** `definitions.py` is the composition root; editing it before all
  other steps are complete and tested would introduce a partially-working code location
  into the repo, breaking `dagster definitions validate`.

---

## 8. Assumptions

- A1 (from spec): Matchbook credentials from the sports-gaming-engine project work against the same API endpoint. No IP allowlisting blocks access.
- A2 (from spec): `per-page=20` is appropriate. `matchbook_throttle_seconds` defaults to `0.0`; can be tuned via env var without a code change.
- A3 (from spec): UTC-aligned `0 */6 * * *` schedule is correct.
- A4 (from spec): Sport-ids 15 (football) and 2 (rugby union) are hardcoded; additional sports require a follow-up spec.
- A5 (from spec): `status=open` filter is correct for production; no historical events needed.
- A6: The `matchbook_throttle_seconds` field added in S3 defaults to `0.0` and is not wired into the ingest engine's fetch loop in this spec. It is declared now to allow tuning via env var later without a code change. If wiring is desired, it is a trivial addition to `run_matchbook_events_ingest`.
- A7: `volume` field may be absent from some event dicts (not all events have liquidity); the Pydantic model declares it `float | None = None`.
- A8: The ingest engine receives `username` and `password` as arguments (not reading `settings` directly) so it is testable without `monkeypatch`. The thin asset wrapper reads from `settings` and passes them down.
- A9: The Matchbook REST base URL is `https://api.matchbook.com`. It is added as a `matchbook_events_base_url: str` config field in S3 (defaults to the production URL) so it can be overridden in tests without `monkeypatch` on the settings object. Note: this is a minor addition to the S4 scope — it is simpler and more testable than hardcoding the URL in the engine.
- A10: The `conftest.py` in `tests/matchbook/` should patch `data_platform.matchbook.ingest.get_tracer` (the ingest module's OTel target), mirroring `tests/espn/conftest.py`'s approach.
- A11: The batch-timestamp format is `%Y%m%dT%H%M%SZ` (e.g. `20260629T120000Z`), consistent with the spec example.
- A12: `volume` in the Matchbook API is a floating-point field; may be absent for events without matched liquidity. `nullable=True` in the Pandera schema.

---

## 9. Open questions

**BLOCKER — Conv-audit gap (S0):** The auth convention (session-token auth pattern)
must be approved and committed before implementation begins. The proposed rule text
is in §3 above. Awaiting approval.

**Assumption A9 (non-blocking, best-guess: add `matchbook_events_base_url`):** Should
the Matchbook REST API base URL be a `config.py` field (for testability + env
override) or hardcoded in the engine? Best guess: add it as
`matchbook_events_base_url: str = "https://api.matchbook.com"` alongside the
credentials in S3. This is a minor addition to the stated S3 scope.

**Q1 from spec (non-blocking, best-guess: add `matchbook_throttle_seconds`):**
`matchbook_throttle_seconds` is added as a `float = 0.0` field in S3 but NOT wired
into the engine's fetch loop in this plan. The field is declared for future use.

**Q2 from spec (non-blocking, resolved in spec):** Zero events for all sports →
run succeeds with log. Captured in E8 / the "zero-all-sports succeeds" unit test.

**Q3 from spec (non-blocking, resolved in spec):** `per-page=20` is hardcoded (not
config-driven) in this plan. `matchbook_per_page` can be added later if needed.

---

## 10. Traceability

Every spec scenario and acceptance criterion maps to at least one step and one test unit.

| Spec scenario / AC | Unit(s) | Step(s) | Guardrail(s) |
|--------------------|---------|---------|--------------|
| Auth — "Successful session token acquisition" | `authenticate()` returns token | S2 | pytest, ruff |
| Auth — "Missing credentials" / AC6, E2 | Missing credentials raises before HTTP | S2, S3 | pytest, config |
| Auth — "Auth endpoint returns error or no token" / AC16, E1, E3 | `authenticate()` raises on non-2xx; ValueError on missing token | S2 | pytest, ruff |
| Event fetching — "Paginated fetch…" | `fetch_events()` pagination loop | S2 | pytest |
| Event fetching — "Empty result for a sport" / E7 | Zero events: no Parquet, continues | S2 | pytest |
| Event fetching — "Both sports fetched per run" | `run_matchbook_events_ingest` loops sports | S2 | pytest |
| Record validation — "Well-formed events pass" / AC4 | `MatchbookEventRecord` validates | S1 | Pydantic |
| Record validation — "Individual malformed record skipped" / AC7, E5 | Skip-and-count, re-raise at end | S2 | pytest |
| Record validation — "Frame fails Pandera schema" / E6 | `matchbook_events_bronze_schema` rejects | S1 | Pandera |
| Parquet write — "Successful atomic write" / AC1, AC2, AC8 | Atomic write to correct partitioned path | S2 | pytest, temp+rename |
| Parquet write — "Output path created on first run" | `mkdir(parents=True, exist_ok=True)` | S2 | pytest |
| Parquet write — "`raw_event` column…" / AC3 | `raw_event` round-trip with `markets` | S2 | pytest |
| Scheduling — "6-hourly schedule fires the asset" / AC10 | `matchbook_events_schedule` cron | S5 | pytest, dagster validate |
| Scheduling — "Manual job launch" / AC10 | `matchbook_events_ingestion` job registered | S5 | pytest, dagster validate |
| AC1 | Football Parquet under `matchbook_events/football/...` | S2 | artifact assertion |
| AC2 | Rugby union Parquet under `matchbook_events/rugby_union/...` | S2 | artifact assertion |
| AC3 | `raw_event` round-trips to original dict including `markets` | S2 | pytest |
| AC4 | Structured columns `event_id`, `event_name`, `sport_id`, `status`, `start_utc`, `volume`, `ingested_at`, `raw_event` | S1, S2 | Pydantic, Pandera, pytest |
| AC5 | Replay appends new file; no overwrite | S2 | pytest |
| AC6 | Missing credentials raises before HTTP call | S2, S3 | pytest |
| AC7 | Per-record failure: valid records written, run marked failed | S2 | pytest |
| AC8 | No partial Parquet on write failure | S2 | pytest (temp+rename) |
| AC9 | `matchbook_events_bronze` NOT in `medallion_hello_world` | S5 | pytest, dagster validate |
| AC10 | `matchbook_events_ingestion` job + `matchbook_events_schedule` registered | S5 | pytest, dagster validate |
| AC11 | `MATCHBOOK_USERNAME` + `MATCHBOOK_PASSWORD` in `config.py` + `.env.example` | S3 | pytest, code review |
| A9 / `matchbook_events_base_url` | Config field with default URL, used by `authenticate` and `fetch_events` | S3 | pytest |
| A6 / `matchbook_throttle_seconds` | Declared in `config.py` for future use (not wired in this plan — intentional; see Open Question Q1) | S3 | — (no test; documented as future work) |
| AC12 | `matchbook_events_bronze_dir` property distinct from `matchbook_bronze_dir` | S3 | pytest |
| AC13 | No `from __future__ import annotations` in `assets/matchbook_events.py` | S4 | pytest (inspect) |
| AC14 | Pure-Python engine in `matchbook/ingest.py`; thin wrapper in `assets/matchbook_events.py`; unit tests under `tests/matchbook/` | S2, S4 | pytest, architecture review |
| AC15 | `dagster definitions validate` exits 0 | S5 | dagster validate |
| AC16 | Auth failure raises before Parquet write | S2 | pytest |
| E1 | Auth endpoint unreachable | `authenticate()` raises | S2 | pytest |
| E2 | Missing credentials | raise before HTTP | S2, S3 | pytest |
| E3 | Auth response no `session-token` | `ValueError` raised | S2 | pytest |
| E4 | Events endpoint non-2xx | `fetch_events()` raises | S2 | pytest |
| E5 | Single record fails Pydantic | skip-and-count | S2 | pytest |
| E6 | Frame fails Pandera | raises for that sport | S1, S2 | Pandera |
| E7 | Zero events for a sport | no Parquet, continues | S2 | pytest |
| E8 | Zero events all sports | run succeeds, no Parquet | S2 | pytest |
| E9 | Parquet write fails | atomic write, no partial | S2 | pytest |
| E10 | Same partition already exists | new batch-ts file, no overwrite | S2 | pytest |
| E11 | `sport-id` missing | Pydantic rejects | S1 | Pydantic |
| E12 | `start` absent/unparseable | Pydantic rejects | S1 | Pydantic |
| E13 | `total` absent from API response | single page, log warning | S2 | pytest |
