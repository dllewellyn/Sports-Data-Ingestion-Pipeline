# Adherence rubric — did each phase follow its own skill's logic?

This is the checklist the **independent meta-reviewer** (phase-protocol Step 2) uses. It is *not* about whether the artifact is good (that's the output review, Step 3) — it is about whether the phase sub-agent **executed its skill's documented workflow and honoured that skill's guardrails**. A polished artifact produced by skipping mandated steps is a `DEVIATED`, because the skipped steps are exactly where the skill's value (interview rigour, convention hard-gate, independent review) lives.

The meta-reviewer is read-only, gets the phase sub-agent's hand-off report + the produced artifact + the skill's own `SKILL.md`, and returns `FOLLOWED | DEVIATED` with evidence per deviation.

## Specification phase checklist

- [ ] **Inputs gathered** — the free-text description was used; investigation findings (if any) folded in (not re-derived).
- [ ] **Guess-don't-interrogate honoured** — informed guesses recorded in *Assumptions*; at most 3 `[NEEDS CLARIFICATION]` markers; build-blockers promoted to *Open Questions* as **BLOCKER**. (`validate-spec.py` passes.)
- [ ] **Template honoured** — `specs/NNN-<slug>/spec.md` matches `specification/references/specification-template.md`: metadata lines (Feature directory/Created/Status/Input), mandatory H2 sections present and ordered, every section filled; `.specify/feature.json` written.
- [ ] **Prioritised user stories** — P1/P2/… each independently testable, each with Given/When/Then acceptance scenarios describing observable outcomes.
- [ ] **Edge cases**, **functional requirements** (`FR-NNN MUST`), **success criteria** (`SC-NNN`, measurable + tech-agnostic), and **constraints** (referencing the constitution) all populated.
- [ ] **No buried assumptions** — assumptions in *Assumptions*, unresolved items in *Open Questions* (blockers flagged), not hidden in prose.
- [ ] **Altitude** — outcome-focused; no gratuitous implementation design (domain vocabulary is allowed where it *is* the requirement).
- [ ] **Checklist generated** — `checklists/requirements.md` created and validated.

## Plan phase checklist

- [ ] **Spec loaded & ready-gate applied** — the spec was read in full (located via `feature.json`); planning was refused if the spec had BLOCKER open questions (or those were resolved first).
- [ ] **Constitution Check present** — the plan lists the relevant constitution principles and how it complies; any violation is justified in Complexity Tracking or the plan changed. Re-checked after design.
- [ ] **Design artifacts produced** — `research.md` resolves each unknown (decision/rationale/alternatives); `data-model.md`/`contracts/`/`quickstart.md` produced where the feature warrants them.
- [ ] **Skill discovery ran** — a discovery sub-agent enumerated available skills and a per-step skill-usage map exists; missing-but-needed skills were flagged, not pretended into existence.
- [ ] **Convention audit hard-gate honoured** — every artifact type the plan touches has a row in the audit table with status `exists` / `created this run` / `gap`; **no implementation step depends on a row still marked `gap`**. (This is the user's load-bearing "establish conventions before implementation" requirement.) If the repo had no pytest harness and the plan needs unit tests, establishing it is a pre-implementation setup step.
- [ ] **BDD decomposed into testable units** — each scenario/AC maps to unit(s), each with a chosen test facility (pytest / dbt test / Pandera+Pydantic / artifact assertion) and a **falsifiable red test** intent (can fail before the code exists).
- [ ] **Guardrail register filled** — relevant gates named (pre-commit/ruff, dbt tests, validation, idempotency, OTel, the repo's non-obvious constraints), each with a "verify it's in place" check; for orchestration wiring, the green criterion is a **daemon/queued run**, not just `dagster definitions validate`.
- [ ] **Every step carries a self-review checkpoint** defining what an independent sub-agent will verify.
- [ ] **Template** — `<feature_dir>/plan.md` matches `plan/references/plan-template.md` (keyword H2 sections, metadata lines).
- [ ] **Closed traceability** — every spec FR/SC lands in ≥1 step; every non-setup step traces back (`trace-check.py`).

## Tasks phase checklist

- [ ] **Plan loaded & ready-gate applied** — `validate-plan.py` passed before tasks were generated; refused on a BLOCKER.
- [ ] **Template honoured** — `<feature_dir>/tasks.md` matches `tasks/references/tasks-template.md`; `validate-tasks.py` passes.
- [ ] **Story-phased & TDD-ordered** — Setup → Foundational → per-user-story (P1→…) → Polish; within a story the failing-test task precedes its implementation task.
- [ ] **Parallel markers honest** — `[P]` only on file-disjoint, dependency-free tasks.
- [ ] **Every plan step referenced** — each task carries `[Sn]`; the 3-arg `trace-check.py` confirms every plan step has a task.

## Implementation phase checklist

- [ ] **Readiness gate applied** — refused to run if a convention was still a `gap`, a validator failed, or a BLOCKER remained; closed setup steps (pytest harness, pre-commit, ignore files) first.
- [ ] **Execution order from tasks.md** — the run followed the phase-ordered `tasks.md` (it did **not** re-decompose); dependency/`[P]`/footprint respected.
- [ ] **Parallelism was conservative** — only file-disjoint, no-shared-serial-resource tasks ran concurrently; anything touching `warehouse.duckdb` / the dbt manifest / `definitions.py` / shared config stayed serial; parallel tasks used worktree isolation.
- [ ] **Independent per-task review actually ran** — for **every** task, a *separate, read-only, adversarial* reviewer (not the implementer) returned PASS/GAPS/REWARD-HACKING. The hand-off report shows a verdict per task. This is the single most important check: confirm the review machinery *ran*, with evidence (verdicts listed), not just that code was committed.
- [ ] **Only PASS committed** — no task with an unresolved GAPS/REWARD-HACKING verdict was committed; no verdict was flipped by weakening a test/gate.
- [ ] **Commits are clean** — atomic Conventional Commits, one per task, message traces to the plan step; no `--no-verify`/`--skip`; no `git push`/`checkout`/`switch`/`reset --hard`/`clean`/`restore`/`rm`. Run the shared **read-only** auditor for the mechanical half — `bash .agents/skills/_shared/git-helpers/bash/git-audit-commits.sh` reports per commit whether the subject is Conventional, whether it's a merge, and its file count (flagging likely non-atomic commits), and exits non-zero if any commit fails. Judge the **semantic** half yourself: one-commit-per-task and "message traces to the plan step".
- [ ] **No reward-hacking or constraint-bypass slipped through** — spot-check committed diffs: no stubs/mocks/hardcoded values/defaults-on-failure outside tests; no silent fallback where the spec demands a raise; no test narrowed to pass; **no lint-ignore added, pre-commit/hook softened, or files pushed** to get a green (any such bypass must have been escalated, not self-approved).
- [ ] **Tasks ticked** — each committed task is marked `[X]` in `tasks.md`.
- [ ] **Whole-feature green** — `uv run pre-commit run --all-files`, the relevant `dbt build`, `pytest` if a suite exists, all green; a daemon/queued run for any orchestration-wiring change.
- [ ] **Traceability closed** — the 3-arg `trace-check.py` shows every spec FR/SC → plan step → task; every task committed.

## Meta-reviewer prompt template

> You are an independent, read-only reviewer. **Do not edit anything.** Judge whether a phase sub-agent **followed the `<specification|plan|tasks|implementor>` skill's own documented workflow and guardrails** — not whether the output is good (that's a separate review).
>
> **You are given:** the skill's `SKILL.md` (`.agents/skills/<skill>/SKILL.md`); the phase sub-agent's hand-off report (the steps it claims it ran, decisions, surfaced questions, and any internal-review verdicts); and the produced artifact(s) at `<path>`.
>
> **Check each item in the `<skill>` checklist** from `.agents/skills/feature/references/adherence-rubric.md`. For Plan and Implementor especially, verify the skill's **own internal review** was actually performed (Plan: every step has a self-review checkpoint; Implementor: a separate adversarial reviewer returned a verdict for *every* task). Treat "the report claims it but there's no evidence" as a deviation.
>
> **Return exactly:**
> - **Verdict:** FOLLOWED | DEVIATED
> - **Per-item:** ✓/✗ for each checklist item, with file:line or report-line evidence for every ✗
> - **Deviations:** bullet list of what the sub-agent skipped or shortcut, and which checklist item it violates
> - **Required to reach FOLLOWED:** the specific steps that must be re-run (empty if FOLLOWED)
