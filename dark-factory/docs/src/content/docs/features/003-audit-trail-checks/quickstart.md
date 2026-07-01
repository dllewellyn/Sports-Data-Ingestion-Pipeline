---
title: "Quickstart — Code-Defined Audit Trail Checks"
---

# Quickstart — Code-Defined Audit Trail Checks

**Feature directory**: `specs/003-audit-trail-checks/`
**Date**: 2026-06-30

Runnable validation scenarios proving the feature works end-to-end. These are validation references —
the falsifiable red/green tests live in `tests/` (see plan.md §Testable units). Run from the repo
root (`/Users/danielllewellyn/dark-factory`), consistent with the feature-run hooks' repo-root-launch
requirement.

---

## Prerequisites

- `uv` installed; dev deps synced (`uv sync`).
- For the Grafana/Loki scenarios: the telemetry stack up
  (`cd telemetry && docker compose up -d`); Loki reachable at `http://localhost:3100`, Grafana at
  `http://localhost:3000` (admin/admin). Scenarios that do not mention Grafana need NO stack
  (fire-and-forget — SC-005).

---

## Scenario A — Author + run an audit, read the verdict (US1, SC-001/SC-002)

1. Create an audit file, e.g. `audits/example_audits.py`. Import the framework as `from audit import …`
   — the runner injects `.agents/skills/_shared/telemetry` onto `sys.path` before importing this file
   (there is NO `telemetry.audit` package path and NO `audit-run` console script — `pyproject.toml`
   sets `[tool.uv] package = false`):
   ```python
   from audit import audit, AuditFailure

   @audit(name="all_changed_files_code_reviewed", severity="high", category="review-integrity")
   def all_changed_files_code_reviewed(run):
       reviewed = run.get_all_reads_from_code_review_agent()
       unreviewed = sorted(f for f in run.all_diffs_for_feature() if f not in reviewed)
       if unreviewed:
           raise AuditFailure(evidence={"unreviewed_files": unreviewed})
   ```
2. Run the runner BY PATH against a recorded run (mirrors how `emit.py` is invoked):
   ```bash
   uv run python .agents/skills/_shared/telemetry/audit/runner.py \
       --run-id 20260630T132155Z-cce4e3 --path audits/example_audits.py
   ```
3. **Expected:** one verdict line per audit. On a run where every changed file was reviewed →
   `all_changed_files_code_reviewed: pass`, exit `0`. On a run with an unreviewed changed file →
   `all_changed_files_code_reviewed: fail` listing the unreviewed file(s), exit `1`. No Grafana
   needed.

## Scenario B — Two audits, one passes one fails; error isolation (US1 scenarios 3/4)

1. Add a second always-fails audit and a third that raises `ValueError` to the file.
2. `uv run python .agents/skills/_shared/telemetry/audit/runner.py --run-id <id> --path audits/example_audits.py`
3. **Expected:** three independent verdicts — `pass`, `fail`, `error` (the `error` one carries the
   exception detail and does NOT stop the others), exit `1`.

## Scenario C — No audits discovered (Edge E1)

1. `uv run python .agents/skills/_shared/telemetry/audit/runner.py --run-id <id> --path audits/empty.py` (a file with no `@audit`).
2. **Expected:** "no audits discovered" message, exit `2` (distinct from "all passed" `0`).

## Scenario D — Capture the real read path (US3, SC-003) — the hook enrichment proof

1. With the stack up and an instrumented feature run active, drive a sub-agent (e.g. the code-review
   role) through a `Read` of a known path, e.g. `src/foo.py`.
2. Query Loki for the captured value (the dedicated `tool_read` record, one per file-touching block):
   ```bash
   curl -s -G http://localhost:3100/loki/api/v1/query_range \
     --data-urlencode 'query={run_id="<id>"} | event_type="tool_read" | role="code-review"' \
     --data-urlencode 'limit=50' | grep -o 'src/foo.py'
   ```
3. **Expected:** `src/foo.py` appears as the `tool_input_value` attr of a `tool_read` record,
   attributable to the code-review role — proving the keys-only gap is closed (parallel Reads in one
   message each get their own `tool_read` record, no collision). The query helper
   `run.get_all_reads_from_code_review_agent()` returns a set containing `src/foo.py`.

## Scenario E — Results in Grafana, filterable by audit name + metadata (US2, SC-004)

1. After Scenario A/B with the stack up, open Grafana → **Feature Runs** dashboard, select the
   `feature` then `run_id`.
2. **Expected:** the "Audit results" panel shows one record per executed audit (name · verdict ·
   evidence); the "Audit failures" stat goes red on ≥1 fail.
3. In Explore, the structured-metadata filter works (the FR-015 idiom):
   ```logql
   {run_id="<id>"} | audit="all_changed_files_code_reviewed"
   {feature="003-audit-trail-checks"} | event_type="audit_result" | verdict="fail" | severity="high"
   ```

## Scenario F — Telemetry outage is harmless (US2 scenario 4, SC-005, FR-012)

1. Stop the stack: `cd telemetry && docker compose down`.
2. Re-run Scenario A.
3. **Expected:** identical verdicts and identical exit status — zero verdicts lost; the emission
   failure is silent and non-fatal.

## Scenario G — Empty change set is vacuously pass (US1 scenario 5, Edge E3)

1. Run the flagship audit against a run whose commits changed no files.
2. **Expected:** `all_changed_files_code_reviewed: pass` (nothing left unreviewed), exit `0` — not
   `error`/`fail`.

## Scenario H — Docs let a newcomer do it (SC-006)

1. Open the shipped docs page (Starlight site / `docs/src/content/docs/features/003-audit-trail-checks`
   plus the hand-authored guide).
2. **Expected:** a developer who has never seen the framework can follow it to author a passing audit
   and locate its result in Grafana, using the reproduced flagship example and the LogQL filter — with
   no further guidance.
