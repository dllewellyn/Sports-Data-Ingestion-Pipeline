---
id: 002
title: ESPN soccer ingestion (bronze fixtures + canonical match/league/season/team population)
slug: espn-ingestion
status: draft
created: 2026-06-28
specification: 002-espn-ingestion-specification.md
user_stories: [espn-data-flow]
---

# ESPN soccer ingestion — implementation plan

## 1. Summary

Build an ESPN soccer ingestion flow that mirrors the football-data.co.uk source one-for-one:
a new `src/data_platform/espn/` package (typed league allowlist registry, a throttled
cache-aware `ConfigurableResource` HTTP client, season-window discovery, a Dagster-free
ingest engine), a bronze Dagster asset that is the only network edge (Pydantic-per-record +
open Pandera `strict=False` frame, per-unit failure isolation, atomic temp-file+rename
Parquet writes, OTel span), and the **first conform layer** that populates the canonical
`silver/canonical/` tables. Bronze writes **one Parquet per league/season** carrying the full
ESPN event payload verbatim, overwriting the unit with the latest scoreboard each run.

Canonical identity is computed **inside dbt** by a shared, provider-agnostic macro
`canonical_match_id(league, season, kickoff_date_utc, home, away)` returning a deterministic
`md5` surrogate over the 5-component natural key. The conform models (`league`, `season`,
`team`, `match`, `espn_match_link`) are full-rebuild `+materialized: table` models keyed on
that surrogate, so re-running yields the **same** `match_id` with updated post-match scores —
idempotent upsert without incremental/merge machinery. Team names resolve against a pre-seeded
`team.similar_names` dbt seed (seed-only; no auto-learn). ESPN gets its own job + a 6-hourly
schedule and is subtracted from `AssetSelection.all()`-based jobs, exactly as `football_assets`
are. The `espn_match_link` table gains the three spec link-provenance columns
(`match_method`/`confidence`/`review_status`), populated truthfully as
`deterministic`/`1.0`/`auto_confirmed`. `ERD.md` is updated in the same commit as the conform
models.

## 2. Skills to use

From Phase-1 skill discovery (project-local `.agents/skills/`, global `~/.claude/`). There is
**no dedicated "create data ingestion pipeline" skill** — but this is not a blocking gap: the
football source (`src/data_platform/football/` + `assets/football_*.py`) is a complete,
tested in-repo template the steps mirror directly, and `implementor` drives the build with
per-task review. `self-learn` after the build can codify any reusable ingestion pattern.

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| Drive this plan to done (task graph, per-task red→green→review→commit) | `implementor` | available |
| Per-step independent self-review (the §6 checkpoints) | fresh `general-purpose` agent / `code-review` | available |
| New ingestion package, bronze asset, contracts, dbt models, resolver macro, seed, wiring | `implementor` (mirrors `football/` template) | available — **no "create-ingestion-pipeline" skill exists; mirror football + implementor** |
| Draft a brand-new governing rule if one is genuinely missing | `create-rule` | available (not needed — see §3) |
| Architecture conformance of the new package/assets/models vs ARCHITECTURE.md | `code-architecture-review` | available (post-build review) |
| Code quality / debt of the change | `analyze-code-quality` | available (post-build review) |
| Security review of the new network edge | `analyze-security` / `security-review` | available (post-build review) |
| Confirm the flow actually runs (daemon/queued run) | `verify` / `run` | available |
| Capture learnings after the build | `self-learn` | available |

## 3. Convention & rule audit (resolved before implementation)

Every artifact type this plan touches has a governing convention that **already exists** — either
a written rule in `CLAUDE.md`/`ARCHITECTURE.md`/`pyproject.toml`, or a clear in-repo pattern to
mirror. The two artifacts with **no direct in-repo precedent** (a dbt macro; a dbt seed) are
nonetheless governed by an unambiguous standard dbt convention and are created *following that
convention this run* in their own atomic commits **before** the steps that depend on them — they
are **not** open gaps and need no new hand-authored rule. **Zero rows are a blocking gap.**

