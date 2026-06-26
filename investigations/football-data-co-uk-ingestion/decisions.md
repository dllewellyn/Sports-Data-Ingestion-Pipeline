# Decisions

## Made
- D1 (2026-06-26): Investigation deliverable is an **approach recommendation doc**, not
  production code. Backed by a disposable spike that lands a validated bronze Parquet
  sample. — rationale: user's chosen done criteria + target output.
- D2 (2026-06-26): Scope target is **all leagues / all history**, but the spike only
  *samples* leagues/seasons during the investigation; no full backfill now.

- D3 (2026-06-26): **No BeautifulSoup.** Link discovery uses `requests` + a regex; the
  platform stack is sufficient. — closes Q1 (evidence: spike1).
- D4 (2026-06-26): **Sparse canonical bronze schema** — enforce a small mandatory core
  per record (Pydantic), let all optional odds/stat columns ride along (Pandera
  `strict=False`). A strict/wide schema is rejected. — closes Q2 (evidence: spike2).
- D5 (2026-06-26): **Treat the two dataset families as two bronze tables** — main
  (`mmz4281/<season>/<div>.csv`, latin-1, core = Div/Date/HomeTeam/AwayTeam/FTHG/FTAG/FTR,
  season from URL) and extra (`new/<CODE>.csv`, utf-8-sig, core = Country/League/Season/
  Date/Home/Away/HG/AG/Res, season in-file). Not one unified schema.
- D6 (2026-06-26): **Drive discovery from a known league registry**, not a blanket
  `*m.php` suffix filter (which matches noise and drops all 19 extra leagues).

## Closed / resolved
- Q1 → D3. Q2 → D4. (See above.)

## Open questions (for Specification)
- Q3: football-data.co.uk terms of use for downstream **redistribution** (robots.txt
  permits crawling; the site disclaimer should be confirmed before publishing gold data
  externally). Acceptable request rate: no published limit — default to polite throttle.
- Q4: Incremental-refresh keying — current-season files (e.g. `mmz4281/2526/E0.csv`) are
  updated in-place mid-season; extra-league `new/<CODE>.csv` files grow over time. Need a
  refresh strategy (re-fetch current season always; ETag/Last-Modified if available;
  content hash otherwise). Historical seasons are immutable → fetch once.
- Q5: Partition/naming layout for ~689+19 Parquet files under `data/bronze/` and how
  silver/gold should unify the two families (or keep them separate marts).
