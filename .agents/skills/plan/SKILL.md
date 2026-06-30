---
name: plan
description: Turn an approved Specification into a rigorous, guardrailed implementation plan stored as <feature_dir>/plan.md, alongside the Phase-0/1 design artifacts (research.md, data-model.md, contracts/, quickstart.md). Checks the plan against the project constitution, discovers accelerating skills, audits for missing conventions and establishes them BEFORE implementation, decomposes BDD scenarios into testable units with an explicit red/green TDD loop, and defines a per-step self-review sub-agent that independently verifies each step against the spec. USE WHEN the user wants to plan HOW to build an already-specified feature.
---

# Plan

Plan is the **build-preparation phase after `specification` (and `speckit-clarify`) and before writing
implementation code**. It turns an approved Specification into a plan an engineer (or this agent) can
execute step by step, where *every step is testable, guardrailed, traceable to the spec, and
independently reviewed* — and it produces the design artifacts (research, data model, contracts,
quickstart) the rest of the chain reads.

Output lives **inside the feature directory**: `<feature_dir>/plan.md` plus sibling `research.md`,
`data-model.md`, `contracts/`, `quickstart.md`. The feature is located via `.specify/feature.json`
(resolve with `_shared/spec-helpers/feature-dir.sh`) — never via a git branch.

A good plan is **spec-traceable**, **test-first** (each unit has a test that can fail before the code
exists), **guardrailed** (the gates protecting the change are named and verified in place),
**convention-clean before it starts** (any governing rule that should exist is established and
committed before the first implementation step), **constitution-compliant**, and **self-reviewing**
(each step ends with an independent verification by a sub-agent).

## When to use this skill

- "Plan the implementation of this feature / spec."
- "Break this spec into testable steps before we build."
- A completed **specification** (or `speckit-clarify`) proposes the hand-off to planning.

If *what to build* is still open, that is `specification` first. If feasibility/approach is open,
that is `investigation`. This skill assumes the **what** is settled and produces the **how**.

## The workflow

The convention audit (Phase 2) and the Constitution Check are **hard gates**: planning does not
finalise until missing conventions are established and the plan complies with the constitution.

### 0. Locate the feature and load inputs

1. Resolve the feature directory: `FEATURE_DIR=$(bash .agents/skills/_shared/spec-helpers/feature-dir.sh --require-file spec.md)`.
2. Read `$FEATURE_DIR/spec.md` in full — user scenarios, edge cases, functional requirements,
   success criteria, constraints, assumptions, open questions.
3. **Refuse to plan a spec that isn't ready.** If the spec has **BLOCKER** open questions, stop and
   surface them; they must be resolved (or explicitly accepted) first. If no spec exists, offer to run
   `specification`.
4. **Load governance.** Read `.specify/memory/constitution.md` (canonical) and any project `CLAUDE.md`
   / `ARCHITECTURE.md` that exist. The plan must not contradict the constitution.
5. **Check `before_plan` hooks** in `.specify/extensions.yml` (enabled). Execute mandatory hooks and
   wait; surface optional ones.

### 1. Phase 0 — research the unknowns → `research.md`

For each `[NEEDS CLARIFICATION]` in the spec, each technology choice, and each dependency, resolve the
decision (dispatch research sub-agents where useful). Write `$FEATURE_DIR/research.md` with, per
unknown: **Decision**, **Rationale**, **Alternatives considered**. No unknown may remain before
Phase 1.

### 2. Skill discovery (delegate to a sub-agent)

Classify the kinds of work the spec implies and find the skills that standardise or accelerate each,
so the plan reuses established machinery. Spawn an `Explore`/`general-purpose` sub-agent to enumerate
**all** skills (project-local, user/global, plugins) and match them to each work kind. Record per
planned step which skill it will use. **Surface gaps** — if a clearly-needed skill is missing, say so
and offer to create it (or proceed without and capture via `self-learn`). Prompt + rubric:
`references/skill-discovery.md`.

### 3. Convention & rule audit — establish BEFORE implementation (HARD GATE)

For **every artifact type the plan will create or touch**, confirm the governing convention exists;
where one that should exist is missing, create and commit it **before** any implementation step.

1. Enumerate artifact types (new Python module, API client, ingestion code, new dbt model, new
   Dagster asset module, new Pydantic/Pandera contract, …).
2. For each, find the governing rule and nearest analogous code (checklist + search targets:
   `references/convention-audit.md`). Sources: the **constitution**, `CLAUDE.md`, `ARCHITECTURE.md`,
   `pyproject.toml` (ruff), any rules location, and existing patterns the new code must mirror.
3. Where a needed convention is absent, **create it first** (via `create-rule`), get approval, commit.
4. **The test harness itself is a convention.** If the plan produces pure-Python units needing unit
   tests and no pytest harness exists, establishing it is a Phase-3 (S0) setup step that lands before
   any red/green step.
5. Output: a table of *artifact type → governing convention → status (exists / created this run /
   gap)*. No implementation step may depend on a row still marked `gap` — `validate-plan.py` enforces
   this mechanically.

### 4. Phase 1 — design artifacts

1. **`data-model.md`** — extract entities from the spec: fields, relationships, validation rules,
   state transitions.
2. **`contracts/`** — interface/schema contracts (API schemas, CLI grammars, frame schemas) where the
   feature exposes or consumes one. Omit the directory if purely internal.
3. **`quickstart.md`** — runnable validation scenarios (prerequisites, setup, the command to run,
   expected outcome). A reference for proving the feature works end-to-end — not test code.