| # | Artifact type | Governing convention | Status |
|---|---------------|----------------------|--------|
| 1 | New Python source sub-package (`espn/`) | `ARCHITECTURE.md` layering + `CLAUDE.md` *Python conventions*; mirror `src/data_platform/football/` (registry, http_client, discovery, season, ingest) | exists |
| 2 | Bronze Dagster asset (network edge) | `CLAUDE.md` *Non-obvious constraints* (no `from __future__`, OTel span, atomic temp+rename, per-unit isolation, asset is the only net edge); mirror `assets/football_main.py` | exists |
| 3 | Pydantic v2 record + open Pandera `strict=False` frame | `CLAUDE.md` *Python conventions* ("validate at boundaries with Pydantic… DataFrame contracts via Pandera"); mirror `models/schemas.py` + `models/validation.py` | exists |
| 4 | New typed config fields (`config.py`) | `CLAUDE.md` "Config comes from `pydantic-settings`, never ad-hoc `os.getenv`"; mirror the `football_*` fields in `config.py` | exists |
| 5 | dbt source for ESPN bronze Parquet | mirror `dbt/data_platform/models/silver/_sources.yml` (`external_location` via `env_var('DATA_DIR')`) | exists |
| 6 | dbt silver staging + canonical conform models + dbt tests | `CLAUDE.md` canonical-tables-are-dbt-models rule; `dbt_project.yml` (`canonical: +materialized: table`); mirror `stg_users.sql`, `_schema.yml` data_tests, `tests/assert_*.sql` custom tests, the `football_data_match_link` natural-key test | exists |
| 7 | Deterministic match-id **dbt macro** (`macros/`) | Standard dbt macro convention (`{% macro %}` in `macro-paths: ["macros"]`, already configured). No in-repo macro precedent and **no `dbt_utils` installed/no `packages.yml`** → macro is hand-written over DuckDB `md5()`; created this run in S2 before any model uses it | exists (std dbt) — **created this run, S2** |
| 8 | dbt **seed** for `team.similar_names` (`seeds/`) | Standard dbt seed convention (`seed-paths: ["seeds"]` already configured; CSV + `seeds:` config in `dbt_project.yml`). **No seed exists anywhere yet** → first seed, created this run in S6 following the standard pattern, before the conform model that reads it | exists (std dbt) — **created this run, S6** |
| 9 | pytest unit tests | `pyproject.toml` `[tool.pytest.ini_options]` (`pythonpath=["src"]`, `testpaths=["tests"]`), `pytest>=9.1.1` in `[dependency-groups]`; harness + layout **already established** (`tests/`, `tests/football/`, `tests/conftest.py`); mirror `tests/football/` | exists |
| 10 | Dagster job + 6-hourly `ScheduleDefinition`; subtract ESPN from `all()`-jobs | `CLAUDE.md` "give heavy/standalone sources their own job and exclude from `all()`-based jobs"; mirror `definitions.py` `football_assets`/`football_backfill_job`; daemon/queued-run green criterion (`CLAUDE.md` same-`workspace.yaml` rule) | exists |
| 11 | `ERD.md` update (link-provenance columns) | `CLAUDE.md` "ERD.md is living documentation — update in the same commit as canonical-model changes" | exists |

**Gate result:** no implementation step depends on a row marked gap. The macro (S2) and the
seed (S6) are created *before* their dependent conform steps; both follow a single
unambiguous dbt-standard convention, so neither requires a new hand-authored rule or user
approval. (`create-rule` is on standby only if review later decides the md5-surrogate macro
deserves a written CLAUDE.md rule — see Open Questions Q-plan-1.)

## 4. Testable units (BDD → tests)

| Unit | Spec trace | Test facility | Failing-first assertion |
|------|------------|---------------|-------------------------|
| `espn/registry.py` typed league allowlist (slugs e.g. `eng.1`) | Scenario "League allowlist drives discovery" | pytest | Importing the registry / asserting only allowlisted slugs are emitted fails until the registry exists |
| `espn/season.py` season-window selection from ESPN `startDate`/`endDate` overlapping today±horizon | Scenario "Season windows resolved from ESPN, not guessed"; E8 | pytest | Feeding seasons + a run date expects the overlapping window(s); fails (no function) then passes; a guessed/hard-coded range fails the Aug→May overlap case |
| `EspnEventRecord` Pydantic core (event id, kickoff date, home+away competitor, status) | Scenario "Full payload preserved"; E3 | Pydantic | A record missing event id / a competitor expects `ValidationError`; a valid record coerces — fails before the model exists |
| `espn_bronze_schema` open Pandera frame (core columns enforced, extras ride along) | Scenario "Full ESPN event payload preserved verbatim"; AC1 | Pandera | A frame missing a core column raises; a wide frame with extra ESPN columns passes — fails before the schema exists |
| Ingest engine writes **one** Parquet per league/season at deterministic path | Scenario "One bronze Parquet per fetched unit"; AC1 | pytest + artifact | After ingest, exactly one Parquet at `bronze/espn/<league>/<season>.parquet`; fails before engine exists |
| Bronze unit overwritten with latest scoreboard (post-match payload replaces pre-match) | Scenario "Post-match re-fetch captures the richer payload"; AC2 | pytest + artifact | Run1 (SCHEDULED) then Run2 (FINAL+scores) over same unit → Parquet now carries scores/completed; fails if append-only or skipped |
| Per-unit failure isolation: fetch error / zero-event window writes **no** Parquet, run re-raises | E1, E2; AC11 | pytest | A failing unit leaves no Parquet, other units still land, the engine re-raises at end; zero-event window writes nothing — fails before isolation logic exists |
| `canonical_match_id` dbt macro = `md5` over (league, season, kickoff_date_utc, home, away) | Scenario "Match identity computed by a provider-agnostic resolver"; AC6 | dbt test | A dbt test computing the macro on fixed literals expects a fixed deterministic id and that raw `espn_event_id` is **not** an input; fails before the macro exists |
| Date component = `cast(kickoff_time as date)` in UTC; intra-day time revision keeps `match_id` | Scenario "Date component uses the UTC calendar date"; AC6b; E7 | dbt test | A dbt test feeding two kickoff timestamps on the same UTC day expects one identical `match_id`; a different day → different id |
| `match` conform: pre-match fixture creates `league`/`season`/`team`/`match` rows; scores null | Scenario "Pre-match fixture creates canonical rows"; AC3 | dbt test (`dbt build`) | `dbt build --select silver.match` and the canonical not_null/unique tests fail until the conform SQL exists and populates rows with `ht_score`/`ft_score` null, `favourite_team_id` null |
| Idempotent upsert: re-run fills scores on the **same** `match_id`; no dup match/link | Scenario "Post-match re-run fills results on the SAME match"; AC4; E4, E9 | dbt test (custom) + artifact | A custom dbt test asserting match/link counts are stable across two builds and `ft_score` populated post-match; fails if a second match_id or duplicate link appears |
| `espn_match_link` one row per event with provenance `deterministic`/`1.0`/`auto_confirmed` | Scenario "Pre-match fixture…link"; AC5 | dbt test | `_schema.yml` data_tests (unique link_id; accepted_values on `match_method`/`review_status`) + a not_null on `confidence`; fails before the columns/conform exist |
| Seeded alias resolves to existing `team_id`; unseen name → new team; no auto-learn | Scenarios "Team alias resolution (seeded)"; AC7, AC7b; E5, E5b | dbt test | A seed row ("Wolves"→"Wolverhampton Wanderers") + a fixture naming "Wolves" expects one `team_id`; an unseeded name yields a distinct team; a test asserts the seed table is unchanged by conform |
| **AC8** second-provider-shaped fixture through the **same** macro → same `match_id` | Scenario "A second provider…resolves to the same match_id"; AC8 | dbt test (custom) | A custom dbt test feeds non-ESPN literal `(league, season, date, home, away)` through `canonical_match_id` and asserts equality with the ESPN-derived `match.match_id`; fails if the macro has any ESPN-specific input |
| Canonical FK shape: `match.season_id`→season, season reachable via `season.league_id` | Scenario "Pre-match fixture creates canonical rows"; AC3 | dbt test (relationships) | `relationships` tests on the FKs fail until conform wires them |
| 6-hourly schedule (`0 */6 * * *`) runs the ESPN job | Scenario "The flow runs every 6 hours"; AC9 | pytest (defs) + daemon/queued run | A defs test asserts the schedule exists with cron `0 */6 * * *` targeting the ESPN job; the orchestration green criterion is an actual queued run |
| ESPN assets excluded from `all()`-based jobs; run only via dedicated job | Scenario "ESPN is its own job, excluded from all()-based jobs"; AC10 | pytest (defs) | Mirror `test_definitions_*`: assert `medallion_hello_world` selection ∩ ESPN keys is empty and the ESPN job selects exactly the ESPN assets |
| `BronzeAwareTranslator` maps the ESPN dbt source to the ESPN bronze `AssetKey` | §8 (lineage edge) | pytest (defs) + manifest | Assert the silver staging model's upstream includes the ESPN bronze asset key; fails if the source isn't mapped |

