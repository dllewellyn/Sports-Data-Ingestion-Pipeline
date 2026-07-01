---
title: "Tasks: Telemetry Emit Demo"
---

# Tasks: Telemetry Emit Demo

**Feature directory**: `specs/001-telemetry-emit-demo/`
**Date**: 2026-06-30
**Plan**: `plan.md`
**Status**: Draft

> Test runner is **`uv run pytest`** (pytest is a `uv` dev dependency, not globally installed).
> Pinned constants (use these exact values everywhere): span name `demo.emit`, default label
> `demo-emit`, label key `demo.label` (span attribute + Loki structured metadata), event body
> `demo emit: <label>`, event type `demo`. The module imports `emit.py` by inserting
> `<repo>/.agents/skills/_shared/telemetry` onto `sys.path` (idempotently) then `import emit`, using
> `Path(__file__).resolve().parent.parent` as the repo root.

## Phase 1: Setup (shared infrastructure)

> S0 and S1 were PROVISIONED and committed in the B2 capability gate (commit `c4d1605`). These tasks
> are **verify-only** — do NOT recreate `pyproject.toml`, `uv.lock`, `telemetry/__init__.py`, or the
> `tests/` harness.

- [X] T001 [S0] Verify-only: confirm the pytest + ruff harness already exists and runs — `pyproject.toml` is present with `[tool.pytest.ini_options] testpaths=["tests"]` and ruff lint set `E,W,F,I,UP,B,C4,SIM`, `uv.lock` is present, and `uv run pytest tests/test_harness_smoke.py -q` collects and passes (1 passed). Do NOT recreate any of these files (plan step S0).
- [X] T002 [P] [S0] Verify-only: confirm `uv run ruff check .` is clean on the existing tree (ruff config lives in the same root `pyproject.toml`). Do NOT add or modify config (plan step S0).
- [X] T003 [S1] Verify-only: confirm `telemetry/__init__.py` already exists and is empty (no exports) and that `python3 -c "import telemetry"` succeeds, so `python -m telemetry.demo_emit` will resolve once the module lands. Do NOT recreate the package marker (plan step S1).

## Phase 2: Foundational (blocking prerequisites)

> No user-story work begins until Phase 1 verification passes. There is no additional shared model or
> contract to build — the only blocking prerequisites are the provisioned harness (S0) and package
> marker (S1) verified above.

## Phase 3: User Story 1 — Emit a labelled span and event and learn where to find them (Priority: P1) 🎯 MVP

**Goal**: One run emits exactly one span (Tempo) and one matching event (Loki), both carrying the
supplied label under `demo.label`, prints span name / event body / label / destinations to stdout, and
exits 0.
**Independent Test**: With the stack up, run `python -m telemetry.demo_emit --label smoke-<unique>`,
observe the printed span name / event body / label / destinations and a 0 exit, then find the span in
Tempo and the event in Loki in Grafana by that label.

