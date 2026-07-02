---
name: feature
description: One-shot a feature end-to-end by orchestrating specification → clarify → checklist → plan → tasks → analyze → implementor → converge as independent sub-agents, with an adherence check and output review at every hand-off, blocker-gated user contact, the self-learning loop after every phase, and a final propose-only improvement-review. USE WHEN the user wants to take a feature from an idea all the way to committed, reviewed code in a single drive — "build this feature", "one-shot <feature>", "run the whole spec→plan→tasks→implement chain", or "take this to done".
---

# Feature (the end-to-end orchestrator)

Feature is the **conductor** of the phased workflow. It does not write specs, plans, tasks, or code
itself — it drives the skills that do, each as its **own independent sub-agent**, threaded through the
feature directory (`.specify/feature.json`). The full chain it conducts:

```
specification → speckit-clarify → speckit-checklist → plan → tasks → speckit-analyze → implementor → speckit-converge → improvement-review
```

`speckit-clarify`, `speckit-checklist`, and `speckit-analyze` are **mandatory** gate steps, not
optional. Between phases Feature (a) verifies the sub-agent actually followed its skill's internal
logic, (b) independently reviews the artifact that phase produced, (c) runs `self-learn`, and (d) only
then advances. After the build lands it runs `improvement-review` (propose-only) before the final
report. A single invocation thus takes a feature from *an idea* to *committed, reviewed,
learning-captured, improvement-assessed code* — without the user babysitting each phase.

A good feature run is **faithful to each phase's own logic**, **independently reviewed at every
hand-off** (the phase agent never certifies its own output), **self-improving** (`self-learn` after
every phase), **autonomous but honest** (runs back-to-back, pauses *only* on a genuine blocker), and
**traceable end-to-end** (every spec FR/SC → plan step → task → commit; nothing dropped).

## When to use this skill

- "Build this feature from this idea." / "One-shot `<feature>`."
- "Run the whole specification → plan → tasks → implementation chain."
- "Take this to done — spec it, clarify it, plan it, build it, capture the learnings."

**When *not* to use it.** If the open question is feasibility/approach, run `investigation` first. If
the user wants only one phase, invoke that skill directly. If a feature directory already exists with
some artifacts, Feature detects completed phases in Phase 0 and resumes from the first incomplete one.

## How it drives the sub-skills (read this first)

The phase skills run **interactive interviews** (`AskUserQuestion`). **Sub-agents cannot talk to the
user.** Feature runs in the main conversation and owns **all** user contact. Each phase sub-agent runs
in **non-interactive mode**: it executes its skill's full workflow but, wherever the skill would
interview or seek approval, it **records the question/assumption and returns it** to Feature, which
resolves it per the blocker protocol (autonomously if it can; by asking the user if it can't).

Phase sub-agents are spawned as `general-purpose` (full tools) — never `fork` — because each must
spawn its own nested sub-agents (e.g. `plan`'s skill-discovery `Explore`, `implementor`'s implementer
+ reviewer agents). The independent reviewers Feature itself spawns are read-only.

All phases after `specification` locate the feature the same way:
`FEATURE_DIR=$(bash .agents/skills/_shared/spec-helpers/feature-dir.sh)`.

## The workflow

Phase 0 is a hard gate. The build phases each run the **universal phase protocol**
(`references/phase-protocol.md`) — delegate → adherence check → output review → resolve/blocker →
self-learn → gate. The gate steps (clarify/checklist/analyze/converge) are lighter inserts described
below. Improvement-review is propose-only. Self-learn runs after every phase.

### 0. Intake and readiness (HARD GATE)

1. Gather inputs: the user's feature description and any upstream `investigation` findings
   (`investigations/<slug>/findings.md`).
2. **Detect resume.** If `.specify/feature.json` resolves to a feature dir, inspect which artifacts
   exist (`spec.md`, `plan.md`, `tasks.md`) and **resume from the first incomplete phase** (note this
   to the user). Otherwise this is a new feature — `specification` will create the directory, allocate
   the `NNN` (`next-number.sh specs`), and write `feature.json`.
3. Confirm the *what* is settled enough to specify; if feasibility/approach is open, propose
   `investigation` first.
4. **Load governance:** `.specify/memory/constitution.md` (canonical) and any project `CLAUDE.md` /
   `ARCHITECTURE.md`. Every phase's output is judged against the constitution.
4b. **Check for pre-existing uncommitted work before any phase edits a file.** Once a plan exists (or,
   on resume, immediately), run `git status --short` and `git diff --stat` and compare against the
   plan's *Source layout touched* list (or, pre-plan, against the feature description's likely files).
   If uncommitted changes already sit in a file this feature is about to edit, do **not** silently edit
   on top of them or silently fold them into this feature's commits — that breaks atomic-commit hygiene
   and misattributes work that isn't this feature's. Surface it via `blocker-protocol.md` (it is a
   concrete instance of "touches something outside the feature's scope") and let the user choose:
   commit the pre-existing work separately first, leave it and stage narrowly (`git add -p`), or pause
   entirely if it's still in-progress work elsewhere. Re-run this check at the start of the
   Implementation phase too, since time may have passed since Plan.
