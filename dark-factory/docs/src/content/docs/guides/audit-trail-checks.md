---
title: Code-defined audit trail checks
description: Write an @audit function over a feature run's telemetry, run it, and find its result in Grafana.
---

An **audit** is a plain Python function, decorated `@audit`, that expresses a rule about a
feature run — for example, "every file changed across the feature's diffs was read by the
code-review agent". You write the rule; a runner discovers every `@audit`, evaluates each
against a run's recorded telemetry, prints a `pass`/`fail`/`error`/`warn` verdict with
concrete evidence on failure, and emits each result into Loki so it shows up on the
**Feature Runs** Grafana dashboard.

The framework lives beside `emit.py` at `.agents/skills/_shared/telemetry/audit/`. It is
stdlib-only and — like `emit.py` — is invoked **by path**; there is no console script
(`pyproject.toml` sets `[tool.uv] package = false`).

## Write an `@audit` function

Import the framework as `from audit import audit, AuditFailure, AuditWarning`. The decorator
registers the function in a module-level registry at import time. Signal a failure by
**raising** — never by return value:

- a clean return ⇒ `pass`
- `raise AuditFailure(evidence=…)` ⇒ `fail` (the evidence rides on the result)
- `raise AuditWarning(evidence=…)` ⇒ `warn` (a non-fatal finding)
- any other uncaught exception ⇒ `error` (never coerced to `pass`)

Your function receives one argument — a `FeatureRunQuery` handle scoped to the run under
audit. Read the run's telemetry through its helpers; never hand-roll a Loki query.

The flagship example — every changed file must have been read by the code-review agent:

```python
from audit import audit, AuditFailure, AuditWarning

@audit(name="all_changed_files_code_reviewed", severity="high", category="review-integrity")
def all_changed_files_code_reviewed(run):
    reviewed = run.get_all_reads_from_code_review_agent()
    unreviewed = sorted(f for f in run.all_diffs_for_feature() if f not in reviewed)
    if unreviewed:
        raise AuditFailure(evidence={"unreviewed_files": unreviewed})
```

(`AuditWarning` is imported here for completeness — raise it from a rule that should surface
a soft finding rather than a hard failure.)

## The query helpers

`FeatureRunQuery` reads a run's recorded telemetry over the Loki HTTP API (read-only):

| Helper | Returns |
|--------|---------|
| `run.get_all_reads_from_code_review_agent()` | the set of file paths the **code-review** agent read (by telemetry `role`) |
| `run.reads_by_role(role)` | the set of file paths read by any given role |
| `run.all_diffs_for_feature()` | the union of files changed across the run's commit records |

Reads are attributed by the agent's **`role`**, not by `agent_id`. A run with **no recorded
telemetry** is *unknown*: the helpers raise `UnknownRunError`, which the runner reports as
the distinct `error` verdict (never a false `pass`). A *known* run that simply changed no
files legitimately returns the empty set — so the flagship above is a vacuous `pass`.

## Declare metadata

`@audit(name=…, **metadata)` accepts an open set of key/value metadata; the recommended keys
are `severity`, `category`, and `owner`, but you may add your own. Every metadata value is
recorded as Loki **structured metadata** on the audit result, so it is filterable in Grafana
(e.g. `| severity="high"`). Give each audit a **unique name** — a duplicate name is refused.

## Run the runner (by path)

Invoke the runner by path, exactly like `emit.py` — there is **no** installed console
script. Point it at your audit file and a run:

```bash
uv run python .agents/skills/_shared/telemetry/audit/runner.py \
    --run-id 20260630T132155Z-cce4e3 --path audits/example_audits.py
```

The runner prepends `.agents/skills/_shared/telemetry` onto `sys.path` before importing your
audit file, so the bare `from audit import …` resolves. It prints one verdict line per audit
(with evidence on `fail` and the detail on `error`), and its **exit status** gates automated
workflows:

- any `fail` or `error` ⇒ exit `1`
- only `pass`/`warn` ⇒ exit `0`
- no audits discovered ⇒ exit `2` (distinct from "all passed")

One audit raising an error never stops the others — every discovered audit runs and reports.
The flagship `all_changed_files_code_reviewed` ships as a built-in; pass `--no-builtins` to
run only the audits in your `--path` file.

## Find results in Grafana

Every executed audit emits one `event_type="audit_result"` log record into Loki,
fire-and-forget — a telemetry outage never changes a verdict or the exit status. Open the
**Feature Runs** dashboard, pick the `feature` then `run_id`: the **Audit results** panel
lists each audit (name · verdict · evidence) and the **Audit failures** stat turns red on any
`fail`.

Audit name and metadata ride as **structured metadata**, queried with `| key="…"` — they are
NOT index labels, so they never go inside the `{…}` stream selector. In Grafana Explore:

```logql
{run_id="20260630T132155Z-cce4e3"} | audit="all_changed_files_code_reviewed"
{feature="003-audit-trail-checks"} | event_type="audit_result" | verdict="fail" | severity="high"
```