- [X] T004 [US1] [S2] Write failing tests in `tests/test_demo_emit.py`: U7 (top-level imports of `telemetry/demo_emit.py` are stdlib + `emit` only — parse/import-surface assertion, fails if any third-party import is added) and `test_module_is_importable` (`importlib.import_module("telemetry.demo_emit")` succeeds). Run `uv run pytest tests/test_demo_emit.py -q` and confirm red (module does not exist) — red before green (plan step S2).
- [X] T005 [US1] [S2] Implement the module skeleton in `telemetry/demo_emit.py`: emit.py-style module docstring, stdlib-only imports, pin constants `SPAN_NAME="demo.emit"`, `DEFAULT_LABEL="demo-emit"`, `LABEL_KEY="demo.label"`, `EVENT_TYPE="demo"`, and an **idempotent** `sys.path` insert of `<repo>/.agents/skills/_shared/telemetry` (repo root via `Path(__file__).resolve().parent.parent`; only insert if not already on `sys.path`) followed by `import emit`. Also wire `argparse` with the `--label` argument and pass the parsed label value through to where emission/stdout will consume it; at this US1 stage `--label` may be **required** (no default yet) so US1's tests, which always pass `--label`, stay green. `DEFAULT_LABEL` is defined as a constant here but is only WIRED as the argparse default later in T011. No emission logic yet (the actual span/event SEND calls still arrive in T007). Make T004 green; keep `uv run ruff check .` clean (plan step S2).
- [X] T006 [US1] [S3] Write failing tests in `tests/test_demo_emit.py`: U1 (with `--label smoke-1`, monkeypatch `emit.send_span`/`emit.send_logs`: each called exactly once, span `attrs` contain `("demo.label","smoke-1")` AND the event record `attrs` contain `("demo.label","smoke-1")`) and U6 (monkeypatch `emit.current_context` → `{}`: both sends invoked with a **non-empty** `trace_id`). Run `uv run pytest -q` and confirm red (no emission code) — red before green (plan step S3).
- [X] T007 [US1] [S3] Implement emission in `telemetry/demo_emit.py`: resolve ids via `emit.current_context()`; when `{}`, mint `trace_id=os.urandom(16).hex()`, a `span_id=os.urandom(8).hex()`, and a `run_id` that is a **valid Loki label value (no spaces)** since the user label can be arbitrary text. Always pass a **non-empty** `trace_id` to `send_span` (empty → `send_span` returns False → false FR-008 failure). Call `emit.send_span(..., name="demo.emit", attrs=[("demo.label", label)], strict=True)` and `emit.send_logs(..., records=[{"body": f"demo emit: {label}", "severity":"INFO", "attrs":[("event_type","demo"),("demo.label",label)]}], strict=True)`. No endpoint literal anywhere — endpoint resolution stays owned by `emit.py` (FR-009). Make T006 green; keep `uv run ruff check .` clean (plan step S3).
- [X] T008 [US1] [S4] Write failing test in `tests/test_demo_emit.py`: U2 (success path with both sends true — capsys asserts stdout contains span name `demo.emit`, the event body `demo emit: <label>`, the label, the strings `Tempo` and `Loki`, and the key `demo.label`). Run `uv run pytest -q` and confirm red (no stdout report contract yet) — red before green (plan step S4).
- [X] T009 [US1] [S4] Implement the success-path stdout report in `telemetry/demo_emit.py`: when both sends return True, print to stdout the span name → Tempo, event body → Loki, label, and `demo.label` key, then exit 0. Make T008 green; keep `uv run ruff check .` and `uv run ruff format --check .` clean (plan step S4).

**Checkpoint**: User Story 1 independently functional and testable collector-free (emit-once-with-label + success stdout + non-empty trace id).

## Phase 4: User Story 2 — Default label when none is supplied (Priority: P2)

**Goal**: Running with no `--label` applies the documented default `demo-emit`, emits both signals
under it, prints it, and exits 0.
**Independent Test**: Run `python -m telemetry.demo_emit` with no `--label`; confirm `demo-emit` is
used on both signals, printed to stdout, and the process exits 0.

- [X] T010 [US2] [S2] Write failing tests in `tests/test_demo_emit.py`: U4 (`--label "   "` whitespace → non-zero `SystemExit`, no send attempted, clear stderr message) and U3 (no `--label` → both sends carry `demo-emit` and it is printed). Run `uv run pytest -q` and confirm red (no `demo-emit` default / whitespace validation yet — the `--label` parser itself already exists from T005) — red before green (plan step S2).
- [X] T011 [US2] [S2] Complete the US2-specific `--label` behaviour in `telemetry/demo_emit.py` (the `argparse` parser and `--label` argument already landed in T005): (a) make `--label` optional by wiring the `demo-emit` **default** using the `DEFAULT_LABEL` constant from T005 so an omitted `--label` falls back to it; (b) add `.strip()` validation that **rejects** empty/whitespace-only values to **stderr** with a non-zero exit (do NOT default an empty value away). Make T010 green; keep `uv run ruff check .` clean (plan step S2).

**Checkpoint**: User Stories 1 and 2 both work independently (labelled + default-label paths).

## Phase 5: User Story 3 — Fail loudly when emission does not succeed (Priority: P2)

