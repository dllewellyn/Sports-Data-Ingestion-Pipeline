# The universal phase protocol

Every build phase (Specification, Plan, Tasks, Implementation) runs this **same six-step loop**. Only the inputs, the delegated skill, and the adherence/output checks differ (those phase-specific bits live in `SKILL.md` §A–D and in `adherence-rubric.md`). The loop is what makes Feature more than "call the skills in a row": it verifies each phase did its job *and* did it the way its skill prescribes, before the next phase consumes its output. The spec-kit gate tools (`speckit-clarify`/`speckit-checklist`/`speckit-analyze`/`speckit-converge`) are lighter inserts between phases — they run, then gate — not full six-step loops.

```
   ┌─────────────────────────── one phase ───────────────────────────┐
1. delegate ─▶ 2. adherence check ─▶ 3. output review ─▶ 4. resolve ─┐
   (run skill)   (followed its own     (artifact good vs   (gaps/Q's) │
                  logic?)               its input?)                    │
        ▲                                                              │
        └──────────────── re-delegate on gaps ◀────────────────────── ┘
                                  │ clean
                                  ▼
                          5. self-learn ─▶ 6. gate ─▶ next phase
```

## Telemetry: label every spawn (applies to Steps 1–3)

This flow is traced end-to-end (`_shared/telemetry/`). **Immediately before you spawn ANY sub-agent** in this loop — the phase agent (Step 1) and each independent reviewer (Steps 2–3) — call:

```
python3 .agents/skills/_shared/telemetry/emit.py label-next --role <role> --phase <phase>
```

so its span carries a human label in the Grafana *Feature runs* waterfall. Use stable roles: `<phase>-phase` (e.g. `plan-phase`), `<phase>-adherence-check`, `<phase>-output-review`. The Claude Code hooks capture the spawn, the stop, and the sub-agent's own transcript (its tool calls + reasoning) automatically — this one call just supplies the role the hooks can't infer. It is best-effort: if telemetry is down it is a silent no-op; never block on it.

## Step 1 — Delegate the phase to a fresh sub-agent

`label-next --role <phase>-phase --phase <phase>`, then spawn a `general-purpose` sub-agent (full tools, so it can spawn its *own* nested sub-agents; **never `fork`**). Give it the **non-interactive delegation prompt** (templates below). The sub-agent must:

- Execute the named skill's **entire** documented workflow — every phase of that skill, in order. It reads the skill's own `SKILL.md` and `references/` and follows them.
- Run in **non-interactive mode**: wherever the skill would call `AskUserQuestion` or seek user approval, it instead **records** the question (with the options it would have offered and its own best-guess answer + rationale) and continues using the best guess where safe, or marks it a blocker where not.
- **Report back**, as its final message, a structured hand-off: artifact path(s); which workflow steps it ran (so the adherence check can verify); the decisions/assumptions it made; the list of surfaced questions/blockers; and the result of any reviews the skill itself mandates (Plan's per-step self-review design; Implementor's per-task independent reviews — with their verdicts).

One phase = one delegation. Do not bundle two phases into one sub-agent (it destroys the hand-off review between them).

## Step 2 — Adherence check (did it follow its own logic?)

`label-next --role <phase>-adherence-check --phase <phase>`, then spawn a **separate, independent, read-only** meta-reviewer (`general-purpose`, fresh context). Its sole job: confirm the phase sub-agent actually executed its skill's workflow and honoured that skill's guardrails — not merely that a file appeared. It uses the phase's checklist in `adherence-rubric.md` and returns `FOLLOWED | DEVIATED` with file:line / report evidence for every deviation.

This is distinct from Step 3: Step 2 judges *process* (was the skill run correctly), Step 3 judges *product* (is the artifact correct). A beautiful spec produced by skipping the interview still fails Step 2.

## Step 3 — Independent output review (is the artifact good vs its input?)

`label-next --role <phase>-output-review --phase <phase>`, then spawn another **separate, read-only** reviewer to judge the artifact against the phase's input:
- Spec vs the feature description + investigation findings (implementable, outcome-focused, nothing dropped/unsourced).
- Plan vs the spec (closed traceability, real red/green, convention gaps all closed, Constitution Check real).
- Tasks vs the plan (every plan step has a task, TDD-ordered, `[P]` only on file-disjoint work — confirmed by the 3-arg `trace-check.py`).
- Implementation vs the tasks + plan + spec (per-task reviews ran, no reward-hacking or constraint-bypass slipped through, whole-feature traceability closed).

For Plan and Implementation, this reviewer **confirms the skill's own internal review machinery ran** — it does not re-do or replace it. (Plan *defines* per-step self-review; Implementor *runs* per-task independent review. Feature checks they happened and spot-checks the result.)

You may reuse `code-review` for diff-level checking in the Implementation phase, but the adversarial reward-hacking lens from `../plan/references/self-review.md` is the baseline.

## Step 4 — Resolve gaps and blockers

Collect everything Steps 1–3 surfaced: the sub-agent's questions/assumptions, adherence deviations, output-review findings. For each, decide (per `blocker-protocol.md`):

