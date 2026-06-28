---
name: implementor
description: Execute an approved implementation plan end-to-end — decompose specs/NNN-<slug>-plan.md into a dependency-ordered task graph, delegate each task to an implementer sub-agent, independently review every task (plan followed, tests present and useful, no scope drift, no reward-hacking), commit when a task genuinely passes, run file-disjoint tasks in parallel where safe, and loop until the whole plan is complete. USE WHEN the user wants to build/implement an already-planned feature, "run the plan", "execute spec NNN", or drive a plan to done with per-task review and commits.
---

# Implementor

Implementor is the **execution phase that comes after `plan`**. Its job is to take an approved `specs/NNN-<slug>-plan.md` (and its paired `specs/NNN-<slug>-specification.md`) and drive it all the way to a working, committed implementation — one reviewed, green, atomically-committed task at a time, until nothing in the plan is left undone.

It is the disciplined executor of the loop the `plan` skill sketches in its Phase 7. Plan *describes* per-step red/green + self-review; Implementor *runs* it at scale: it breaks the plan into a task graph, dispatches each task to a fresh implementer sub-agent, has an **independent** reviewer verify the result against the plan and spec, commits only on a genuine pass, parallelises file-disjoint tasks where the repo allows, and keeps going until the plan is complete.

A good implementor run is:
- **Plan-faithful** — every task traces to a plan step; the build does what the plan said, no more (no scope creep) and no less (no dropped steps).
- **Test-honest** — each task lands a falsifiable check that genuinely exercises the behaviour (red before, green after); a test that can't fail is treated as a failure, not a pass.
- **Independently reviewed** — the agent that wrote the code never certifies its own work; a separate read-only reviewer decides pass/gap/reward-hacking before anything is committed.
- **Committed in safe increments** — each passing task is an atomic Conventional Commit, so every commit is a known-good checkpoint and the run is resumable.
- **Parallel only where safe** — independent, file-disjoint tasks fan out to concurrent sub-agents; anything touching shared state (the DuckDB warehouse, the dbt manifest, `definitions.py`) stays serialized.

## When to use this skill

- "Implement spec 003 / build the plan / execute `specs/003-…-plan.md`."
- "Run the plan to completion with reviews and commits."
- "Break this plan into tasks and start building."
- A completed **plan** proposes the hand-off to implementation.

If there is **no approved plan**, this is the wrong skill — run `plan` first (and `specification` before that if the *what* is unsettled). Implementor does not invent steps the plan didn't authorise; if the plan is missing, stale, or has unresolved blocking open questions, stop and surface that rather than improvising the build. See `references/execution-loop.md` → *Refuse to run an unready plan*.

## The workflow

Follow these phases in order. Phase 0 is a hard gate (don't execute an unready plan); Phase 3 is the loop that repeats until done.

### 0. Load the plan and confirm it's ready to execute (HARD GATE)

1. Read `specs/NNN-<slug>-plan.md` in full — every step's goal, spec trace, red test, implementation outline, green criterion, guardrails, and self-review checkpoint; plus §3 convention audit, §4 testable units, §5 guardrail register, §7 sequencing, §10 traceability.
2. Read the paired `specs/NNN-<slug>-specification.md` and carry forward its scenarios/ACs and constraints — the reviewer judges against the spec, not just the plan.
3. Read the repo contract files and keep them open: `CLAUDE.md` (*Non-obvious constraints*, *Python conventions*), `ARCHITECTURE.md` (layering), `pyproject.toml` (ruff set, Python pin). The build must not contradict them.
4. **Refuse to run an unready plan.** If §3 still lists a convention as a **gap**, or §9 has blocking open questions, or required setup steps (pytest harness, pre-commit) aren't done — stop and resolve those first (the plan's Phase 2 should have closed them; if not, close them now via `create-rule` and commit before any feature task). Don't build on an un-established convention.

### 1. Decompose the plan into a task graph

Turn the plan's ordered steps into an executable task graph with explicit dependencies and parallelism. Full method: `references/task-graph.md`.

