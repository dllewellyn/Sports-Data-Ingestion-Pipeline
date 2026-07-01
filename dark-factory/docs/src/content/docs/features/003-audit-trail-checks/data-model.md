---
title: "Phase 1 Data Model — Code-Defined Audit Trail Checks"
---

# Phase 1 Data Model — Code-Defined Audit Trail Checks

**Feature directory**: `specs/003-audit-trail-checks/`
**Date**: 2026-06-30

Entities extracted from the spec's *Key Entities* and *Requirements*. These are in-process Python
objects and telemetry records — there is no database. "Validation rules" are the invariants the code
must enforce; "state transitions" describe verdict derivation.

---

## 1. AuditCheck (the decorated function + its metadata)

The registered unit. Created when `@audit(...)` decorates a function and registers it.

| Field | Type | Notes / validation |
|-------|------|--------------------|
| `name` | str | Required, unique across the registry (Edge E4 — duplicate ⇒ registration error). Defaults to the function's `__name__` when not given explicitly. |
| `func` | callable | The audit body. Receives the run-query handle (see `FeatureRunQuery`). |
| `metadata` | dict[str, str] | Open key/value set (FR-002). Recommended keys: `severity`, `category`, `owner`. Authors may add their own. All values coerced to `str` for emission. |

**Validation rules.**
- `name` non-empty and unique (registry refuses duplicates deterministically — E4).
- `metadata` keys/values must be string-coercible (they become Loki structured-metadata attrs).

---

## 2. AuditResult (the outcome of evaluating one AuditCheck against one run)

| Field | Type | Notes / validation |
|-------|------|--------------------|
| `audit_name` | str | From the AuditCheck. |
| `verdict` | enum: `pass` \| `fail` \| `error` \| `warn` | Fixed set (FR-004). `fail` and `error` distinguishable. |
| `run_id` | str | The evaluated run (FR-006, FR-011). |
| `feature` | str | The run's bound feature slug (FR-011). |
| `metadata` | dict[str, str] | Copied from the AuditCheck (FR-011). |
| `evidence` | dict / str / None | Present on `fail` (and where applicable `warn`) — the concrete explanation, e.g. `{"unreviewed_files": [...]}` (FR-005). `None` on `pass`. |
| `error_detail` | str / None | Present only on `error` — the exception summary (FR-004, Edge E2/B). Bounded in size. |
| `timestamp_ns` | int | When the result was produced. |

**State transitions (verdict derivation, R6).**
```
audit body runs ─┬─ returns cleanly ──────────────► pass   (evidence=None)
                 ├─ raises AuditFailure(evidence) ─► fail   (evidence set)
                 ├─ raises AuditWarning(evidence) ─► warn   (evidence optional)
                 └─ raises any other Exception ────► error  (error_detail=summary)
```
One audit's `error` MUST NOT stop the others (FR-007) — each runs in its own try/except.

---

## 3. FeatureRun / FeatureRunQuery (the query surface over recorded telemetry)

The handle an audit body uses to read the run's telemetry (US3, FR-008). Resolves `run_id` from the
active run context when not given (FR-006), then queries Loki.

| Field / method | Type | Notes |
|----------------|------|------|
| `run_id` | str | Resolved explicitly or via `run-context.sh current --field run_id`. |
| `feature` | str | Resolved from the run context. |
| `get_all_reads_from_code_review_agent()` | → set[str] | File paths read by the **code-review role** (R5) — the union of `tool_input_value` from `event_type="tool_read"` records whose `role` is the code-review role (read cleanly off the attr, NOT grepped from `body` — Finding 1). |
| `reads_by_role(role)` | → set[str] | Generalised: `tool_input_value`s from `tool_read` records for any role. |
| `all_diffs_for_feature()` | → set[str] | Union of changed files across the run's `event_type="commit"` records' `git_files` (comma-joined string → set). Data exists today. |

**Validation rules (E2/E3 discriminator — Finding 3).**
- A run is **known** iff at least one record of ANY `event_type` exists for its `run_id` (a one-shot
  `{run_id="…"}` probe, `limit=1`, cached on the instance).
- **Unknown run (Edge E2):** the probe finds zero records ⇒ the query methods **raise**
  `UnknownRunError`; the runner turns that into the distinct `error` verdict, never a false `pass`.
