# Adherence rubric — did each phase follow its own skill's logic?

This is the checklist the **independent meta-reviewer** (phase-protocol Step 2) uses. It is *not* about whether the artifact is good (that's the output review, Step 3) — it is about whether the phase sub-agent **executed its skill's documented workflow and honoured that skill's guardrails**. A polished artifact produced by skipping mandated steps is a `DEVIATED`, because the skipped steps are exactly where the skill's value (interview rigour, convention hard-gate, independent review) lives.

The meta-reviewer is read-only, gets the phase sub-agent's hand-off report + the produced artifact + the skill's own `SKILL.md`, and returns `FOLLOWED | DEVIATED` with evidence per deviation.

## Specification phase checklist

- [ ] **Inputs gathered** — every referenced user story was actually read; investigation findings folded in (not re-derived); a missing story was flagged, not invented.
- [ ] **Interview content covered** — the five interview areas (outcome/scope, actors/triggers, behaviour/rules, edge cases/failure, acceptance/done) were each either answered from inputs (assumption recorded) or surfaced as a question. None silently skipped.
- [ ] **Template honoured** — file matches `specification/references/specification-template.md`: same frontmatter keys (incl. `user_stories`), same section order, every section filled.
- [ ] **BDD scenarios** present as Given/When/Then, grouped by capability.
- [ ] **Edge cases & error handling**, **acceptance criteria** (testable checklist), and **constraints** all populated.
- [ ] **Traceability table** maps every source story → scenarios → ACs; nothing dropped, nothing unsourced.
- [ ] **No buried assumptions** — assumptions in *Assumptions*, unresolved items in *Open questions* (blockers flagged), not hidden in prose.
- [ ] **Altitude** — outcome-focused; no gratuitous implementation design (domain vocabulary is allowed where it *is* the requirement).

## Plan phase checklist

- [ ] **Spec loaded & ready-gate applied** — the spec was read in full; planning was refused if the spec had blocking open questions (or those were resolved first).
- [ ] **Skill discovery ran** — a discovery sub-agent enumerated available skills and a per-step skill-usage map exists; missing-but-needed skills were flagged, not pretended into existence.
- [ ] **Convention audit hard-gate honoured** — every artifact type the plan touches has a row in the audit table with status `exists` / `created this run` / `gap`; **no implementation step depends on a row still marked `gap`**. (This is the user's load-bearing "establish conventions before implementation" requirement.) If the repo had no pytest harness and the plan needs unit tests, establishing it is a pre-implementation setup step.
- [ ] **BDD decomposed into testable units** — each scenario/AC maps to unit(s), each with a chosen test facility (pytest / dbt test / Pandera+Pydantic / artifact assertion) and a **falsifiable red test** intent (can fail before the code exists).
- [ ] **Guardrail register filled** — relevant gates named (pre-commit/ruff, dbt tests, validation, idempotency, OTel, the repo's non-obvious constraints), each with a "verify it's in place" check; for orchestration wiring, the green criterion is a **daemon/queued run**, not just `dagster definitions validate`.
- [ ] **Every step carries a self-review checkpoint** defining what an independent sub-agent will verify.
- [ ] **Template + numbering** — matches `plan/references/plan-template.md`; shares the spec's `NNN`.
- [ ] **Closed traceability** — every spec scenario/AC lands in ≥1 step; every step traces back.

## Implementation phase checklist

- [ ] **Readiness gate applied** — refused to run if a convention was still a `gap` or a blocking open question remained; closed setup steps (pytest harness, pre-commit) first.
- [ ] **Task graph built** — one task per plan step (split only for independently-testable sub-units; steps never merged); dependency edges + file/resource footprints recorded.
- [ ] **Parallelism was conservative** — only file-disjoint, no-shared-serial-resource tasks ran concurrently; anything touching `warehouse.duckdb` / the dbt manifest / `definitions.py` / shared config stayed serial; parallel tasks used worktree isolation.
- [ ] **Independent per-task review actually ran** — for **every** task, a *separate, read-only, adversarial* reviewer (not the implementer) returned PASS/GAPS/REWARD-HACKING. The hand-off report shows a verdict per task. This is the single most important check: confirm the review machinery *ran*, with evidence (verdicts listed), not just that code was committed.
- [ ] **Only PASS committed** — no task with an unresolved GAPS/REWARD-HACKING verdict was committed; no verdict was flipped by weakening a test/gate.
- [ ] **Commits are clean** — atomic Conventional Commits, one per task, message traces to the plan step; no `--no-verify`/`--skip`; no `git push`/`checkout`/`switch`/`reset --hard`/`clean`/`restore`/`rm`.
- [ ] **No reward-hacking slipped through** — spot-check committed diffs: no stubs/mocks/hardcoded values/defaults-on-failure outside tests; no silent fallback where the spec demands a raise; no test narrowed to pass.
- [ ] **Whole-plan green** — `uv run pre-commit run --all-files`, the relevant `dbt build`, `pytest` if a suite exists, all green; a daemon/queued run for any orchestration-wiring change.
- [ ] **§10 traceability closed** — every plan step became a committed task.

## Meta-reviewer prompt template

> You are an independent, read-only reviewer. **Do not edit anything.** Judge whether a phase sub-agent **followed the `<specification|plan|implementor>` skill's own documented workflow and guardrails** — not whether the output is good (that's a separate review).
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
