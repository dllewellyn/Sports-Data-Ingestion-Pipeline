---
name: feature
description: One-shot a feature end-to-end by orchestrating the specification → plan → implementor skills as independent sub-agents, with an adherence check, an output review, blocker-gated user contact, and the self-learning loop after every phase. USE WHEN the user wants to take a feature from user stories/idea all the way to committed, reviewed code in a single drive — "build this feature", "one-shot <feature>", "run the whole spec→plan→implement chain", or "take these stories to done".
---

# Feature (the end-to-end orchestrator)

Feature is the **conductor** of the phased workflow. It does not write specs, plans, or code itself — it drives the three skills that do (`specification` → `plan` → `implementor`), each as its **own independent sub-agent**, and between phases it (a) verifies the sub-agent actually followed its own skill's internal logic, (b) independently reviews the artifact that phase produced, (c) runs the `self-learn` loop, and (d) only then advances. After the build lands it runs one more skill — `improvement-review` — to evaluate the whole changeset for architecture/reuse/repackaging upside (and the coupled skills/docs each opportunity would ripple into) before the final report. The result is that a single invocation takes a feature from *user stories / an idea* to *committed, reviewed, learning-captured, improvement-assessed code* — without the user having to invoke and babysit each phase by hand.

It is the automation of the hand-offs the skills each *propose* at their end. `specification` ends by proposing planning; `plan` ends by proposing `implementor`; `implementor` ends by proposing `improvement-review` then `self-learn`. Feature wires those proposals together and adds the connective tissue: an adherence check, an output review, and a disciplined blocker protocol so it can run **autonomously and stop only when genuinely blocked**.

A good feature run is:
- **Faithful to each phase's own logic** — each sub-agent executes its skill's documented workflow in full (not a shortcut), and an independent meta-reviewer confirms it did before the artifact is accepted.
- **Independently reviewed at every hand-off** — the spec is checked against the stories, the plan against the spec, the implementation against the plan + spec. The phase agent never certifies its own output; a separate read-only reviewer does.
- **Self-improving** — `self-learn` runs after every phase, so gotchas discovered while specing/planning/building are codified into `CLAUDE.md` or the skills while they're fresh.
- **Autonomous but honest** — it runs the chain back-to-back without check-in, and pauses to ask the user *only* on a genuine blocker (an ambiguity it cannot resolve from the inputs, a review gap it cannot close, a missing convention, or a destructive/irreversible choice). It never papers over a blocker to keep moving.
- **Traceable end-to-end** — every story lands in the spec, every spec scenario/AC lands in the plan, every plan step becomes a committed task. Nothing is dropped between phases.

## When to use this skill

- "Build this feature from these user stories." / "One-shot `<feature>`."
- "Run the whole specification → plan → implementation chain on US-00x."
- "Take this idea to done — spec it, plan it, build it, capture the learnings."
- The user has the *what* roughly in hand and wants the entire pipeline driven for them.

**When *not* to use it.** If the open question is *whether/which approach* (feasibility), run `investigation` first — Feature starts from a settled-enough *what*. If the user only wants one phase ("just write the spec", "just plan it"), invoke that single skill directly; Feature is for driving the whole chain. If a spec and plan already exist and only the build remains, `implementor` alone is lighter — but Feature still works (it detects completed phases in Phase 0 and resumes from the first incomplete one).

## How it drives the sub-skills (read this first)

The three phase skills run **interactive interviews** (`AskUserQuestion`). **Sub-agents cannot talk to the user.** Therefore Feature — which runs in the main conversation and *can* — owns **all** user contact. Each phase sub-agent is run in **non-interactive mode**: it executes its skill's full workflow but, wherever the skill would interview or seek approval, it instead **records the question/assumption and returns it** to Feature. Feature then resolves it per the blocker protocol (autonomously from the inputs if it can; by asking the user if it can't). This preserves every skill's interview *content* while routing it through the one process that can reach the user.

Phase sub-agents are spawned as `general-purpose` (full tools) — never `fork` — because each must spawn *its own* nested sub-agents (e.g. `plan`'s skill-discovery `Explore`, `implementor`'s implementer + reviewer agents). The independent reviewers Feature itself spawns are read-only.

## The workflow

Phase 0 is a hard gate. Phases A–C are each one run of the **universal phase protocol** (`references/phase-protocol.md`) — the same six-step loop with phase-specific inputs and checks. Phase D is the propose-only `improvement-review` evaluation (not the build protocol). Phase E closes out.

### 0. Intake and readiness (HARD GATE)