- **Known run, empty result (Edge E3):** for a known run, `all_diffs_for_feature()` returning `∅`
  (zero commit `git_files`) is legitimate and does NOT raise ⇒ flagship audit is vacuously `pass`.
  Empty read sets for a known run are likewise legitimate.

---

## 4. ToolReadRecord (the dedicated per-block telemetry record — FR-009/FR-010)

The capture the hook enrichment produces. Today one transcript record folds a whole message (which may
carry MANY `tool_use` blocks) into a single `body` and records only tool-input *keys*. This entity is a
**dedicated log record emitted once per file-touching `tool_use` block** (`event_type="tool_read"`),
so parallel Reads/Edits in one message do NOT collide on one key (Finding 1). It is yielded by
`_transcript_records`/`_summarize_content` and sent through the same `emit.send_logs` path as the
existing transcript records.

| Field (telemetry attr) | Carrier | Type | Notes |
|------------------------|---------|------|------|
| `event_type` | per-record attr | str = `tool_read` | **NEW value** — distinct from `transcript`; the query filter key. |
| `tool_name` | per-record attr | str | `Read`/`Edit`/`Write`/`Grep`/`Glob`. |
| **`tool_input_value`** | per-record attr | str | **NEW** — the path (`file_path`) for Read/Edit/Write, the pattern[+`path`] for Grep/Glob. Masked (R10) then bounded to `MAX_TOOL_INPUT_VALUE = 512` chars (R1). |
| `role` | per-record attr | str | The acting agent's role (already threaded into `_transcript_records`). The attribution key (R5). |
| `agent_id` | per-record attr | str | Already threaded into `_transcript_records`. |
| `msg_index` | per-record attr | int | The transcript line index (carried from the existing records). |
| **`value_truncated`** | per-record attr | "true" (only when truncated) | **NEW** — Edge E5; marks truncation so it is observable, not silent. |
| **`value_len`** | per-record attr | str(int) (only when truncated) | **NEW** — original length. |
| **`value_redacted`** | per-record attr | "true" (only when masked) | **NEW** — set when R10 secret-masking fired. |
| `run_id` / `feature` / `service.name` | resource attr | str | The existing index labels (set by `send_logs`). |
| body | — | str | Human-readable `tool_read <tool_name> <tool_input_value>`. |

**Validation rules (FR-010, Security).**
- **Secret-safe (applied first, R10).** Capture-scope already limits the captured field to path/pattern
  keys only (never arbitrary tool input). The one realistic leak vector — a `Grep`/`Glob` `pattern`
  that IS a secret being searched for — is handled by a concrete, tested redaction rule: a value
  matching the named high-entropy / secret-prefix regex (`sk-`, `ghp_`, `AKIA`, `xox*-`, JWT, ≥40-char
  base64 blob) is masked to first/last 4 chars and flagged `value_redacted="true"`. Ordinary paths and
  globs do NOT match (tested negative). See research R10.
- **Bounded.** Value bounded to `MAX_TOOL_INPUT_VALUE`; over-bound ⇒ truncated + `value_truncated="true"`
  + `value_len`.
- **No legacy keys-only path retained** for the file-touching tool set (Constitution I) — the keys-only
  body summary is *removed* for those tools, not kept alongside the dedicated `tool_read` record.
  Non-file-touching tools keep their existing keys-only body summary.

---

## 5. AuditResultRecord (the emitted telemetry log record — FR-011)

How an AuditResult lands in Loki via `emit.send_logs`.

| Carrier | Field | Loki treatment |
|---------|-------|----------------|
| resource attr | `run_id` | **index label** (existing) |
| resource attr | `feature` | **index label** (existing) |
| resource attr | `service.name` | **index label** (existing) |
| per-record attr | `event_type="audit_result"` | structured metadata |
| per-record attr | `audit` = audit_name | structured metadata — the LogQL filter key `| audit="…"` |
| per-record attr | `verdict` | structured metadata `| verdict="…"` |
| per-record attr | each metadata key (`severity`, `category`, `owner`, …) | structured metadata |
| per-record attr | `evidence` | structured metadata (bounded string form) |
| body | human-readable `audit <name> -> <VERDICT>` | log line |

**Invariant (FR-011, Assumptions, clarify Q1).** The audit name and ALL declared metadata travel as
per-record attrs (structured metadata), NEVER as new Loki index labels. `loki-config.yaml`
`attributes_config` is NOT touched.
