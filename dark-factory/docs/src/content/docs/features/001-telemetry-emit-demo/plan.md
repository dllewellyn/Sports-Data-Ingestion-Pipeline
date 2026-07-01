---
title: "Implementation Plan: Telemetry Emit Demo"
---

# Implementation Plan: Telemetry Emit Demo

**Feature directory**: `specs/001-telemetry-emit-demo/`
**Date**: 2026-06-30
**Spec**: `spec.md`
**Status**: Draft

## Summary

Build one small, standalone, pytest-tested Python CLI module `telemetry/demo_emit.py`, runnable as
`python -m telemetry.demo_emit --label <name>`, that emits exactly one OpenTelemetry span (to Tempo)
and one matching log event (to Loki) by importing and calling the existing `send_span` / `send_logs`
functions in `.agents/skills/_shared/telemetry/emit.py` — no re-implemented OTLP/HTTP. Both signals
carry a user-supplied label (default `demo-emit`) under a single stable key `demo.label` (span
attribute + Loki structured metadata); the span name is the fixed constant `demo.emit`. The module
mints its own non-empty `trace_id`/`run_id` when no feature-run is active (so it works standalone),
reuses `emit.py`'s endpoint resolution, prints what it emitted and where on success, and exits non-zero
when either send fails (inspecting the boolean returns, since `emit.py` is fire-and-forget). Because
the repo currently has no Python test/lint harness, establishing a minimal pytest + `pyproject.toml`
convention is a Phase-2/S0 prerequisite. Approach and reuse mechanics are settled in `research.md`.

## Technical Context

**Language/Version**: Python 3 (system `python3`, currently 3.14); module is stdlib-only and version-agnostic, so no project-specific version pin is imposed.
**Primary Dependencies**: stdlib only (`argparse`, `os`, `sys`, `time`) + the repo's own `.agents/skills/_shared/telemetry/emit.py` (imported, not copied). No third-party runtime deps (FR-010, SC-004). `pytest` is a dev-only dependency.
**Storage**: None. Telemetry is emitted over OTLP/HTTP via `emit.py`; nothing is persisted locally.
**Testing**: pytest with `monkeypatch` fakes at the `emit.send_span`/`emit.send_logs` boundary — collector-free (FR-011, SC-005). New harness established this run (S0).
**Target Platform**: local CLI / developer smoke-test of the telemetry pipeline.
**Project Type**: single project (one module + its tests + a package marker).
**Performance Goals**: N/A (one span + one event per invocation).
**Constraints**: Reuse `emit.py` (no duplicated OTLP/HTTP, no faked emission outside fixtures); endpoint resolution owned by `emit.py` (`FEATURE_OTLP_HTTP_ENDPOINT` or `http://localhost:14318`); label rides as Loki structured metadata, not an index label; exit 0 iff both signals emit.
**Scale/Scope**: One module, one package marker, one test file. No metrics, dashboards, span trees, or config beyond `--label`.

## Constitution Check

| Principle (constitution) | Compliance in this plan |
|--------------------------|-------------------------|
| I. No Backward Compatibility | Net-new standalone module; no legacy emit path to preserve or dual-purpose. No backward-compat scaffolding planned (spec Constraints). |
| II. No Reward Hacking (NON-NEGOTIABLE) | Emission goes through the **real** imported `send_span`/`send_logs` (FR-003); no duplicated OTLP code, no stubbed emission outside test fixtures. The `monkeypatch` fakes exist only in pytest (allowed). FR-008 is met by honestly inspecting `emit.py`'s real boolean returns, not by faking success. No gate is weakened; the missing test/lint harness is *established*, not bypassed. The pinned label-not-an-index-label fact is honoured (no emit.py edit to fake a selector). |
| III. Test-First (NON-NEGOTIABLE) | Every implementation step writes a red pytest test first (seen failing for the right reason) before the code; red→green→refactor. The two SC-005 anchors (label-propagation test, failed-emission-exit test) are genuinely red-able. The harness itself (S0) is proven with a known-fail-then-pass before any feature step depends on it. |
| IV. Honesty & Permission to Fail | The convention gaps (no harness) and the emit.py fire-and-forget tension are surfaced explicitly (Open Questions / Convention audit), not papered over. |
| V. Surface Contradictions & Beneficial Changes | Surfaced: the README component table says HTTP `4318` but the host port / `emit.py` default is `14318` (resolved by reusing `emit.py`); the `tdd-and-guardrails` reference assumes a `uv`/ruff/`pyproject`/`dbt`/Python-pin stack that does **not** exist in this repo (see Open Questions). |