- **Autonomously resolvable** (the inputs, the repo, or a sensible convention answer it) → re-delegate to a **fresh** phase sub-agent with the corrective guidance folded in (or, for a small fix, a tightly-scoped follow-up sub-agent). Re-run Steps 2–3 on the result. Loop until adherence is `FOLLOWED` and the output review is clean.
- **Genuine blocker** (unresolvable ambiguity, a gap needing a product/user decision, a missing convention, a destructive/irreversible action) → **pause and ask the user** via `blocker-protocol.md`, then fold the answer in and re-delegate.

Never flip a verdict by weakening a test or a gate, and never accept a `DEVIATED` adherence result — re-delegate instead.

## Step 5 — self-learn for the phase

Invoke the `self-learn` skill scoped to the work this phase just produced (its conversation slice + the git changes + the existing skills/CLAUDE.md). Because `self-learn` is **approval-gated**, relay its proposal table to the user and apply only what they approve. "No durable learnings this phase" is a valid, common outcome — don't manufacture learnings. Capture here keeps spec/plan/build gotchas fresh rather than batching them at the end.

## Step 6 — Gate before advancing

Confirm the phase's exit condition (in `SKILL.md` §A–C) is met — e.g. no blocking open question, convention table has zero gaps, whole-plan green. Only then feed the artifact into the next phase. If the gate fails, it's a blocker → Step 4.

---

## Delegation prompt templates (non-interactive mode)

Fill the `<…>` and pass as the sub-agent prompt. Keep the "do not contact the user" instruction verbatim — it is what makes the sub-agent safe to run headless.

### Specification

> You are running the **`specification`** skill end-to-end. Read `.agents/skills/specification/SKILL.md` and its `references/` and follow the entire workflow in order.
> **Inputs:** the user's free-text feature description: `<…>`; investigation findings: `<path or none>`.
> **Non-interactive mode — you cannot contact the user.** The skill already prefers informed guesses with ≤3 `[NEEDS CLARIFICATION]` markers — make those guesses (record them in Assumptions) and promote any genuine build-blocker to a recorded **blocker** with your best-guess pick. Do **not** call `AskUserQuestion`.
> **Produce:** the feature directory `specs/NNN-<slug>/` with `spec.md` + `checklists/requirements.md`, and write `.specify/feature.json`.
> **Return** (final message): the feature directory; the skill workflow steps you executed; assumptions made; surfaced questions/blockers (each with your best guess); and the `validate-spec.py` result.

### Plan

> You are running the **`plan`** skill end-to-end. Read `.agents/skills/plan/SKILL.md` and its `references/` and follow the entire workflow in order, including the Constitution Check, spawning the skill-discovery sub-agent and the convention-audit sub-agents, and producing the design artifacts.
> **Input:** the feature directory (resolve with `bash .agents/skills/_shared/spec-helpers/feature-dir.sh`); read its `spec.md`.
> **Non-interactive mode — you cannot contact the user.** Assume-and-record where safe, blocker-and-record where not; never call `AskUserQuestion`. **The convention/rule audit is a hard gate** — for any missing convention, draft it (via `create-rule`) and record it as a blocker needing approval rather than silently committing a rule on the user's behalf.
> **Produce:** `<feature_dir>/plan.md` + `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, every step carrying a self-review checkpoint.
> **Return:** the artifact paths; the skill steps executed; the skill-usage map; the convention-audit table with each row's status (exists / created-pending-approval / gap); the unit→test→trace map; and surfaced questions/blockers.

### Tasks

> You are running the **`tasks`** skill end-to-end. Read `.agents/skills/tasks/SKILL.md` and its `references/` and follow the workflow.
> **Input:** the feature directory (`feature-dir.sh`); read its `plan.md` and `spec.md`.
> **Non-interactive mode — you cannot contact the user.** Assume-and-record where safe; never call `AskUserQuestion`.
> **Produce:** `<feature_dir>/tasks.md` — story-phased, TDD-ordered, `[P]` only on file-disjoint tasks, every plan step referenced via `[Sn]`.
> **Return:** the tasks.md path; the skill steps executed; the `validate-tasks.py` and 3-arg `trace-check.py` results; and surfaced blockers.

### Implementor

> You are running the **`implementor`** skill end-to-end. Read `.agents/skills/implementor/SKILL.md` and its `references/` and follow the entire workflow: read the already-decomposed `tasks.md` (do NOT re-decompose), and for **each** task in phase order run its implement → **independent read-only review** → commit-on-PASS → tick-`[X]` loop, parallelising only file-disjoint `[P]` tasks per the repo's serial-state rules.
> **Input:** the feature directory (`feature-dir.sh`); read its `tasks.md`, `plan.md`, `spec.md`, and design artifacts.
> **Non-interactive mode — you cannot contact the user.** Assume-and-record where safe; record a blocker where a decision is genuinely needed; never call `AskUserQuestion`. **Constraint-bypass (lint-ignore, softened pre-commit, narrowed test, pushing files) is never an in-loop fix — escalate it as a blocker.** Make atomic Conventional Commits per passing task. Never `--no-verify`/`--skip`, never `git push`/`checkout`/`reset --hard`.
> **Return:** each task's status; for **each** task, the independent reviewer's verdict (PASS/GAPS/REWARD-HACKING) and the commit hash; the whole-feature green-check result (`pre-commit`, `dbt build`, `pytest`, and a daemon/queued run for any orchestration-wiring change); the 3-arg trace closure status; and any surfaced blockers.
