---
name: tasks
description: Turn an approved plan into an actionable, dependency-ordered tasks.md inside the feature directory — story-phased (Setup → Foundational → per-user-story → Polish), TDD-ordered (failing test task before its implementation task), with [P] parallel markers for file-disjoint work and a [Sn] reference linking every task back to its plan step. USE WHEN a feature has an approved plan and you need to break it into executable, traceable tasks before implementation.
---

# Tasks

Tasks is the phase **between `plan` and `implementor`**. It turns `<feature_dir>/plan.md` (plus the
spec and design artifacts) into `<feature_dir>/tasks.md`: a dependency-ordered, story-phased task list
that `implementor` executes. Splitting decomposition (here) from execution (`implementor`) is what
lets the rest of the chain — `speckit-analyze`, `speckit-converge`, `speckit-taskstoissues` — operate
on a stable task artifact.

The feature is located via `.specify/feature.json` (`_shared/spec-helpers/feature-dir.sh`).

A good `tasks.md` is:
- **Story-phased** — Setup → Foundational (blocking prerequisites) → one phase per prioritised user
  story (P1, P2, …) → Polish. Each user story is an independently testable, deliverable increment.
- **TDD-ordered** — within a step/story the failing-test task comes before its implementation task,
  mirroring the plan's red/green loop.
- **Dependency-ordered & parallel-aware** — tasks are numbered in execution order; `[P]` marks tasks
  that touch disjoint files and have no unmet dependency, so `implementor` can run them concurrently.
- **Plan-traceable** — every task carries a `[Sn]` reference to the plan step it implements, so
  `trace-check.py` can prove every plan step has at least one task.

## When to use this skill

- "Generate tasks for this feature / break the plan into tasks."
- A completed `plan` proposes the hand-off to tasks.

If there is no approved `plan.md`, run `plan` first — do not invent tasks without a plan.

## The workflow

### 0. Locate the feature and load inputs

1. `FEATURE_DIR=$(bash .agents/skills/_shared/spec-helpers/feature-dir.sh --require-file plan.md)`.
2. Read `$FEATURE_DIR/plan.md` (required — steps, guardrails, sequencing), `$FEATURE_DIR/spec.md`
   (required — prioritised user stories), and any `data-model.md`, `contracts/`, `research.md`,
   `quickstart.md`. Read `.specify/memory/constitution.md` for governing principles.
3. **Refuse to generate tasks from an unready plan.** If `validate-plan.py` fails on the plan, or the
   plan has **BLOCKER** open questions, stop and surface them.
4. Check `before_tasks` hooks in `.specify/extensions.yml` (enabled); execute mandatory, surface optional.

### 1. Derive tasks from the plan

1. **Phase 1 — Setup:** the plan's S0-style setup steps (harness, pre-commit, conventions established
   this run) become Setup tasks.
2. **Phase 2 — Foundational:** shared prerequisites that block all user stories (base models/contracts,
   shared infrastructure) become Foundational tasks.
3. **Phases 3+ — per user story (P1, P2, …):** for each prioritised story in the spec, emit the plan
   steps that satisfy it. **Within a story, the failing-test task precedes its implementation task**
   (the plan step's red before its green). Models before services before wiring.
4. **Final — Polish:** cross-cutting cleanup, docs, `quickstart.md` validation.

### 2. Number, mark, and reference

Each task line uses the format:

```
- [ ] T001 [P] [US1] [S2] <imperative description with the exact file path it touches>
```

- **T###** — sequential id in execution order.
- **[P]** — include only when the task touches files disjoint from every other concurrently-eligible
  task and has no unmet dependency (this is the file-disjoint parallelism `implementor` relies on).
- **[USn]** — the user story this task serves (omit for Setup/Foundational/Polish).
- **[Sn]** — the plan step this task implements. **Every implementation/test task must carry one** so
  spec→plan→tasks traceability closes; Setup/Polish tasks may reference the relevant setup step or be
  marked `[setup]`.
- Always include the concrete file path in the description.

### 3. Record dependencies and parallelism

Add the **Dependencies & Execution Order** section: phase dependencies, per-story dependencies,
within-story ordering (tests fail first; models → services → wiring), and the explicit parallel
opportunities. Respect repo ordering gotchas carried from the plan (bronze→silver→gold; single-writer
DuckDB; prefixed dbt asset keys).

### 4. Write and validate

Create `$FEATURE_DIR/tasks.md` from `references/tasks-template.md`. Then:

```bash
FEATURE_DIR=$(bash .agents/skills/_shared/spec-helpers/feature-dir.sh)
python3 .agents/skills/_shared/spec-helpers/validate-tasks.py "$FEATURE_DIR/tasks.md"
python3 .agents/skills/_shared/spec-helpers/trace-check.py "$FEATURE_DIR/spec.md" "$FEATURE_DIR/plan.md" "$FEATURE_DIR/tasks.md"
```

`validate-tasks.py` checks the task-line format, unique ids, the presence of phase and dependency
sections, and that plan-step references exist. `trace-check.py` (with the third argument) proves every
plan step has at least one task.

### 5. Sync to docs and hand off

1. `bash .agents/skills/_shared/spec-helpers/docs-sync.sh "$FEATURE_DIR"`.
2. Run `after_tasks` hooks from `.specify/extensions.yml`.
3. Propose the next step: `speckit-analyze` (cross-artifact consistency) then `implementor`.

## Guardrails

- **No tasks without an approved, valid plan.** A failing `validate-plan.py` or a BLOCKER blocks task
  generation.
- **TDD order is mandatory** where the plan defines a red/green step: the test task precedes the
  implementation task. Tests must be able to fail first.
- **Every plan step maps to at least one task** (proven by `trace-check.py`); no plan step is dropped.
- **`[P]` only for genuinely file-disjoint, dependency-free tasks.** A wrong `[P]` causes parallel
  write conflicts in `implementor`.
- **No backward-compatibility tasks** (constitution I); no tasks that bypass a quality gate
  (constitution II).
- **Each user story stays independently testable** — avoid cross-story dependencies that break the
  MVP-increment property.

## References

- [`references/tasks-template.md`](references/tasks-template.md) — the exact output format.
