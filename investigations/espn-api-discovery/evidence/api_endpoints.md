# ESPN Unofficial API — Confirmed Endpoints

## League Discovery

### Soccer (239 leagues, string slugs)
```
GET https://sports.core.api.espn.com/v2/sports/soccer/leagues?limit=100&page={n}
Response: { count, pageCount, pageSize, items: [{$ref}] }
Slug extraction: ref.split("/leagues/")[1].split("?")[0]  → e.g. "eng.1"
```

### Rugby (25 leagues, numeric IDs)
```
GET https://sports.core.api.espn.com/v2/sports/rugby/leagues?limit=100
Response: { count, items: [{$ref}] }
ID extraction: ref.split("/leagues/")[1].split("?")[0]  → e.g. "180659"
```

### League Detail (name, slug)
```
GET https://sports.core.api.espn.com/v2/sports/{soccer|rugby}/leagues/{id}
Response: { id, name, displayName, abbreviation, slug, season, seasons:{$ref}, ... }
```

## Season Discovery
```
GET https://sports.core.api.espn.com/v2/sports/{soccer|rugby}/leagues/{id}/seasons?limit=N
→ items[i].$ref → GET that ref
Response: { year, startDate, endDate, ... }

EPL example: 26 seasons available back to 2001-02
```

## Scoreboard (matches within a date window)
```
GET https://site.api.espn.com/apis/site/v2/sports/{soccer|rugby}/{league_id}/scoreboard
    ?dates={YYYYMMDD}-{YYYYMMDD}&limit=1000

Response: { events: [...], leagues, season, day, provider }

Event fields:
  id, date, name, shortName, status, venue, season, competitions: [
    { competitors: [{ homeAway, team: { id, displayName } }],
      status: { type: { name } } }
  ]
```

## Known Working Sport Slugs
| Sport | Slug for core API | Slug for scoreboard |
|-------|------------------|---------------------|
| Soccer/Football | `soccer` | `soccer` |
| Rugby (all codes) | `rugby` | `rugby` |

Note: `rugby-union`, `rugby_union` → 400 error. Just `rugby` works and covers Union, League, 7s.

## Rate Limits
- No auth required (public API)
- 20 rapid requests in ~9s with zero errors — no aggressive rate limiting observed
- Recommend 0.1s sleep between calls to be courteous

## Historic Depth
- EPL: 26 seasons back to 2001-02
- Rugby: varies by league; RWC has 2023, 2027 (future) available

## Rugby League IDs of Interest
| ID | Name |
|----|------|
| 164205 | Rugby World Cup |
| 180659 | Six Nations |
| 244293 | The Rugby Championship |
| 267979 | Gallagher Prem |
| 270557 | United Rugby Championship |
| 270559 | French Top 14 |
| 242041 | Super Rugby Pacific |