Re-checked after Phase 1 design: no new violation introduced. Complexity Tracking: None.

## Project Structure

```text
specs/001-telemetry-emit-demo/
├── spec.md
├── plan.md           # this file
├── research.md       # Phase 0 — D1–D8 decisions/rationale/alternatives
├── data-model.md     # Phase 1 — Label, Demo span, Demo event entities + invariants
├── contracts/
│   └── cli.md        # Phase 1 — CLI grammar, exit codes, stdout/stderr, behavioural contract C1–C5
├── quickstart.md     # Phase 1 — pytest layer + live Grafana verification + failure path
└── tasks.md          # Phase 2 — produced later by the `tasks` skill, NOT here
```

**Source layout touched**:
- `telemetry/__init__.py` (new — package marker so `python -m telemetry.demo_emit` resolves)
- `telemetry/demo_emit.py` (new — the module)
- `tests/test_demo_emit.py` (new — collector-free pytest)
- `pyproject.toml` (new — minimal pytest + ruff dev config; root)
- Imported, not modified: `.agents/skills/_shared/telemetry/emit.py`

## Skills to use

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| New standalone Python CLI module scaffold | — (no dedicated CLI-scaffold skill) | MISSING — proceed from the `emit.py` / spec-helpers pattern; capture via `self-learn` after build |
| Establish pytest harness + lint config | — (no harness-bootstrap skill; `bootstrap` is governance-oriented, not language test infra) | MISSING — done explicitly as S0 + a pending convention rule |
| pytest unit tests (collector-free) | — (no test-authoring skill; `implementor` executes the TDD steps) | MISSING — authored per step from the Phase-3 unit map |
| Author the missing conventions/rules | `create-rule` (`~/.claude/commands/create-rule.md`, confirmed present) | available |
| Per-step independent self-review of the diff | `code-review` (per-step), and `implementor`'s built-in independent reviewer | available |
| Verify the change runs end-to-end against the live stack | `verify` / `run` | available |
| Capture learnings (CLI/harness pattern) after the build | `self-learn` | available |
| Capture durable project-wide rules into governance | `speckit-constitution` / `self-learn` (if the harness convention should become constitutional) | available |

## Convention & rule audit (resolved before implementation)

Audited against: project `CLAUDE.md`→`AGENTS.md` (SpecKit pointer only — no Python conventions),
`.specify/memory/constitution.md` (mandates TDD/pytest + no-reward-hacking but no tooling specifics),
no `ARCHITECTURE.md`, **no `pyproject.toml` / ruff / pytest / pre-commit / `tests/` / rules dir**, and
the de-facto Python style in `emit.py` + `spec-helpers/*.py` (stdlib, no type hints, no
`from __future__`, `# noqa: BLE001` with reason, `pathlib`/`os.path`, UPPERCASE constants, `_private`
helpers). `create-rule` is present.

