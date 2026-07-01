---
title: "PROPOSED project rule — `@audit` framework convention (DRAFT, approval-pending)"
---

# PROPOSED project rule — `@audit` framework convention (DRAFT, approval-pending)

Status: **created-pending-approval** — drafted by the `plan` skill's convention-audit hard gate
(via `create-rule`) in non-interactive mode. **NOT committed.** This is BLOCKER-1: the rule MUST NOT
be written into the constitution until a human approves it. Target file once approved: the project
constitution (`.specify/memory/constitution.md`, a new sub-section under *Development Workflow &
Quality Gates*), because the project keeps conventions there + in `CLAUDE.md` and has no
`.claude/rules/` dir.

This file lives durably inside the feature directory so the convention-audit row "created this run"
is real and discoverable across sessions (it does NOT depend on an ephemeral session scratchpad).

Proposed rule text (concise, true/false-framed, with a minimal example):

---

### Code-defined audit checks (`@audit`)

- **ALWAYS** define an audit check as a single function decorated `@audit(name="…", **metadata)`; the
  decorator registers it in the module-level audit registry at import time. NEVER discover audits by
  scanning source text.
- **ALWAYS** signal a failure by raising the framework's `AuditFailure(evidence=…)` (and a soft
  finding by raising `AuditWarning`); a clean return is `pass`. NEVER signal pass/fail by return value
  alone, and NEVER swallow an unexpected exception inside an audit — an uncaught exception is reported
  as the distinct `error` verdict by the runner.
- **ALWAYS** give each audit a unique `name`; NEVER register two audits under the same name (the
  registry refuses the duplicate).
- **ALWAYS** read a run's telemetry through the provided query helpers
  (`get_all_reads_from_code_review_agent()`, `all_diffs_for_feature()`, …); NEVER hand-roll a Loki
  query inside an audit body.
- **ALWAYS** resolve "which agent" by the telemetry `role` attribute, NEVER by `agent_id`.
- **ALWAYS** import the framework as `from audit import audit, AuditFailure, AuditWarning` (the runner
  injects `.agents/skills/_shared/telemetry` onto `sys.path` before importing the audit file);
  NEVER assume a `telemetry.audit` package path or a `[project.scripts]` console entry point — the
  runner is invoked by path (`uv run python .agents/skills/_shared/telemetry/audit/runner.py …`),
  mirroring `emit.py` (the repo's `pyproject.toml` sets `[tool.uv] package = false`).

Minimal example:

```python
from audit import audit, AuditFailure

@audit(name="all_changed_files_code_reviewed", severity="high", category="review-integrity")
def all_changed_files_code_reviewed(run):
    reviewed = run.get_all_reads_from_code_review_agent()
    unreviewed = [f for f in run.all_diffs_for_feature() if f not in reviewed]
    if unreviewed:
        raise AuditFailure(evidence={"unreviewed_files": sorted(unreviewed)})
```

Source/rationale: derived from the feature spec (`specs/003-audit-trail-checks`) FR-001..FR-008 and the
repo's existing stdlib/fire-and-forget telemetry conventions (`emit.py`, the hooks). Mirrors the
decorator-registry discovery pattern used by pytest/click/Flask.
