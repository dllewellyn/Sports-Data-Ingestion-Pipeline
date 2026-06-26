---
name: plan
description: Turn an approved Specification into a rigorous, guardrailed implementation plan stored as specs/NNN-<slug>-plan.md — discovers the skills that will accelerate the work, audits for missing conventions/rules and establishes them BEFORE implementation, decomposes BDD scenarios into testable units with an explicit red/green TDD loop, and defines a per-step self-review sub-agent that independently verifies each step against the spec. USE WHEN the user wants to plan HOW to build an already-specified feature — to plan an implementation, break a spec into testable steps, or set up the TDD/guardrail approach before writing code.
---

# Plan

Plan is the **build-preparation phase that comes after `specification` and before writing implementation code**. Its job is to turn an approved Specification into a plan an engineer (or this agent) can execute step by step, where *every step is testable, guardrailed, traceable to the spec, and independently reviewed*.

This is the structured cousin of plan mode: instead of a prose sketch, it produces a numbered plan in which each step states the failing test to write first, the implementation, the green criterion, the guardrails it must satisfy, and what a self-review sub-agent will check before the next step starts.

The output is one Markdown file, `specs/NNN-<slug>-plan.md`, sharing the **same `NNN` as the specification it implements** so the two stay paired.

A good plan is:
- **Spec-traceable** — every step maps back to a BDD scenario and/or acceptance criterion in the spec; nothing in the spec is left unplanned, nothing in the plan is unsourced.
- **Test-first** — each unit of behaviour has a test that can fail *before* the code exists and pass *after*. The red/green loop is explicit, not implied.
- **Guardrailed** — the quality gates that protect the change (pre-commit/ruff, dbt tests, Pandera/Pydantic validation, idempotency, telemetry) are named, and "is this guardrail actually in place?" is itself a checklist item.
- **Convention-clean before it starts** — any governing rule that *should* exist for the code we're about to write is established and committed **before** the first implementation step, not discovered mid-build.
- **Self-reviewing** — each step ends with an independent verification by a sub-agent that confirms the step exists, passes its test, meets the spec, honours conventions, and contains no reward-hacking.

## When to use this skill

- "Plan the implementation of spec 003 / this specification."
- "Break this spec into testable steps before we build."
- "Set up the TDD / red-green approach for <feature>."
- A completed **specification** proposes the hand-off to planning.

If *what to build* is still open, that is the `specification` skill's job first — do not plan against a spec that doesn't exist or hasn't been agreed. If feasibility/approach is the open question, that is `investigation`. This skill assumes the **what** is settled and produces the **how**.

## The workflow

Follow these phases in order. The convention audit (Phase 2) is a **hard gate**: implementation planning does not finalise until missing conventions are established.

### 0. Load the specification (the input)

1. Read the target `specs/NNN-<slug>-specification.md` in full — Summary, BDD scenarios, edge cases, acceptance criteria, constraints, assumptions, open questions, traceability.
2. Follow its frontmatter: read each linked story in `user_stories/` and any `investigation:` findings. Carry forward their constraints.
3. **Refuse to plan a spec that isn't ready.** If the spec has open questions flagged as blockers, stop and surface them — they must be resolved (or explicitly accepted) before planning. If no spec exists, offer to run the `specification` skill first; do not invent requirements.
4. Read the repo's contract files now and keep them open the whole way through: `CLAUDE.md` → *Non-obvious constraints*, `ARCHITECTURE.md` (layering & dependency rules), and `pyproject.toml` (ruff lint set, Python pin). The plan must not contradict any of them.

### 1. Skill discovery (delegate to a sub-agent)

Identify the *kinds of work* the spec implies, then find the skills that standardise or accelerate each — so the plan reuses established machinery instead of reinventing it.

