---
name: implementor
description: Execute an approved feature end-to-end — read the dependency-ordered <feature_dir>/tasks.md, run each task phase-by-phase (Setup → Foundational → user stories → Polish), delegate each task to an implementer sub-agent, independently review every task (plan/spec followed, tests present and useful, no scope drift, no reward-hacking), commit when a task genuinely passes and tick it [X] in tasks.md, run file-disjoint [P] tasks in parallel where safe, and loop until every task is done. USE WHEN the user wants to build/implement an already-planned-and-tasked feature, "run the tasks", "execute the feature", or drive it to done with per-task review and commits.
---

# Implementor

Implementor is the **execution phase after `tasks`**. It takes the feature's `tasks.md` (and the
`plan.md`, `spec.md` and design artifacts beside it) and drives it to a working, committed
implementation — one reviewed, green, atomically-committed task at a time, phase by phase, until
nothing in `tasks.md` is left undone.

Decomposition is **not** this skill's job any more — the `tasks` skill already produced the
dependency-ordered, story-phased, `[P]`-marked task list. Implementor *runs* it: it dispatches each
task to a fresh implementer sub-agent, has an **independent** reviewer verify the result against the
plan and spec, commits only on a genuine pass (and ticks the task `[X]` in `tasks.md`), parallelises
file-disjoint `[P]` tasks where the repo allows, and keeps going until the feature is complete.

The feature is located via `.specify/feature.json` (`_shared/spec-helpers/feature-dir.sh`).

A good implementor run is **plan-faithful** (every task does what the plan/spec said, no scope creep,
no dropped tasks), **test-honest** (a falsifiable check, red before green; a test that can't fail is a
failure), **independently reviewed** (the agent that wrote the code never certifies it), **committed
in safe increments** (one atomic Conventional Commit per passing task — every commit a known-good,
resumable checkpoint), and **parallel only where safe** (`[P]`, file-disjoint, no shared serial state).

## When to use this skill

- "Implement this feature / run the tasks / execute `tasks.md`."
- "Build it to completion with reviews and commits."
- A completed **tasks** (or `speckit-analyze`) proposes the hand-off to implementation.

If there is **no approved plan + tasks**, this is the wrong skill — run `plan` then `tasks` first
(and `specification` before those). Implementor does not invent tasks; if `tasks.md`/`plan.md` is
missing, stale, or has unresolved blocking open questions, stop and surface that.

## The workflow