5. State the plan of record in one line (which phases run, that the run is autonomous and pauses only
   on a blocker) and begin — do not wait for approval to start; autonomy was chosen.
6. **Open the run trace (telemetry).** Run `bash .agents/skills/_shared/telemetry/run-context.sh init`
   for a NEW feature (no `--feature-dir`) — this mints a FRESH `run_id` + `trace_id` so each feature is
   its own run in the Grafana *Feature runs* dropdowns. When **resuming** a known feature, pass
   `--feature-dir <dir>` so it reuses that feature's existing run instead of forking. Every phase,
   sub-agent, gate, and commit is correlated to this id. This is best-effort: if the telemetry stack is
   down it is a silent no-op and the run proceeds normally. The `specification` phase binds this run to
   the feature dir (and mirrors the ids back into `feature.json`) the moment it writes `feature.json` —
   so the dashboard groups the run under its feature, not an opaque id; you do not repeat the bind here.
   Record the request that started the run so the dashboard shows it:
   `python3 .agents/skills/_shared/telemetry/emit.py event --type intake --phase intake --body "<the user's feature description>"`.

### A. Specification phase

Phase protocol with `skill: specification`.
- **Adherence (mechanical):** `validate-spec.py "$FEATURE_DIR/spec.md"` must pass. Then judge: user
  stories prioritised and independently testable; BDD scenarios real and outcome-altitude; FR/SC
  testable and measurable; assumptions/open-questions explicit; `feature.json` written.
- **Output review:** independent reviewer confirms the spec is implementable and outcome-focused.
- **Gate:** no spec open-question is labelled **BLOCKER**.

### A2. Clarify gate (MANDATORY)

Run `speckit-clarify` as a sub-agent over `spec.md` to surface and resolve underspecified areas (up to
its question budget); questions route through Feature per the blocker protocol. If it edits the spec,
re-run `validate-spec.py`. **Gate:** no unresolved clarification that materially blocks planning.

### A3. Checklist gate (MANDATORY)

Run `speckit-checklist` to generate the requirements-quality checklist(s) for the feature and validate
the spec against them. **Gate:** no critical requirements-quality item fails (ambiguous/untestable
requirement, unbounded scope). Failures route back to clarify/specification via the blocker protocol.

### B. Plan phase

Phase protocol with `skill: plan` (input: the clarified spec).
- **Adherence (mechanical):** `validate-plan.py "$FEATURE_DIR/plan.md"` must pass — template shape,
  every step's seven fields (incl. the self-review checkpoint), and the **convention-audit hard gate**
  (fails on any audit row still marked `gap` — the "establish conventions before implementation"
  requirement, checked by script). Then judge: skill-discovery ran; conventions genuinely established;
  the Constitution Check is real; design artifacts (`research.md`, `data-model.md`, `contracts/`,
  `quickstart.md`) present where relevant; BDD decomposed into units each with a falsifiable red test.
- **Output review:** `trace-check.py "$FEATURE_DIR/spec.md" "$FEATURE_DIR/plan.md"` (every FR/SC
  reaches a step; every non-setup step traces back), then confirm the mappings are meaningful and the
  red/green loop is real.
- **Gate:** `validate-plan.py` passes (zero `gap` rows) and no BLOCKER plan open-question remains.

### B2. Capability provisioning gate (MANDATORY — done OUTSIDE implementation)