## 5. Guardrail register

| Guardrail | How verified in place | Covered by step |
|-----------|------------------------|-----------------|
| ruff check + format (pre-commit) | `uv run pre-commit run --all-files` clean; `uv run ruff check src` / `ruff format src` | S0 + every step |
| pre-commit hook installed | `uv run pre-commit install` (once) then hook runs on commit | S0 |
| dbt tests run via `dbt build` | `_schema.yml` data_tests + custom `tests/assert_*.sql` present; `dbt parse` then `dbt build --select <model>` green | S2–S8 |
| Pydantic per record + Pandera per frame at the boundary | bad ESPN record raises `ValidationError`; frame missing a core column raises | S3 |
| Idempotency / re-run safety | bronze unit overwritten with latest scoreboard; canonical `+materialized: table` full-rebuild keyed on the deterministic surrogate → stable counts + updated scores across two runs (custom dbt test + two-build artifact check) | S4 (bronze) + S7 (canonical) |
| OTel span emitted at the network edge | `get_tracer().start_as_current_span("ingest.espn")` wraps the fetch (mirror `football/ingest.py`); conftest no-op tracer in tests | S4 |
| Single-writer DuckDB | conform is **dbt models only**; Python reads bronze **Parquet files**; no second process opens `warehouse.duckdb` read-write | S5–S8 |
| Prefixed dbt asset keys (RESOLVED FROM MANIFEST) | the canonical Dagster `AssetKey` is **`["silver","<model>"]`** (e.g. `["silver","match"]`, `["silver","espn_match_link"]`) — NOT `["silver","canonical","match"]` (the spec's guess); verified via `dbt_models.keys`. `BronzeAwareTranslator` + any `deps=[...]` use the exact key | S5, S8, S9 |
| No `from __future__ import annotations` in asset modules | the new `assets/espn.py` omits it (Dagster introspects annotations) | S4 |
| `pathlib.Path` for paths; context managers for spans | settings expose `Path`; spans via `with` | S1, S4 |
| Importing `definitions` reads the dbt manifest → `dbt parse` first | every step touching models re-runs `dbt parse`; defs/pytest gated on manifest (mirror `test_backfill_idempotency.py` skip-on-missing-manifest) | S2, S5–S9 |
| Orchestration green = daemon/**queued** run | `dagster definitions validate -w workspace.yaml`, then launch the ESPN job as a **queued** run via the daemon and confirm it leaves PENDING (not just `definitions validate`) | S9 |
| ERD.md updated in the same commit as conform/link changes | `ERD.md` `espn_match_link` table + provenance columns edited in S8's commit | S8 |

## 6. Implementation steps

### Step S0 — Verify the guardrail baseline (pre-commit + pytest harness)
- **Goal:** confirm the gates that protect every later step are installed and green on a clean tree.
- **Spec trace:** setup — enables S1–S9.
- **Red (failing test first):** run `uv run pre-commit run --all-files` and `PYTHONPATH=src uv run pytest`; if pre-commit isn't installed or the suite doesn't run, that is the red.
- **Implementation:** `uv sync`; `uv run pre-commit install` if needed. No new harness work — `tests/` + `pyproject` `[tool.pytest.ini_options]` already exist (the plan-skill's "no test suite" note is stale for this repo).
- **Green criterion:** `uv run pre-commit run --all-files` clean; `PYTHONPATH=src uv run pytest` collects + passes the existing suite.
- **Guardrails to satisfy:** ruff, pre-commit installed, pytest harness.
- **Self-review checkpoint:** reviewer confirms gates run and are green on `main` before any feature code; no gate weakened.

### Step S1 — `espn/` package leaf modules: registry, config fields, season-window selection
- **Goal:** typed league allowlist (`registry.py`), `pydantic-settings` config fields, and pure season-window selection (`season.py`).
- **Spec trace:** Scenarios "League allowlist drives discovery", "Season windows resolved from ESPN"; A2, A3; AC9 enabling; E8.
- **Red:** `tests/espn/test_registry.py` asserts the allowlist exposes the agreed soccer slugs and nothing off-list; `tests/espn/test_season.py` asserts windows overlapping `today±horizon` are selected from given `(year,startDate,endDate)` triples (incl. an Aug→May split, E8). Both fail (modules absent).
- **Implementation:** `espn/registry.py` frozen-dataclass allowlist (mirror `football/registry.py`, no network); add `espn_*` fields to `config.py` (base URLs for `sports.core.api.espn.com` + `site.api.espn.com`, allowlist default, fetch-horizon days, throttle 0.1s, timeout, max_retries, browser `User-Agent`); `espn/season.py` pure window-overlap selection taking the run date explicitly (no hidden clock, mirror `football/season.py`).
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/espn/test_registry.py tests/espn/test_season.py` passes; `ruff check src` clean.
- **Guardrails:** `pydantic-settings` config (no `os.getenv`); `pathlib.Path`; ruff.
- **Self-review checkpoint:** reviewer confirms allowlist is a typed in-repo constant (not data → dataclass not Pydantic, per the football precedent), config fields are typed `pydantic-settings`, season selection uses ESPN's own dates (no hard-coded rollover), tests can fail.

### Step S2 — `canonical_match_id` dbt macro (the provider-agnostic resolver) — **N1**
- **Goal:** one shared dbt macro computing a deterministic surrogate `match_id` over the 5-component natural key, inside dbt (single-writer-safe). Created **before** any model uses it.
- **Spec trace:** Scenarios "Match identity computed by a provider-agnostic resolver", "Date component uses the UTC calendar date"; AC6, AC6b, AC8.
- **Red:** `dbt/data_platform/tests/assert_canonical_match_id_deterministic.sql` computes the macro on fixed literals and asserts a fixed expected `md5` value AND that two same-UTC-day timestamps yield one id while a different day differs; `dbt build --select test_name` fails (macro undefined). **The expected hash must be computed from the macro's EXACT `concat_ws` separator, argument ordering, and text/date coercion** (i.e. derive it by hand from the same `md5(concat_ws('|', …))` expression the macro emits) so "green" can only be reached by implementing the macro correctly — never by tweaking the expected value to match whatever the macro happens to produce.
- **Implementation:** `macros/canonical_match_id.sql` — `{% macro canonical_match_id(league, season, kickoff_date_utc, home, away) %}` returning `md5(concat_ws('|', <args coerced to text, date as cast(... as date)>))`. Hand-written (no `dbt_utils` in the project); the date arg is documented to be passed as `cast(kickoff_time as date)`. Raw provider event ids are **not** parameters.
- **Green criterion:** `cd dbt/data_platform && uv run --project ../.. dbt parse --profiles-dir .` then `dbt build --select test_type:singular` (the new test) green.
- **Guardrails:** single-writer DuckDB (identity computed in dbt); dbt test present.
- **Self-review checkpoint:** reviewer confirms the macro has **no** ESPN-specific argument, date is UTC-calendar via `cast(... as date)`, the test pins a deterministic value and *can* fail, and the macro is committed before S5/S7 use it.

### Step S3 — ESPN bronze contracts: `EspnEventRecord` (Pydantic) + `espn_bronze_schema` (open Pandera)
- **Goal:** boundary validation — mandatory event core per record, wide payload rides along on the frame.
- **Spec trace:** Scenarios "Full ESPN event payload preserved verbatim", "invalid event dropped"; AC1; E3.
- **Red:** `tests/espn/test_contracts.py` — a record missing event id / a competitor expects `ValidationError`; a frame missing a core column raises; a wide frame with extra ESPN columns passes. Fails (contracts absent).
- **Implementation:** add `EspnEventRecord` to `models/schemas.py` (`ConfigDict(extra="ignore")`, validators rejecting missing core: event id, kickoff date, home+away competitor team id/name, status name) and `espn_bronze_schema` to `models/validation.py` (`strict=False`, `coerce=True`, only core columns declared) — mirror the football pair.
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/espn/test_contracts.py` passes; ruff clean.
- **Guardrails:** Pydantic per record + open Pandera per frame.
- **Self-review checkpoint:** reviewer confirms core is enforced, extras genuinely ride along (frame stays open), no fabricated defaults, tests can fail.

### Step S4 — ESPN ingest engine + bronze Dagster asset (the network edge)
- **Goal:** discovery (scoreboard fetch) → decode JSON events → row validation → frame validation → **one** Parquet per league/season at a deterministic path, inside an OTel span, with per-unit failure isolation + atomic temp+rename; the unit is overwritten with the latest scoreboard each run.
- **Spec trace:** Scenarios "One bronze Parquet per fetched unit", "Post-match re-fetch captures the richer payload"; AC1, AC2, AC11; E1, E2, E11.
- **Red:** `tests/espn/test_ingest.py` (Dagster-free, fake fetcher mirroring `tests/football/`): one league/season → exactly one Parquet at `bronze/espn/<league>/<season>.parquet`; Run1 SCHEDULED then Run2 FINAL+scores → Parquet now carries scores (overwrite); a fetch error / zero-event window writes **no** Parquet and the run re-raises; other units still land. `tests/espn/test_espn_asset.py` asserts the asset wiring. All fail (engine/asset absent).
- **Implementation:** `espn/http_client.py` (`ThrottledHttpClient` `ConfigurableResource` + testable fetcher with injected clock/sleep, mirror football); `espn/discovery.py` (resolve seasons via `/seasons`, build scoreboard URLs); `espn/ingest.py` (Dagster-free engine: per-unit isolation, atomic temp+rename, OTel span `ingest.espn`, re-raise at end on failures); `assets/espn.py` (`@asset key=AssetKey(["espn_bronze"])`, `group_name="bronze"`, **no `from __future__`**, builds fetcher, calls engine, returns `MaterializeResult`). **OTel test isolation (F1):** the autouse `_silence_otel` fixture in `tests/conftest.py` only patches `data_platform.football.ingest.get_tracer`, so ESPN tests would hit a real tracer/exporter. Either extend that fixture to ALSO `monkeypatch.setattr("data_platform.espn.ingest.get_tracer", lambda *a, **k: _NoOpTracer())`, or add a `tests/espn/conftest.py` with an equivalent autouse no-op-tracer fixture targeting the ESPN module. (Tests that assert on spans override it with their own monkeypatch, as the football tests do.)
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/espn/` passes (and never opens a real OTLP exporter); ruff clean.
- **Guardrails:** OTel span; atomic temp+rename; per-unit isolation + re-raise; no `from __future__`; `pathlib.Path`; idempotent overwrite of the unit; OTel no-op test fixture covers the ESPN module.
- **Self-review checkpoint:** reviewer confirms the asset is the only net edge, no partial Parquet on failure, no silent fallback (raises), span emitted, overwrite (not append) proven by the two-run test, **the no-op tracer fixture patches `data_platform.espn.ingest.get_tracer` (no real exporter in the suite)**, tests can fail.

### Step S5 — ESPN dbt source + silver staging model (flatten bronze events)
- **Goal:** register the ESPN bronze Parquet as a dbt external source and stage it into typed rows (one row per event with league, season + dates, home/away names, kickoff timestamp, status, scores).
- **Spec trace:** enables AC3–AC8 (conform reads staging); Scenario "Full payload preserved" (staging selects from faithful bronze).
- **Red:** `dbt build --select stg_espn_events` fails (model + source absent); a `_schema.yml` not_null on `espn_event_id` is red until staging exists.
- **Implementation:** add an `espn` source (or `bronze.espn_*`) entry mirroring `_sources.yml` (`external_location` glob over `{{ env_var('DATA_DIR') }}/bronze/espn/**/*.parquet`); `models/silver/stg_espn_events.sql` flattening the event payload; map the source in `BronzeAwareTranslator` to `AssetKey(["espn_bronze"])` so the lineage edge forms (mirror the `users`→`raw_users` mapping). Re-`dbt parse`.
- **Green criterion:** `dbt parse` then `dbt build --select stg_espn_events` green (requires a bronze Parquet present — run S4's asset or a fixture first, per the documented "dbt not green from clean checkout").
- **Guardrails:** single-writer (read Parquet as external source); prefixed asset key resolved from manifest; translator mapping; `dbt parse` before defs import.
- **Self-review checkpoint:** reviewer confirms the source maps to the real bronze key, staging types are correct, `kickoff_time` is a timestamp (so S2's `cast(... as date)` works), no second writer.

### Step S6 — `team.similar_names` dbt seed (alias resolution input) — first seed in the project
- **Goal:** a CSV seed pre-seeding canonical teams + aliases for the allowlisted leagues; seed-only (no auto-learn).
- **Spec trace:** Scenarios "Team alias resolution (seeded)"; AC7, AC7b; D2; E5, E5b.
- **Red:** `dbt build --select <seed>` fails (no `seeds/` content; first seed); a conform test resolving "Wolves" is red until the seed + conform exist.
- **Implementation:** `dbt/data_platform/seeds/team_aliases.csv` (canonical team name + alias rows for allowlisted leagues) and a `seeds:` config block in `dbt_project.yml` typing the columns; `dbt seed`/`dbt build` loads it. (First seed — follows the standard dbt seed convention; created before S7 reads it.)
- **Green criterion:** `dbt build --select team_aliases` (the seed) green; the seed relation is queryable.
- **Guardrails:** dbt-owned warehouse (seed loaded by dbt, not a second writer).
- **Self-review checkpoint:** reviewer confirms it's a real seed (not hardcoded SQL literals in a model), columns typed, no auto-learn path introduced.

### Step S7 — Conform models: populate `league`, `season`, `team`, `match` (idempotent, via the macro)
- **Goal:** replace the empty canonical scaffolds with conform SQL that derives entities from `stg_espn_events` + the team seed, assigns `match_id` via the S2 macro, and is a full-rebuild `+materialized: table` keyed on the deterministic surrogate (so re-run = same ids + updated scores).
- **Spec trace:** Scenarios "Pre-match fixture creates canonical rows", "Post-match re-run fills results on the SAME match", "Re-running unchanged is a no-op", "Date component uses UTC calendar date", "Team alias resolution (seeded)", "second provider resolves to same match_id"; AC3, AC4, AC6, AC6b, AC7, AC7b, AC8, AC9-data; E4, E5, E6, E7, E9, E11.
- **Red:** `dbt build --select silver.league silver.season silver.team silver.match` + the canonical not_null/unique tests fail until conform SQL exists; a **custom** `tests/assert_espn_match_idempotent.sql` (match/link counts stable + `ft_score` populated across two builds) is red; the **AC8** custom test (`tests/assert_resolver_provider_agnostic.sql`) is red until conform exists. **AC8 must be load-bearing (F2):** the test feeds the **already-canonicalised** components of an existing `match` row — i.e. it joins `match` to its `season`/`league`/`team` rows and calls `canonical_match_id(league_name, season_name/key, cast(match.kickoff_time as date), home_team_name, away_team_name)` using the SAME call-site shape and resolved canonical values `match.sql` uses, then asserts the result equals that row's `match.match_id`. It must NOT feed arbitrary unrelated literals (which could pass vacuously); the equality has to exercise the exact resolver path a second provider would, against real conform output.
- **Implementation:** rewrite `league.sql` (distinct league from staging slug→name, `is_tournament`), `season.sql` (distinct season with `start_date`/`end_date` from ESPN, `league_id`), `team.sql` (union of seed + staging-derived teams, resolving names via seed `similar_names`, **no** write-back of new spellings), `match.sql` (one row per resolved fixture; `match_id = canonical_match_id(league, season, cast(kickoff_time as date), home, away)`; `season_id`/`home_team_id`/`away_team_id` FKs; `kickoff_time`; `ht_score`/`ft_score` from FINAL events else null; `favourite_team_id` null). Add the two custom tests + relationships/accepted-values data_tests in `_schema.yml`. Keep all `+materialized: table`.
- **Green criterion:** `dbt build --select silver.league+ silver.season+ silver.team+ silver.match+` green incl. the new tests; run the conform twice over a pre-match then post-match bronze fixture and confirm stable `match` count with `ft_score` filled (idempotency artifact check).
- **Guardrails:** single-writer (all dbt); identity via shared macro (no provider id); idempotent via deterministic surrogate + full rebuild; dbt tests green; seed-only team resolution.
- **Self-review checkpoint:** reviewer confirms `match_id` comes from the macro (not the event id), UTC-date component, scores null pre-match and filled post-match on the **same** id, no duplicate rows, no auto-learn write-back, **the AC8 test is load-bearing — it feeds the already-canonicalised components of a real `match` row through `canonical_match_id` using the same call-site shape as `match.sql` and asserts equality with that row's `match_id` (not arbitrary literals that could pass vacuously)**, tests can fail.

### Step S8 — `espn_match_link` conform + link-provenance columns + ERD.md (same commit) — **N2**
- **Goal:** one link row per ESPN event → its canonical `match_id`, carrying the three spec provenance columns; document them in `ERD.md` and `_schema.yml` in the same commit.
- **Spec trace:** Scenario "Pre-match fixture creates canonical rows (…link)"; AC5; D-linkage-seam; E4.
- **Red:** `dbt build --select silver.espn_match_link` + `_schema.yml` data_tests (unique `link_id`; `accepted_values` `match_method ∈ {deterministic}`, `review_status ∈ {auto_confirmed}`; not_null `confidence`) fail until the model is rewritten; a test asserting exactly one link per `espn_event_id` (no dup on re-run) is red.
- **Implementation:** rewrite `espn_match_link.sql` to select `link_id` (deterministic surrogate of `espn_event_id`), `match_id` (from `match` via the same natural key), `espn_event_id`, and the **spec** provenance columns — `match_method = 'deterministic'`, `confidence = cast(1.0 as double)` (**N2: `double`**), `review_status = 'auto_confirmed'`. Add the three columns to `_schema.yml` with data_tests. Update `ERD.md`: add `match_method` (VARCHAR), `confidence` (**DOUBLE**), `review_status` (VARCHAR) to the `ESPN_MATCH_LINK` mermaid block and its attribute table, in the **same commit**.
- **Green criterion:** `dbt build --select silver.espn_match_link` green incl. the accepted_values/not_null tests; `ERD.md` diff present in the commit.
- **Guardrails:** single-writer; dbt tests; ERD.md living-doc rule (same commit); truthful values (not stubs).
- **Self-review checkpoint:** reviewer confirms the columns are the spec's `match_method`/`confidence`/`review_status` with values `deterministic`/`1.0`/`auto_confirmed` (NOT ETL run_id/timestamp), `confidence` typed `double`, one link per event, ERD.md updated in the same commit.

### Step S9 — Orchestration wiring: ESPN end-to-end job + 6-hourly schedule, excluded from all()-jobs
- **Goal:** register the ESPN bronze asset + the ESPN dbt models, add an **end-to-end** `espn_job` (bronze → stg → conform → link) and a 6-hourly `ScheduleDefinition`, and subtract ESPN assets from `AssetSelection.all()`-based jobs (mirror `football_assets`).
- **Decision (Q-plan-2 resolved — Option A):** the spec §4 internal order explicitly includes the conform step, so the 6-hourly `espn_job` runs **end-to-end**: the ESPN bronze asset PLUS the ESPN dbt models (`stg_espn_events`, the conform `league`/`season`/`team`/`match`, and `espn_match_link`). The selection therefore includes those dbt model keys, using the **verified** `["silver","<model>"]` keys: `["silver","stg_espn_events"]`, `["silver","league"]`, `["silver","season"]`, `["silver","team"]`, `["silver","match"]`, `["silver","espn_match_link"]`. (Because the canonical models are shared singletons, the conform must be safe to run from this job; bronze for non-ESPN sources is excluded — see the note in Sequencing.)
- **Spec trace:** Scenarios "The flow runs every 6 hours", "ESPN is its own job, excluded from all()-based jobs"; §4 internal order (conform in-job); AC9, AC10.
- **Red:** extend `tests/test_definitions*` (mirror `test_definitions_registers_football_assets...`): assert the ESPN asset key + resource registered, `espn_job` selects the ESPN **bronze + dbt model** keys (end-to-end), the 6-hourly schedule (`0 */6 * * *`) targets it, and `medallion_hello_world` selection ∩ ESPN bronze key is empty. Red until `definitions.py` is wired.
- **Implementation:** in `definitions.py` import the ESPN asset + resource; build `espn_assets = AssetSelection.assets(espn_bronze) | AssetSelection.keys(["silver","stg_espn_events"], ["silver","league"], ["silver","season"], ["silver","team"], ["silver","match"], ["silver","espn_match_link"])` (verified prefixed keys); `medallion_job` selection becomes `AssetSelection.all() - football_assets - espn_assets`; add `espn_job = define_asset_job(name="espn_ingestion", selection=espn_assets)` and `espn_schedule = ScheduleDefinition(cron_schedule="0 */6 * * *", job=espn_job)`; register the ESPN HTTP resource. Re-`dbt parse`.
- **Green criterion:** `PYTHONPATH=src ... uv run pytest tests/test_definitions*` passes; `dagster definitions validate -w workspace.yaml` clean; **then launch `espn_job` as a queued run via the daemon** and confirm it enqueues/launches without `DagsterCodeLocationNotFoundError` (the documented queued-run-only failure mode) — `definitions validate` alone is NOT sufficient.
- **Guardrails:** ESPN excluded from `all()`-jobs; daemon/queued-run green criterion; prefixed asset keys **resolved from the manifest** (`["silver","<model>"]`); `dbt parse` before import.
- **Self-review checkpoint:** reviewer confirms `espn_job` is end-to-end (bronze + the ESPN dbt models) using the verified `["silver","<model>"]` keys, ESPN is subtracted from the hello-world job AND its daily schedule, the schedule cron is `0 */6 * * *`, the green check was an actual queued run (not just validate), the same `workspace.yaml` is loaded by webserver + daemon.

## 7. Sequencing & dependencies

```
S0 (gates)
 ├─ S1 espn/ leaf modules (registry, config, season)         ─┐
 ├─ S2 canonical_match_id macro  ───────────────────────────┐ │
 ├─ S3 ESPN contracts (Pydantic+Pandera)  ──┐               │ │
 │                                          ▼               │ │
 └─ S4 ingest engine + bronze asset (needs S1,S3) ──┐       │ │
                                                     ▼       │ │
        S5 dbt source + stg_espn_events (needs bronze Parquet from S4)
                                                     │       │ │
        S6 team_aliases seed (independent dbt) ──────┤       │ │
                                                     ▼       ▼ │
        S7 conform league/season/team/match (needs S5,S6,S2) │
                                                     ▼         │
        S8 espn_match_link + provenance + ERD.md (needs S7) ──┘
                                                     ▼
        S9 orchestration job + 6h schedule (needs S4 asset + S5–S8 models)
```

Edges driven by repo gotchas:
- **bronze → silver → canonical** — S5 can only `dbt build` green once S4 has written a bronze Parquet (documented "not green from clean checkout"); use S4's asset output or a fixture.
- **Macro before models** — S2 lands before S5/S7 use `canonical_match_id`.
- **Seed before conform** — S6 lands before S7 reads `team_aliases`.
- **Derive identity inside dbt, never a 2nd writer** — all of S2/S5–S8 are dbt; Python only reads bronze Parquet.
- **Prefixed asset keys from the manifest** — `["silver","<model>"]` (verified), used by `BronzeAwareTranslator` (S5) and any `deps=[...]`.
- **`dbt parse` before importing `definitions`** — re-run after every model change feeding S9's defs tests.

## 8. Assumptions

- **A-plan-1** — The league allowlist membership is agreed at build time (spec A2); the plan governs behaviour, not the exact slug list. S1 ships a sensible default (e.g. `eng.1`, `esp.1`, `uefa.champions`) editable in the registry.
- **A-plan-2** — `kickoff_time` is stored as a UTC timestamp in `match`, so the resolver's `cast(kickoff_time as date)` is an unambiguous UTC calendar date (spec AC6b). ESPN `date` is ISO-8601 with offset → normalised to UTC on staging (S5).
- **A-plan-3** — Idempotency is achieved by **full-rebuild `+materialized: table`** conform models over a deterministic surrogate key (no dbt incremental/merge), and by **overwriting** each bronze league/season unit with the latest scoreboard each run. This is the simplest mechanism that satisfies "same match_id, updated scores" (KISS).
- **A-plan-4** — `link_id` is a deterministic surrogate of `espn_event_id` (so re-runs don't duplicate links), computed in dbt.
- **A-plan-5** — `team_id`/`league_id`/`season_id` are deterministic surrogates of their natural keys (name / slug / league+label) so the conform full-rebuild is stable across runs.
- **A-plan-6** — A small bronze fixture (a captured scoreboard payload) is used to make S5–S8 `dbt build` green in tests/CI without hitting the live API.

## 9. Open questions

- **Q-plan-1 (deferred — CLAUDE.md is approval-gated, OFF-LIMITS for the build).** Writing the md5-surrogate identity convention into `CLAUDE.md` as a rule ("ALWAYS derive canonical `match_id` via the `canonical_match_id` macro; NEVER mint identity from a provider event id"), and the related correction of CLAUDE.md's loose "dbt asset keys are prefixed by their model subfolder" wording → "prefixed by the **schema** folder, not deeper subfolders" (the canonical Dagster key is `["silver","<model>"]`, NOT `["silver","canonical","<model>"]`), are **both deferred to the post-build `self-learn`** for explicit user approval. **The implementor MUST NOT modify `CLAUDE.md` during the build.** This is sufficient: the `canonical_match_id` macro + the load-bearing AC8 test already enforce the identity authority technically, and S5/S8/S9 already use the verified key regardless of the doc wording.
- No blockers remain. The spec's Q1/Q2/Q3 are resolved/accepted; this plan's gaps (macro, seed) are closed by standard-dbt-convention steps before their dependents. **Q-plan-2 is RESOLVED (Option A)** — recorded as a decision in S9: the 6-hourly `espn_job` runs end-to-end (bronze + the ESPN dbt models), per the spec §4 internal order.

## 10. Traceability

| Spec scenario / AC | Unit(s) | Step(s) | Guardrail(s) |
|--------------------|---------|---------|--------------|
| League allowlist drives discovery | registry allowlist | S1 | pytest, ruff |
| Season windows resolved from ESPN / E8 | season-window selection | S1 | pytest, ruff |
| Full payload preserved verbatim / AC1 | Pydantic core + open Pandera frame; one-Parquet-per-unit | S3, S4 | Pydantic, Pandera, artifact |
| One bronze Parquet per fetched unit / AC1 | deterministic-path Parquet write | S4 | artifact, atomic write |
| Post-match re-fetch captures richer payload / AC2 | unit overwrite with latest scoreboard | S4 | idempotency, artifact |
| Pre-match fixture creates canonical rows / AC3 | conform league/season/team/match + FKs | S5, S6, S7 | dbt tests, single-writer |
| Post-match re-run fills results on SAME match / AC4, E4, E9 | deterministic surrogate + full rebuild; custom idempotency test | S7 | dbt test, idempotency |
| Re-running unchanged is a no-op | stable counts custom test | S7 | dbt test |
| Match identity via provider-agnostic resolver / AC6 | `canonical_match_id` macro | S2, S7 | dbt test, single-writer |
| Date component = UTC calendar date / AC6b, E7 | macro `cast(... as date)` UTC | S2, S5, S7 | dbt test |
| Team alias resolution seeded / AC7, AC7b, E5, E5b | team seed + seed-only resolution | S6, S7 | dbt test |
| Second provider → same match_id / AC8 | custom resolver-provider-agnostic test | S7 | dbt test |
| Each event one link w/ provenance / AC5 | `espn_match_link` + match_method/confidence/review_status | S8 | dbt test, ERD.md |
| The flow runs every 6 hours / AC9 | 6-hourly schedule | S9 | defs test, queued run |
| ESPN excluded from all()-jobs / AC10 | `all() - football - espn` | S9 | defs test |
| Robustness: failure isolation, zero-event window / AC11, E1, E2, E11 | per-unit isolation + re-raise; status handling no fabricated scores | S4, S7 | pytest, artifact |
| Lineage edge (bronze→silver) / §8 | `BronzeAwareTranslator` ESPN source map | S5, S9 | defs test, manifest |
