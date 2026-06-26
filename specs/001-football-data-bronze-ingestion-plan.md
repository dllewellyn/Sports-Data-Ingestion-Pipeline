---
id: 001
title: football-data.co.uk bronze ingestion (main + extra families) — implementation plan
slug: football-data-bronze-ingestion
status: draft
created: 2026-06-26
specification: 001-football-data-bronze-ingestion-specification.md
user_stories: [2, new-implement-football-main-bronze-ingestion-and-validation-path, new-implement-football-extra-bronze-ingestion-and-validation-path]
---

# football-data.co.uk bronze ingestion (main + extra families) — implementation plan

## 1. Summary

We build a new **bronze data source** for football-data.co.uk as a self-contained
`football` package under the Dagster code location. A shared, deterministic **link
discoverer** (`requests` + regex, driven by a hard-coded **league registry**) emits
family-tagged CSV URLs; a single shared **throttled HTTP client** (0.4 s pacing, within-run
cache for immutable historical files, unconditional re-fetch for current-season files,
artifact-presence skip-existing) retrieves them. Two **family ingestors** decode each file
with its mandated encoding (main = latin-1, extra = utf-8-sig), validate each record against
a small mandatory core (Pydantic v2, skip-and-count invalid rows), validate the assembled
frame against an **open** (`strict=False`) Pandera contract, and land **one Parquet per
source file** under family partitioning (`football_main/<league>/<season>/<div>.parquet`,
`football_extra/<code>.parquet`). A backfill job iterates the whole registry; failures are
**isolated per file** (logged + surfaced, never a partial/empty Parquet). The work is gated
by a newly-established pytest harness, plus the existing ruff/pre-commit gate, Pydantic/
Pandera boundary validation, and OTel spans on each ingestor. Silver/gold/dbt wiring is
explicitly out of scope (spec Non-goals).

## 2. Skills to use

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| Build the ingestion pipeline (registry, discovery, throttled fetch, family ingestors) | — (no "create data ingestion pipeline" skill exists) | **MISSING** — proceed from `ARCHITECTURE.md` §6 + the `assets/bronze.py` pattern; run `self-learn` afterwards to codify what was learned (offer to author the skill via `skill-creator` if it will recur) |
| Establish the missing conventions (pytest layout rule; network-edge clarification) | `create-rule` | available |
| Per-step independent diff review (self-review checkpoint) | `code-review` (or a fresh `general-purpose` reviewer) | available |
| Confirm network edge + layering after wiring | `code-architecture-review`, `analyze-architecture` | available |
| Confirm the assets actually materialize | `verify`, `run` | available |
| Optional hardening review of the fetcher/parsers | `analyze-code-quality`, `analyze-security` | available |
| Capture learnings at the end (closes the MISSING-skill gap) | `self-learn` | available |

## 3. Convention & rule audit (resolved before implementation)

Conventions in this repo live in `CLAUDE.md` (Python conventions, Non-obvious constraints) and
`ARCHITECTURE.md` (structure, layering); there is **no `.claude/rules/` directory**, so new rules
go into those files via `create-rule`. The two gaps below are closed by setup steps **S0** and
**S1**, which land as their own `chore:`/`docs:` commits **before** any implementation step.

| Artifact type | Governing convention | Status |
|---------------|----------------------|--------|
| New Python module(s) in the code location | `CLAUDE.md` *Python conventions* | exists |
| **Network / discovery / HTTP-resource code** | `ARCHITECTURE.md` rule #1 says the edge is *only `assets/bronze.py`* — too narrow for a discoverer + shared HTTP resource + two assets | **gap → closed in S1**: generalise to "the **bronze layer** is the sole network edge"; document the new `football` bronze package in §2/§4 of `ARCHITECTURE.md` |
| New Pydantic v2 record schema | `CLAUDE.md` (validate at boundary, Pydantic v2) + `models/schemas.py` pattern | exists |
| New Pandera frame contract, **`strict=False`** | `models/validation.py` pattern (currently `strict=True`); D4/spec §8 sanction the sparse open contract for drift-prone sources | exists (decision-backed) — write down the `strict=False` rationale in the module docstring |
| New config fields | `CLAUDE.md` (`pydantic-settings` in `config.py`, no ad-hoc `os.getenv`) | exists |
| League registry (whitelist data) | none — new artifact type | resolved in plan: an in-repo **typed Python constant** in the `football` package (version-controlled, deterministic, unit-testable); not external YAML. Captured here, no separate rule file needed |
| Bronze Parquet partition layout | spec §8 + A6 (deterministic path) | exists (path fixed by spec; encoded in the ingestor) |
| New Dagster asset module | `assets/` pattern; **no `from __future__ import annotations`** | exists |
| Dagster resource (throttled HTTP client) | `definitions.py` `DbtCliResource` registration pattern; Dagster `ConfigurableResource` | exists (pattern) |
| **pytest unit tests** | none — `CLAUDE.md`: "There is no Python unit-test suite" | **gap → closed in S0**: add `pytest` dev dep (via `uv`), create `tests/` layout, write the layout/convention rule into `CLAUDE.md`, prove a trivial red→green |