1. Make **one task per plan step** by default (a step already carries goal · spec trace · red test · green criterion · guardrails · self-review). Split a step into sub-tasks only if it bundles independently-testable units; never merge steps (it destroys traceability and makes commits non-atomic).
2. Draw the dependency edges from the plan's §7 sequencing and the repo's ordering gotchas (bronze→silver→gold; derive Parquet *inside* dbt then read the file; prefixed dbt asset keys; setup steps S0/S1 before the work they enable).
3. Mark each task's **file/resource footprint** and decide what may run in parallel — only file-disjoint tasks that touch no shared serial resource (see Phase 2). Everything else is sequential.
4. Record the graph as the run's checklist (a TaskCreate list or a short table): id, plan step, deps, parallel-group, status. This is the progress spine for Phase 3 and for resuming.

### 2. Decide the parallelism (conservatively)

Parallelism is an optimisation, not the goal — correctness first. `references/task-graph.md` → *Parallelisation rules* has the full test. The short version:

- **Safe to parallelise:** tasks with disjoint file sets and no shared serial resource — e.g. two unrelated pure-Python modules with their own pytest files; independent docs.
- **Must stay serial (shared single-writer/global state):** anything that runs `dbt build`/touches `warehouse.duckdb` (DuckDB is single-writer); anything that rebuilds the dbt manifest; edits to `definitions.py` / asset-job/schedule/`AssetSelection` wiring; edits to shared config (`config.py`, `pyproject.toml`, `.env*`). Two of these at once corrupt state or race the manifest.
- When parallelising, give each concurrent implementer sub-agent its **own git worktree** (`Agent` with `isolation: "worktree"`) so their edits don't collide, and **review + commit each in dependency order** as they return. When in doubt, serialize — the repo's constraints make most multi-step plans here mostly sequential anyway.

### 3. Execute the loop — implement → review → commit, until the plan is complete

Repeat until every task is `done`. For each ready task (deps satisfied), follow the cycle. Implementer prompt and scoping: `references/delegation.md`. Review + commit protocol: `references/review-and-commit.md`.