**Goal**: When either signal fails (collector unreachable, or partial failure), report the failed
signal on stderr, print no success line, and exit non-zero.
**Independent Test**: Point `FEATURE_OTLP_HTTP_ENDPOINT` at an unreachable address (or fake a `False`
return), run the module, confirm it reports the failure on stderr and exits non-zero with no success
line on stdout.

- [X] T012 [US3] [S4] Write failing tests in `tests/test_demo_emit.py`: U5 (three cases — monkeypatch `send_logs` → `False`; separately `send_span` → `False`; and a send that raises under `strict=True`): each asserts non-zero exit, stderr names the **specific** failed signal, and NO success line on stdout. Run `uv run pytest -q` and confirm red (no failure/exit-code logic yet) — red before green (plan step S4).
- [X] T013 [US3] [S4] Implement the outcome contract in `telemetry/demo_emit.py`: wrap **each** of `send_span` and `send_logs` in its **own** try/except (not both in one) so partial-failure attribution names the right signal; capture each boolean (and catch the `strict=True` exception per signal); if either is False/raised → print which signal failed to stderr and `sys.exit(1)` with no success line; exit 0 only when BOTH returned True. Make T012 green; verify `uv run pytest tests/test_demo_emit.py -q` (full file) passes and `uv run ruff check .` + `uv run ruff format --check .` clean (plan step S4).

**Checkpoint**: All three user stories work independently; the full collector-free pytest suite passes.

## Phase 6: Polish & cross-cutting

- [X] T014 [US1] [S5] Live verification per `quickstart.md` Layer 2: bring the telemetry stack up, run `python -m telemetry.demo_emit --label smoke-<unique>`, confirm exit 0, then confirm Grafana shows exactly one Tempo span `demo.emit` with `demo.label=<label>` and exactly one Loki event matching the label under `service.name=feature-orchestrator` (plan step S5).
- [X] T015 [US3] [S5] Live failure-path verification per `quickstart.md` Layer 3: run `FEATURE_OTLP_HTTP_ENDPOINT=http://localhost:1 python -m telemetry.demo_emit --label smoke-<unique>`, confirm a non-zero exit with a stderr failure report and NO success line on stdout (plan step S5).

## Dependencies & Execution Order

- **Setup (Phase 1)**: verify-only; no dependencies — start immediately. Must pass before any feature code.
- **Foundational (Phase 2)**: none beyond the verified harness (S0) and package marker (S1).
- **User Stories (Phase 3+)**: depend on Phase 1 verification. Recommended order P1 (US1) → P2 (US2) → P2 (US3); US2 and US3 build on the US1 module.
- **Within a story / step**: the failing-test task precedes its implementation task (red before green), mirroring the plan's S2 → S3 → S4 red/green loop.
- **Step ordering carried from the plan**: S2 (skeleton + import) → S3 (emission) → S4 (exit/report) → S5 (live verify). Each step adds its own red tests first.
- **`--label` parsing (both `[S2]`)**: the `argparse` parser and the `--label` argument are established in **T005** (US1), so US1's `--label smoke-1` tests (T006/T008) have their parser within US1; the `demo-emit` **default** (via the `DEFAULT_LABEL` constant) and the whitespace **validation** are completed later in **T011** (US2).
- **Same-file gotcha**: every task in Phases 3–5 edits the single file `telemetry/demo_emit.py` and/or the single file `tests/test_demo_emit.py`, so tasks T004–T013 are sequential and are **not** marked `[P]`.

### Parallel opportunities

- T001 and T002 are independent verify-only checks (T002 marked `[P]`); T003 is also independent of them but is left sequential for a clean Phase-1 gate.
- No `[P]` within Phases 3–5: `telemetry/demo_emit.py` and `tests/test_demo_emit.py` are each single files, so concurrent edits would conflict.

## Notes

- [P] = different files, no unmet dependency. A wrong [P] causes parallel write conflicts.
- [Sn] links each task to its plan step (traceability). [USn] maps it to a user story.
- Verify tests fail before implementing (run `uv run pytest`). Commit after each task or logical group.
- Reuse the real imported `emit.py` `send_span`/`send_logs` (no duplicated OTLP/HTTP; fakes only under `tests/`). No third-party runtime dependency (pytest/ruff are dev-only).
