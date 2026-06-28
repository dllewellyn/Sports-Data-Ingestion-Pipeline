# Investigation: ESPN Unofficial API — Full Event Catalogue

**Question:** Can we query the ESPN unofficial API to discover and fetch all upcoming + historic football (soccer) and rugby union matches, without needing a pre-seeded list of competition IDs?

**Date:** 2026-06-28
**Status:** Complete — done criteria met

## Done criteria result
✅ A working spike (`code/spike_espn_discovery.py`) fetches upcoming + historic matches across soccer and rugby with zero hardcoded competition IDs, using only a sport name as input.

---

## Findings

### 1. League discovery is fully self-contained
Two endpoints on `sports.core.api.espn.com` list every league ESPN tracks:
- Soccer: 239 leagues, paginated, string slugs (e.g. `eng.1`, `uefa.champions`)
- Rugby: 25 leagues, numeric IDs (e.g. `180659` = Six Nations, `267979` = Gallagher Prem)

No seed data or config needed — one API call discovers the full catalogue.

### 2. Seasons expose exact date windows
Each league has a `/seasons` endpoint returning `startDate` / `endDate` per season. This means we can iterate seasons without guessing date ranges.
- EPL: 26 seasons available, back to 2001-02
- Rugby: varies by league; most have 2–5 seasons

### 3. Scoreboard endpoint supports arbitrary date windows
```
GET site.api.espn.com/apis/site/v2/sports/{sport}/{league_id}/scoreboard
    ?dates={YYYYMMDD}-{YYYYMMDD}&limit=1000
```
Returns all matches in that window. Tested:
- EPL full season = 380 matches ✅
- Six Nations 2025 = 15 matches ✅
- Rugby World Cup 2023 = 48 matches ✅

### 4. Sport slug for rugby is just `rugby`
`rugby-union`, `rugby_union` → 400 error. `rugby` covers all codes (union, league, sevens). The scoreboard endpoint uses the same slug.

### 5. No auth, no API key
Fully public. A `User-Agent` browser header is enough. 20 rapid requests in 9s produced zero errors; the API is not aggressively rate-limited. A 0.1s sleep between calls is sufficient courtesy.

### 6. provider_entity_cache is confirmed dead
The original ESPN ingestion queried this table for competition IDs, but it was never populated by any code. The table can be dropped from the migration entirely — league discovery replaces it cleanly.

---

## The pattern (3 API calls per league per season)

```
1. GET /v2/sports/{sport}/leagues?limit=100   → all league IDs
2. GET /v2/sports/{sport}/leagues/{id}/seasons → startDate, endDate per season
3. GET /site/.../scoreboard?dates={start}-{end} → all match events
```

Total for a full refresh of all soccer + rugby (239 + 25 leagues × ~3 seasons each):
~800 API calls, at 0.1s spacing ≈ ~80 seconds. Very manageable for a daily or 6-hourly job.

---

## Limitations / open questions

1. **Rugby sub-sport filtering**: The `rugby` slug returns all rugby codes (union, league, 7s). We'd want to filter by league ID to get only union competitions. The 25 leagues we discovered include sevens (IDs 282, 283) and women's (289237). Easy to exclude by ID allowlist or by fetching league metadata and checking a flag.

2. **Match status completeness**: The scoreboard returns `STATUS_SCHEDULED`, `STATUS_IN_PROGRESS`, `STATUS_FINAL`, etc. Historic matches correctly show `STATUS_FINAL`. No gaps observed.

3. **Depth vs. breadth tradeoff**: Fetching all 239 soccer leagues × last 3 seasons = 717 scoreboard requests. For the migration we likely only want a curated subset (e.g. top-flight European leagues + international tournaments). This is config, not a discovery limitation.

---

## Recommendation

**Yes, this is feasible — move to Specification.**

The recommended architecture for the migrated ESPN ingestor:

- **Config**: a small allowlist of league slugs/IDs per sport (e.g. `SOCCER_LEAGUES = ["eng.1", "esp.1", "uefa.champions"]`, `RUGBY_LEAGUES = ["180659", "267979", "270557"]`). This replaces `provider_entity_cache` entirely.
- **Discovery**: on each run, fetch seasons for each configured league, determine which season windows overlap with "today ± N days", and fetch only those scoreboards.
- **Historic backfill**: same code path, just iterate all seasons back to a configured cutoff year.
- **Output**: Parquet to `data/bronze/espn_matches/` — one file per league per season, matching the football-data.co.uk convention already in the target project.