**Gate:** no implementation step (S2–S11) begins until S0 and S1 are committed. No row above is left "gap".

## 4. Testable units (BDD → tests)

| Unit | Spec trace (scenario / AC) | Test facility | Failing-first assertion |
|------|----------------------------|---------------|-------------------------|
| Discovery emits identical ordered URL list on repeat | "Discovery is reproducible" / AC1 | pytest | Two calls over the same HTML fixtures return equal lists incl. order; fails (no discoverer) |
| Whitelist filters noise + off-list leagues | "Whitelist filtering excludes noise" / AC2, E5 | pytest | HTML with `profitable_betting_system.php`, `downloadm.php`, off-list league → none emitted |
| Both families discovered + family-tagged | "Both families are discovered" / AC2 | pytest | Mixed `mmz4281/...csv` + `new/CODE.csv` → both emitted, each tagged `main`/`extra` |
| Relative/absolute URL de-dup | "Relative and absolute URLs do not duplicate work" / E6 | pytest | Same CSV as rel + abs link → exactly one entry |
| 0.4 s pacing between consecutive requests | "Polite pacing" / AC3 | pytest (injected clock/sleep) | 2nd request without a ≥0.4 s budget → fails; client must enforce the delay |
| Within-run cache reuses historical file | "Within-run cache reuse" / AC4 | pytest (fake session, fetch counter) | Same historical URL fetched twice → underlying GET count must be 1 |
| Current-season file never cached | "Current-season files are never cached" / AC5 | pytest | `mmz4281/2526/E0.csv` twice → GET count is 2 (cache bypassed) |
| Current-season detection from URL/run-date | A3 (enables AC5/AC16) | pytest | `2526` season classified current vs `9394` historical relative to run date |
| Artifact-presence skip-existing (historical) | "Historical files fetched once" / AC16, E9 | pytest | Re-run with existing Parquet → no GET for that historical file; artifact untouched |
| Latin-1 main decode without mojibake | "Latin-1 main file decodes" / AC7 | pytest | Latin-1 bytes fixture → decoded chars correct; fails if read as utf-8 |
| `MainMatchRecord` rejects blank/footer rows | "Row-level core validation skips invalid" / AC8, E1, E4 | Pydantic | Blank/footer row raises `ValidationError`; valid fixture row parses |
| Main skip-and-count returns (raw, valid, reject) | AC8 (552→462), A4 | pytest | Function over a mixed fixture returns correct counts; invalid rows dropped not raised-out |
| Main frame contract tolerates optional-column drift | "Frame-level contract passes" / AC9, E3 | Pandera (`strict=False`) | Frame with core + unknown odds cols passes; frame missing a core col fails |
| One main Parquet at `football_main/<league>/<season>/<div>` | "Bronze lands under football_main" / AC10 | artifact assertion (asset + fake HTTP) | Materialize → file exists at deterministic path with stable columns/dtypes |
| utf-8-sig read normalizes BOM header | "utf-8-sig handling normalizes BOM" / AC11, E2 | pytest | utf-8-BOM fixture → header `Country` (not `ï»¿Country`) |
| `ExtraMatchRecord` enforces required fields, deterministic rejects | "Row-level extra validation" / AC12 | Pydantic + pytest | Bad row raises; same input twice → identical reject set/count |
| Extra frame contract passes | "Frame-level contract passes" (extra) / AC13 | Pandera (`strict=False`) | Extra core + optionals passes; missing core col fails |
| One extra Parquet at `football_extra/<code>` | "Bronze lands under football_extra" / AC14 | artifact assertion | Materialize → file at deterministic path, stable structure |
| Backfill lands every whitelisted file | "Full backfill" / AC15 | pytest integration (small fixture registry) | Each discovered URL → an artifact or a surfaced failure; none silently skipped |
| Re-run skips historical, refreshes current | "Historical skip" + "Current refresh" / AC16, E10 | pytest integration (run twice) | Historical: GET count 0, file unchanged; current-season: re-fetched + overwritten |
| Unreachable file isolated, no partial Parquet | E7, A5 | pytest | Fake resource raises on one URL → that file surfaced as failed, **no Parquet written**, others continue |
| Zero-valid-rows file surfaced, no empty Parquet | E8 | pytest | All-invalid fixture → failure surfaced for that file, **no Parquet written** |
| Transient error retried within polite limits | E11 | pytest | Fake session fails once then succeeds → retried; persistent failure → handled as E7 |
| OTel span emitted per ingested file | spec §8 (mirror `raw_users`) | pytest (span exporter) / inspection | Ingestor opens a span with record/output attributes |
| Lineage references present on artifacts | "lineage refs present" / AC6 | inspection (grep) | The three refs appear in the spec §8 / stories (already satisfied) |

