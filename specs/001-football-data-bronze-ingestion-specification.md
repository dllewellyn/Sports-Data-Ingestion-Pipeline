---
id: 001
title: football-data.co.uk bronze ingestion (main + extra families)
slug: football-data-bronze-ingestion
status: draft
created: 2026-06-26
user_stories: [2, new-implement-football-main-bronze-ingestion-and-validation-path, new-implement-football-extra-bronze-ingestion-and-validation-path]
investigation: football-data-co-uk-ingestion
related_specs: []
---

# football-data.co.uk bronze ingestion (main + extra families)

## 1. Summary

A data platform engineer can ingest the entirety of football-data.co.uk — every
whitelisted league across all available history — into the medallion platform as
**validated bronze Parquet**. The system discovers source CSV links deterministically
from a known league whitelist, fetches them through a single polite, throttled HTTP
client, decodes each of the **two dataset families** with its correct encoding
(main = latin-1, extra = utf-8-sig), validates each record against a small mandatory
core and each frame against a sparse (open) frame contract, and lands **one Parquet
artifact per source file** under family-specific partitioning. Re-running is cheap and
stable: immutable historical files are fetched once and skipped thereafter, while
current-season files are always re-fetched and their bronze output refreshed.

## 2. Background & context

Source user stories (all children of **Epic #1 — "football-data.co.uk ingestion
architecture (main + extra tracks)"**):

- **Story #2 — "Discover and throttle football-data URL ingestion deterministically"**
  (`user_stories/2.json`). The shared foundation both tracks build on.
- **Story `new-implement-football-main-bronze-ingestion-and-validation-path`** — the
  main-family ingestion/validation path.
- **Story `new-implement-football-extra-bronze-ingestion-and-validation-path`** — the
  extra-family ingestion/validation path.

The epic explicitly defines *two implementation tracks and one shared foundation*, and
its Component Architecture Overview states discovery + throttled HTTP are foundational
and must exist before family-specific ingestion. These three child stories are therefore
specified together as one cohesive bronze-ingestion capability.

This spec draws directly on **investigation `football-data-co-uk-ingestion`**
(`investigations/football-data-co-uk-ingestion/findings.md`, `decisions.md`), which
concluded the ingestion is feasible and proved the validated-Parquet pattern on real
downloaded files. Prior decisions already taken there and carried in here:

- **D3** — no BeautifulSoup; discovery uses `requests` + regex.
- **D4** — sparse canonical bronze schema: enforce a small mandatory **core** per record
  (Pydantic), let all optional odds/stat columns ride along (Pandera `strict=False`).
- **D5** — treat the two families as **two separate bronze tables**, not one unified
  schema (different cores, keys, encodings, and season provenance).
- **D6** — drive discovery from a **known league registry / whitelist**, not a blanket
  `*m.php` suffix filter (which matches noise like `profitable_betting_system.php` /
  `downloadm.php` and silently drops the 19 extra leagues).

Evidence highlights: main-family E0 grew 7 → 45 → 71 → 106 columns across 1993/94 →
2023/24 (union of 7 sampled files = 146 cols); a stable 7-field core
(`Div, Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR`) appears in *every* main file; `9394/E0.csv`
had 552 raw rows of which only 462 (= a 22-team season, 22×21) passed core validation,
the rest being blank/footer rows; extra files are UTF-8-with-BOM and pack all seasons
into one file (ARG = 6,235 rows, USA = 6,034). `robots.txt` is `Disallow:` (crawling
permitted site-wide) with no published rate limit.

## 3. Goals & non-goals

**Goals**

- Land validated bronze Parquet for the **main family** (`mmz4281/<season>/<div>.csv`,
  latin-1) under `football_main` partitioning.
- Land validated bronze Parquet for the **extra family** (`new/<CODE>.csv`, utf-8-sig)
  under `football_extra` partitioning.
- A shared, **deterministic** discovery step that emits the same whitelisted URLs (same
  content and order) on repeated runs over unchanged source content.
- A single shared **throttled** HTTP client (0.4 s pacing) with explicit cache policy:
  reuse historical files within a run; always re-fetch current-season files.
- Two-stage validation per family: **row-level** (Pydantic core) skipping invalid rows
  while keeping valid ones and recording reject counts, then **frame-level** (Pandera,
  open/`strict=False`) before any write.
- A **full backfill** of every whitelisted main and extra file across all available
  history (the run target, see §8 for the volume/politeness implications this creates).
- Stable, idempotent re-runs: historical files fetched once and skipped if already
  landed; current-season files always refreshed.

**Non-goals (explicitly out of scope)**

- Silver/gold dbt models, marts, or any unification of the two families downstream.
- External redistribution / publication of the data (gated on terms-of-use, see Q3).
- A Dagster schedule or sensor for automated periodic refresh (the path is run on
  demand; recurring scheduling is a later concern).
- Backfilling leagues not in the agreed whitelist/registry.
- Enriching, deduplicating, or reshaping columns beyond the family core + ride-along
  optionals (bronze is faithful-to-source).

## 4. Actors & triggers

- **Actor:** a data platform engineer (or an operator running the platform).
- **Trigger:** a manual, on-demand execution of the football-data bronze ingestion
  (a Dagster materialization / job run), scoped to the whitelisted league registry.
- **Internal trigger order:** discovery + throttled HTTP (Story #2 foundation) run first
  and feed both family tracks; each family track then fetches → validates → writes its
  bronze Parquet artifacts.

## 5. Behaviour specification (BDD)

### Capability: Deterministic discovery (Story #2)

**Scenario: Discovery is reproducible**
- **Given** a fixed league whitelist and unchanged source page content
- **When** discovery runs repeatedly
- **Then** the emitted set of file URLs is identical in content **and order** across runs.

**Scenario: Whitelist filtering excludes noise and off-list leagues**
- **Given** the source pages containing relevant CSV links plus noise links
  (e.g. `profitable_betting_system.php`, `downloadm.php`) and off-whitelist leagues
- **When** discovery executes
- **Then** only URLs matching approved family/code patterns for whitelisted leagues are
  emitted, and noise/off-list links are excluded.

**Scenario: Both families are discovered**
- **Given** main-family leagues exposed as `mmz4281/<season>/<div>.csv` and extra-family
  leagues exposed as `new/<CODE>.csv`
- **When** discovery executes against the whitelist
- **Then** URLs for both families are emitted and each is tagged with its family so the
  correct downstream track and encoding are selected.

**Scenario: Relative and absolute URLs do not duplicate work**
- **Given** the same CSV linked once as a relative and once as an absolute URL
- **When** discovery normalizes results
- **Then** the file is emitted exactly once (no duplicate/garbage processing).

### Capability: Throttled, cache-aware HTTP retrieval (Story #2)

**Scenario: Polite pacing between requests**
- **Given** sequential outbound requests through the shared HTTP client
- **When** more than one request is made
- **Then** a 0.4 second delay budget is enforced between consecutive requests.

**Scenario: Within-run cache reuse for historical files**
- **Given** a non-current (historical) file is requested more than once in a single run
  with caching enabled
- **When** the second request occurs
- **Then** only one network fetch happened and the cached content is reused for the rest.

**Scenario: Current-season files are never cached**
- **Given** a current-season file (e.g. `mmz4281/2526/E0.csv`)
- **When** ingestion runs
- **Then** the file is fetched fresh from source and is never served from cache.

### Capability: Main-family bronze ingestion & validation

**Scenario: Latin-1 main file decodes and parses**
- **Given** an `mmz4281/<season>/<div>.csv` input with latin-1 encoding
- **When** ingestion reads it
- **Then** rows decode and parse correctly without mojibake.

**Scenario: Row-level core validation skips invalid rows and keeps valid ones**
- **Given** parsed main rows where some are blank/footer/incomplete (e.g. `9394/E0.csv`
  with 552 raw rows of which 462 are real fixtures)
- **When** row-level main-core validation runs (core = `Div, Date, HomeTeam, AwayTeam,
  FTHG, FTAG, FTR`)
- **Then** rows missing/failing the core are dropped, valid rows continue, and the
  raw-vs-valid counts (e.g. 552 → 462) are recorded in the asset's metadata/log.

**Scenario: Frame-level contract passes before write**
- **Given** a validated main frame carrying the 7-field core plus arbitrary optional
  odds/stat columns
- **When** frame-level (open / `strict=False`) validation executes
- **Then** the frame contract checks pass and unexpected optional columns are tolerated
  (no failure on schema drift) before any Parquet is written.

**Scenario: Bronze Parquet lands under football_main partitioning**
- **Given** a successfully validated main frame for one season×division file
- **When** the artifact is materialized
- **Then** exactly one bronze Parquet is written under `football_main` partitioning keyed
  by league/season (season derived from the URL path), with structure and naming
  identical across runs of the same file.

### Capability: Extra-family bronze ingestion & validation

**Scenario: utf-8-sig handling normalizes BOM headers**
- **Given** a `new/<CODE>.csv` input that is UTF-8 with a BOM
- **When** ingestion reads it with utf-8-sig–compatible handling
- **Then** the first header is normalized (e.g. `Country`, not `ï»¿Country`) and records
  are produced normalized.

**Scenario: Row-level extra validation enforces required fields deterministically**
- **Given** parsed extra rows
- **When** row-level extra-core validation runs (core = `Country, League, Season, Date,
  Home, Away, HG, AG, Res`)
- **Then** rows failing the required fields are surfaced **deterministically** (same
  input → same rejects), invalid rows are dropped with counts recorded, and valid rows
  continue.

**Scenario: Frame-level contract passes before write**
- **Given** a validated extra frame (≈25 core/typical columns plus optional odds)
- **When** frame-level (open / `strict=False`) validation executes
- **Then** the frame contract checks pass before any Parquet is written.

**Scenario: Bronze Parquet lands under football_extra partitioning**
- **Given** a successfully validated extra frame (one file holds all seasons for that
  league, season carried in-file)
- **When** the artifact is materialized
- **Then** exactly one bronze Parquet is written under `football_extra` partitioning keyed
  by league code, with structure and naming consistent across runs.

### Capability: Full backfill & idempotent re-runs

**Scenario: Full backfill across all whitelisted files**
- **Given** the agreed whitelist (≈689 main season×division files across 11 leagues, plus
  ≈19 extra-league files)
- **When** a backfill run executes
- **Then** every whitelisted main and extra file is fetched, validated, and landed as
  bronze Parquet in its family partitioning.

**Scenario: Historical files are fetched once and skipped on re-run**
- **Given** an immutable historical file whose bronze Parquet already exists from a prior
  run
- **When** ingestion runs again
- **Then** the file is not re-fetched and its existing bronze artifact is left unchanged.

**Scenario: Current-season files are always refreshed**
- **Given** a current-season file that has been updated in place at source since the last
  run
- **When** ingestion runs again
- **Then** the file is re-fetched and its bronze Parquet is overwritten with the same
  structure/naming, reflecting the new fixtures.

## 6. Edge cases & error handling

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | Blank / footer / incomplete rows in a CSV (e.g. ~90 rows in `9394/E0.csv`) | Dropped by row-level core validation; valid rows continue; raw-vs-valid counts recorded in metadata. |
| E2 | Extra file read with the wrong (latin-1) encoding mangles the BOM header (`ï»¿Country`) | Extra family must be read with utf-8-sig handling; header normalized to `Country`. Reading an extra file as latin-1 is a defect, not an accepted path. |
| E3 | Schema drift — a file introduces new/unknown optional columns | Tolerated: optional columns ride along under the open frame contract (`strict=False`); no failure. |
| E4 | A row is missing one or more mandatory core fields | Row is invalid → dropped (skip-and-continue), counted; never written to bronze. |
| E5 | Discovery noise links (`profitable_betting_system.php`, `downloadm.php`) or off-whitelist leagues | Excluded by whitelist/pattern filtering; never fetched. |
| E6 | Same file linked as both relative and absolute URL | De-duplicated in discovery; fetched and landed once. |
| E7 | A whitelisted source file is unreachable / returns non-200 after polite retries | That file/partition fails and is surfaced (logged + reflected in run status); **no empty or partial Parquet is written** for it; other files/partitions continue. (See A5 / Q-open on fail-isolation.) |
| E8 | A file parses but yields zero valid rows after core validation | Surfaced as a failure for that file; no empty bronze artifact is silently written. |
| E9 | Re-run over already-landed historical files | Skip-existing: no re-fetch, existing artifact untouched (idempotent). |
| E10 | Current-season file changed in place at source | Always re-fetched; bronze overwritten with identical structure/naming. |
| E11 | Transient network error / timeout mid-fetch | Retried within polite limits; persistent failure handled as E7. |

## 7. Acceptance criteria

Discovery & throttling (Story #2):
- [ ] AC1 — Repeated discovery over a fixed whitelist and unchanged source content emits identical URLs in **content and order**.
- [ ] AC2 — Only URLs matching approved family/code patterns for whitelisted leagues are emitted; noise and off-list leagues are excluded.
- [ ] AC3 — A 0.4 second delay budget is enforced between sequential outbound requests via the single shared HTTP client.
- [ ] AC4 — Repeated requests for the same non-current file within one run cause exactly one network fetch (cache reused).
- [ ] AC5 — Current-season files are always fetched from source and never served from cache.
- [ ] AC6 — The story/spec artifact carries the architecture lineage references listed in §8.

Main family:
- [ ] AC7 — latin-1 `mmz4281/<season>/<div>.csv` inputs decode and parse correctly.
- [ ] AC8 — Row-level main-core validation drops invalid rows, keeps valid rows, and records raw-vs-valid counts.
- [ ] AC9 — Frame-level (`strict=False`) validation passes before write and tolerates optional-column drift.
- [ ] AC10 — One bronze Parquet per main file is written under `football_main` partitioning (league/season) with structure/naming consistent across runs.

Extra family:
- [ ] AC11 — `new/<CODE>.csv` inputs are read with utf-8-sig handling and BOM headers are normalized.
- [ ] AC12 — Row-level extra-core validation enforces required fields, surfaces invalid rows deterministically, and keeps valid rows.
- [ ] AC13 — Frame-level validation passes before write.
- [ ] AC14 — One bronze Parquet per extra file is written under `football_extra` partitioning (league code) with structure/naming consistent across runs.

Backfill & idempotency:
- [ ] AC15 — A backfill lands bronze Parquet for every whitelisted main (~689) and extra (~19) file.
- [ ] AC16 — Re-running skips already-landed historical files (no re-fetch, artifact unchanged) and always refreshes current-season files.

## 8. Things to be aware of / constraints

**Dependencies & sequencing**
- Discovery + throttled HTTP (Story #2) is foundational and must function before either
  family track can run; both tracks consume its output.
- Parent epic: **Story #1**. The two family tracks are independent of each other but both
  depend on #2.

**Full-backfill knock-ons (raised by the chosen "full backfill is part of done" scope —
this diverges from the investigation, which scoped the full backfill *out*):**
- Volume: ~689 main + ~19 extra files. At the mandated 0.4 s pacing, the throttle floor
  alone is ≈ 4–5 minutes of delay budget for a cold full run, before download/parse time.
- Skip-existing historical behaviour (AC16) is what keeps subsequent backfills cheap;
  without it a full re-run re-downloads everything. Treat it as load-bearing, not optional.
- Politeness: keep the 0.4 s pacing and skip-existing even during the initial backfill;
  `robots.txt` permits crawling but there is no published rate limit.

**Data contracts (domain vocabulary is the requirement here)**
- Two bronze tables, **not** one: `football_main` (core `Div, Date, HomeTeam, AwayTeam,
  FTHG, FTAG, FTR`; one season×division per file; season from URL path) and
  `football_extra` (core `Country, League, Season, Date, Home, Away, HG, AG, Res`; all
  seasons in one file; season in-file).
- Sparse canonical schema: enforce the core per record (Pydantic v2), let optional
  odds/stat columns ride along (Pandera `strict=False`). Do **not** enforce a wide schema
  and do **not** assume column stability — drift is severe (7 → 106 columns).
- Encodings are family-specific and mandatory: main = latin-1, extra = utf-8-sig.
- One Parquet artifact per source file; partition by family → league → season
  (main) / league code (extra). Bronze is faithful-to-source.

**Repo / platform constraints (from `CLAUDE.md` & `ARCHITECTURE.md`)**
- Validate at boundaries with **Pydantic v2**, DataFrame contracts via **Pandera**; config
  via **pydantic-settings** in `config.py` (add typed settings; no ad-hoc `os.getenv`).
- Mirror the existing edge-of-system pattern in `assets/bronze.py` (`raw_users`): the
  ingestion asset is the only thing touching the network, and an asset either produces its
  artifact or raises — **no silent fallbacks / defaults-on-failure / stubbed data**.
- **No `from __future__ import annotations`** in Dagster asset modules.
- When these bronze artifacts are later wired to dbt (out of scope here), remember dbt
  model **asset keys are prefixed by their model subfolder** and DuckDB is **single-writer
  / dbt owns the warehouse** — Python reads derived Parquet files, never the warehouse
  table mid-run.
- Use `pathlib.Path`; ruff-enforced PEP 8 (`E,W,F,I,UP,B,C4,SIM`); fix findings rather than
  suppressing.

**Lineage references (required on the story artifacts, AC6):**
- `architecture/football-data-ingestion.md`
- `temp/8c8290a/extracted_architecture__football-data-ingestion.md.json`
- `temp/8c8290a/arch_extracted_architecture__football-data-ingestion.md.json`

## 9. Assumptions

- **A1** — "Whitelist / known league registry" = the leagues characterized in the
  investigation (11 main leagues ≈ 689 files; ≈19 extra leagues). The exact registry
  contents are agreed at build time; this spec governs behaviour, not the list.
  **Implementation note (2026-06-26):** a live enumeration of the site found **16**
  extra leagues (`new/<CODE>.csv`), not ~19 — the registry in
  `src/data_platform/football/registry.py` reflects the real 16. The "~19" above was
  an estimate; AC15's count is likewise approximate.
- **A2** — Ingestion is run on demand via Dagster (materialization/job), consistent with
  the existing bronze asset pattern; no schedule is built (Non-goal).
- **A3** — "Current season" is determinable from the file's season identifier (URL path
  for main, in-file `Season` for extra) relative to the run date, so the always-refresh
  rule (AC5/AC16) can be applied deterministically.
- **A4** — Invalid-row reject counts recorded "in metadata" means Dagster asset
  metadata/logs (raw count, valid count, reject count per file); no separate quarantine
  artifact is produced (per the chosen skip-+-count policy).
- **A5** — On an unreachable/zero-valid file (E7/E8), failure is **isolated to that
  file/partition** (other files continue and the run surfaces the failed ones), rather
  than aborting the whole backfill. See Q-open if fail-fast is preferred instead.
- **A6** — "Consistent structure and naming across runs" means a deterministic output path
  and a stable column ordering/dtype contract for a given source file, not byte-identical
  Parquet.

## 10. Open questions

- **Q3 (non-blocking for bronze; blocks downstream gold publication)** —
  football-data.co.uk terms of use for downstream **redistribution**. Crawling is
  permitted (`robots.txt`), but the site disclaimer must be confirmed before any gold data
  is published externally. Does not block landing bronze.
- **Q-refresh-keying (resolve before build)** — the *mechanism* for "current-season vs
  historical" and skip-existing: re-fetch current season always (agreed); for historical,
  is skip-existing keyed purely on the landed artifact's presence, or should ETag/
  Last-Modified be honoured when the source provides it (content-hash otherwise)? Behaviour
  (AC16) is fixed; the keying mechanism is open.
- **Q-fail-isolation (resolve before build; see A5)** — confirm per-file/partition failure
  isolation vs fail-fast for the whole backfill on a persistently unreachable file.

## 11. Traceability

| User story | Story acceptance criteria covered | Scenarios | Spec acceptance criteria |
|------------|-----------------------------------|-----------|--------------------------|
| #2 (discover & throttle) | Deterministic content+order; whitelist-only; 0.4 s pacing; within-run cache (1 fetch); current-season always fetched; lineage refs present | Discovery is reproducible; Whitelist filtering excludes noise; Both families discovered; Relative/absolute dedup; Polite pacing; Within-run cache reuse; Current-season never cached | AC1, AC2, AC3, AC4, AC5, AC6 |
| main-bronze ingestion | latin-1 decode/parse; row-level main validation (invalid surfaced, valid continue); frame-level passes before write; bronze Parquet under football_main, consistent across runs | Latin-1 main file decodes; Row-level core skips invalid; Frame-level passes; Bronze lands under football_main; Full backfill; Historical skip; Current refresh | AC7, AC8, AC9, AC10, AC15, AC16 |
| extra-bronze ingestion | utf-8-sig normalized records; row-level extra validation (required fields, deterministic rejects); frame-level passes before write; bronze Parquet under football_extra, consistent naming across runs | utf-8-sig normalizes BOM headers; Row-level extra deterministic rejects; Frame-level passes; Bronze lands under football_extra; Full backfill; Historical skip; Current refresh | AC11, AC12, AC13, AC14, AC15, AC16 |