1. Classify the work: e.g. data-ingestion pipeline, new dbt model, API client, validation/schema contract, Dagster asset wiring, telemetry, docs.
2. Spawn an `Explore` (or `general-purpose`) sub-agent to enumerate **all** available skills — project-local (`.agents/skills/`), user/global (`~/.claude`), and plugin skills — and match them to each kind of work. (Prompt + matching rubric: `references/skill-discovery.md`.)
3. Record, per planned step, which skill it will invoke (e.g. an ingestion-pipeline step → a "create data ingestion pipeline" skill if one exists; a warehouse step → the dbt/test skills; review → `code-architecture-review` / `analyze-*`).
4. **Surface gaps.** If a clearly-needed skill is *missing* (e.g. there's no "create data ingestion pipeline" skill but the spec is exactly that), say so and offer to create it (the `skill-creator` workflow) before relying on it — or to proceed without and capture the learning via `self-learn` afterwards. Don't silently pretend a skill exists.

### 2. Convention & rule audit — establish BEFORE implementation (HARD GATE)

For **every kind of artifact the plan will create or touch**, confirm the governing convention exists. Where one that *should* exist is missing, create and commit it **before** any implementation step. This is the user's explicit requirement: don't discover conventions mid-build.

1. Enumerate the artifact types this plan introduces — e.g. *new Python file*, *API/network code*, *ingestion code into module X*, *new dbt model in silver/gold*, *new Dagster asset module*, *new Pydantic/Pandera contract*.
2. For each, spawn a sub-agent to find the governing rules and the nearest analogous existing code (audit checklist + search targets: `references/convention-audit.md`). Sources include `CLAUDE.md`, `ARCHITECTURE.md`, `pyproject.toml` (ruff), any rules location (`.claude/rules/`, `~/.claude/CLAUDE.md`, `~/.claude/rules/`), and the existing code patterns the new code must mirror.
3. **Where a needed convention is absent, create it first** — use the `create-rule` command/skill to draft a concise rule, get user approval, and commit it. Examples: there's no rule for how ingestion modules structure validation; no rule for API client retry/error handling; no convention for where new dbt tests live.
4. **Special case — the test harness itself is a convention.** This repo has *no Python unit-test suite* (`CLAUDE.md`: "There is no Python unit-test suite"). If the plan will produce pure-Python units that need unit tests (Phase 3), then *establishing a pytest harness + its conventions is itself a Phase-2 step that must land before any red/green step* — flag it, get agreement, do it first. (Detail: `references/tdd-and-guardrails.md` → *No test suite yet*.)
5. Output of this phase: a short table of *artifact type → governing convention → status (exists / created this run / agreed gap)*. No implementation step in the plan may depend on a convention still marked "gap".

### 3. Decompose BDD into testable units

Bridge the spec's behaviour to concrete, test-first units.

1. For each BDD scenario and each acceptance criterion, define the **unit(s) of behaviour** that satisfy it — at outcome altitude (a function/asset/model behaviour and its observable result), not a full internal design.
2. For each unit, pick the **testing facility that will assert it** and write the test intent (the assertion that must fail before, pass after):
   - pure-Python logic → **pytest** unit test (requires the harness from Phase 2);
   - data-entering-the-system → **Pydantic** (per record) / **Pandera** (per frame) contract test;
   - warehouse transform/aggregate → **dbt test** run inline via `dbt build`;
   - end-to-end artifact → assert the produced **Parquet file / model output** exists and conforms.
3. Map each unit back to its scenario/AC. This mapping is the plan's traceability spine (it becomes a table in the plan doc). (How to choose the facility and write a failing-first test: `references/tdd-and-guardrails.md`.)

### 4. Define the red/green TDD loop and the guardrails

1. **TDD loop, adapted to this repo.** For each unit, lay out red → green → refactor against the facility chosen in Phase 3. Be honest where the facility isn't a classic unit test (dbt tests run via `dbt build`; Pandera validates a frame) and write the loop in those terms. Full mapping: `references/tdd-and-guardrails.md`.
2. **Name the guardrails** that protect this change and, for each, add a "verify it's in place" check to the plan: pre-commit hook installed + `ruff check`/`ruff format` clean; dbt tests present and run via `dbt build`; Pydantic/Pandera validation at the boundary; idempotency / re-run safety; OTel span emitted where the spec implies it; the repo's *Non-obvious constraints* (single-writer DuckDB, prefixed dbt asset keys, no `from __future__ import annotations` in asset modules) respected. **For Dagster orchestration wiring (changes to `definitions.py` assets/jobs/schedules/resources, or any `AssetSelection`), the green criterion must launch a run through the daemon/queued path — not merely `dagster definitions validate` or import/unit tests, which load the location in a single process and so miss daemon-workspace and `AssetSelection.all()` resolution failures.**
3. A guardrail that isn't yet in place becomes a Phase-2-style setup step that runs *before* the work it guards.

### 5. Sequence into steps, each with a self-review checkpoint

1. Order the units into steps respecting dependencies and the repo's ordering gotchas (e.g. bronze→silver→gold; prefixed dbt asset keys; single-writer DuckDB — derive Parquet inside dbt, read the file in Python).
2. Give **every step** the same shape (the plan template enforces it): goal · spec trace (scenario/AC) · failing test to write first (red) · implementation outline · green criterion · guardrails to satisfy · **self-review checkpoint**.
3. The self-review checkpoint defines exactly what an independent sub-agent will verify for that step. The reviewer protocol and its prompt template are in `references/self-review.md`.

### 6. Write the plan document

Create `specs/NNN-<slug>-plan.md` using `references/plan-template.md` **exactly** — same frontmatter keys and section order, same per-step shape. Share the spec's `NNN`. Fill every section; carry the skill-usage map (Phase 1), the convention-audit table (Phase 2), the unit→test→trace map (Phase 3), the guardrail register (Phase 4), and the sequenced steps (Phase 5). Put anything unresolved under *Open questions* (blockers flagged) and any taken-as-true item under *Assumptions* — never bury an assumption.

### 7. Drive execution with per-step self-review (when the user proceeds to build)

When the user says go, execute the plan step by step. For each step:

1. **Red** — write the failing test from the step; run it; confirm it fails for the right reason.
2. **Green** — implement the minimum to pass; run the test (and the relevant guardrails — `ruff`, `dbt build`).
3. **Self-review (independent sub-agent).** Spawn a fresh `general-purpose` agent (or invoke the `code-review` skill) with the reviewer prompt from `references/self-review.md`. It is read-only and adversarial: it confirms the step *actually* meets its spec scenario/AC, the test genuinely exercises the behaviour (not a test that can't fail), conventions are honoured, and there's **no reward-hacking** (no stubs/mocks/hardcoded values/defaults-on-failure outside test contexts; no suppressed gates). It returns a verdict: pass / gaps (with evidence) / reward-hacking detected.
4. **Gate.** Do not start the next step until the current one passes review. Fix and re-review on a fail — never weaken the test or the gate to make it pass.
5. At each logical conclusion, make an atomic Conventional Commit (per the user's git rules). Do not `git push`.

## Guardrails

- **No plan without an agreed spec.** Blocking open questions in the spec block planning; surface them, don't plan around them.
- **Conventions before code (hard gate).** Every artifact type the plan touches must have a governing convention that *exists or is created this run* before the step that depends on it. "We'll figure out the pattern as we go" is not allowed.
- **Test-first or it's not a step.** Every step has a test that can fail before the code exists. A step with no falsifiable check is incomplete.
- **No reward-hacking — and the reviewer hunts for it.** No placeholders, mocks, hardcoded values, stubs, or defaults-on-failure outside test contexts; never suppress, skip, or add permissive variants to a quality gate or test to make a step pass. The per-step self-review explicitly looks for these.
- **Trace, don't drop.** Every spec scenario and AC lands in at least one step; every step traces back to the spec. Prove it in the plan's traceability table.
- **No backward-compatibility scaffolding.** Plan to remove legacy paths, not to make code serve both its old and new purpose (per the user's design principles).
- **Surface contradictions & knock-on effects.** If the spec implies work it didn't state, or collides with a repo constraint, say so in the plan rather than silently resolving it.
- **Respect the repo's non-obvious constraints** (CLAUDE.md / ARCHITECTURE.md) in every step — they caused real bugs.

## References

- [`references/plan-template.md`](references/plan-template.md) — the exact output format (frontmatter + sections + per-step shape). Copy it verbatim and fill it in.
- [`references/skill-discovery.md`](references/skill-discovery.md) — the sub-agent prompt and rubric for finding/matching helpful skills and flagging missing ones.
- [`references/convention-audit.md`](references/convention-audit.md) — the audit checklist, where rules/conventions live, how to detect a missing one, and how to establish it (via `create-rule`) before implementation.
- [`references/tdd-and-guardrails.md`](references/tdd-and-guardrails.md) — how red/green TDD works *in this repo's setup* (pytest vs dbt tests vs Pandera/Pydantic), choosing the right test facility, and the guardrail register.
- [`references/self-review.md`](references/self-review.md) — the per-step self-review sub-agent: when to spawn it, its read-only/adversarial prompt template, and the verdict format.
