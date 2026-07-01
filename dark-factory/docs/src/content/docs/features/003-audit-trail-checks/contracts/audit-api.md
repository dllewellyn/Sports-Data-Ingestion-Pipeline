---
title: "Contract — `@audit` framework public API"
---

# Contract — `@audit` framework public API

The interface audit authors and the runner depend on. Stdlib-only, fire-and-forget on the emit side
(mirrors `emit.py`). Module location: a new package under
`.agents/skills/_shared/telemetry/audit/` (sibling to `emit.py`).

## Importability + invocation (Finding 4 — mirror `emit.py`, no console script)

`pyproject.toml` sets `[tool.uv] package = false` — there is **no** console-script packaging, so the
framework introduces **no** `[project.scripts] audit-run` entry point. Both the import path and the
invocation mirror `emit.py`:

- **Invoke the runner BY PATH:** `uv run python .agents/skills/_shared/telemetry/audit/runner.py [opts]`.
- **Audit files import the framework as** `from audit import audit, AuditFailure, AuditWarning` — the
  runner prepends `.agents/skills/_shared/telemetry` (the package's parent dir) onto `sys.path` before
  importing the configured audit file, exactly as the hooks insert the shared telemetry dir for
  `import emit` and `conftest.py` inserts the repo root. NOT `from telemetry.audit import …`.

## Decorator

```python
def audit(_func=None, *, name=None, **metadata):
    """Register an audit check. Usable bare (@audit) or called (@audit(name=..., severity=...)).

    name: unique audit name (defaults to func.__name__). Duplicate name => AuditNameCollision at
          import/registration time (Edge E4).
    metadata: open key/value set (FR-002); recommended severity/category/owner; values str-coerced.

    The wrapped function receives one positional arg: a FeatureRunQuery handle (the run under audit).
    """
```

## Failure signalling (FR-001, FR-004)

```python
class AuditFailure(Exception):
    def __init__(self, evidence=None): ...   # -> verdict "fail", carries evidence (FR-005)

class AuditWarning(Exception):
    def __init__(self, evidence=None): ...   # -> verdict "warn" (Edge E8), distinct from pass/fail/error
```

- Clean return ⇒ `pass`. `AuditFailure` ⇒ `fail`. `AuditWarning` ⇒ `warn`. Any **other** exception ⇒
  `error` (FR-004; never coerced to pass — Constitution IV / Edge E2).

## Run query surface (FR-008)

```python
class FeatureRunQuery:
    run_id: str
    feature: str
    def get_all_reads_from_code_review_agent(self) -> set[str]: ...   # by role (R5)
    def reads_by_role(self, role: str) -> set[str]: ...
    def all_diffs_for_feature(self) -> set[str]: ...                  # union of commit git_files
```

- `reads_by_role(role)` filters `{run_id="…"} | event_type="tool_read" | role="…"` and reads the
  `tool_input_value` attr off each record cleanly (Finding 1) — it does NOT grep free-text `body`.
  `get_all_reads_from_code_review_agent()` is `reads_by_role(<code-review role>)`.
- `all_diffs_for_feature()` filters `{run_id="…"} | event_type="commit"` and unions the comma-split
  `git_files` attr.

- `run_id` resolved explicitly or via the active run context (`run-context.sh current`, FR-006).

### Known vs unknown run — the E2/E3 discriminator (Finding 3)

Both "unknown run" (E2) and "known run, empty diff" (E3) can *look like* "the query returned nothing",
so the discriminator is pinned here and enforced in `query.py`:

- A run is **known** iff **at least one record of ANY `event_type` exists for its `run_id`**. The
  query layer issues a probe (`{run_id="…"}` with no event filter, `limit=1`); zero hits ⇒ the run is
  unknown.
- **Unknown run (E2)** ⇒ the query method **raises** `UnknownRunError(run_id)` → the runner's per-audit
  try/except turns it into the distinct `error` verdict (never a silent `pass`).
- **Known run, zero commit `git_files` (E3)** ⇒ `all_diffs_for_feature()` legitimately returns the
  **empty set** (no raise) → the flagship audit finds nothing unreviewed → vacuous `pass`.

So `get_all_reads_from_code_review_agent()` / `reads_by_role()` / `all_diffs_for_feature()` return
empty sets only for *known* runs; against an *unknown* run they raise. The probe runs once and is
cached on the `FeatureRunQuery` instance.

## Runner (FR-003, FR-007, FR-014)

```
uv run python .agents/skills/_shared/telemetry/audit/runner.py \
    [--run-id RUN_ID] [--feature FEATURE] [--path AUDIT_PATH] [--loki-endpoint URL]
```

- Prepends `.agents/skills/_shared/telemetry` onto `sys.path`, then imports the configured `--path`
  audit file so `@audit` registration populates the registry; iterates it. (No console script —
  Finding 4.)
- Runs every discovered audit (FR-003), isolating each (one `error` never stops the rest — FR-007).
- Prints a per-audit verdict line + evidence on fail (US1: readable without Grafana).
- Emits one `AuditResultRecord` per audit via `emit.send_logs` (FR-011), fire-and-forget (FR-012).
- **Exit status (R2 / FR-014):** any `fail`/`error` ⇒ `1`; only `pass`/`warn` ⇒ `0`; no audits
  discovered ⇒ `2` (distinct from "all passed" — Edge E1).
