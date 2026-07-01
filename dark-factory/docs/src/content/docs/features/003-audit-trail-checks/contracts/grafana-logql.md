---
title: "Contract — Grafana / LogQL surfacing of audit results (FR-013)"
---

# Contract — Grafana / LogQL surfacing of audit results (FR-013)

Audit results are surfaced by **extending the existing `feature-runs` dashboard**
(`telemetry/grafana/dashboards/feature-runs.json`) — NOT a parallel stack. Filtering by
`feature`/`run_id` uses the existing index-label template dropdowns; filtering by audit name / metadata
uses LogQL **structured-metadata** filters (`| audit="…"`), NOT a new index label.

## The structured-metadata idiom (FR-015 requires at least one runnable example)

All of these run against Loki HTTP API host port `3100` (`/loki/api/v1/query_range`) and in Grafana
Explore. The stream selector uses index labels; the `|` filters are structured metadata:

```logql
# every audit result for a run
{run_id="$run_id"} | event_type="audit_result"

# the flagship audit's result for a run (THE structured-metadata example authors learn from)
{run_id="20260630T132155Z-cce4e3"} | audit="all_changed_files_code_reviewed"

# only failing audits for a feature, by severity
{feature="003-audit-trail-checks"} | event_type="audit_result" | verdict="fail" | severity="high"
```

The key teaching point (FR-015): `audit`, `verdict`, `severity`, `category`, `owner`, `evidence` are
**structured metadata**, queried with `| key="value"` — they are NOT index labels and must NOT be put
inside the `{…}` selector.

## Dashboard panels to add (extend feature-runs.json)

| Panel | Type | Query |
|-------|------|-------|
| "Audit failures" stat (red on ≥1) | stat | `sum(count_over_time({run_id="$run_id"} \| event_type="audit_result" \| verdict="fail" [$__range]))` |
| "Audit results" log panel (name · verdict · evidence) | logs | `{run_id="$run_id"} \| event_type="audit_result"` |

These mirror the existing "Gate failures" stat and "Gates" log panels (same shape, same datasource
`loki`), so the convention is the existing file. No `loki-config.yaml` change.

## Verification (acceptance)

- US2 scenario 1: after a run, `{run_id="…"} | event_type="audit_result"` returns one record per
  executed audit, each carrying `audit`, `verdict`, `feature`, `run_id`.
- US2 scenario 2: `| severity="high"` / `| category="review-integrity"` filters work (metadata is
  structured-metadata).
- US2 scenario 3: the failing record's `evidence` attr is readable in the log panel.