| Artifact type | Governing convention | Status |
|---------------|----------------------|--------|
| New stdlib-only Python CLI module (`telemetry/demo_emit.py`) | De-facto pattern of `.agents/skills/_shared/telemetry/emit.py` (module docstring, stdlib imports, keyword-only API, `# noqa: BLE001`+reason for broad catches, no `from __future__`) + Constitution II/III | exists |
| Reuse-the-real-emitter constraint | Constitution II + spec FR-003/FR-009 (import `emit.py`'s `send_span`/`send_logs`; no duplicated OTLP/HTTP; reuse `_endpoint()`) | exists |
| Importable package marker (`telemetry/__init__.py`) | **Rule drafted this run** (no existing package pattern in the repo): "ALWAYS add an `__init__.py` before shipping a `python -m <pkg>.<module>` entry point; keep it empty unless a public surface is genuinely needed." Target: project `CLAUDE.md`/`AGENTS.md`. | created-pending-approval |
| pytest harness + test layout + lint config (`tests/`, `pyproject.toml`, ruff) | **Rule drafted this run** (no harness/config exists): "ALWAYS place pytest tests in top-level `tests/` named `test_*.py`, collector-free and stdlib-only unless a dep is explicitly added; declare pytest+ruff dev config in a single root `pyproject.toml` (`[tool.pytest.ini_options] testpaths=['tests']`; ruff set `E,W,F,I,UP,B,C4,SIM`); NEVER add a third-party *runtime* dep to a stdlib-only module (pytest/ruff are dev-only)." Target: project `CLAUDE.md`/`AGENTS.md`. | created-pending-approval |

**Gate**: zero rows are `gap`. The two `created-pending-approval` rules are drafted (exact text above)
but, per non-interactive mode, are **not** committed on the user's behalf — they are recorded as
approval blockers (see Open Questions B1/B2). S0 lands the harness + `pyproject.toml`; S1 lands the
package marker — both after the rules are approved and committed.

## Testable units (BDD → tests)

| Unit | Spec trace (scenario / FR / SC) | Test facility | Failing-first assertion |
|------|----------------------------------|---------------|-------------------------|
| U0 Harness works | setup — enables U1–U6 | pytest | A trivial `test_harness_smoke` is collected and runs; before S0 there is no `pytest` config / `tests/` so collection fails — proven by a deliberate known-fail then known-pass. |
| U1 Emits one span + one event with label on BOTH | US1 scenario 1 / FR-002, FR-003, FR-004 / SC-001 | pytest (monkeypatch `emit.send_span`/`emit.send_logs`) | With `--label smoke-1`: assert `send_span` called once with `attrs` containing `("demo.label","smoke-1")` and `send_logs` called once with a record whose `attrs` contain `("demo.label","smoke-1")`. Fails before the module exists / if label not propagated to both. |
| U2 Success stdout names span/event/label/destinations | US1 scenario 2 / FR-007 / SC-002 | pytest (capsys) | Assert stdout contains span name `demo.emit`, the event body, the label, "Tempo", "Loki", and key `demo.label`. Fails before the print contract exists. |
| U3 Default label when `--label` omitted | US2 scenario 1 / FR-005 / E3 | pytest | Run with no `--label`: assert both sends carry `demo-emit` and it is printed. Fails before the default is wired. |
| U4 Empty/whitespace label rejected non-zero | E4 / FR-006 | pytest | `--label "   "`: assert `SystemExit` non-zero, no send attempted, clear stderr message. Fails before validation exists. |
| U5 Non-zero exit when a send fails / partial failure | US3 scenarios 1–2 / FR-008 / SC-003, E1, E2 | pytest | Fake `send_logs` → `False` (and separately `send_span` → `False`): assert non-zero exit, stderr names the failed signal, no success line. Fails if a `False` return still exits 0. |
| U6 Standalone (no feature-run context) mints non-empty trace id | US1 / FR-002 / E6 | pytest | With `current.json` absent (monkeypatch `emit.current_context` → `{}`): assert both sends invoked with a **non-empty** `trace_id`. Fails if the module passes an empty trace id (which `send_span` would reject → false FR-008 failure). |
| U7 No third-party runtime dependency | FR-010 / SC-004 | pytest (artifact/import assertion) | Assert `telemetry/demo_emit.py`'s top-level imports are stdlib + `emit` only (parse imports / import in a clean namespace). Fails if a third-party import is added. |

## Guardrail register

| Guardrail | How verified in place | Covered by step |
|-----------|------------------------|-----------------|
| pytest harness exists & runs | `pytest tests/ -q` collects and runs; proven known-fail→known-pass | S0 |
| ruff lint + format clean | `ruff check .` and `ruff format --check .` clean on the new files | S0 (config), all (kept clean) |
| Reuse real `emit.py` (no duplicated OTLP/HTTP; no faked emission outside fixtures) | code-review / self-review inspects imports: only `import emit` + stdlib; fakes only under `tests/` | S2, S3 |
| Non-empty trace id before span call | U6 test asserts non-empty `trace_id` passed to sends | S3 |
| Exit 0 iff both signals emit (FR-008) | U5 test asserts non-zero on any `False`/raise; U1 asserts 0 on both-true | S4 |
| Label propagated to both signals (FR-004) | U1 asserts `demo.label` on span attrs AND event structured metadata | S3 |
| Zero third-party runtime deps (SC-004) | U7 import-surface assertion | S2 |
| Endpoint resolution reused (FR-009, E5) | self-review confirms no endpoint literal in `demo_emit.py`; quickstart Layer 3 exercises `FEATURE_OTLP_HTTP_ENDPOINT` | S3 |
| Constitution principles respected | II No-reward-hacking · III Test-first · I No-backward-compat | all |
| Live ingestion + label propagation (SC-001) | `verify`/`run` via quickstart Layer 2 (manual Grafana lookup, per spec Assumptions) | S5 |

## Implementation Steps

### Step S0 — setup: establish the pytest + ruff harness and `pyproject.toml`
- **Goal:** A working, committed Python test/lint harness so later steps have a real red/green facility — the repo currently has none.
- **Spec trace:** setup — enables S2–S4 (FR-011, SC-005); closes the harness convention gap.
- **Red (failing test first):** Add `tests/test_harness_smoke.py` with `def test_harness_smoke(): assert True`; run `pytest -q` and confirm it **errors/does not collect** first (no `pyproject.toml`/`tests` config), i.e. the harness is genuinely absent.
- **Implementation:** ✅ **PROVISIONED in the B2 capability-provisioning gate (commit `c4d1605`)** — root `pyproject.toml` (`[project]`, `[tool.uv] package=false`, `[dependency-groups] dev=["pytest>=8"]`, `[tool.pytest.ini_options] testpaths=["tests"]`, `[tool.ruff.lint] select=E,W,F,I,UP,B,C4,SIM`), `uv.lock`, and `tests/`. Tests run via `uv run pytest`. **Implementor: verify only — do not recreate this step.** Codifying these as `AGENTS.md` governance rules was deferred to the end-of-run `self-learn` per the user's B2 decision (Option A).
- **Green criterion:** `pytest tests/test_harness_smoke.py -q` passes (1 passed); `ruff check .` clean. Then flip the smoke test to `assert False` once to confirm it can fail, revert to passing.
- **Guardrails to satisfy:** pytest harness exists & runs; ruff clean.
- **Self-review checkpoint:** Independent reviewer confirms the harness genuinely did not exist before, the smoke test was seen both red and green, no existing gate was weakened, and `pyproject.toml` introduces no third-party *runtime* dependency. See `references/self-review.md`.

### Step S1 — setup: add the `telemetry/__init__.py` package marker
- **Goal:** Make `telemetry/` an importable package so `python -m telemetry.demo_emit` resolves.
- **Spec trace:** setup — enables FR-001; closes the package-marker convention gap.
- **Red (failing test first):** `tests/test_demo_emit.py::test_module_is_importable` does `import importlib; importlib.import_module("telemetry.demo_emit")` and expects success; before S1/S2 it fails with `ModuleNotFoundError` (no package / no module).
- **Implementation:** ✅ **PROVISIONED in the B2 capability-provisioning gate (commit `c4d1605`)** — empty `telemetry/__init__.py` added (no exports). **Implementor: verify only — do not recreate this step.** Rule codification deferred to end-of-run `self-learn` per the user's B2 decision (Option A).
- **Green criterion:** `python -c "import telemetry"` succeeds; the import test will go green once S2 adds the module (the marker alone removes the package-level `ModuleNotFoundError`).
- **Guardrails to satisfy:** ruff clean (empty file is trivially clean).
- **Self-review checkpoint:** Reviewer confirms `__init__.py` is empty (no premature public surface), the package convention rule was committed first, and the marker does not shadow or alter the existing `telemetry/` docker-stack contents.

### Step S2 — module skeleton: argparse + label validation + import of `emit.py`, stdlib-only
- **Goal:** The runnable module entry point with `--label` parsing, empty/whitespace rejection, and a real import of `emit.py` — no emission logic yet beyond wiring.
- **Spec trace:** FR-001, FR-005, FR-006, FR-010 / US2, E4 / SC-004 (U3 default, U4 reject, U7 imports).
- **Red (failing test first):** Write U4 (`--label "   "` → non-zero `SystemExit`, no send) and U7 (import surface is stdlib + `emit` only) and U3's default-label assertion; run — they fail because the module/argparse/validation don't exist.
- **Implementation:** `telemetry/demo_emit.py` with module docstring (emit.py style), stdlib imports, `argparse` with `--label` default `demo-emit`, `.strip()` validation (reject empty/whitespace to stderr + non-zero exit), and `sys.path` insertion of `<repo>/.agents/skills/_shared/telemetry` then `import emit`. Pin the constants `SPAN_NAME="demo.emit"`, `DEFAULT_LABEL="demo-emit"`, `LABEL_KEY="demo.label"`, `EVENT_TYPE="demo"`.
- **Green criterion:** `pytest tests/test_demo_emit.py -k "reject or imports or default" -q` passes; `ruff check .` clean.
- **Guardrails to satisfy:** Reuse real `emit.py`; zero third-party runtime deps; ruff clean.
- **Self-review checkpoint:** Reviewer confirms `emit` is genuinely imported (not copied/stubbed), no third-party import crept in, validation rejects whitespace via a non-zero exit (not a default-away), and the pinned constants match `research.md` D6.

### Step S3 — emission: mint ids, build span + event carrying the label on both, call `send_span`/`send_logs`
- **Goal:** Emit exactly one span and one event, both carrying `demo.label`, with a non-empty trace id, reusing `emit.py`'s endpoint.
- **Spec trace:** FR-002, FR-003, FR-004, FR-009 / US1 scenarios 1 & 3, E5, E6 / SC-001 (U1, U6).
- **Red (failing test first):** Write U1 (both sends called once; `demo.label=<value>` on span `attrs` AND event record `attrs`) and U6 (`current_context()` → `{}` ⇒ non-empty `trace_id` passed to both sends); run — fail (no emission code).
- **Implementation:** Resolve ids via `emit.current_context()`; if `{}`, mint `trace_id=os.urandom(16).hex()`, a recognisable `run_id`, and `span_id=os.urandom(8).hex()`. Call `emit.send_span(trace_id=…, run_id=…, name="demo.emit", span_id=…, start_ns=…, end_ns=…, attrs=[("demo.label", label)], strict=True)` and `emit.send_logs(trace_id=…, run_id=…, records=[{"body": f"demo emit: {label}", "severity":"INFO", "attrs":[("event_type","demo"),("demo.label",label)]}], strict=True)`. No endpoint literal anywhere (FR-009).
- **Green criterion:** `pytest tests/test_demo_emit.py -k "propagat or standalone or both_signals" -q` passes; `ruff check .` clean.
- **Guardrails to satisfy:** Label on both signals; non-empty trace id before span call; endpoint resolution reused; reuse real `emit.py`.
- **Self-review checkpoint:** Reviewer confirms a non-empty `trace_id` is always passed (so FR-008 can't trip falsely), the label is on **both** span attribute and event structured metadata under `demo.label`, there is no hardcoded endpoint, and `current_context()` reuse vs. minting is correct for E6.

### Step S4 — outcome contract: exit code + stdout/stderr reporting from the boolean returns
- **Goal:** Exit 0 iff both sends returned True; otherwise report the failed signal on stderr and exit non-zero; on success print span/event/label/destinations to stdout.
- **Spec trace:** FR-007, FR-008 / US1 scenario 2, US3 scenarios 1–2, E1, E2 / SC-002, SC-003 (U2, U5).
- **Red (failing test first):** Write U5 (fake `send_logs`→`False`, separately `send_span`→`False`, and a raise under `strict=True` ⇒ non-zero exit, stderr names the signal, no stdout success line) and U2 (success stdout names span/event/label/Tempo/Loki/`demo.label`); run — fail (no exit/report logic).
- **Implementation:** Capture both booleans (and catch the `strict=True` exception to identify which signal failed); if either is False/raised → print which failed to stderr, `sys.exit(1)`, print no success line; if both True → print the success report to stdout, exit 0.
- **Green criterion:** `pytest tests/test_demo_emit.py -q` all pass (full file); `ruff check .` + `ruff format --check .` clean; `python -m telemetry.demo_emit --label selftest` exits 0 with the stack up (or non-zero with `FEATURE_OTLP_HTTP_ENDPOINT=http://localhost:1`).
- **Guardrails to satisfy:** Exit 0 iff both emit; success stdout contract; failure stderr contract; reuse real `emit.py`.
- **Self-review checkpoint:** Reviewer confirms FR-008 is met by inspecting **real** boolean returns (not a faked success), no success line is printed on failure (SC-003), partial failure (E2) exits non-zero and names the signal, and the U5 tests genuinely fail if a False return is allowed to exit 0 (revert-and-confirm).

### Step S5 — live verification (the change actually runs end-to-end)
- **Goal:** Prove real ingestion and label propagation against the live stack (SC-001) — the manual Grafana layer the pytest suite intentionally does not cover.
- **Spec trace:** US1 scenario 3 / SC-001, SC-002 / E5.
- **Red (failing test first):** Pre-state: querying Tempo for span `demo.emit` with a fresh unique label returns nothing (the data point doesn't exist yet) — the falsifiable "before".
- **Implementation:** Run quickstart Layer 2: stack up, `python -m telemetry.demo_emit --label smoke-<unique>`, exit 0; then Layer 3 with `FEATURE_OTLP_HTTP_ENDPOINT=http://localhost:1` for the failure path.
- **Green criterion:** Grafana shows exactly one Tempo span `demo.emit` with attribute `demo.label=<label>` and exactly one Loki event matching `| demo_label="<label>"` under `service.name=feature-orchestrator`; the failure-path run exits non-zero with a stderr report and no success line.
- **Guardrails to satisfy:** Live ingestion + label propagation; endpoint override path.
- **Self-review checkpoint:** Use `verify`/`run`; reviewer confirms the span and event are actually found by the label in Grafana (not just that the process exited 0), and the failure path produced a non-zero exit with no success line — i.e. the smoke test cannot give a false OK.

## Sequencing & dependencies

```
S0 (harness) ──▶ S1 (package marker) ──▶ S2 (skeleton+validation) ──▶ S3 (emission) ──▶ S4 (exit/report) ──▶ S5 (live verify)
   │                  │
   └ requires harness-convention rule approved+committed (B2)
                      └ requires package-marker rule approved+committed (B1)
```

- S0 before everything: no red/green facility exists until the pytest harness lands.
- S1 before S2: `python -m telemetry.demo_emit` needs `telemetry/__init__.py`.
- S2 before S3 before S4: skeleton → emission → outcome contract is the natural data/control-flow order;
  each adds its own red tests first.
- S5 last: only after the module is green collector-free do we verify live ingestion.
- **Convention gate edge:** RESOLVED — S0 (harness) and S1 (package marker) were provisioned and
  committed in the B2 capability-provisioning gate (`c4d1605`) before any feature code; the
  implementor verifies them rather than recreating them, and starts real feature work at S2.

## Complexity Tracking

None.

## Assumptions

- Module path `telemetry/demo_emit.py` and run command `python -m telemetry.demo_emit` are fixed by the
  spec; an empty `telemetry/__init__.py` is added to make the package importable.
- The system `python3` (3.14) is the interpreter; the module + tests are stdlib-only so no
  project-specific version pin is imposed (the `tdd-and-guardrails` reference's `>=3.12,<3.13` pin
  describes a different, non-existent data-platform repo — see Open Questions).
- `pytest` and `ruff` are introduced as **dev-only** dependencies via `uv`; they do not count against
  SC-004 (zero third-party *runtime* deps).
- Pinned values (research D6, recorded here as decisions, not lingering assumptions): span name
  `demo.emit`; default label `demo-emit`; label key `demo.label` (span attribute + Loki structured
  metadata); event body `demo emit: <label>`; event_type `demo`.
- "Find it in Grafana" (SC-001) is verified manually by the developer in S5; automated query-back
  against live Tempo/Loki is out of scope (pytest is collector-free).

## Open Questions

- **B1 (RESOLVED ✅ — user chose Option A):** the `telemetry/__init__.py` package marker was provisioned in the B2 gate (commit `c4d1605`). Codifying it as an `AGENTS.md` rule is **deferred to end-of-run `self-learn`**; the draft below is retained as that candidate. Original draft (non-interactive,
  not committed): *"ALWAYS add an `__init__.py` before shipping a `python -m <pkg>.<module>` entry
  point; keep it empty unless a public export surface is genuinely needed."* Target: project
  `CLAUDE.md`/`AGENTS.md`. **Best guess:** approve as drafted — it matches the spec's own assumption and
  is minimal. *Rationale:* `create-rule` requires user confirmation before appending and never
  auto-creates a target; in non-interactive mode the rule is drafted and recorded rather than committed
  on the user's behalf. S1 (and downstream) wait on this approval + commit.
- **B2 (RESOLVED ✅ — user chose Option A):** the pytest+ruff harness and root `pyproject.toml` (+ `uv.lock`, `tests/`) were provisioned in the B2 gate (commit `c4d1605`), verified red→green. Codifying the convention as an `AGENTS.md` rule is **deferred to end-of-run `self-learn`**; the draft below is retained as that candidate. Original draft: *"ALWAYS place pytest tests in top-level `tests/` named `test_*.py`,
  collector-free and stdlib-only unless a dep is explicitly added; declare pytest+ruff dev config in a
  single root `pyproject.toml` (`[tool.pytest.ini_options] testpaths=['tests']`; ruff set
  `E,W,F,I,UP,B,C4,SIM`); NEVER add a third-party runtime dep to a stdlib-only module."* Target: project
  `CLAUDE.md`/`AGENTS.md` + new root `pyproject.toml`. **Best guess:** approve as drafted — it is the
  minimum harness the constitution's Test-First principle requires and matches the `emit.py` lint set
  convention. *Rationale:* same as B1; the repo has no harness, so establishing one is a real,
  approval-worthy governance act, not a silent commit. S0 (and downstream) wait on this.
- **Resolved tension (not a blocker):** `emit.py` is fire-and-forget (CLI always exits 0). FR-008 is met
  by calling the importable `send_span`/`send_logs` and inspecting their boolean returns (with
  `strict=True` to surface the exception). No change to `emit.py` (spec Open Questions; research D2).
- **Surfaced contradiction (not a blocker):** the README *component table* lists OTLP HTTP as `4318`,
  but the host-mapped port and `emit.py`'s `DEFAULT_ENDPOINT` are `14318`. The plan reuses `emit.py`'s
  resolution and uses `14318` in the quickstart; it does **not** hardcode `4318` (FR-009).

## Traceability

| Spec scenario / FR / SC | Unit(s) | Step(s) | Guardrail(s) |
|-------------------------|---------|---------|--------------|
| FR-001 (runnable as `python -m telemetry.demo_emit`) | U0, U2 | S1, S2 | pytest harness; ruff |
| FR-002 (exactly one span + one event) | U1 | S3 | label-on-both; reuse emit.py |
| FR-003 (emit via `emit.py` send funcs, no reinvention) | U1, U7 | S2, S3 | reuse real emit.py; zero runtime deps |
| FR-004 / US1 scenario 1 / SC-001 (label searchable on both) | U1 | S3, S5 | label-on-both; live ingestion |
| FR-005 / US2 scenario 1 / E3 (default label) | U3 | S2 | reuse emit.py; ruff |
| FR-006 / E4 (reject empty/whitespace label) | U4 | S2 | exit-non-zero contract |
| FR-007 / US1 scenario 2 / SC-002 (success stdout content) | U2 | S4 | success stdout contract |
| FR-008 / US3 scenarios 1–2 / E1, E2 / SC-003 (exit non-zero on failure) | U5 | S4 | exit-0-iff-both; failure stderr contract |
| FR-009 / E5 (reuse endpoint resolution, honour override) | U6(setup), S3/S5 checks | S3, S5 | endpoint resolution reused |
| FR-010 / SC-004 (zero third-party runtime deps) | U7 | S0, S2 | zero runtime deps; ruff |
| FR-011 / SC-005 (collector-free pytest; propagation + failed-exit anchors) | U0, U1, U5 | S0, S3, S4 | pytest harness; test-first |
| E6 / US1 (standalone, no feature-run context) | U6 | S3 | non-empty trace id |
| SC-001 (manual Grafana find) | U1 | S5 | live ingestion + label propagation |