## 5. Guardrail register

| Guardrail | How verified in place | Covered by step |
|-----------|------------------------|-----------------|
| ruff check + format (pre-commit) | `uv run pre-commit run --all-files` clean; `uv run ruff check src` | S0 + every step |
| pytest harness exists and runs | `uv run pytest` runs; trivial red→green proven | S0 |
| Pydantic per-record validation at the boundary | bad record raises; main/extra cores enforced | S6, S7, S8, S9 |
| Pandera per-frame validation (`strict=False`) before write | core-missing frame fails; optional drift tolerated | S6, S7, S8, S9 |
| Deterministic discovery (content + order) | repeat-call equality test | S3 |
| 0.4 s throttle + cache policy | injected-clock pacing test; fetch-count cache tests | S4 |
| Idempotency / re-run safety (artifact-presence) | run twice: historical GET count 0 + file unchanged; current overwritten | S4, S10 |
| Per-file failure isolation, no partial/empty Parquet | E7/E8 tests assert no file written, run continues | S7, S9 |
| OTel span emitted per file | span attributes asserted / inspected | S7, S9 |
| Repo non-obvious constraints respected | **no `from __future__` in asset modules** (S7, S9); `pathlib.Path`; config via `pydantic-settings` (S2); network edge = bronze layer (S1); warehouse untouched (no dbt this scope) | all |

## 6. Implementation steps

### Step S0 — Establish the pytest harness + tests layout convention
- **Goal:** A working pytest harness so every pure-Python unit below has a falsifiable red→green check.
- **Spec trace:** setup — enables the pytest units for AC1–AC5, AC7, AC8, AC11, AC12, AC15, AC16, E1–E11.
- **Red (failing test first):** `uv run pytest` fails (no `pytest`, no `tests/`). Add `tests/test_harness_smoke.py` with one `assert False` and watch it fail, then flip to `assert True`.
- **Implementation:** `uv add --dev pytest` (respects `uv.lock` + the `>=3.12,<3.13` pin; do **not** swap tooling). Create `tests/` mirroring `src/data_platform/` (`tests/football/`, `tests/conftest.py` for fixtures/`PYTHONPATH=src`). Add a concise rule to `CLAUDE.md` (Commands + Python conventions): "Unit-test pure-Python logic with pytest under `tests/`, mirroring `src/` layout; run `PYTHONPATH=src uv run pytest`." Decide pre-commit posture: keep pytest as a manual/local gate invoked in CI/by hand (do **not** weaken the existing ruff hooks).
- **Green criterion:** `PYTHONPATH=src uv run pytest` collects and passes the smoke test; `uv run pre-commit run --all-files` clean.
- **Guardrails to satisfy:** ruff/pre-commit clean; harness proven via red→green.
- **Self-review checkpoint:** reviewer confirms pytest was added through `uv` (not a tooling swap), the layout rule is committed to `CLAUDE.md`, the smoke test genuinely failed before passing, and no existing gate was weakened. Atomic commit: `chore(test): add pytest harness and tests layout convention`.

