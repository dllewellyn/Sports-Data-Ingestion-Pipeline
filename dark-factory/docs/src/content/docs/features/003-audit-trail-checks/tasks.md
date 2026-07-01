---
title: "Tasks: Code-Defined Audit Trail Checks"
---

# Tasks: Code-Defined Audit Trail Checks

**Feature directory**: `specs/003-audit-trail-checks/`
**Date**: 2026-06-30
**Plan**: `plan.md`
**Status**: Draft

## Phase 1: Setup (shared infrastructure)

- [X] T001 [S0] Confirm the `uv`+`pytest` harness runs from repo root (`uv run pytest -q`) and `uv run ruff check` is clean on the touched tree, per plan step S0.
- [X] T002 [S0] Write failing smoke test `tests/test_audit_fixtures_smoke.py` that imports the shared fake-telemetry recorder fixture and the `loki_stub` HTTP fixture, asserting the stub returns canned `query_range` JSON and the recorder captures a `send_logs` call (red — fixtures do not exist yet).
- [X] T003 [S0] Add the shared test fixtures to make T002 green: extend the `recorders` pattern from `tests/test_telemetry_hooks.py` (fake-telemetry recorder for `send_logs`/`send_span`) and add a `loki_stub` fixture that starts an `http.server` on a free port serving canned `query_range` JSON, pointing the query client at it via `FEATURE_LOKI_HTTP_ENDPOINT` (deterministic, own free port, teardown — no live stack), in `tests/conftest.py`.
- [X] T004 [S0] Confirm the drafted `@audit` convention rule exists durably at `specs/003-audit-trail-checks/PROPOSED-audit-rule.md` and is recorded as approval-pending; do NOT commit it into `.specify/memory/constitution.md` (BLOCKER-1 — gated on user approval; see Dependencies & Notes).

> **BLOCKER-1 gate (approval precondition).** The `@audit` framework convention rule MUST NOT be committed into `.specify/memory/constitution.md` until the user approves it. T004 only verifies the durable draft; the commit-into-constitution task (T005) carries the approval precondition and stays unchecked until BLOCKER-1 is approved.

- [X] T005 [S0] **(PRECONDITION: BLOCKER-1 approved)** Commit the approved `@audit` framework convention from `specs/003-audit-trail-checks/PROPOSED-audit-rule.md` into `.specify/memory/constitution.md` under *Development Workflow & Quality Gates* (`docs(constitution): add @audit framework convention`). Must land before S3 self-review treats the convention as final. Skip while approval is pending.

## Phase 2: Foundational (blocking prerequisites)

> No user-story work begins until the Setup fixtures (T002–T003) are green. The convention-commit (T005) is approval-gated and does not block fixture-only or test-authoring work, but S3/S4 self-reviews must not treat the convention as final until T005 lands.