1. Gather the inputs: the user stories referenced (read each from `user_stories/`), the user's initial description, and any upstream `investigation` findings. If a referenced story can't be found, stop and ask — don't invent it.
2. Detect where to start. Scan `specs/` for an existing `NNN-<slug>-specification.md` / `-plan.md` that already covers this feature. If a phase's artifact already exists and is complete, **resume from the first incomplete phase** rather than redoing it (note this to the user). Decide the shared `NNN` the spec/plan will share.
3. Confirm the *what* is settled enough to specify. If the core feasibility/approach is still open, stop and propose `investigation` first — do not spec around an unknown.
4. Read and keep open the repo contract files: `CLAUDE.md` (*Non-obvious constraints*, *Python conventions*), `ARCHITECTURE.md`, `pyproject.toml`. Every phase's output is judged against these.
5. State the plan of record to the user in one line (which phases will run, the shared `NNN`, that the run is autonomous and will only pause on a blocker) and begin — do **not** wait for approval to start; autonomy was chosen.

### A. Specification phase

Run the phase protocol with `skill: specification`. Phase-specific:
- **Delegate:** the sub-agent executes the `specification` skill end-to-end against the stories + inputs, in non-interactive mode (interview questions → returned to Feature, not asked).
- **Adherence check** (did it follow its own logic): interview points were genuinely covered or surfaced as questions; the file matches `specification/references/specification-template.md`; BDD Given/When/Then scenarios present; edge cases + acceptance criteria + constraints filled; **traceability table** maps every story → scenarios → ACs; assumptions/open-questions made explicit, none buried. (Full rubric: `references/adherence-rubric.md`.)
- **Output review:** independent read-only reviewer confirms the spec is implementable, outcome-focused, and that nothing in the stories was dropped and nothing in the spec is unsourced.
- **Gate to advance:** no spec open-question is flagged as a *blocker*. A blocking open question is a genuine blocker → resolve via the blocker protocol before planning.

### B. Plan phase