### Step S1 — Convention: generalise the network-edge rule + document the `football` bronze package
- **Goal:** Resolve the contradiction between `ARCHITECTURE.md` rule #1 ("edge only in `assets/bronze.py`") and a design that adds a discoverer + shared HTTP resource + two assets, **before** writing that code.
- **Spec trace:** setup — unblocks S2–S10; preserves the layering guardrail.
- **Red (failing test first):** N/A (documentation/convention). The falsifiable check is the later `code-architecture-review` (S11): the new package must conform to the rule as written.
- **Implementation:** via `create-rule`, edit `ARCHITECTURE.md` §3 rule #1 to "the **bronze layer** is the sole network edge (any module under `assets/` that ingests/lands bronze + its discovery/HTTP helpers)"; add the `football` package to §2 structure and §4 module-responsibility table (registry, discovery, throttled client, two ingestors). Keep `CLAUDE.md` Non-obvious constraints unchanged here (football runtime gotchas get added at S11 in the same change that discovers them).
- **Green criterion:** `ARCHITECTURE.md` describes the package and the generalised rule; `uv run pre-commit run --all-files` clean.
- **Guardrails to satisfy:** non-obvious constraints documented, not contradicted.
- **Self-review checkpoint:** reviewer confirms the rule still forbids network calls outside the bronze layer (no loophole for downstream code), and the documented package matches what S2–S10 will build. Atomic commit: `docs(arch): scope network edge to the bronze layer; document football package`.

### Step S2 — Config fields + league registry
- **Goal:** Add typed config and the hard-coded, family-tagged league whitelist that drives discovery.
- **Spec trace:** AC2/D6 (whitelist), A1 (registry is build-time agreed); foundation for AC1.
- **Red (failing test first):** `tests/football/test_registry.py` asserts the registry exposes the 11 main leagues + 19 extra codes with their family + URL-pattern metadata, and `settings.football_base_url` / throttle/cache fields exist. Fails (nothing exists).
- **Implementation:** add fields to `config.py` (`football_base_url`, `football_throttle_seconds: float = 0.4`, plus `bronze_dir`-derived `football_main_dir`/`football_extra_dir` helpers) — `pydantic-settings`, no `os.getenv`. Create `src/data_platform/football/registry.py` with a typed constant (the whitelist). Keep it a pure leaf (no I/O).
- **Green criterion:** `PYTHONPATH=src uv run pytest tests/football/test_registry.py` passes; ruff clean.
- **Guardrails to satisfy:** config via `pydantic-settings`; `pathlib.Path`; ruff.
- **Self-review checkpoint:** reviewer confirms the registry is the single source of truth, contents match the investigation (11 main / 19 extra), no hardcoded URLs leak into discovery logic, no `os.getenv`. Atomic commit: `feat(football): add config + league registry`.