Creating the *capabilities the build will rely on* — skills, hooks, rules, and guardrails — is a
**separate activity from implementation**, done here, before any feature code is written. The Plan
phase surfaces what's needed; this gate provisions it and amends the plan to mandate its use.

1. **Identify needs.** From the plan's *Skills to use* (rows marked MISSING), *Convention & rule
   audit* (rows that needed a new rule), and *Guardrail register* (gates not yet in place), plus a
   pre-plan scan of the feature description: enumerate the skills, hooks (`.specify/extensions.yml` /
   Claude Code hooks via the `update-config` skill), rules (`create-rule`), and guardrails
   (pre-commit/ruff config, dbt tests, validators) the build will depend on.
2. **Provision each, outside the implementation flow.** Create missing skills (skill-creator), rules
   (`create-rule`), hooks (`update-config`), and guardrail setup — each approval-gated via the blocker
   protocol, each committed on its own. These are **not** implementation tasks and must not be deferred
   into `implementor`; "figure out the convention as we build" is forbidden (inherited convention-audit
   hard gate).
3. **Amend the plan to mandate use.** Update `$FEATURE_DIR/plan.md` so the relevant steps explicitly
   require the newly-provisioned skills/rules/guardrails (e.g. a step now names the skill it must
   invoke, or the rule it must satisfy). Re-run `validate-plan.py` after the amendment.
4. **Gate:** every MISSING skill / convention `gap` / not-in-place guardrail the build depends on is
   either provisioned (and the plan updated to mandate it) or explicitly deferred with user approval.
   Unresolved → blocker.

### C. Tasks phase

Phase protocol with `skill: tasks` (input: the plan).
- **Adherence (mechanical):** `validate-tasks.py "$FEATURE_DIR/tasks.md"` must pass. Then judge: tasks
  are story-phased and TDD-ordered (test task before its implementation), `[P]` only on file-disjoint
  work, every plan step referenced.
- **Output review:** `trace-check.py "$FEATURE_DIR/spec.md" "$FEATURE_DIR/plan.md" "$FEATURE_DIR/tasks.md"`
  proves every plan step has a task.
- **Gate:** validators pass; no plan step left untasked.

### C2. Analyze gate (MANDATORY)

Run `speckit-analyze` as a read-only sub-agent for cross-artifact consistency across
`spec.md`/`plan.md`/`tasks.md` (duplication, ambiguity, coverage gaps, constitution alignment,
terminology drift). **Gate:** no critical inconsistency or constitution-alignment violation. Criticals
route back to the offending phase via the blocker protocol before any build begins.

### D. Implementation phase

Phase protocol with `skill: implementor` (input: `tasks.md` + `plan.md` + spec + design artifacts).
- **Delegate:** the sub-agent executes `implementor` end-to-end — phase-ordered, and for **each** task
  its own implement → independent-review → commit → tick-`[X]` loop, parallelising only file-disjoint
  `[P]` tasks per the repo's serial-state rules. (This sub-agent makes commits; expected.)
- **Adherence:** `implementor`'s **own** per-task independent review actually ran (Feature confirms the
  machinery ran, does not replace it); only PASS tasks committed; atomic Conventional Commits, one per
  task; no `--no-verify`/`--skip`, no `push`/`checkout`/`reset --hard`; serial-state constraints
  respected.
- **Output review:** independent reviewer spot-checks committed tasks for reward-hacking (constitution
  II) and confirms the 3-arg trace closure.
- **Gate:** the **whole-feature green check** passes — `uv run pre-commit run --all-files`, the
  relevant `dbt build`, `PYTHONPATH=src uv run pytest` if a suite exists; for any Dagster orchestration
  wiring change, a run launched through the **daemon/queued path** (not merely `dagster definitions
  validate`).

### D2. Converge gate

Run `speckit-converge` to assess the codebase against spec/plan/tasks and append any remaining unbuilt
work as new tasks in `tasks.md`. If it appends tasks, **loop back into Phase D** (implementor) for just
those tasks. When converge appends nothing, the feature is built.

### E. Improvement-review phase (evaluate the changeset)

Run `improvement-review` as an independent sub-agent over the changeset. **Propose-only and
approval-gated** (no adherence/gate cycle — it commits nothing). Relay its opportunities + evidence +
ripple sets for approval; an empty result is valid. **Do not auto-loop** a fresh plan→implementor
cycle from its proposals — record accepted opportunities as proposed next steps. (Exception: a finding
that the *current* change is broken/contradictory is a blocker.)