1. **Delegate the implementation.** Spawn a fresh implementer sub-agent (`general-purpose`, or `worktree`-isolated for a parallel task) scoped to **exactly one task**. Hand it only that task's contract (goal, spec trace, the red test to write first, implementation outline, green criterion, guardrails, governing conventions) — not licence to touch the rest of the plan. It must do red→green→refactor: write the failing test, confirm it fails for the right reason, implement the minimum to pass, run the guardrails (`ruff`, `dbt build`, etc.), and report back what it changed and the commands it ran.
2. **Review independently (the gate).** Spawn a **separate, read-only, adversarial** reviewer — never the implementing agent. It verifies, with file:line evidence: the task meets its spec scenario/AC; **the plan was followed** and the agent **did not stray** beyond the task's scope; the **test exists, is useful, and can actually fail**; conventions are honoured; and there is **no reward-hacking** (no stubs/mocks/hardcoded values/defaults-on-failure outside tests; no suppressed/skipped/weakened gates). It returns PASS | GAPS | REWARD-HACKING. Reuse the plan skill's reviewer protocol — `../plan/references/self-review.md` — extended with the plan-adherence and scope-drift checks detailed in `references/review-and-commit.md`.
3. **Gate on the verdict.** Only **PASS** advances. On GAPS / REWARD-HACKING, feed the findings back (fix the code, or the test if the test was the problem), then **re-spawn a fresh reviewer** — never edit the test or weaken a gate to flip the verdict, never override the reviewer. Repeat until PASS.
4. **Commit the task.** On PASS, make one atomic **Conventional Commit** for that task (scope it to the task's files; message traces to the plan step). This is the known-good checkpoint. Never `git push`; never `git checkout`/`switch`/`reset --hard`/`clean`/`restore`/`rm`; never `--no-verify`/`--skip` (let pre-commit run). Update the task's status to `done` in the checklist.
5. **Advance.** Mark newly-unblocked tasks ready; dispatch the next (or the next parallel batch). Keep looping.

### 4. Final verification and report

When every task is `done`:

1. Run the **whole-plan green check**, not just per-task: the full guardrail set (`uv run pre-commit run --all-files`; the relevant `dbt build`; `PYTHONPATH=src uv run pytest` if a suite exists). For any change to Dagster orchestration wiring, the green criterion is launching a run through the **daemon/queued path** (a UI/queued launch), not merely `dagster definitions validate` — per the plan's guardrail register and CLAUDE.md (validate loads the location in one process and misses daemon-workspace / `AssetSelection.all()` failures).
2. Confirm **traceability is closed**: every spec scenario/AC in the plan's §10 is satisfied by a committed task. Report any that aren't.
3. Report: tasks completed, commits made (hashes + messages), what's green, anything deferred to Open questions, and propose the natural next step (e.g. run `self-learn` to codify learnings; open a PR if the user asks — you do not push).

## Guardrails

- **No execution without a ready plan (hard gate).** Missing/stale plan, an unresolved §3 convention gap, or a blocking §9 open question stops the run. Resolve first; don't improvise the build.
- **One task in flight per agent; never self-certify.** The agent that wrote the code never reviews it. Review is always a separate, read-only, adversarial sub-agent.
- **PASS is the only thing that commits.** GAPS/REWARD-HACKING never get committed and never get "fixed" by weakening the test or the gate. Re-spawn a fresh reviewer until a genuine PASS.
- **No reward-hacking — and the reviewer hunts for it.** No placeholders/mocks/hardcoded values/stubs outside test contexts; no defaults-on-failure/silent fallbacks where the spec demands a raise; no suppressed/skipped/weakened gates (`--no-verify`, `--skip`, blanket `# noqa`, `xfail`/`skip` to dodge a failure); no test narrowed to make red go green.
- **Stay inside the task's scope.** An implementer changes only what its task needs. Scope drift (touching other steps, refactoring unrelated code, gold-plating beyond the spec) is a review failure, not a bonus.
- **Trace, don't drop.** Every plan step becomes a task; every task traces to a step and a spec scenario/AC. The run isn't done until §10 traceability is fully covered.
- **Respect the repo's serial/non-obvious constraints in parallelism and order.** Single-writer DuckDB and the dbt manifest are shared state — never run two warehouse/manifest tasks concurrently; keep `definitions.py`/`AssetSelection` edits serial and verify them through a real queued run. No `from __future__ import annotations` in asset modules; prefixed dbt asset keys; `pathlib.Path`; config via `pydantic-settings`.
- **No backward-compatibility scaffolding.** Remove the legacy path a task replaces; don't make code serve both old and new purposes (per the user's design principles).
- **Atomic, conventional, local commits only.** One commit per passing task, Conventional Commits, at the logical conclusion. Never push; never use the destructive/branch-switching git commands listed above.
- **Surface contradictions & knock-on effects.** If executing a task reveals the plan is wrong, contradicts a repo constraint, or implies unstated work, stop and surface it — don't silently deviate from the plan.

## References

- [`references/task-graph.md`](references/task-graph.md) — turning plan steps into a dependency-ordered task graph, footprint analysis, and the conservative parallelisation rules (what is safe vs must-stay-serial in this repo).
- [`references/delegation.md`](references/delegation.md) — scoping a single task and the implementer sub-agent prompt template (red→green→refactor, report-back contract, worktree isolation for parallel tasks).
- [`references/review-and-commit.md`](references/review-and-commit.md) — the independent review gate (extends `../plan/references/self-review.md` with plan-adherence + scope-drift + test-usefulness checks), the verdict→action table, and the atomic commit protocol.
- [`references/execution-loop.md`](references/execution-loop.md) — the driver loop: readiness gate, progress/state tracking, handling failures and re-reviews, resuming a partially-built plan, and the final whole-plan verification.
- [`../plan/references/self-review.md`](../plan/references/self-review.md) — the base reviewer protocol and prompt this skill reuses; don't duplicate it, extend it.