### Step S3 — Deterministic link discoverer (Story #2)
- **Goal:** From fetched page HTML + the registry, emit a deterministic, de-duplicated, family-tagged list of CSV URLs for whitelisted leagues only.
- **Spec trace:** "Discovery is reproducible" (AC1), "Whitelist filtering excludes noise" (AC2, E5), "Both families are discovered", "Relative/absolute URLs do not duplicate work" (E6).
- **Red (failing test first):** `tests/football/test_discovery.py` with HTML fixtures (whitelisted main+extra links, noise links, off-list league, a CSV linked both relative and absolute): assert identical ordered output across two calls; noise/off-list excluded; both families tagged; rel/abs de-duped to one. All fail (no discoverer).
- **Implementation:** `football/discovery.py` — `requests`-fetched HTML in, regex extract `href`s, normalize relative→absolute against the base URL, filter to registry family/code patterns, tag family, sort deterministically, de-dup. Pure given HTML (fetching delegated to S4's client so pacing applies to page GETs too).
- **Green criterion:** `pytest tests/football/test_discovery.py` green; ruff clean.
- **Guardrails to satisfy:** determinism; whitelist-only; no BeautifulSoup (D3); ruff.
- **Self-review checkpoint:** reviewer confirms ordering is stable (not dict/set insertion luck), noise patterns are actually excluded (not just the two named), dedup is by normalized URL, and the test fixtures genuinely contain the trap links. Atomic commit: `feat(football): deterministic whitelist link discovery`.

### Step S4 — Throttled, cache-aware HTTP client resource (Story #2)
- **Goal:** One shared client enforcing 0.4 s pacing, within-run cache for historical files, unconditional re-fetch for current-season, artifact-presence skip-existing, and polite retry.
- **Spec trace:** "Polite pacing" (AC3), "Within-run cache reuse" (AC4), "Current-season files are never cached" (AC5), "Historical files fetched once" (AC16 fetch side, E9), transient retry (E11).
- **Red (failing test first):** `tests/football/test_http_client.py` with an **injected clock + injected sleep** and a **fake session with a GET counter**: assert ≥0.4 s budget enforced between consecutive GETs; same historical URL twice → 1 GET; current-season URL twice → 2 GETs; existing-artifact historical URL → 0 GETs (skip-existing); one transient failure then success → retried; persistent failure → raises for the caller to isolate.
- **Implementation:** `football/http_client.py` as a Dagster `ConfigurableResource` wrapping a `requests.Session` (auto-instrumented by `otel.py`). Inject clock/sleep so pacing is deterministically testable (no real wall-clock sleeps in tests). Skip-existing = check the deterministic bronze path exists **and** the file is historical (current-season never skipped). Bounded retry with the polite delay.
- **Green criterion:** `pytest tests/football/test_http_client.py` green; ruff clean.
- **Guardrails to satisfy:** 0.4 s pacing; cache policy; idempotency (skip-existing); retry; `pathlib.Path`.
- **Self-review checkpoint:** reviewer confirms pacing is enforced by the client (not the test), current-season bypass cannot be defeated by cache, skip-existing keys on artifact presence (per the resolved Q-refresh-keying — **not** ETag/hash), and retry has a real bound (no infinite loop, no silent swallow). Atomic commit: `feat(football): throttled cache-aware HTTP client resource`.

### Step S5 — Current-season detection
- **Goal:** Deterministically classify a file as current-season vs historical so AC5/AC16 apply correctly.
- **Spec trace:** A3 (enables AC5, AC16); E10.
- **Red (failing test first):** `tests/football/test_season.py`: given a fixed run date, `2526` (main URL) classifies current and `9394` historical; extra files (season in-file) classified "always refresh". Fails (no function).
- **Implementation:** `football/season.py` — pure function mapping a main URL's season token + run date → current/historical; extra family treated as always-refresh whole-file (current season carried in-file). Run date injected (no `datetime.now()` buried in logic).
- **Green criterion:** `pytest tests/football/test_season.py` green; ruff clean.
- **Guardrails to satisfy:** determinism (run date injected); ruff.
- **Self-review checkpoint:** reviewer confirms the boundary (e.g. season rollover) is correct and the run date is a parameter, not a hidden global. Atomic commit: `feat(football): current-season detection`.

### Step S6 — Main-family contracts (Pydantic record + Pandera frame)
- **Goal:** `MainMatchRecord` enforcing the 7-field core; `main_bronze_schema` (`strict=False`) for the assembled frame.
- **Spec trace:** "Row-level core validation skips invalid" (AC8, E1, E4), "Frame-level contract passes" (AC9, E3).
- **Red (failing test first):** Pydantic test: a blank/footer row raises `ValidationError`, a real fixture row parses (core = `Div, Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR`). Pandera test: frame with core + unknown odds columns passes; frame missing a core column fails. Both fail (no schemas).
- **Implementation:** extend `models/schemas.py` with `MainMatchRecord` and `models/validation.py` with `main_bronze_schema = DataFrameSchema({...core...}, strict=False, coerce=True)`. Leaf modules — `from __future__ import annotations` is allowed here (these are NOT asset modules). Docstring records the `strict=False` rationale (D4).
- **Green criterion:** `pytest tests/.../test_main_contracts.py` green; ruff clean.
- **Guardrails to satisfy:** Pydantic boundary; Pandera `strict=False`; ruff.
- **Self-review checkpoint:** reviewer confirms the core matches the spec exactly, `strict=False` genuinely tolerates extra columns while still requiring the core, and the "invalid row" test uses a realistic blank/footer row (not a contrived one). Atomic commit: `feat(football): main-family Pydantic + Pandera contracts`.

### Step S7 — Main-family ingestor asset
- **Goal:** Per discovered main URL: fetch (latin-1), parse, row-validate (skip+count), frame-validate, write one Parquet, emit metadata + span; isolate failures.
- **Spec trace:** "Latin-1 main file decodes" (AC7), AC8, AC9, "Bronze lands under football_main" (AC10), E7, E8, A4.
- **Red (failing test first):** integration test with a **fake HTTP resource** returning a latin-1 fixture (incl. blank/footer rows, latin-1 chars): assert Parquet written at `football_main/<league>/<season>/<div>.parquet` with stable columns; raw/valid/reject counts in metadata (552→462-style); chars not mojibaked. Separate tests: E7 (resource raises → file surfaced as failed, **no Parquet**, run continues); E8 (all-invalid fixture → failure surfaced, **no Parquet**).
- **Implementation:** `assets/football_main.py` (or `football/assets_main.py` registered as a Dagster asset). **No `from __future__ import annotations`.** Wrap fetch in a `get_tracer()` span (mirror `raw_users`). Decode latin-1, parse with pandas, validate rows via `MainMatchRecord` skipping+counting, validate frame via `main_bronze_schema`, write Parquet to the deterministic path. Raise/surface (no empty Parquet) on E7/E8 — isolate-per-file (resolved Q-fail-isolation).
- **Green criterion:** `pytest tests/.../test_main_ingestor.py` green; ruff clean.
- **Guardrails to satisfy:** Pydantic+Pandera at boundary; no empty/partial Parquet; OTel span; no `from __future__`; `pathlib.Path`; idempotent path.
- **Self-review checkpoint:** reviewer confirms the asset **raises/surfaces** rather than writing empty/default Parquet on failure (no defaults-on-failure), counts are real (not hardcoded), the span is emitted, the module has no `from __future__ import annotations`, and the Parquet path is deterministic. Atomic commit: `feat(football): main-family bronze ingestor asset`.

### Step S8 — Extra-family contracts (Pydantic record + Pandera frame)
- **Goal:** `ExtraMatchRecord` enforcing the 9-field core; `extra_bronze_schema` (`strict=False`).
- **Spec trace:** "Row-level extra validation" (AC12), "Frame-level contract passes" (extra) (AC13).
- **Red (failing test first):** Pydantic test: bad row raises; valid row parses (core = `Country, League, Season, Date, Home, Away, HG, AG, Res`); **determinism** — same input twice yields identical reject set. Pandera test: extra core + optionals passes; missing core fails. Fail first.
- **Implementation:** add `ExtraMatchRecord` to `models/schemas.py` and `extra_bronze_schema` to `models/validation.py` (`strict=False`, `coerce=True`).
- **Green criterion:** `pytest tests/.../test_extra_contracts.py` green; ruff clean.
- **Guardrails to satisfy:** Pydantic boundary; Pandera `strict=False`; deterministic rejects; ruff.
- **Self-review checkpoint:** reviewer confirms the extra core differs correctly from main (D5, two tables not one), determinism is actually asserted, `strict=False` tolerates the ~25-col + odds shape. Atomic commit: `feat(football): extra-family Pydantic + Pandera contracts`.

### Step S9 — Extra-family ingestor asset
- **Goal:** Per extra URL: utf-8-sig read (BOM-normalized), row-validate (skip+count), frame-validate, write one Parquet per league code, metadata + span; isolate failures.
- **Spec trace:** "utf-8-sig handling normalizes BOM" (AC11, E2), AC12, AC13, "Bronze lands under football_extra" (AC14), E7, E8.
- **Red (failing test first):** integration test with a fake HTTP resource returning a **utf-8-BOM** fixture: assert header normalized to `Country` (not `ï»¿Country`); Parquet at `football_extra/<code>.parquet`; counts in metadata. E7/E8 tests as in S7 (no Parquet on failure).
- **Implementation:** `assets/football_extra.py`. **No `from __future__`.** Read with `utf-8-sig`, validate rows via `ExtraMatchRecord`, frame via `extra_bronze_schema`, write Parquet to the deterministic path, span + metadata, isolate-per-file.
- **Green criterion:** `pytest tests/.../test_extra_ingestor.py` green; ruff clean.
- **Guardrails to satisfy:** utf-8-sig (latin-1 on extra is a defect, E2); Pydantic+Pandera; no empty Parquet; span; no `from __future__`.
- **Self-review checkpoint:** reviewer confirms the BOM is actually normalized (header asserted), reading as latin-1 is not an accepted fallback, failure isolation holds, no `from __future__`. Atomic commit: `feat(football): extra-family bronze ingestor asset`.

### Step S10 — Wire into the code location + backfill / idempotency
- **Goal:** Register both assets + the throttled HTTP resource in `definitions.py`; a backfill job over the whole registry; prove idempotent re-runs and full coverage.
- **Spec trace:** "Full backfill" (AC15), "Historical files fetched once and skipped" + "Current-season files are always refreshed" (AC16, E9, E10).
- **Red (failing test first):** integration test over a **small fixture registry** running the assets/job **twice**: first run lands a Parquet (or surfaced failure) for every discovered URL (AC15 coverage); second run → historical GET count 0 and artifact unchanged, current-season re-fetched + overwritten (AC16). Fails until wired + skip-existing applied end-to-end.
- **Implementation:** add the assets to `Definitions(assets=[...])` and the throttled client to `resources={...}` (mirror `DbtCliResource`); add a `define_asset_job` backfill selection. No schedule (Non-goal). Ensure discovery page GETs and file GETs both flow through the throttled client.
- **Green criterion:** `pytest tests/.../test_backfill_idempotency.py` green; `uv run pre-commit run --all-files` clean.
- **Guardrails to satisfy:** idempotency/re-run safety; full coverage; pacing applies to all GETs; no schedule added.
- **Self-review checkpoint:** reviewer confirms the second run genuinely makes 0 historical GETs (counter evidence), current-season is overwritten with identical structure, every registry entry is accounted for (artifact or surfaced failure — none silently dropped), and no warehouse file is opened (dbt out of scope). Atomic commit: `feat(football): register assets + backfill job with idempotent re-runs`.

### Step S11 — Review, guardrail sweep, and learnings
- **Goal:** Confirm the change conforms structurally and runs; record any new runtime gotcha; close the MISSING-skill gap.
- **Spec trace:** verification of all ACs end-to-end; AC6 (lineage refs present) confirmed by inspection.
- **Red (failing test first):** N/A (review). Falsifiable via the review skills' findings.
- **Implementation:** run `code-architecture-review` / `analyze-architecture` (network edge stays in the bronze layer per S1; no asset imports another); `uv run pre-commit run --all-files`; `PYTHONPATH=src uv run pytest`; `verify`/`run` to materialize against a tiny live or fixture slice. Add any discovered runtime gotcha (e.g. season-rollover edge, encoding trap) to `CLAUDE.md` Non-obvious constraints **in this commit**. Run `self-learn` to propose codifying the ingestion pattern into a reusable skill (the §2 gap).
- **Green criterion:** all gates clean; architecture review finds no layering violation; assets materialize.
- **Guardrails to satisfy:** all of §5.
- **Self-review checkpoint:** independent reviewer confirms no reward-hacking slipped through across steps (no suppressed gates, no stubbed ingestor, no defaults-on-failure), and that `CLAUDE.md`/`ARCHITECTURE.md` reflect reality. Atomic commit: `docs(football): record runtime constraints; close ingestion learnings`.

## 7. Sequencing & dependencies

```
S0 (pytest harness) ─┐
S1 (network-edge rule)┼─ HARD GATE (both committed) ─▶ implementation
                      │
S2 registry+config ─▶ S3 discovery ─┐
                                     ├─▶ S5 season ─┐
S2 ─────────────────▶ S4 http client┘               │
                                                     ▼
S6 main contracts ─▶ S7 main ingestor ───────────────┤
S8 extra contracts ▶ S9 extra ingestor ──────────────┤
                                                     ▼
                          S10 wire + backfill/idempotency
                                                     ▼
                                S11 review + learnings
```

- **S0 + S1 are a hard gate** (Phase-2 convention audit): no implementation until both are committed.
- Discovery (S3) and the HTTP client (S4) both depend on the registry/config (S2); the client also realises skip-existing, which needs season detection (S5).
- Each family track (contracts → ingestor: S6→S7, S8→S9) is independent of the other (mirrors the spec: tracks independent, both depend on #2). They can be built in either order or in parallel.
- S10 depends on both ingestors + the client's skip-existing; idempotency is only provable once writes (S7/S9) and skip-existing (S4) coexist.
- **Repo-gotcha edges honoured:** bronze writes **Parquet files only** (no warehouse access — dbt/silver/gold out of scope, so the single-writer DuckDB rule isn't exercised); asset modules carry **no `from __future__ import annotations`** (S7, S9); leaf contract/config modules may; assets don't import each other (wired only in `definitions.py`).

## 8. Assumptions

- **A-plan-1** — pytest is acceptable as a new dev dependency and local/CI gate (confirmed this session); it does **not** join the ruff pre-commit hook so the existing gate is unchanged.
- **A-plan-2** — Skip-existing is keyed purely on **bronze-artifact presence** for historical files (confirmed this session, resolving Q-refresh-keying); ETag/Last-Modified/content-hash are **not** implemented.
- **A-plan-3** — Failure is **isolated per file/partition** (confirmed this session, resolving Q-fail-isolation / A5); the backfill never aborts wholesale on one bad file.
- **A-plan-4** — The league registry is an in-repo typed Python constant (the build-time agreed list per spec A1), not external config; its exact contents are finalised in S2 from the investigation (11 main / 19 extra).
- **A-plan-5** — Two Pandera frame schemas (one per family core), not the single `BronzeMatchFrame` the architecture doc sketches — required because the cores differ (D5). Surfaced as a deliberate deviation.
- **A-plan-6** — "Consistent structure/naming across runs" means a deterministic output path + stable column ordering/dtype contract, not byte-identical Parquet (spec A6).
- **A-plan-7** — The shared throttled client carries **both** discovery page GETs and file GETs, so the 0.4 s budget applies site-wide (per the architecture doc's discoverer→client edge).

## 9. Open questions

- **Q3 (non-blocking for bronze)** — football-data.co.uk terms-of-use for downstream **redistribution**. Does not block landing bronze; blocks any later gold publication. Carried forward from the spec; out of scope here.
- **MISSING-skill gap (non-blocking)** — there is no "create data ingestion pipeline" skill; the plan proceeds from `ARCHITECTURE.md` §6 + the `raw_users` pattern and runs `self-learn` at S11 to codify the pattern. Offer to author the skill via `skill-creator` if this kind of source-onboarding will recur.
- No remaining **blockers**. The two spec "resolve-before-build" questions (Q-refresh-keying, Q-fail-isolation) are resolved (A-plan-2, A-plan-3).

## 10. Traceability

| Spec scenario / AC | Unit(s) | Step(s) | Guardrail(s) |
|--------------------|---------|---------|--------------|
| "Discovery is reproducible" / AC1 | deterministic ordered URL list | S3 | determinism test, ruff |
| "Whitelist filtering excludes noise" / AC2, E5 | whitelist filter; both-families tag | S2, S3 | discovery tests, ruff |
| "Both families are discovered" / AC2 | family tagging | S3 | discovery tests |
| "Relative and absolute URLs do not duplicate work" / E6 | URL normalize + dedup | S3 | discovery tests |
| "Polite pacing" / AC3 | 0.4 s pacing | S4 | injected-clock test |
| "Within-run cache reuse" / AC4, E9 | within-run cache | S4 | fetch-count test |
| "Current-season files are never cached" / AC5 | current-season bypass | S4, S5 | fetch-count test, season test |
| "lineage refs present" / AC6 | refs on spec/stories | (S1 inspection) | inspection |
| "Latin-1 main file decodes" / AC7 | latin-1 decode | S7 | ingestor test |
| "Row-level core validation skips invalid" / AC8, E1, E4 | MainMatchRecord + skip-count | S6, S7 | Pydantic, count test |
| "Frame-level contract passes" (main) / AC9, E3 | main_bronze_schema strict=False | S6, S7 | Pandera test |
| "Bronze lands under football_main" / AC10 | main Parquet at deterministic path | S7 | artifact assertion |
| "utf-8-sig handling normalizes BOM" / AC11, E2 | utf-8-sig read | S9 | ingestor test |
| "Row-level extra validation" / AC12 | ExtraMatchRecord + deterministic rejects | S8, S9 | Pydantic, determinism test |
| "Frame-level contract passes" (extra) / AC13 | extra_bronze_schema strict=False | S8, S9 | Pandera test |
| "Bronze lands under football_extra" / AC14 | extra Parquet at deterministic path | S9 | artifact assertion |
| "Full backfill" / AC15 | backfill coverage over registry | S10 | integration test |
| "Historical files fetched once and skipped" / AC16, E9 | artifact-presence skip-existing | S4, S5, S10 | fetch-count + unchanged-artifact test |
| "Current-season files are always refreshed" / AC16, E10 | current-season re-fetch + overwrite | S4, S5, S10 | integration test |
| E7 (unreachable, isolate, no partial Parquet) | per-file isolation, raise not stub | S4, S7, S9 | E7 tests |
| E8 (zero valid rows, no empty Parquet) | surface failure, no write | S7, S9 | E8 tests |
| E11 (transient retry) | bounded polite retry | S4 | retry test |
| spec §8 (OTel span per file) | span emission | S7, S9 | span test/inspection |
```