Run the phase protocol with `skill: plan` (input: the spec from Phase A). Phase-specific:
- **Adherence check:** skill-discovery sub-agent was run and a skill-usage map produced; the **convention/rule audit hard-gate** was honoured — every artifact type the plan touches has a governing convention that *exists or was created+committed this run*, **no step depends on a convention still marked "gap"** (this is the user's explicit "establish conventions before implementation" requirement); BDD decomposed into testable units each with a chosen test facility and a falsifiable red test; the guardrail register is filled; **every step carries a self-review checkpoint**; file matches `plan/references/plan-template.md`; shares the spec's `NNN`.
- **Output review:** independent reviewer confirms every spec scenario/AC maps to ≥1 step and every step traces back to the spec (closed traceability), and that the red/green loop is real (tests can fail before the code exists).
- **Gate:** the convention audit table has **zero** rows still marked "gap", and no blocking plan open-question remains. Either is a hard blocker.

### C. Implementation phase

Run the phase protocol with `skill: implementor` (input: the plan from Phase B + its paired spec). Phase-specific:
- **Delegate:** the sub-agent executes `implementor` end-to-end — decompose into the task graph, and for **each** task run its own implement → independent-review → commit loop, parallelising only file-disjoint tasks per the repo's serial-state rules. (This sub-agent makes commits; that is expected.)
- **Adherence check:** the sub-agent actually ran **`implementor`'s own** per-task independent review (a separate read-only adversarial reviewer per task — Feature confirms this machinery *ran*, it does not replace it); only PASS tasks were committed; commits are atomic Conventional Commits, one per task; no `--no-verify`/`--skip`, no `git push`/`checkout`/`reset --hard`; serial-state constraints (single-writer DuckDB, dbt manifest, `definitions.py`/`AssetSelection`) respected in ordering/parallelism.
- **Output review:** independent reviewer spot-checks committed tasks for reward-hacking the per-task reviews might have missed (stubs/mocks/hardcoded values/defaults-on-failure outside tests; weakened gates; tests narrowed to pass), and confirms whole-plan traceability (§10) is closed.
- **Gate:** the **whole-plan green check** passes — `uv run pre-commit run --all-files`, the relevant `dbt build`, `PYTHONPATH=src uv run pytest` if a suite exists; and for any Dagster orchestration wiring change, a run launched through the **daemon/queued path** (not merely `dagster definitions validate`), per CLAUDE.md.

### D. Improvement-review phase (evaluate the changeset)

After the build is green and committed, run the `improvement-review` skill as an independent sub-agent over the changeset this run produced. This phase is **propose-only and approval-gated** — it is shaped like the `self-learn` pass, not like the build protocol (no adherence/output-review/gate cycle, since it produces no committed artifact).

- **Delegate:** the sub-agent executes `improvement-review` end-to-end — map what landed, run the three lenses (architecture quality, reuse, repackaging), and for **every** opportunity attach its complete **ripple set** (the coupled skills, `ARCHITECTURE.md`/`ERD.md` diagrams, `CLAUDE.md` constraints, dbt models and docs that must change with it). It is read-only: it edits nothing.
- **Relay for approval:** present its report (opportunities + evidence + ripple sets + routes) to the user, exactly as you relay `self-learn` proposals. An empty result ("no improvements warranted") is a valid, complete outcome — do not press the sub-agent to manufacture findings.
- **Do not auto-loop.** Feature does **not** spawn a fresh `plan` → `implementor` cycle from these proposals within the same run — that risks unbounded recursion. Accepted opportunities are recorded as proposed next steps in the final report for the user to kick off as a new Feature run. (The one exception: a finding that the *current* change is broken/contradictory is a blocker — handle it via the blocker protocol, don't defer it.)
- **No gate.** Because it's advisory, the improvement-review phase never blocks the run from reaching the final report; it only adds proposed follow-up work.

### E. Final verification and report

1. Confirm end-to-end traceability across all three artifacts: every story → spec scenario/AC → plan step → committed task. Report any break.
2. Confirm each phase's `self-learn` pass ran and its approved learnings landed (or that "nothing durable" was the honest outcome).
3. Report: the spec/plan paths, tasks completed, commits made (hashes + messages), what's green, every learning codified, the `improvement-review` outcome (accepted opportunities + their ripple sets, as proposed next steps), and anything deferred to Open questions. Offer the natural next step (e.g. open a PR — Feature does not push, and Feature does not auto-start the improvement refactors) without taking it unbidden.

## Guardrails

- **Each phase runs its skill in full — no shortcuts.** Feature must not inline-summarise or skip a phase's workflow. If a sub-agent returns an artifact without having run the skill's mandated steps, that's an adherence failure → re-delegate; it is never accepted as-is.
- **Never self-certify.** The agent that produced a phase's output never reviews it. Adherence and output reviews are always separate, read-only sub-agents. The per-task review inside `implementor` is likewise independent and must have actually run.
- **Autonomous, but a blocker is a full stop.** Run the chain without check-ins, but the moment a sub-agent surfaces an unresolvable ambiguity, a review gap that can't be closed from the inputs, a missing convention, or a destructive/irreversible action — **pause and ask the user** (`references/blocker-protocol.md`). Never guess past a blocker, never weaken a gate or a test to keep moving, never override a reviewer.
- **Conventions before code (inherited hard gate).** The Plan phase's convention audit must close every gap before the Implementation phase begins. Feature will not start building on an un-established convention.
- **self-learn after every phase, approval-gated.** Run it each phase; relay its proposals to the user for approval (it may honestly propose nothing). Never let a sub-agent silently edit `CLAUDE.md` or a skill.
- **improvement-review after the build, propose-only, no auto-loop.** Run it once over the changeset (Phase D); relay its opportunities + ripple sets for approval (empty is valid). It edits nothing, and Feature never auto-spawns a `plan`→`implementor` cycle from its proposals — accepted refactors are reported as next steps, run as a fresh Feature pass by the user. (A finding that the current change is *broken* is a blocker, not a deferred improvement.)
- **Trace, don't drop, across phases.** A story missing from the spec, a spec AC missing from the plan, or a plan step with no committed task is a hand-off failure — surface it, don't let it slide.
- **Respect the repo's non-obvious + serial constraints throughout** (CLAUDE.md / ARCHITECTURE.md): single-writer DuckDB and the dbt manifest are shared state; keep `definitions.py`/`AssetSelection` edits serial and verify them via a real queued run; no `from __future__ import annotations` in asset modules; prefixed dbt asset keys; `pathlib.Path`; config via `pydantic-settings`.
- **No backward-compatibility scaffolding** anywhere in the chain — replace legacy paths, don't make code serve old and new purposes (per the user's design principles).
- **Surface contradictions & knock-on effects** the moment any phase reveals them — between stories, between a phase's output and a repo constraint, or work the inputs imply but didn't state. Don't silently resolve them.

## References

- [`references/phase-protocol.md`](references/phase-protocol.md) — the universal six-step per-phase loop (delegate → adherence check → output review → resolve/blocker → self-learn → gate) and the sub-agent prompt templates for delegating each skill in non-interactive mode.
- [`references/adherence-rubric.md`](references/adherence-rubric.md) — the per-phase checklist an independent meta-reviewer uses to confirm each sub-agent followed its *own* skill's internal logic and guardrails, plus the meta-reviewer prompt template.
- [`references/blocker-protocol.md`](references/blocker-protocol.md) — what counts as a genuine blocker that justifies pausing the autonomous run, what does *not* (resolve it yourself), and how to ask the user crisply when you must.
