# Findings

## Conclusion

**Answer to the question:** **Yes — ingesting football-data.co.uk as validated bronze
Parquet is feasible and fits the platform**, but *not* via the user's sample script. The
real work is **not downloading; it is schema management.** The source has two distinct
dataset families and a column set that grows from **7 → 106 columns** across 30 years.
A strict per-file model is impossible; a **sparse canonical schema (small mandatory core
+ everything else optional)** is the viable bronze contract, and it validates cleanly.

**Recommendation:** Build a Dagster bronze ingestion that:
1. **Discovers** links with `requests` + regex (no BeautifulSoup needed), restricted to a
   **known league registry**, not a blanket `*m.php` filter.
2. Handles **both dataset families** — main (`mmz4281/<season>/<div>.csv`, latin-1) and
   extra (`new/<CODE>.csv`, UTF-8-BOM) — as **two bronze tables** (different cores,
   different keys), not one.
3. Validates a **mandatory 7-field core** per record (Pydantic) and lets all optional
   odds/stat columns ride along (Pandera `strict=False`), landing **one Parquet per
   source file**, partitioned by family/league/season.
4. Throttles politely; records a stable file key for incremental refresh.

**Confidence: HIGH** — every claim below is backed by real downloaded files and a working
validated Parquet, not assumption. The two unknowns left (full terms-of-use posture;
incremental-refresh keying) are specification concerns, not feasibility blockers.

**Key evidence**
- Link discovery, requests-only: `evidence/spike1_discovery.json` (`code/spike1_discover.py`)
- Schema drift + validated Parquet: `evidence/spike2_report.json`,
  `evidence/spike2_schema_matrix.csv`, `evidence/spike2_bronze_sample.parquet`,
  raw samples in `evidence/samples/` (`code/spike2_schema_and_parquet.py`)

---

## Log

### 2026-06-26 — Spike 2: schema-drift map + bronze Parquet proof
- **What I did:** Downloaded a representative sample across eras/divisions (main family:
  E0 for 1993/94, 2000/01, 2010/11, 2023/24; plus E1/I1/SC0 2023/24) and the extra family
  (`new/ARG.csv`, `new/USA.csv`). Built a column-presence matrix; validated a unioned
  bronze frame with Pydantic (core) + Pandera (frame); wrote it to Parquet.
- **What I observed** (`evidence/spike2_report.json`, `spike2_schema_matrix.csv`):
  - **Column drift is severe**: main-family E0 grew **7 cols (1993/94) → 45 (2000/01) →
    71 (2010/11) → 106 (2023/24)**. Union of 7 sampled files = **146 columns**; 31 of them
    appear in only one file (the bookmaker-odds tail churns constantly).
  - **A stable core exists**: exactly 7 columns appear in *every* main file —
    `Div, Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR` — identical to the entire 1993/94 file.
  - **Validation earns its keep**: `9394/E0.csv` had 552 raw rows but only **462** passed
    core validation. 462 = exactly a 22-team season (22×21), i.e. Pydantic correctly
    rejected ~90 blank/footer rows. Recent files validate 100%.
  - **Two schema families, not one**: extra-family files have a *different* 25-col schema
    (`Country, League, Season, Date, Time, Home, Away, HG, AG, Res` + odds) and pack
    **all seasons into one file** (ARG = 6,235 rows; USA = 6,034), whereas main-family
    files are one season×division each and carry season only in the URL path.
  - **Encoding differs by family**: main files are latin-1/ASCII (`b'Div,Date,...'`);
    extra files are **UTF-8 with BOM** (`b'\xef\xbb\xbfCountry,...'`). Reading an extra
    file as latin-1 mangles the first header to `ï»¿Country`. Must use `utf-8-sig` there.
  - **Bronze Parquet proof:** unioned 7 main files → 2,762 validated rows × 148 cols,
    written to `evidence/spike2_bronze_sample.parquet`. The Pydantic-core + Pandera-
    `strict=False` pattern handles the optional-column sprawl with no per-file schema.
- **What it tells us:** The mandatory-core + sparse-optional design is correct and proven.
  Drift means we must NOT enforce a wide schema and must NOT assume CSV columns are stable.

### 2026-06-26 — Politeness / terms check
- **What I did:** Fetched `robots.txt`; checked acceptable-use signals.
- **What I observed:** `robots.txt` = `User-agent: * / Disallow:` (empty Disallow →
  crawling permitted site-wide). No rate hints. Site offers data free for personal use
  with a disclaimer page.
- **What it tells us:** Crawling is permitted; still throttle (used 0.4s/req). A full main
  backfill is ~689 files → keep a polite delay + on-disk caching/skip-existing. Confirm the
  site disclaimer/terms for any redistribution before publishing downstream. (Open Q3.)

### 2026-06-26 — Spike 1: link discovery (requests-only)
- **What I did:** Fetched `data.php`, regex-extracted `*m.php` country pages, then each
  league page's `.csv` links. (`code/spike1_discover.py`)
- **What I observed** (`evidence/spike1_discovery.json`):
  - **No BeautifulSoup needed** — `requests` + a single `href` regex discovers everything,
    so the platform stack is sufficient (H2 confirmed; closes Q1).
  - **11 real main leagues**, ~**689** season×division CSV files (England 153, Scotland
    122, Germany 66, France 63, Spain 63, Italy 62, Netherlands 33, Greece 32, Portugal 32,
    Turkey 32, Belgium 31). CSV shape: `mmz4281/<season>/<div>.csv`.
  - **The user's `endswith('m.php')` filter is buggy**: it also matches noise like
    `profitable_betting_system.php` and `downloadm.php` (both end in `m.php`), and treats
    relative + absolute URLs as different leagues → duplicate/garbage processing.
  - **It silently drops 19 extra leagues**: Argentina, Austria, Brazil, China, Denmark,
    Finland, Ireland, Japan, Mexico, Norway, Poland, Romania, Russia, Sweden, Switzerland,
    USA (+ more) live on plain `*.php` pages (no `m`) as `new/<CODE>.csv`. "All leagues"
    requires handling these explicitly.
- **What it tells us:** Discovery is easy but must be driven by a **known league registry**,
  not a blanket suffix filter, and must cover **both** families to honour the stated scope.
