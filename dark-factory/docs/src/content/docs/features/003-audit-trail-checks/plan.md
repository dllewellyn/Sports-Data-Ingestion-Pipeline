---
title: "Implementation Plan: Code-Defined Audit Trail Checks"
---

# Implementation Plan: Code-Defined Audit Trail Checks

**Feature directory**: `specs/003-audit-trail-checks/`
**Date**: 2026-06-30
**Spec**: `spec.md`
**Status**: Draft

## Summary

Build a code-defined audit-trail framework on top of the existing feature-run telemetry substrate. An
author writes a plain Python function decorated `@audit(name=…, **metadata)` that expresses a rule
about a feature run (flagship: "every changed file was read by the code-review agent"); a runner
discovers all such functions, evaluates each against a run's recorded telemetry, and produces a
`pass`/`fail`/`error`/`warn` verdict with concrete evidence on failure — readable from the runner's own
output and emitted (fire-and-forget) into Loki so it shows up on the existing Feature Runs Grafana
dashboard, filterable by `feature`/`run_id` (index labels) and audit name/metadata (LogQL structured
metadata). The one hard prerequisite is closing a known gap: the transcript-ingest hook
(`subagent_stop.py`, `_transcript_records`/`_summarize_content`) records only tool-input *keys* today
and folds a whole message into one `body`; we **replace** that for file-touching tools by **emitting one
dedicated `event_type="tool_read"` record per file-touching `tool_use` block** (so parallel Reads/Edits
don't collide on one key), each carrying the bounded, secret-safe, role-attributable path/pattern
*value* as a `tool_input_value` attr. The query helper then reads that attr cleanly via
`{run_id="…"} | event_type="tool_read" | role="…"` rather than grepping free-text. Everything is
stdlib-only (`urllib`, like `emit.py`), the runner is invoked **by path** (`uv run python
.agents/skills/_shared/telemetry/audit/runner.py …`; no console script — `pyproject.toml` has
`[tool.uv] package = false`), uses the repo's `uv`+`pytest` harness, and adds no new index label and no
`loki-config.yaml` change.

## Technical Context

**Language/Version**: Python 3.12 (`requires-python >=3.12`)
**Primary Dependencies**: stdlib only at runtime (`urllib`, `json`, `os`, `argparse`) — mirrors
`emit.py`; **no pydantic-settings** (not a repo dependency — see research R4). `pytest` for tests.
**Storage**: none added — reads recorded telemetry from Loki (host `:3100`,
`/loki/api/v1/query_range`); writes audit results via `emit.send_logs` to the collector (host `:14318`).
**Testing**: `pytest` under `tests/` (existing harness); shell touched (none expected) would be tested
via `subprocess`; live-stack scenarios are quickstart references, not unit tests.
**Target Platform**: developer/CI-invoked Python entry point run from repo root (not a service).
**Project Type**: single project (framework tooling under `.agents/skills/_shared/telemetry/`).
**Performance Goals**: N/A — low-volume, evidence-bearing audit events.
**Constraints**: fire-and-forget emission (telemetry outage never changes a verdict or exit status);
captured values bounded to 512 chars and secret-safe; only `feature`/`run_id`/`service.name` are Loki
index labels; no backward-compat keys-only path retained.
**Scale/Scope**: a handful of audits per run; one result record each.

## Constitution Check

| Principle (constitution) | Compliance in this plan |
|--------------------------|-------------------------|
| I. No Backward Compatibility | The keys-only tool-input summary is **removed** for file-touching tools (S1) — replaced by dedicated `tool_read` records, not kept alongside them. No legacy audit/runner shims; runner is invoked by path (no `[project.scripts]` console-entry layer added — `package = false`). |
| II. No Reward Hacking | No placeholders/mocks/stubs outside tests; the `error` verdict is reported honestly and never coerced to `pass`; fire-and-forget emission is the existing real contract, not a defaults-on-failure dodge. Every step has a genuinely-failing-first test; each step ends with an independent self-review hunting for corner-cutting. No gate is weakened. |
| III. Test-First | Every step writes a falsifiable test that is seen red before code exists (S1–S5 pytest; S6 JSON-load + query assertion; S7 doc-example executed). Facilities chosen per unit in §Testable units. |
| IV. Honesty & Permission to Fail | `error` (audit could not evaluate, Edge E2) is a distinct verdict, never silent `pass`; truncation is marked (Edge E5); the missing `@audit` convention is recorded as approval-pending, not silently committed. |
| V. Surface Contradictions | The pydantic-settings contradiction (brief says use it; repo doesn't have it) is surfaced and resolved to stdlib env reads (research R4, Open Questions). |
| Security Requirements | FR-010 is satisfied concretely (research R10): capture-scope limits the captured field to path/pattern keys only, the 512 bound caps size, and a NAMED, TESTED redaction regex masks the one real leak vector (a Grep `pattern` that is itself a secret) to first/last 4 chars with a positive AND a negative unit test — no vague "secret-shaped" helper. S1. |
| Shell / installer conventions | No shell scripts expected to change; if any are touched they keep `set -euo pipefail` + quoted expansions and are tested via `subprocess` under `tests/`. |

Re-check after Phase 1 design: no new violation introduced; Complexity Tracking = None.

## Project Structure

```text
specs/003-audit-trail-checks/
├── spec.md
├── plan.md           # this file
├── research.md       # Phase 0 — R1..R9 decisions/rationale/alternatives
├── data-model.md     # Phase 1 — entities, fields, verdict state transitions
├── contracts/        # Phase 1 — audit-api.md, telemetry-capture.md, grafana-logql.md
├── quickstart.md     # Phase 1 — runnable validation scenarios A..H
└── tasks.md          # Phase 2 — produced later by the `tasks` skill, NOT here
```

**Source layout touched**:
- `.agents/skills/_shared/telemetry/hooks/subagent_stop.py` — `_transcript_records`/`_summarize_content`
  yield dedicated `event_type="tool_read"` records per file-touching block (FR-009/010).
- `.agents/skills/_shared/telemetry/audit/` — NEW package: `__init__.py` (decorator, registry,
  `AuditFailure`/`AuditWarning`), `query.py` (`FeatureRunQuery` + Loki client + `UnknownRunError`),
  `runner.py` (path-invoked entry point + `sys.path` injection + exit-status mapping; NO console
  script — `package = false`), `result.py` (`AuditResult` + emission). Audit author files import
  `from audit import audit, AuditFailure, AuditWarning`.
- `tests/test_tool_input_capture.py`, `tests/test_audit_query.py`, `tests/test_audit_decorator.py`,
  `tests/test_audit_runner.py`, `tests/test_audit_emit.py` — NEW pytest modules.
- `telemetry/grafana/dashboards/feature-runs.json` — add audit panels (FR-013).
- `docs/src/content/docs/...` + the feature dir docs (FR-015), mirrored via `docs-sync.sh`.
- `.specify/memory/constitution.md` — add the `@audit` convention rule (S0, approval-gated).

## Skills to use

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| Establish the missing `@audit` convention rule | `create-rule` | available |
| New Python modules (decorator/runner/query/result) | (no build skill; mirror `emit.py` pattern) — `code-review` per step | available |
| Edit existing hook `subagent_stop.py` | `code-review` / per-step self-review | available |
| pytest unit + hook-integration tests | (existing `tests/` harness; `test_telemetry_hooks.py` pattern) | available |
| Loki-query test harness (stub HTTP fixture) | (no skill; new fixture mirroring `recorders`) | MISSING — proceed from existing pattern; codify via `self-learn` after build |
| Extend Grafana dashboard JSON | (no skill; mirror existing `feature-runs.json`) | MISSING — proceed from existing pattern; codify via `self-learn` if it recurs |
| Developer docs (Starlight) | `developer-docs-bootstrap` / hand-author + `docs-sync.sh` | available |
| Per-step independent verification | `code-review` (self-review sub-agent) | available |
| Architecture/quality confirmation of the change | `code-architecture-review`, `analyze-code-quality` | available |
| Confirm the change actually runs | `verify` / `run` | available |
| Capture learnings afterwards | `self-learn` | available |

Missing-skill note: the Loki-query test harness and Grafana-dashboard-as-code are single-use here with
a clear existing pattern to mirror (`recorders` fixture; `feature-runs.json`), so they are planned as
steps, not blocked on a new skill. Flagged to `self-learn` post-build (research R9).

## Convention & rule audit (resolved before implementation)

| Artifact type | Governing convention | Status |
|---------------|----------------------|--------|
| New Python module under `_shared/telemetry/` | `emit.py` pattern: stdlib-only, `os.path`, module docstrings, fire-and-forget; constitution Tooling (no swaps) | exists |
| `@audit` decorator/registry framework | **No prior decorator/registry convention** in repo | **created this run** (drafted durably via `create-rule` at `specs/003-audit-trail-checks/PROPOSED-audit-rule.md`, approval-pending — see Open Questions BLOCKER-1) |
| Python CLI entry point (argparse) | `emit.py` CLI: subparsers, `--debug/--strict`, swallow + exit 0 | exists |
| Importability / invocation (no console script) | `emit.py` + `conftest.py` + the hooks: `package = false`, invoked by path, parent dir injected on `sys.path` for a bare `import` (NOT a `[project.scripts]` entry or a `telemetry.audit` dotted import) | exists |
| Telemetry-query client (Loki HTTP) | `emit.py` `urllib` + `os.environ.get(..., default)` env-config (NOT pydantic-settings — research R4) | exists |
| Editing a Claude Code hook | `_hooklib.py`/`subagent_stop.py`: never block, `contextlib.suppress`, `sys.exit(0)` | exists |
| pytest unit tests | `pyproject.toml` (`pytest>=8`, `testpaths=["tests"]`), `conftest.py`, `test_telemetry_hooks.py` monkeypatch-the-emit pattern | exists |
| Tests invoking shell via subprocess | constitution Shell/installer "Testing shell scripts" | exists |
| Loki label model (index labels) | `loki-config.yaml` `attributes_config` + `emit.py send_logs` docstring — only `feature`/`run_id`/`service.name` | exists |
| Grafana dashboard JSON | existing `feature-runs.json` is the pattern (no written rule, edit in place) | exists |
| Starlight developer docs | `docs-sync.sh` frontmatter convention (title from first H1), feature dir mirroring | exists |

**Gate:** exactly one row was a gap (the `@audit` framework convention). It is drafted and recorded as
approval-pending (BLOCKER-1) rather than silently committed (non-interactive mode). No step's
*self-review* may treat the `@audit` convention as final until BLOCKER-1 is approved; the draft text is
durably in `specs/003-audit-trail-checks/PROPOSED-audit-rule.md` (inside the feature dir so it survives
the session — NOT an ephemeral scratchpad). The linter requires no literal "gap" cell — this row is
"created this run", consistent with the hard gate (a drafted+recorded convention is not an open gap).

## Testable units (BDD → tests)

| Unit | Spec trace (scenario / FR / SC) | Test facility | Failing-first assertion |
|------|----------------------------------|---------------|-------------------------|
| Capture `Read` path as a dedicated `tool_read` record attributable to role | US3 sc.1 / FR-009 / SC-003 | pytest | `_transcript_records` of a `Read` block yields a `tool_read` record with `tool_input_value="src/foo.py"` + `role`; fails today (keys-only body) |
| ONE message, parallel `tool_use` blocks ⇒ one `tool_read` record each (no collision) | US3 sc.1 / FR-009 (Finding 1) | pytest | two Reads in one message ⇒ two `tool_read` records, both values present; fails if folded into one body/key |
| Capture `Edit`/`Write`/`Grep`/`Glob` path/pattern | US3 sc.3 / FR-009 | pytest | each tool's value captured on its own `tool_read` record; fails before enrichment |
| Bound + mark truncation at 512 | Edge E5 / FR-010 | pytest | a >512-char value is truncated + `value_truncated="true"` + `value_len`; fails before bound exists |
| Secret pattern masked (positive) | Security / FR-010 (R10) | pytest | a `Grep` `pattern="sk-ABCD1234EFGH5678IJKL"` ⇒ masked first/last 4 + `value_redacted="true"`; fails before R10 mask |
| Ordinary path NOT masked (negative) | Security / FR-010 (R10) | pytest | `file_path="src/services/auth_secret_loader.py"` ⇒ full path verbatim, no `value_redacted`; fails if the masker over-matches |
| Path-bearing opaque/hashed segment NOT masked (generic catch-all restricted) | Security / FR-010 (R10) + flagship byte-identity | pytest | a ≥40-char opaque path segment `dist/assets/index-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0.js` ⇒ full path verbatim, no `value_redacted`, so it stays byte-identical to its never-masked `git_files` diff path; fails if the generic high-entropy branch matches a `/`-bearing value |
| `reads_by_role` / `get_all_reads_from_code_review_agent` reads `tool_input_value` off `tool_read` records | US3 sc.1 / FR-008 / SC-003 | pytest (stub Loki HTTP) | returns exactly the seeded `tool_read` values for the code-review role (read off the attr, not grepped from body); fails before client exists |
| `all_diffs_for_feature` from commit `git_files` | US3 sc.2 / FR-008 | pytest (stub Loki HTTP) | returns union of seeded `git_files`; fails before client |
| Unknown run (zero records) ⇒ raises ⇒ error | Edge E2 / FR-006 | pytest (stub Loki HTTP) | a run with NO records ⇒ query raises `UnknownRunError` ⇒ dependent audit reports `error`; fails if it returns empty `pass` |
| Known run, empty diff ⇒ no raise ⇒ vacuous pass (distinct from E2) | Edge E3 / US1 sc.5 (Finding 3) | pytest (stub Loki HTTP) | a run WITH records but zero commit `git_files` ⇒ `all_diffs_for_feature()` returns `∅` (no raise) ⇒ flagship `pass`; fails if it raises/errors |
| `@audit` registers + carries metadata | US1 sc.3 / FR-001/FR-002 | pytest | decorated fn appears in registry with metadata; fails before decorator |
| Verdict derivation pass/fail/error/warn | US1 sc.1/2/4 / FR-004/FR-005 / Edge E8 | pytest | clean→pass, `AuditFailure`→fail+evidence, other exc→error, `AuditWarning`→warn; fails before mapping |
| Duplicate audit name refused | Edge E4 | pytest | second registration under same name raises collision; fails if silently overwrites |
| Runner discovers + isolates audits | US1 sc.3/4 / FR-003/FR-007 | pytest | all audits run; one `error` doesn't stop others; fails before runner |
| Exit status mapping (1 / 0 / 2) | FR-014 / Edge E1 | pytest | fail/error→1, pass/warn→0, no-audits→2; fails before mapping |
| Flagship pass on holds / fail naming files | US1 sc.1/2 / SC-002 | pytest (stub Loki HTTP) | pass when all reviewed; fail listing unreviewed; fails before flagship+query |
| Flagship: known run + empty diff ⇒ vacuous pass | US1 sc.5 / Edge E3 | pytest (stub Loki HTTP) | flagship over a known run with empty diff → `pass`; fails if `error`/`fail` (complements the S2 query-level discriminator) |
| Read by other role ≠ code-review ⇒ fail | Edge E6 | pytest | a file read only by another role is unreviewed → fail; fails if it passes |
| Audit result emitted as structured metadata | US2 sc.1/2 / FR-011 / SC-004 | pytest (monkeypatch `send_logs`) | one record/audit with `audit`/`verdict`/metadata as per-record attrs, `run_id`/`feature` as resource attrs; fails before emit |
| Evidence readable on fail record | US2 sc.3 / FR-005 | pytest | failing record carries `evidence`; fails before emit carries it |
| Emission outage harmless | US2 sc.4 / Edge E7 / FR-012 / SC-005 | pytest | with `send_logs` raising, verdicts + exit status unchanged; fails if it propagates |
| Dashboard exposes audit panels + filters | US2 sc.1 / FR-013 | pytest (JSON load) + quickstart E | `feature-runs.json` parses and contains an `audit_result` query panel; fails before panel added |
| Docs reproduce runnable flagship + LogQL filter | FR-015 / SC-001 / SC-006 | pytest (extract+exec example) + quickstart H | the doc's flagship example imports/registers and a `| audit="…"` filter is present; fails before docs |

## Guardrail register

| Guardrail | How verified in place | Covered by step |
|-----------|------------------------|-----------------|
| ruff check + format clean | `uv run ruff check` + `uv run ruff format --check` on touched files | S0, all |
| pytest harness present + green | `uv run pytest` (existing `pyproject.toml`/`conftest.py`) | S0, all |
| Fake-telemetry fixture (records `send_logs`/`send_span`) | reuse/extend `recorders` from `test_telemetry_hooks.py` | S0 |
| Loki-query stub-HTTP fixture (deterministic, no live stack) | fixture serves canned `query_range` JSON; test order-independent | S0 |
| Hook never blocks / swallows + exit 0 | enrichment keeps `contextlib.suppress` + `sys.exit(0)`; test asserts no raise | S1 |
| Capture bounded + secret-safe (R10) | test a >512 value + a positive secret pattern (masked) AND a negative ordinary path (not masked) | S1 |
| One `tool_read` record per file-touching block (no key collision) | test one message with two parallel Reads ⇒ two records | S1 |
| E2≠E3 (unknown run raises; known-empty returns ∅) | test unknown run raises `UnknownRunError`; known-empty returns ∅ | S2 |
| Runner invoked by path, audit files `import audit` (no console script) | test runner via path; doc-example exec under runner `sys.path` injection | S4, S7 |
| Fire-and-forget emission | test with `send_logs` raising → verdict/exit unchanged | S5 |
| Only feature/run_id/service.name index labels | test asserts audit name rides as per-record attr; no `loki-config.yaml` change | S5 |
| Loki query reads, never writes | client only GETs `/query_range` | S2 |
| Dashboard JSON valid | `json.load(feature-runs.json)` in a test | S6 |
| Constitution principles respected | I no-backward-compat · II no-reward-hacking · III test-first · IV honesty | all |

## Implementation Steps

### Step S0 — setup: establish guardrails, harness, and the `@audit` convention
- **Goal:** Land the pre-implementation guardrails so later steps have them: confirm the `uv`+`pytest`
  harness runs, add the **fake-telemetry fixture** and the **Loki-query stub-HTTP fixture** (shared
  test helpers), and draft the missing `@audit` convention rule (approval-gated). Setup — enables
  S1–S7.
- **Spec trace:** setup — enables S1–S7; closes the convention-audit gap (BLOCKER-1).
- **Red (failing test first):** add `tests/test_audit_fixtures_smoke.py` that imports the new shared
  fixtures and asserts the stub-HTTP fixture returns canned `query_range` JSON and the fake-telemetry
  fixture records a `send_logs` call — fails because the fixtures don't exist yet.
- **Implementation:** add the fixtures (extend the `recorders` pattern from `test_telemetry_hooks.py`;
  a `loki_stub` fixture starting a `http.server` on a free port serving canned JSON, pointing the
  client at it via `FEATURE_LOKI_HTTP_ENDPOINT`). The `@audit` convention rule has been drafted
  durably to `specs/003-audit-trail-checks/PROPOSED-audit-rule.md` (via `create-rule`); it is recorded
  as BLOCKER-1 and **MUST NOT be committed into the constitution until approved** — its commit is
  sequenced after approval, before S3 relies on it.
- **Green criterion:** `uv run pytest tests/test_audit_fixtures_smoke.py` passes; `uv run ruff check`
  clean; the drafted rule exists durably at `specs/003-audit-trail-checks/PROPOSED-audit-rule.md`
  awaiting approval (NOT yet in the constitution).
- **Guardrails to satisfy:** ruff clean; pytest harness present; fake-telemetry + Loki-stub fixtures.
- **Self-review checkpoint:** independent agent confirms the fixtures are deterministic (no live
  stack, own free port, teardown), the smoke test can fail (remove a fixture → red), and the `@audit`
  rule is recorded as approval-pending at the durable feature-dir path, NOT committed into the
  constitution.

### Step S1 — emit dedicated `tool_read` records (replace keys-only)
- **Goal:** Replace the keys-only summary for file-touching tools in `subagent_stop.py` by having
  `_transcript_records`/`_summarize_content` **yield one dedicated `event_type="tool_read"` record per
  file-touching `tool_use` block** (`Read`/`Edit`/`Write`/`Grep`/`Glob`), each carrying
  `tool_name`, the bounded + secret-masked `tool_input_value`, `role`, `agent_id`, `msg_index` (per
  `contracts/telemetry-capture.md`). Parallel blocks in one message no longer collide on one key
  (Finding 1).
- **Spec trace:** US3 sc.1/3/4 / FR-009 / FR-010 / SC-003 / Edge E5.
- **Red (failing test first):** `tests/test_tool_input_capture.py` —
  (a) feed a `Read` block `input={"file_path":"src/foo.py"}` ⇒ assert a `tool_read` record with
  `tool_input_value=="src/foo.py"`, `tool_name=="Read"`, `role` present;
  (b) feed ONE message with TWO `Read` blocks (`src/foo.py`, `src/bar.py`) ⇒ assert TWO `tool_read`
  records, both values present (no collision);
  (c) a >512-char value ⇒ truncated + `value_truncated="true"` + `value_len`;
  (d) **positive** secret: `Grep` `pattern="sk-ABCD1234EFGH5678IJKL"` ⇒ masked first/last 4 +
  `value_redacted="true"`;
  (e) **negative** secret: `file_path="src/services/auth_secret_loader.py"` ⇒ full path verbatim, no
  `value_redacted`;
  (f) **negative redaction on a path-bearing opaque value:** a ≥40-char opaque/hashed PATH SEGMENT such
  as `file_path="dist/assets/index-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0.js"` ⇒ full path verbatim,
  no `value_redacted` (the generic high-entropy catch-all must NOT fire on a `/`-bearing value). All
  fail today (keys-only body).
- **Implementation:** in `_transcript_records`/`_summarize_content`, for the file-touching tool set
  extract the value (`file_path` / `pattern`[+`path`]); apply the R10 secret-mask FIRST (named
  credential-prefix regex `_SECRET_PREFIX_RE` masks regardless of `/`; the generic high-entropy branch
  `_SECRET_GENERIC_RE` fires ONLY on a whole-value-anchored, `/`-free ≥40-char base64-ish blob — so a
  path-bearing opaque/hashed segment is left verbatim and a captured read path stays byte-identical to
  its never-masked `git_files` diff path, preventing a spurious flagship read-vs-diff desync) →
  first/last 4 + `value_redacted`; then `MAX_TOOL_INPUT_VALUE=512` truncation with the
  `value_truncated`/`value_len` markers; yield a dedicated `tool_read` record per block. **Remove
  the keys-only branch for those tools** (Constitution I); non-file-touching tools keep their body
  summary. Keep the hook's `contextlib.suppress` + `sys.exit(0)`.
- **Green criterion:** `uv run pytest tests/test_tool_input_capture.py` green; `uv run ruff check`
  clean; existing `tests/test_telemetry_hooks.py` still green.
- **Guardrails to satisfy:** hook never blocks/swallows + exit 0; capture bounded + secret-safe
  (R10 positive AND negative); no legacy keys-only path for file-touching tools; one record per block.
- **Self-review checkpoint:** confirm each file-touching block yields its OWN `tool_read` record (two
  parallel Reads ⇒ two records, no key collision), the value is genuinely captured (not the key),
  truncation is marked not silent, the R10 masker fires on the secret AND leaves BOTH an ordinary path
  AND a ≥40-char opaque/hashed path segment (e.g. `dist/assets/index-<40hex>.js`) verbatim — so the
  generic catch-all cannot desync a captured read path from its byte-identical `git_files` diff path —
  the keys-only path is removed (not dual-pathed), and the test fails when the enrichment is reverted.

### Step S2 — telemetry query client (`FeatureRunQuery` over Loki)
- **Goal:** Provide `reads_by_role`, `get_all_reads_from_code_review_agent` (by `role`, research R5),
  and `all_diffs_for_feature` (from commit `git_files`) over the Loki HTTP API
  (`/loki/api/v1/query_range`, host `:3100`), stdlib `urllib`, env-configurable endpoint.
- **Spec trace:** US3 sc.1/2 / FR-008 / SC-003 / Edge E2.
- **Red (failing test first):** `tests/test_audit_query.py` using the `loki_stub` fixture — seed canned
  `event_type="tool_read"` records (code-review role, `tool_input_value` = `src/foo.py`,`src/bar.py`)
  and commit records with `git_files`; assert `get_all_reads_from_code_review_agent()` ==
  `{src/foo.py, src/bar.py}` (values read off the `tool_input_value` attr, not grepped from body) and
  `all_diffs_for_feature()` == the seeded union. **E2 vs E3 (Finding 3):** assert an **unknown** run
  (stub returns ZERO records of any type) ⇒ the query **raises `UnknownRunError`**; assert a **known**
  run (records exist) but with zero commit `git_files` ⇒ `all_diffs_for_feature()` returns `∅` with NO
  raise. Fails before the client exists.
- **Implementation:** `audit/query.py` — a `_known()` probe (`{run_id="…"}`, `limit=1`, cached on the
  instance) decides known/unknown; unknown ⇒ raise `UnknownRunError`. For known runs build LogQL
  stream selector `{run_id="…"}` + structured-metadata filters
  (`| event_type="tool_read" | role="…"`), GET via `urllib`, parse `resultType: streams`, read the
  `tool_input_value` attr off each stream, and parse commit `git_files` (comma-split). Resolve
  `run_id`/`feature` from explicit args or `run-context.sh current`.
- **Green criterion:** `uv run pytest tests/test_audit_query.py` green; `uv run ruff check` clean.
- **Guardrails to satisfy:** Loki query reads-only (GET); deterministic via stub fixture; env-config
  endpoint (no pydantic-settings); E2≠E3 discriminator enforced.
- **Self-review checkpoint:** confirm role-based attribution (Edge E6 falls out), the value is read off
  the `tool_input_value` attr (NOT grepped from free-text body), **unknown-run RAISES while known-empty
  returns ∅** (the two are genuinely distinguishable, not both "nothing"), the stub test is
  deterministic, and no live-stack dependency leaked into the unit test.

### Step S3 — `@audit` decorator, registry, and verdict derivation
- **Goal:** Implement `@audit` (metadata + registration), `AuditFailure`/`AuditWarning`, duplicate-name
  refusal, and the verdict mapping {clean→pass, AuditFailure→fail+evidence, other→error, AuditWarning→
  warn} (per `contracts/audit-api.md`).
- **Spec trace:** US1 sc.1/2/3/4/5 / FR-001 / FR-002 / FR-004 / FR-005 / Edge E4 / Edge E8.
- **Red (failing test first):** `tests/test_audit_decorator.py` — decorate two functions, assert both
  registered with metadata; assert a clean fn → `pass`, an `AuditFailure(evidence)` → `fail` carrying
  evidence, a `ValueError` → `error` with detail, an `AuditWarning` → `warn`; assert a duplicate name
  raises collision. Fails before the decorator/registry exist.
- **Implementation:** `audit/__init__.py` — registry list/dict, `audit()` decorator (bare + called),
  exception classes, and the per-audit evaluation that maps outcomes to `AuditResult` verdicts.
- **Green criterion:** `uv run pytest tests/test_audit_decorator.py` green; `uv run ruff check` clean.
- **Guardrails to satisfy:** III test-first; IV honesty (error never coerced to pass); E4 deterministic.
- **Self-review checkpoint:** confirm failure is signalled by raise (not return), the four verdicts are
  distinct, evidence rides on `fail`, duplicate names are refused, and the tests can fail.

### Step S4 — the runner (discovery, isolation, local output, exit status)
- **Goal:** A **path-invoked** runner (`uv run python .agents/skills/_shared/telemetry/audit/runner.py`;
  NO `[project.scripts]` console entry — `pyproject.toml` has `package = false`, Finding 4): inject
  `.agents/skills/_shared/telemetry` onto `sys.path`, import the configured `--path` audit file to
  populate the registry (audit files import `from audit import …`), run every audit isolated (one error
  never stops the rest), print per-audit verdicts + evidence locally, and exit per the R2 mapping
  (fail/error→1, pass/warn→0, no-audits→2). Resolve `run_id` from args or run context.
- **Spec trace:** US1 sc.3/4 / FR-003 / FR-006 / FR-007 / FR-014 / Edge E1 / Edge E2.
- **Red (failing test first):** `tests/test_audit_runner.py` — invoke the runner (importing `runner` and
  calling its entry, or via `subprocess` `uv run python …/runner.py`) pointed at a fixture audit file
  that does `from audit import audit, AuditFailure` (one pass, one fail, one raising) over a stub-Loki
  run; assert all three verdicts printed, exit `1`; assert an empty file → "no audits discovered" +
  exit `2`; assert pass/warn-only → exit `0`. Fails before the runner exists.
- **Implementation:** `audit/runner.py` — `sys.path.insert(0, <telemetry dir>)` then argparse CLI
  (mirror `emit.py` shape), import the audit file via `importlib`, iterate the registry with per-audit
  try/except, build `AuditResult`s, print + set exit code. Also implement the **flagship**
  `all_changed_files_code_reviewed` audit using S2's query (its pass/fail/empty-diff behaviour — US1
  sc.1/2/5, SC-002, Edge E3/E6 — is asserted here against stub Loki; the known-empty-diff case is a
  vacuous `pass`, distinct from an unknown run's `error`).
- **Green criterion:** `uv run pytest tests/test_audit_runner.py` green; `uv run ruff check` clean;
  the flagship pass/fail/empty-diff/other-role cases all assert correctly.
- **Guardrails to satisfy:** FR-007 isolation; FR-014 exit mapping; flagship correctness (SC-002,
  Edge E3/E6).
- **Self-review checkpoint:** confirm isolation (kill one audit mid-run, others still report), the
  exit codes are exactly 1/0/2, "no audits" ≠ "all passed", and the flagship fails honestly naming the
  unreviewed files (not a stub).

### Step S5 — emit audit results into telemetry (structured metadata, fire-and-forget)
- **Goal:** Emit one `AuditResultRecord` per audit via `emit.send_logs` with `run_id`/`feature` as
  resource attrs (index labels) and `audit`/`verdict`/metadata/`evidence` as per-record attrs
  (structured metadata); emission is fire-and-forget and never alters verdicts or exit status.
- **Spec trace:** US2 sc.1/2/3/4 / FR-011 / FR-012 / SC-004 / SC-005 / Edge E7.
- **Red (failing test first):** `tests/test_audit_emit.py` (monkeypatch `send_logs`, reuse the
  fake-telemetry fixture) — assert one record per audit with `event_type="audit_result"`, `audit`,
  `verdict`, and declared metadata as per-record attrs, evidence on the failing one; then make
  `send_logs` raise and assert verdicts + exit status are unchanged. Fails before emission exists.
- **Implementation:** `audit/result.py` — map `AuditResult` → `send_logs(records=[...])`, name + all
  metadata + verdict + evidence as `attrs`; wire the runner to call it after each verdict, swallowing
  emission errors (inherit `emit.py` fire-and-forget).
- **Green criterion:** `uv run pytest tests/test_audit_emit.py` green; `uv run ruff check` clean; no
  `loki-config.yaml` change in the diff.
- **Guardrails to satisfy:** fire-and-forget (FR-012); only feature/run_id/service.name index labels;
  IV honesty.
- **Self-review checkpoint:** confirm the audit name/metadata are per-record attrs (not new index
  labels), `loki-config.yaml` untouched, and an emission failure provably cannot change a verdict or
  the exit code.

### Step S6 — extend the Feature Runs Grafana dashboard
- **Goal:** Add an "Audit failures" stat panel (red on ≥1) and an "Audit results" log panel to
  `telemetry/grafana/dashboards/feature-runs.json`, using LogQL structured-metadata filters
  (`| event_type="audit_result"`, `| verdict="fail"`) keyed on the existing `$run_id`/`$feature`
  dropdowns — no new index label, no `loki-config.yaml` change.
- **Spec trace:** US2 sc.1/2/3 / FR-013.
- **Red (failing test first):** `tests/test_dashboard_audit_panels.py` — `json.load` the dashboard and
  assert a panel exists whose target expr contains `event_type="audit_result"`. Fails before the panel
  is added.
- **Implementation:** add the two panels mirroring the existing "Gate failures"/"Gates" panels
  (same `loki` datasource, same gridPos discipline), with the `audit_result` queries.
- **Green criterion:** `uv run pytest tests/test_dashboard_audit_panels.py` green; the JSON loads;
  quickstart Scenario E shows the panels populated against a real run (manual).
- **Guardrails to satisfy:** dashboard JSON valid; structured-metadata filters (not index labels).
- **Self-review checkpoint:** confirm the panels use `| key="…"` filters (not a `{audit=…}` selector),
  the JSON parses, and `loki-config.yaml` is unchanged.

### Step S7 — documentation (FR-015)
- **Goal:** Ship a clear developer-docs page: how to write an `@audit` function, the available query
  helpers, declaring metadata + where it appears, running the runner, finding results in Grafana —
  with the flagship example reproduced and runnable and at least one runnable LogQL structured-metadata
  filter example (`{run_id="…"} | audit="all_changed_files_code_reviewed"`). Mirrored via `docs-sync.sh`.
- **Spec trace:** FR-015 / SC-001 / SC-006.
- **Red (failing test first):** `tests/test_docs_flagship_example.py` — extract the flagship code block
  from the docs page, inject `.agents/skills/_shared/telemetry` onto `sys.path` exactly as the runner
  does, `exec` it, and assert it imports (`from audit import …`) + registers an audit in the registry;
  assert the doc shows the **path invocation** (`uv run python .agents/skills/_shared/telemetry/audit/
  runner.py`) NOT an `audit-run` console script, and contains the `| audit="…"` LogQL filter literal.
  Fails before the docs exist.
- **Implementation:** author the docs page (Starlight markdown), reproduce the flagship example using
  EXACTLY the `from audit import audit, AuditFailure, AuditWarning` import and the
  `uv run python .agents/skills/_shared/telemetry/audit/runner.py …` invocation, and the LogQL filter
  from `contracts/grafana-logql.md`; run `docs-sync.sh "$FEATURE_DIR"`.
- **Green criterion:** `uv run pytest tests/test_docs_flagship_example.py` green; `docs-sync.sh`
  mirrors the page; quickstart Scenario H walkthrough succeeds.
- **Guardrails to satisfy:** docs example executes under the real import (no rotten sample); the shown
  import + invocation match what the test execs and runs; FR-015 LogQL example present.
- **Self-review checkpoint:** confirm the flagship example actually runs (extracted + `exec`'d under
  the runner's `sys.path` injection with `from audit import …`, not just shown), the shown invocation is
  the by-path form (no console script), the LogQL filter is the structured-metadata idiom (not a label
  selector), and a newcomer could follow it end-to-end (SC-006).

## Sequencing & dependencies

```
S0 (fixtures + @audit rule draft)  ── enables all
   └─► S1 (capture value)  ── data prerequisite for S2's reads-by-role
          └─► S2 (query client)  ── data prerequisite for S4's flagship
                 └─► S3 (decorator/verdicts)
                        └─► S4 (runner + flagship)  ── needs S2 + S3
                               └─► S5 (emit results)  ── needs S4's AuditResults
                                      └─► S6 (dashboard, needs the audit_result event_type from S5)
                                      └─► S7 (docs, needs the runnable framework from S1–S5)
```
Edges driven by substrate gotchas: S2 depends on S1 because `get_all_reads_from_code_review_agent`
cannot return real paths until the value is captured (the known gap). S6 depends on S5 because the
dashboard filters on the `event_type="audit_result"` records S5 emits. S3 (pure-Python decorator) is
independent of S1/S2 and could run in parallel with them, but is sequenced before S4 which needs both.

## Complexity Tracking

None.

## Assumptions

- Audits read already-persisted telemetry (post-hoc or in-progress recorded-so-far); the runner does
  not re-execute the feature (spec Assumptions).
- The runner is a developer/CI-invoked Python entry point run from repo root (spec Assumptions).
- `@audit` metadata is an open key/value set; recommended vocabulary name/category/severity/owner is
  documented (spec Assumptions).
- Loki index labels are exactly `feature`/`run_id`/`service.name` (verified live); audit name +
  metadata ride as structured metadata; no `loki-config.yaml` change (clarify Q1, FR-011).
- The code-review agent is resolved by telemetry `role`, not `agent_id` (carry-forward #4, research R5).
- Empty change set ⇒ flagship `pass` (vacuous truth) (clarify Q2, Edge E3).
- `MAX_TOOL_INPUT_VALUE = 512` chars is the capture bound (research R1); verdict→exit mapping is
  fail/error→1, pass/warn→0, no-audits→2 (research R2). Both pinned here, recorded so they can be
  challenged.
- File-touching tool inputs are captured as **one dedicated `event_type="tool_read"` record per
  `tool_use` block** (not folded into the message body), so parallel Reads/Edits don't collide; the
  query reads the value off the `tool_input_value` attr (research-derived Finding 1).
- FR-010 secret-safety is concrete (research R10): capture-scope (path/pattern keys only) + the 512
  bound + a named, tested redaction regex (masking secret-prefix/high-entropy values to first/last 4),
  not a vague "secret-shaped" helper.
- The runner is invoked **by path** and audit files import `from audit import …` (research-derived
  Finding 4); no `[project.scripts]` console script is added (`pyproject.toml` has `package = false`).
- A run is "known" iff any record exists for its `run_id`; an unknown run RAISES `UnknownRunError`
  (→ `error`) while a known run with an empty diff returns ∅ (→ vacuous `pass`) — the E2/E3
  discriminator (Finding 3).
- Config is via stdlib env reads (`FEATURE_LOKI_HTTP_ENDPOINT`, etc.), NOT pydantic-settings, because
  the repo has no pydantic dependency (research R4) — surfaced contradiction.
- Documentation lives with the developer docs and is picked up by `docs-sync.sh` (spec Assumptions).

## Open Questions

- **BLOCKER-1 (convention approval):** The `@audit` framework convention is a real gap with no prior
  rule. In non-interactive mode it has been **drafted durably** at
  `specs/003-audit-trail-checks/PROPOSED-audit-rule.md` (inside the feature dir so it survives the
  session; target once approved = constitution under *Development Workflow & Quality Gates*) and
  recorded here as approval-pending rather than committed on the user's behalf. **Sequencing:** the
  rule-commit waits for approval — S0 must NOT write it into the constitution, and S3/S4 self-reviews
  must not treat the convention as final until BLOCKER-1 is approved. **Best guess / recommendation:**
  approve the drafted rule as written and commit it (`docs(constitution): add @audit framework
  convention`) only after approval, before S3 relies on it.
- **Capture bound (512) and exit mapping (1/0/2):** pinned in research R1/R2 as defensible defaults;
  flagged for challenge. **Best guess:** keep as specified.
- **pydantic-settings contradiction:** resolved to stdlib env reads (research R4). **Best guess:** keep
  stdlib; revisit only if config materially grows.

## Traceability

| Spec scenario / FR / SC | Unit(s) | Step(s) | Guardrail(s) |
|-------------------------|---------|---------|--------------|
| FR-001 (define `@audit`, explicit failure) | `@audit` register, verdict derivation | S3 | III test-first, ruff |
| FR-002 (decorator metadata) | `@audit` metadata | S3 | III, ruff |
| FR-003 (runner discovers + runs all) | runner discovery | S4 | FR-007 isolation, ruff |
| FR-004 (fixed verdict set, fail≠error) | verdict derivation | S3 | IV honesty |
| FR-005 (evidence on fail) | verdict evidence; emit evidence | S3, S5 | IV honesty |
| FR-006 (resolve run_id / run context) | `FeatureRunQuery` resolution; runner | S2, S4 | reads-only |
| FR-007 (one error doesn't stop others) | runner isolation | S4 | FR-007 |
| FR-008 (documented query surface) | reads_by_role, all_diffs_for_feature | S2 | reads-only, stub fixture |
| FR-009 (capture tool-input value) | capture Read/Edit/Write/Grep/Glob value as per-block `tool_read` record (no collision) | S1 | hook safety, no-legacy, one record per block |
| FR-010 (bounded + secret-safe) | bound+truncation; secret mask positive AND negative (R10) | S1 | bounded+secret-safe (R10) |
| FR-011 (emit as structured metadata) | audit result record | S5 | index-label model |
| FR-012 (fire-and-forget emission) | emission outage harmless | S5 | fire-and-forget |
| FR-013 (Grafana filterable by name/metadata) | dashboard panels | S6 | dashboard valid, struct-meta |
| FR-014 (exit status reflects verdict) | exit mapping | S4 | FR-014 |
| FR-015 (runnable docs + LogQL example) | docs flagship + LogQL filter | S7 | docs example executes |
| SC-001 (single decorated fn, no plumbing) | `@audit`; docs example | S3, S7 | III, docs executes |
| SC-002 (flagship pass/fail naming files) | flagship audit | S4 | flagship correctness |
| SC-003 (recorded paths per role) | capture value; reads-by-role | S1, S2 | bounded, role attribution |
| SC-004 (one result/audit in Grafana) | audit result record; dashboard | S5, S6 | index-label model |
| SC-005 (outage loses zero verdicts) | emission outage harmless | S5 | fire-and-forget |
| SC-006 (newcomer can author + locate) | docs flagship + LogQL | S7 | docs executes |
| US1 sc.1/2 (flagship pass/fail) | flagship audit | S4 | flagship correctness |
| US1 sc.3 (two audits, independent verdicts) | runner; `@audit` register | S3, S4 | FR-007 |
| US1 sc.4 (error isolated, distinct) | verdict derivation; isolation | S3, S4 | IV honesty, FR-007 |
| US1 sc.5 / Edge E3 (KNOWN run + empty diff ⇒ vacuous pass, distinct from E2) | known-run empty-diff returns ∅; flagship empty-diff | S2, S4 | E2≠E3, flagship correctness |
| US2 sc.1/2/3 (results + metadata + evidence in Grafana) | result record; dashboard | S5, S6 | struct-meta |
| US2 sc.4 / Edge E7 (outage harmless) | emission outage harmless | S5 | fire-and-forget |
| US3 sc.1/3/4 (capture read/edit/write/grep/glob; bound) | capture value; bound | S1 | bounded+secret-safe |
| US3 sc.2 (diffs from commits) | all_diffs_for_feature | S2 | reads-only |
| Edge E1 (no audits ⇒ distinct status) | exit mapping | S4 | FR-014 |
| Edge E2 (UNKNOWN run, zero records ⇒ raises ⇒ error; distinct from E3) | unknown-run raises `UnknownRunError` | S2, S4 | E2≠E3, IV honesty |
| Edge E4 (duplicate name refused) | duplicate-name collision | S3 | E4 deterministic |
| Edge E5 (oversized value truncated+marked) | bound+truncation | S1 | bounded |
| Edge E6 (other-role read ⇒ fail) | flagship other-role | S2, S4 | role attribution |
| Edge E8 (warn distinct) | verdict derivation (warn) | S3 | IV honesty |