### F. Final verification and report

1. Confirm end-to-end traceability: every spec FR/SC → plan step → task → committed task. Report any break.
2. Confirm each phase's `self-learn` ran and approved learnings landed (or "nothing durable" honestly).
3. `docs-sync.sh "$FEATURE_DIR"` so the site reflects the final artifacts.
4. Report: feature directory, spec/plan/tasks paths, tasks completed, commits (hashes + messages),
   what's green, learnings codified, the analyze/converge outcomes, the improvement-review outcome
   (accepted opportunities + ripple sets as proposed next steps), and anything deferred. Offer to open
   a PR (Feature does not push) without taking it unbidden.
5. **Close the run trace:** `bash .agents/skills/_shared/telemetry/run-context.sh close --status ok`
   (use `--status error` if the run halted on an unresolved blocker) to emit the root `feature-run`
   span. Point the user at the *Feature runs* dashboard in Grafana (`localhost:3000`), filtered to this
   run's `run_id`, for the full stage/sub-agent waterfall and per-sub-agent drill-down.

## Guardrails

- **Each phase runs its skill in full — no shortcuts.** A returned artifact without the skill's
  mandated steps is an adherence failure → re-delegate.
- **The mandatory gates are mandatory.** clarify, checklist, and analyze always run; skipping one is a
  process failure, not an optimisation.
- **Never self-certify.** The agent that produced a phase's output never reviews it. Adherence/output
  reviews are separate read-only sub-agents; `implementor`'s per-task review must have actually run.
- **Autonomous, but a blocker is a full stop.** Pause and ask the user (`references/blocker-protocol.md`)
  on an unresolvable ambiguity, an un-closable review gap, a missing convention, a critical analyze
  finding, or a destructive/irreversible action. Never guess past a blocker, weaken a gate/test, or
  override a reviewer.
- **Conventions before code (inherited hard gate).** The Plan phase's convention audit closes every
  `gap` before the Implementation phase begins, and the B2 capability-provisioning gate creates needed
  skills/hooks/rules/guardrails outside implementation.
- **Constraint-bypass requires escalation, never self-approval.** Weakening any constraint to make a
  phase pass — adding a lint-ignore (`# noqa`, a ruff ignore entry), softening or skipping pre-commit
  (`--no-verify`), loosening a hook, narrowing/`xfail`-ing a test, or pushing files that shouldn't be
  pushed — must be **escalated to Feature via the blocker protocol** and approved by the user. No phase
  sub-agent, implementer, or reviewer may approve such a change itself. A review that finds one returns
  REWARD-HACKING, not PASS.
- **self-learn after every phase, approval-gated**; it routes durable rules to `CLAUDE.md`, a skill, or
  the **constitution** (`.specify/memory/constitution.md`). Never let a sub-agent silently edit them.
- **improvement-review after the build, propose-only, no auto-loop.**
- **Trace, don't drop, across phases.** A spec FR/SC missing from the plan, or a plan step with no task,
  is a hand-off failure — surface it.
- **Respect the repo's non-obvious + serial constraints throughout** (constitution + CLAUDE.md /
  ARCHITECTURE.md): single-writer DuckDB and the dbt manifest are shared state; keep `definitions.py`/
  `AssetSelection` edits serial and verify via a real queued run; no `from __future__ import
  annotations` in asset modules; prefixed dbt asset keys; `pathlib.Path`; config via `pydantic-settings`.
- **No backward-compatibility scaffolding** anywhere in the chain (constitution I).
- **Surface contradictions & knock-on effects** the moment any phase reveals them.

## References

- [`references/phase-protocol.md`](references/phase-protocol.md) — the universal six-step per-phase loop and the sub-agent prompt templates for delegating each skill in non-interactive mode.
- [`references/adherence-rubric.md`](references/adherence-rubric.md) — the per-phase checklist an independent meta-reviewer uses to confirm each sub-agent followed its *own* skill's logic, plus the meta-reviewer prompt template.
- [`references/blocker-protocol.md`](references/blocker-protocol.md) — what counts as a genuine blocker that justifies pausing, what does not, and how to ask the user crisply.