Phase 0 is a hard gate (don't execute an unready feature); Phase 3 is the loop that repeats until done.

### 0. Load the feature and confirm it's ready (HARD GATE)

1. `FEATURE_DIR=$(bash .agents/skills/_shared/spec-helpers/feature-dir.sh --require-file tasks.md)`.
2. Read `$FEATURE_DIR/tasks.md` (the task graph — phases, ids, `[P]`, `[USn]`, `[Sn]`, dependencies),
   `$FEATURE_DIR/plan.md` (each step's red test, green criterion, guardrails, self-review checkpoint;
   convention audit; guardrail register; sequencing), and `$FEATURE_DIR/spec.md` (scenarios/FR/SC and
   constraints — the reviewer judges against the spec, not just the plan). Read any `data-model.md`,
   `contracts/`, `quickstart.md`.
3. **Load governance.** `.specify/memory/constitution.md` (canonical) and any project `CLAUDE.md` /
   `ARCHITECTURE.md`. The build must not contradict them.
4. **Refuse to run an unready feature.** Run the deterministic readiness checks first:

   ```bash
   python3 .agents/skills/_shared/spec-helpers/validate-plan.py  "$FEATURE_DIR/plan.md"
   python3 .agents/skills/_shared/spec-helpers/validate-tasks.py "$FEATURE_DIR/tasks.md"
   python3 .agents/skills/_shared/spec-helpers/trace-check.py "$FEATURE_DIR/spec.md" "$FEATURE_DIR/plan.md" "$FEATURE_DIR/tasks.md"
   ```

   `validate-plan.py` **fails on any convention row still marked `gap`** (the hard gate) and on a step
   missing its seven fields; `validate-tasks.py` fails on malformed/duplicate tasks or a missing
   plan-step reference; `trace-check.py` fails if a spec FR/SC has no covering step or a plan step has
   no task. If any fails — or the plan has BLOCKER open questions — stop and resolve first (close
   convention gaps via `create-rule` and commit before any feature task). A green run is necessary,
   not sufficient — still read the artifacts in full.
5. **Check `before_implement` hooks** in `.specify/extensions.yml` (enabled); execute mandatory, surface optional.

### 1. Build the execution order from tasks.md

The graph is already in `tasks.md` — do not re-decompose. Read it into the run's checklist
(a TaskCreate list mirroring the tasks.md ids): id · phase · `[USn]` · `[Sn]` · deps · `[P]` group ·
status. Execution respects the phase order: **Setup → Foundational → user stories (P1 → P2 → …) →
Polish**. Foundational blocks all stories. This checklist is the progress spine and the resume point.
As part of Setup, detect the tech stack from `plan.md` and create/verify the appropriate ignore files
(`.gitignore`, and `.dockerignore`/etc. only if the stack uses them).

### 2. Decide parallelism (conservatively)

`[P]` in `tasks.md` is the author's intent; you still apply the repo's serial-state rules — `[P]` is
honoured only when the rules agree. Footprint analysis + full rules: `references/task-graph.md`.

- **Safe to parallelise:** `[P]` tasks with disjoint file sets and no shared serial resource (e.g. two
  unrelated pure-Python modules with their own pytest files; independent docs).
- **Must stay serial (shared single-writer/global state):** anything that runs `dbt build` / touches
  `warehouse.duckdb` (DuckDB is single-writer); anything that rebuilds the dbt manifest; edits to
  `definitions.py` / asset-job/schedule/`AssetSelection` wiring; edits to shared config (`config.py`,
  `pyproject.toml`, `.env*`). Two at once corrupt state or race the manifest.
- When parallelising, give each concurrent implementer its **own git worktree**
  (`Agent` with `isolation: "worktree"`); **review + commit each in dependency order** as they return.
  When in doubt, serialize.

### 3. Execute the loop — implement → review → commit → tick, until done

Repeat until every task is `done`, in phase order. For each ready task (deps satisfied). Implementer
prompt + scoping: `references/delegation.md`. Review + commit protocol: `references/review-and-commit.md`.

1. **Delegate the implementation.** Spawn a fresh implementer sub-agent (`general-purpose`, or
   `worktree`-isolated for a parallel task) scoped to **exactly one task**. Hand it only that task's
   contract — its `[Sn]` plan step (goal, the red test to write first, implementation outline, green
   criterion, guardrails, governing conventions) — not licence to touch the rest. It does
   red→green→refactor: write the failing test, confirm it fails for the right reason, implement the
   minimum to pass, run the guardrails (`ruff`, `dbt build`, etc.), report what it changed and the
   commands it ran.
2. **Review independently (the gate).** Spawn a **separate, read-only, adversarial** reviewer — never
   the implementing agent. With file:line evidence it verifies: the task meets its spec scenario/FR/SC;
   the **plan was followed** and the agent **did not stray** beyond scope; the **test exists, is
   useful, and can actually fail**; conventions and the **constitution** are honoured; and there is
   **no reward-hacking** (no stubs/mocks/hardcoded values/defaults-on-failure outside tests; no
   suppressed/skipped/weakened gates). Returns PASS | GAPS | REWARD-HACKING. Reuse the plan skill's
   reviewer protocol — `../plan/references/self-review.md` — extended per `references/review-and-commit.md`.
3. **Gate on the verdict.** Only **PASS** advances. On GAPS / REWARD-HACKING, feed findings back (fix
   the code, or the test if the test was the problem), then **re-spawn a fresh reviewer** — never edit
   the test or weaken a gate to flip the verdict, never override the reviewer. Repeat until PASS.
   **Constraint-bypass is never an in-loop fix.** If making a task pass appears to require weakening a
   constraint — adding a lint-ignore (`# noqa`, a ruff ignore entry), softening/skipping pre-commit
   (`--no-verify`), loosening a hook, narrowing/`xfail`-ing a test, or pushing files that shouldn't be
   pushed — the implementer must **stop and escalate to the caller (`feature`'s blocker protocol, or
   the user)** rather than do it; the reviewer treats any such change as REWARD-HACKING, never PASS,
   and never approves it itself.
4. **Commit and tick.** On PASS, make one atomic **Conventional Commit** for that task via the guarded
   helper (`.agents/skills/_shared/git-helpers/bash/git-commit-safe.sh -m "<conventional msg>"
   <task's files>`) — it stages only the footprint, enforces the format, appends the co-author trailer,
   lets pre-commit run, and exposes none of the forbidden git verbs. Then mark the task `[X]` in
   `$FEATURE_DIR/tasks.md` (and `done` in the checklist). This is the known-good checkpoint.
5. **Advance.** Mark newly-unblocked tasks ready; dispatch the next (or next parallel batch). Keep
   looping through the phases.

### 4. Final verification, sync, and report

When every task is `[X]`:

1. Run the **whole-feature green check**, not just per-task: the full guardrail set
   (`uv run pre-commit run --all-files`; the relevant `dbt build`; `PYTHONPATH=src uv run pytest` if a
   suite exists). For any change to Dagster orchestration wiring, the green criterion is launching a
   run through the **daemon/queued path**, not merely `dagster definitions validate`.
2. Confirm **traceability is closed**: re-run the 3-arg `trace-check.py` for the mechanical
   FR/SC→step→task closure, then confirm by eye that each committed task genuinely delivers its mapped
   item (the script proves the mapping *exists*, not that it's *satisfied*). Report any gap.
3. `bash .agents/skills/_shared/spec-helpers/docs-sync.sh "$FEATURE_DIR"` (so the ticked `tasks.md`
   reaches the site), and run `after_implement` hooks from `.specify/extensions.yml`.
4. Report: tasks completed, commits made (hashes + messages), what's green, anything deferred to Open
   Questions, and propose the next steps in order: first **`speckit-converge`** to catch any unbuilt
   work against the spec, then **`improvement-review`** (architecture/reuse/repackaging upside,
   propose-only), then **`self-learn`** to codify learnings. Open a PR only if asked — you do not push.

## Guardrails

- **No execution without a ready plan + tasks (hard gate).** Missing/stale artifacts, an unresolved
  convention `gap`, a failing validator, or a BLOCKER open question stops the run.
- **One task in flight per agent; never self-certify.** Review is always a separate, read-only,
  adversarial sub-agent.
- **PASS is the only thing that commits.** GAPS/REWARD-HACKING never get committed and never get
  "fixed" by weakening the test or the gate. Re-spawn a fresh reviewer until a genuine PASS.
- **No reward-hacking — and the reviewer hunts for it** (constitution II). No placeholders/mocks/
  hardcoded values/stubs outside tests; no defaults-on-failure/silent fallbacks where the spec demands
  a raise; no suppressed/skipped/weakened gates (`--no-verify`, `--skip`, blanket `# noqa`,
  `xfail`/`skip` to dodge a failure); no test narrowed to make red go green.
- **Stay inside the task's scope.** Scope drift (touching other steps, refactoring unrelated code,
  gold-plating beyond the spec) is a review failure, not a bonus.
- **Trace, don't drop.** Every task traces to a plan step and a spec scenario/FR/SC; the run isn't done
  until the 3-arg trace closure is fully covered.
- **Respect the repo's serial/non-obvious constraints** in parallelism and order: single-writer DuckDB
  and the dbt manifest are shared state; keep `definitions.py`/`AssetSelection` edits serial and verify
  through a real queued run; no `from __future__ import annotations` in asset modules; prefixed dbt
  asset keys; `pathlib.Path`; config via `pydantic-settings`.
- **No backward-compatibility scaffolding** (constitution I). Remove the legacy path a task replaces.
- **Atomic, conventional, local commits only.** One per passing task. Never push; never use the
  destructive/branch-switching git commands.
- **Surface contradictions & knock-on effects.** If executing a task reveals the plan is wrong,
  contradicts a constraint, or implies unstated work, stop and surface it — don't silently deviate.

## References

- [`references/task-graph.md`](references/task-graph.md) — footprint analysis and the conservative parallelisation rules (what is safe vs must-stay-serial in this repo); the task list itself comes from `tasks.md`, not from here.
- [`references/delegation.md`](references/delegation.md) — scoping a single task and the implementer sub-agent prompt template (red→green→refactor, report-back contract, worktree isolation).
- [`references/review-and-commit.md`](references/review-and-commit.md) — the independent review gate (extends `../plan/references/self-review.md` with plan-adherence + scope-drift + test-usefulness checks), the verdict→action table, the atomic commit protocol, and ticking `[X]`.
- [`references/execution-loop.md`](references/execution-loop.md) — the driver loop: readiness gate, phase-ordered progress/state tracking, handling failures and re-reviews, resuming a partially-built feature, and final whole-feature verification.
- [`../plan/references/self-review.md`](../plan/references/self-review.md) — the base reviewer protocol this skill reuses; don't duplicate it, extend it.