_(No additional foundational entities beyond the Setup fixtures — the framework's base modules are introduced per user story as their first task.)_

## Phase 3: User Story 3 — Capture reads + documented query surface (Priority: P1) 🎯 MVP prerequisite

**Goal**: Close the keys-only gap so telemetry records the actual path/pattern an agent (by role) read/edited/wrote/searched, and provide the documented `FeatureRunQuery` surface (`reads_by_role`, `get_all_reads_from_code_review_agent`, `all_diffs_for_feature`) over Loki. This is the hard data prerequisite for US1's flagship audit.
**Independent Test**: Feed a `Read` block through the enriched hook and assert a `tool_read` record carries the read path attributable to the role; seed canned `tool_read`/`commit` records into the `loki_stub` and assert the query helpers return the seeded values.

### Capture enrichment (S1 — `subagent_stop.py`)

- [X] T006 [US3] [S1] Write failing capture tests in `tests/test_tool_input_capture.py`: (a) a `Read` block `input={"file_path":"src/foo.py"}` ⇒ one `tool_read` record with `tool_input_value=="src/foo.py"`, `tool_name=="Read"`, `role` present; (b) ONE message with TWO `Read` blocks (`src/foo.py`, `src/bar.py`) ⇒ TWO `tool_read` records, both values present (no collision); (c) `Edit`/`Write` capture `file_path`, `Grep`/`Glob` capture `pattern`[+`path`]; (d) a >512-char value ⇒ truncated to 512 + `value_truncated="true"` + `value_len`; (e) positive secret `Grep pattern="sk-ABCD1234EFGH5678IJKL"` ⇒ masked first/last 4 + `value_redacted="true"`; (f) the hook still swallows all and exits 0; (g) no keys-only `inputs: …` body fragment for the file-touching tool set (red — keys-only body today).
- [X] T007 [US3] [S1] Enrich `.agents/skills/_shared/telemetry/hooks/subagent_stop.py` (`_transcript_records`/`_summarize_content`) to yield one dedicated `event_type="tool_read"` record per file-touching `tool_use` block (`Read`/`Edit`/`Write`/`Grep`/`Glob`), each carrying `tool_name`, `role`, `agent_id`, `msg_index`, and the captured value: apply the named `_SECRET_RE` mask FIRST (first/last 4 + `value_redacted="true"`), then the `MAX_TOOL_INPUT_VALUE=512` truncation (`value_truncated`/`value_len`); **remove** the keys-only branch for that tool set (Constitution I — non-file-touching tools keep their body summary); keep `contextlib.suppress` + `sys.exit(0)`. Make T006 green; keep `tests/test_telemetry_hooks.py` green.
- [X] T008 [US3] [S1] Write failing **negative redaction** test in `tests/test_tool_input_capture.py`: a ≥40-char *opaque path segment* (a real hashed/bundle path, e.g. `dist/assets/index-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0.js`) and `file_path="src/services/auth_secret_loader.py"` ⇒ full value verbatim, NO `value_redacted` (red — current catch-all over-masks the long opaque segment).
- [X] T009 [US3] [S1] Tighten the secret-redaction catch-all in `subagent_stop.py` so it does not over-mask real file paths: require the generic high-entropy branch to match a value with no `/` path separator AND meeting a length+entropy floor (or anchor to whole-value), so `git_files` diff paths (never masked) and a read of the same path stay byte-identical — preventing a spurious read-vs-diff desync in the flagship comparison. Make T008 green; keep T006 green.

### Query client (S2 — `audit/query.py`)

- [X] T010 [US3] [S2] Write failing query tests in `tests/test_audit_query.py` using `loki_stub`: seed canned `tool_read` records (code-review role, `tool_input_value` = `src/foo.py`,`src/bar.py`) and `commit` records with `git_files`; assert `get_all_reads_from_code_review_agent()=={src/foo.py,src/bar.py}` (read off the `tool_input_value` attr, not grepped from body) and `all_diffs_for_feature()` == the seeded union; assert an **unknown** run (stub returns ZERO records) ⇒ raises `UnknownRunError`; assert a **known** run with zero commit `git_files` ⇒ `all_diffs_for_feature()` returns `∅` with NO raise (E2≠E3). Red — client does not exist.
- [X] T011 [US3] [S2] Implement `.agents/skills/_shared/telemetry/audit/query.py`: `FeatureRunQuery` with a cached `_known()` probe (`{run_id="…"}`, `limit=1`) that raises `UnknownRunError` on zero hits; for known runs build LogQL `{run_id="…"} | event_type="tool_read" | role="…"`, GET via stdlib `urllib`, parse `resultType: streams`, read `tool_input_value` off each stream; `all_diffs_for_feature()` filters `event_type="commit"` and unions comma-split `git_files`; resolve `run_id`/`feature` from explicit args or `run-context.sh current`; env-config endpoint (`FEATURE_LOKI_HTTP_ENDPOINT`, no pydantic-settings). Make T010 green.

**Checkpoint**: The keys-only gap is closed and the query surface returns real per-role read paths and diff files for known runs (raising on unknown runs).

## Phase 4: User Story 1 — Author and run a code-defined audit (Priority: P1) 🎯 MVP

**Goal**: An author writes a single `@audit`-decorated function expressing a rule; the runner discovers every audit, evaluates each against a run's telemetry isolated from the others, derives a `pass`/`fail`/`error`/`warn` verdict with evidence on failure, prints it locally, and exits per the verdict mapping — including the flagship `all_changed_files_code_reviewed`.
**Independent Test**: Run the runner against a stub-Loki fixture run over an audit file with one pass, one fail, and one raising audit; assert the three verdicts print, exit `1`; an empty file ⇒ exit `2`; pass/warn-only ⇒ exit `0`; flagship passes when all reviewed and fails naming unreviewed files.

### Decorator, registry & verdict derivation (S3 — `audit/__init__.py`)

- [X] T012 [US1] [S3] Write failing decorator tests in `tests/test_audit_decorator.py`: decorate two functions ⇒ both in the registry with metadata; clean fn ⇒ `pass` (evidence `None`); `AuditFailure(evidence)` ⇒ `fail` carrying evidence; a `ValueError` ⇒ `error` with detail (never coerced to pass); `AuditWarning` ⇒ `warn`; a duplicate name ⇒ collision raise (Edge E4). Red — decorator/registry absent.
- [X] T013 [US1] [S3] Implement `.agents/skills/_shared/telemetry/audit/__init__.py`: registry, `audit()` decorator (usable bare and called, `name` defaults to `__name__`, str-coerced metadata, duplicate-name `AuditNameCollision`), `AuditFailure`/`AuditWarning`, and the per-audit evaluation mapping {clean→pass, AuditFailure→fail+evidence, AuditWarning→warn, other→error+detail} to `AuditResult`. Make T012 green.

### Runner + flagship audit (S4 — `audit/runner.py`)

- [X] T014 [US1] [S4] Write failing runner tests in `tests/test_audit_runner.py`: invoke the runner (import `runner` and call its entry, or `subprocess` `uv run python .../runner.py`) pointed at a fixture audit file doing `from audit import audit, AuditFailure` (one pass, one fail, one raising) over a `loki_stub` run ⇒ all three verdicts printed, exit `1`; an empty audit file ⇒ "no audits discovered" + exit `2`; pass/warn-only ⇒ exit `0`. Also assert the **flagship** `all_changed_files_code_reviewed`: pass when all changed files reviewed (SC-002); fail naming the unreviewed file(s) as evidence; a file read only by a non-code-review role ⇒ fail (Edge E6); a known run with empty diff ⇒ vacuous `pass` (Edge E3, US1 sc.5), distinct from an unknown run's `error` (Edge E2). Red — runner/flagship absent.
- [X] T015 [US1] [S4] Implement `.agents/skills/_shared/telemetry/audit/runner.py`: `sys.path.insert(0, <.agents/skills/_shared/telemetry>)`, argparse CLI mirroring `emit.py` (`--run-id`/`--feature`/`--path`/`--loki-endpoint`), import the `--path` audit file via `importlib` to populate the registry, iterate it with per-audit try/except (one `error` never stops the rest — FR-007), print per-audit verdict + evidence, and exit per R2 mapping (fail/error→1, pass/warn→0, no-audits→2). Implement the flagship `all_changed_files_code_reviewed` audit using S2's `FeatureRunQuery` (diff-minus-reviewed; empty-diff ⇒ vacuous pass). Make T014 green.

**Checkpoint**: An author can write an `@audit` and read its pass/fail/error/warn verdict from the runner without Grafana; the flagship works against a recorded run.

## Phase 5: User Story 2 — Audit results in Grafana keyed by name + metadata (Priority: P2)

**Goal**: Emit one fire-and-forget audit-result record per audit into Loki (name/verdict/metadata/evidence as structured metadata; `run_id`/`feature` as the existing index labels) and surface it on the Feature Runs Grafana dashboard, filterable by `feature`/`run_id` and audit name/metadata — with a telemetry outage changing no verdict or exit status.
**Independent Test**: Run with one passing + one failing audit and monkeypatched `send_logs` ⇒ two `event_type="audit_result"` records with name/verdict/metadata as per-record attrs and evidence on the failing one; make `send_logs` raise and assert verdicts + exit status are unchanged; `json.load` the dashboard and assert an `audit_result` panel exists.

### Emit results (S5 — `audit/result.py`)

- [X] T016 [US2] [S5] Write failing emit tests in `tests/test_audit_emit.py` (reuse the fake-telemetry recorder, monkeypatch `send_logs`): one record per audit with `event_type="audit_result"`, `audit`, `verdict`, and declared metadata as per-record attrs (`run_id`/`feature` as resource attrs), `evidence` on the failing one; then make `send_logs` raise and assert verdicts + exit status are unchanged (FR-012/Edge E7); assert no `loki-config.yaml` change is required (audit name rides as per-record attr, not a new index label). Red — emission absent.
- [X] T017 [US2] [S5] Implement `.agents/skills/_shared/telemetry/audit/result.py`: map `AuditResult` → `emit.send_logs(records=[…])` with `audit`/`verdict`/metadata/`evidence`/`event_type="audit_result"` as per-record `attrs` and `run_id`/`feature` as resource attrs; wire the runner (S4) to call it after each verdict, swallowing emission errors (inherit `emit.py` fire-and-forget). Make T016 green; leave `telemetry/loki/loki-config.yaml` untouched.

### Dashboard (S6 — `feature-runs.json`)

- [X] T018 [US2] [S6] Write failing dashboard test in `tests/test_dashboard_audit_panels.py`: `json.load` `telemetry/grafana/dashboards/feature-runs.json` and assert a panel exists whose target expr contains `event_type="audit_result"`. Red — panel absent.
- [X] T019 [US2] [S6] Add to `telemetry/grafana/dashboards/feature-runs.json` an "Audit failures" stat panel (red on ≥1, `sum(count_over_time({run_id="$run_id"} | event_type="audit_result" | verdict="fail" [$__range]))`) and an "Audit results" log panel (`{run_id="$run_id"} | event_type="audit_result"`), mirroring the existing "Gate failures"/"Gates" panels (same `loki` datasource, gridPos discipline, structured-metadata `| key="…"` filters — no `{audit=…}` selector, no new index label). Make T018 green; keep the JSON valid.

**Checkpoint**: Every executed audit produces one result discoverable in Grafana by `feature`/`run_id` and audit name; an outage loses zero verdicts.

## Phase 6: Polish & cross-cutting

### Documentation (S7 — FR-015)

- [X] T020 [US2] [S7] Write failing docs test `tests/test_docs_flagship_example.py`: extract the flagship code block from the docs page, inject `.agents/skills/_shared/telemetry` onto `sys.path` exactly as the runner does, `exec` it, and assert it imports (`from audit import …`) and registers an audit in the registry; assert the page shows the **by-path** invocation (`uv run python .agents/skills/_shared/telemetry/audit/runner.py`) NOT an `audit-run` console script, and contains the `| audit="…"` LogQL structured-metadata filter literal. Red — docs absent.
- [X] T021 [S7] Author the developer docs page (Starlight markdown under `docs/src/content/docs/...`): how to write an `@audit` function, the available query helpers, declaring metadata + where it appears, running the runner by path, and finding results in Grafana — reproducing the flagship example with EXACTLY `from audit import audit, AuditFailure, AuditWarning` and the by-path `uv run python .agents/skills/_shared/telemetry/audit/runner.py …` invocation, plus the `{run_id="…"} | audit="all_changed_files_code_reviewed"` LogQL filter from `contracts/grafana-logql.md`. Make T020 green.
- [X] T022 [P] [setup] Run `bash .agents/skills/_shared/spec-helpers/docs-sync.sh "$FEATURE_DIR"` to mirror the feature docs, and walk quickstart Scenarios A–H as the final validation reference.

## Dependencies & Execution Order

- **Setup (Phase 1)**: no dependencies — start immediately. T002 (red) before T003 (fixtures). T004 verifies the durable draft. **T005 is approval-gated (BLOCKER-1)** — it MUST NOT run until the user approves the `@audit` convention rule, and it must land before any S3/S4 self-review treats the convention as final.
- **Foundational (Phase 2)**: the Setup fixtures (T002–T003) block all user-story tests. No separate foundational entities.
- **User Story 3 (Phase 3, P1)**: depends on Setup fixtures. S1 (T006→T007→T008→T009) before S2 (T010→T011) — S2's `reads_by_role` cannot return real paths until S1 captures the value (the known gap).
- **User Story 1 (Phase 4, P1)**: depends on US3. S3 (T012→T013) is pure-Python and independent of S1/S2, but S4 (T014→T015) needs **both** S2 (query) and S3 (decorator/verdicts), so S3 precedes S4. Flagship lives in S4.
- **User Story 2 (Phase 5, P2)**: depends on US1. S5 (T016→T017) needs S4's `AuditResult`s; S6 (T018→T019) needs the `event_type="audit_result"` records S5 emits.
- **Polish (Phase 6)**: S7 docs (T020→T021) need the runnable framework S1–S5; T022 docs-sync/quickstart last.
- **Within a story**: the failing-test task precedes its implementation task (every `Tnnn` test is red-first); models/contracts → services → wiring.
- **Same-file serialization (NOT [P])**: T006/T007/T008/T009 all edit `subagent_stop.py` — serial. T010/T011 edit `audit/query.py`. T012/T013 edit `audit/__init__.py`. T014/T015 edit `audit/runner.py` (and wire to query/decorator). T016/T017 edit `audit/result.py` (T017 also touches `runner.py`, after T015). T018/T019 edit `feature-runs.json`. Each test/impl pair is serial.

### Parallel opportunities

- Within a phase, only file-disjoint, dependency-free tasks may run concurrently. The capture (`subagent_stop.py`), query (`query.py`), decorator (`__init__.py`), runner (`runner.py`), result (`result.py`), and dashboard (`feature-runs.json`) each have a single owning file edited by a serial test→impl pair, so almost nothing inside the implementation phases is `[P]`.
- S3 (decorator) is logically independent of S1/S2 and could be authored alongside US3, but is sequenced before S4 which needs both — not marked `[P]` to keep the per-story checkpoints clean.
- Only T022 (docs-sync + quickstart walk, disjoint from every code/test file) is marked `[P]`.

## Notes

- [P] = different files, no unmet dependency. A wrong [P] causes parallel write conflicts.
- [Sn] links each task to its plan step (traceability — every plan step S0–S7 has ≥1 task). [USn] maps it to a user story.
- Verify each test fails before implementing (red-first is mandatory — Constitution III). Commit after each task or logical group (Conventional Commits).
- **BLOCKER-1 (convention approval)**: T005 (commit the `@audit` rule into the constitution) is the ONLY task gated on user approval. Best guess / recommendation: approve the drafted `specs/003-audit-trail-checks/PROPOSED-audit-rule.md` as written and commit it before S3 relies on it. All other tasks proceed without it.
- No backward-compatibility tasks (Constitution I — the keys-only path for file-touching tools is removed, not dual-pathed); no task bypasses a quality gate (Constitution II); `loki-config.yaml` is never modified (no new index label).