4. **Re-check the Constitution Check** after design; if a violation appeared, record it in *Complexity
   Tracking* with justification or change the design.

### 5. Decompose BDD into testable units + red/green + guardrails

1. For each scenario / functional requirement / success criterion, define the **unit(s) of behaviour**
   at outcome altitude, and pick the **test facility** that asserts it (pytest / Pydantic / Pandera /
   dbt test / artifact assertion). Write the failing-first assertion. Map each unit back to its spec
   item — this is the traceability spine.
2. **Name the guardrails** protecting the change and add a "verify it's in place" check for each
   (pre-commit + ruff clean; dbt tests via `dbt build`; boundary validation; idempotency; constitution
   principles). **For Dagster orchestration wiring (changes to `definitions.py` assets/jobs/schedules/
   resources, or any `AssetSelection`), the green criterion must launch a run through the daemon/
   queued path — not merely `dagster definitions validate`**, which loads the location in one process
   and misses daemon-workspace and `AssetSelection.all()` resolution failures. Facilities + register
   detail: `references/tdd-and-guardrails.md`.

### 6. Sequence into steps, each with a self-review checkpoint

1. Order units into steps respecting dependencies and repo ordering gotchas (bronze→silver→gold;
   prefixed dbt asset keys; single-writer DuckDB — derive Parquet inside dbt, read the file in Python).
2. Give **every step** the seven-field shape (template-enforced): goal · spec trace · failing test
   first (red) · implementation outline · green criterion · guardrails to satisfy · self-review
   checkpoint.
3. The self-review checkpoint defines what an independent sub-agent will verify. Protocol + prompt:
   `references/self-review.md`.

### 7. Write the plan document

Create `$FEATURE_DIR/plan.md` using `references/plan-template.md` **exactly** — same headings and
order, same per-step shape. Fill every section: Summary, Technical Context, Constitution Check,
Project Structure, Skills to use, Convention audit, Testable units, Guardrail register, Implementation
Steps, Sequencing, Complexity Tracking, Assumptions, Open Questions, Traceability. Put unresolved items
under *Open Questions* (blockers labelled **BLOCKER**); taken-as-true items under *Assumptions*.

Then run the deterministic linters and fix anything they flag:

```bash
FEATURE_DIR=$(bash .agents/skills/_shared/spec-helpers/feature-dir.sh)
python3 .agents/skills/_shared/spec-helpers/validate-plan.py "$FEATURE_DIR/plan.md"
python3 .agents/skills/_shared/spec-helpers/trace-check.py "$FEATURE_DIR/spec.md" "$FEATURE_DIR/plan.md"
```

`validate-plan.py` enforces the heading shape, that **every** step carries its seven fields, and the
**convention-audit hard gate** (fails if any audit row is still `gap`). `trace-check.py` proves
traceability closes both ways (every spec scenario/FR/SC reaches a step; every step traces back).

### 8. Sync to docs and hand off

1. `bash .agents/skills/_shared/spec-helpers/docs-sync.sh "$FEATURE_DIR"` to mirror the new artifacts
   into the Starlight site.
2. Run `after_plan` hooks from `.specify/extensions.yml` (e.g. `speckit.agent-context.update`, which
   refreshes the managed agent-context section to point at this plan).
3. Propose the next step: the `tasks` skill (which generates `tasks.md` from this plan), then
   `speckit-analyze` and `implementor`. **Execution is `implementor`'s job, not this skill's** — Plan
   produces the plan; do not start building here.

## Guardrails

- **No plan without an agreed, ready spec.** BLOCKER open questions in the spec block planning.
- **Conventions before code (hard gate).** Every artifact type has a convention that exists or is
  created this run before the step that depends on it. "Figure out the pattern as we go" is not allowed.
- **Constitution-compliant.** The plan complies with `.specify/memory/constitution.md`; violations are
  justified in Complexity Tracking or the plan changes. Never plan to bypass a quality gate.
- **Test-first or it's not a step.** Every step has a test that can fail before the code exists.
- **No reward-hacking — and the reviewer hunts for it.** No placeholders, mocks, hardcoded values,
  stubs, or defaults-on-failure outside tests; never suppress/skip/weaken a gate to make a step pass.
- **Trace, don't drop.** Every spec scenario/FR/SC lands in a step; every step traces back. Proven in
  the traceability table.
- **No backward-compatibility scaffolding** (constitution I). Plan to remove legacy paths.
- **Don't pre-empt reuse-harvesting; build the spec simply.** Reuse/repackaging assessment is the
  post-build `improvement-review` skill's job. Extract now only when a second caller is already real.
- **Surface contradictions & knock-on effects** between the spec and repo constraints or the
  constitution rather than silently resolving them.

## References

- [`references/plan-template.md`](references/plan-template.md) — the exact output format.
- [`references/skill-discovery.md`](references/skill-discovery.md) — sub-agent prompt + rubric for finding/matching skills and flagging gaps.
- [`references/convention-audit.md`](references/convention-audit.md) — the audit checklist, where conventions live, and how to establish a missing one before implementation.
- [`references/tdd-and-guardrails.md`](references/tdd-and-guardrails.md) — red/green TDD in this repo's setup (pytest vs dbt tests vs Pandera/Pydantic) and the guardrail register.
- [`references/self-review.md`](references/self-review.md) — the per-step self-review sub-agent: its read-only/adversarial prompt and verdict format.
