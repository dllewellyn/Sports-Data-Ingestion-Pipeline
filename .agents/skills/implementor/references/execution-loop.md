# The execution loop

Phases 0, 3, and 4 of the implementor skill — the driver that runs implement→review→commit over the task graph until the plan is complete, and how it handles readiness, failures, resuming, and final verification.

## Refuse to run an unready plan (Phase 0 gate)

Before dispatching any task, confirm the plan is executable. Stop and surface — don't improvise — if any of these hold:

- **No plan exists** for the spec → offer to run the `plan` skill first. (And `specification` before that if the *what* is unsettled.)
- **The plan is stale** — it references files/asset keys/conventions that no longer match the tree. Re-plan or have the user confirm before building on it.
- **§3 convention audit has a row still marked `gap`** — a governing convention the build depends on isn't established. Close it first: `create-rule` → user approval → atomic `docs:`/`chore:` commit. Only then start the dependent task.
- **§9 open questions has a blocker** — resolve or get explicit acceptance before building the affected tasks.
- **Required setup (S0/S1) isn't done** — pytest harness, `pre-commit install`. These are tasks too; they just come first.

The plan's Phase 2 should have closed conventions already; if it didn't, closing them is the first thing the implementor does.

## The loop (Phase 3)

```
build task graph (task-graph.md) → checklist with statuses
while any task not done:
    ready = tasks whose deps are all done
    pick the next ready task (or a safe parallel batch — task-graph.md)
    for each:
        implement  (delegation.md)      → fresh implementer sub-agent, red→green→refactor, reports back
        review     (review-and-commit.md) → fresh independent reviewer → PASS | GAPS | REWARD-HACKING
        if not PASS: fix (fresh implementer) → re-review (fresh reviewer); repeat until PASS
        commit     (review-and-commit.md) → atomic Conventional Commit; status = done
    mark newly-unblocked tasks ready
final verification (below)
```

Keep the loop running until **every** task is `done` — that's the user's "keep going until the whole plan is complete". Don't stop at the first green task or hand back a half-built plan unless you hit a genuine blocker (see below).

## State & progress tracking

- The **task checklist** (a `TaskList`, or the table from `task-graph.md`) is the single source of run state: each task is `ready` / `in-progress` / `blocked` / `done`. Update it as you go so the user sees live progress and the run is resumable.
- Set a task `in-progress` when you dispatch it, `done` only after its commit lands. A task that failed review stays `in-progress` (not `done`) through the fix/re-review cycle.

## Handling failures

- **Review GAPS / REWARD-HACKING:** fix-and-re-review loop (see `review-and-commit.md`). Never weaken the test/gate; never commit a non-PASS task.
- **A task can't reach PASS because the plan is wrong:** the outline contradicts the spec, a repo constraint, or another step. **Stop that task, surface it to the user as plan feedback** with evidence. Don't force it green and don't silently deviate. Other independent tasks can continue while the user decides.
- **A guardrail can't pass (e.g. `dbt build` red for a real reason):** that's a genuine failure — fix the cause. Never `--skip`/`--no-verify` it. If it reveals a missing dependency or convention, that's a new setup task to insert before this one.
- **A parallel task collided** despite the disjoint-footprint rule: serialize the offenders, re-run. Tighten the footprint analysis that let it through.
- **An implementer reports it couldn't write a failing-first test:** treat as a red flag — either the behaviour is already present (the step may be redundant — surface as plan feedback) or the test facility is wrong. Route to the reviewer; don't accept a step with no falsifiable check.

## Resuming a partially-built plan

The run is resumable precisely because every passing task is an atomic commit:

1. Read the plan and the task graph.
2. Inspect `git log` (and the diff) to see which plan steps are already committed — mark those tasks `done`.
3. Cross-check the working tree is clean for done tasks (no uncommitted drift). If a task's files show uncommitted changes, that task is mid-flight — re-review before trusting it.
4. Resume the loop at the first not-done ready task.

Never re-run a `done` task's commit; never rewrite history to "tidy" earlier commits (no `reset --hard`/`rebase -i` — and the user's git rules forbid the destructive variants anyway).

## Final verification (Phase 4)

When every task is `done`, verify the **whole plan**, not just the per-task greens that accumulated:

1. **Full guardrail sweep:** `uv run pre-commit run --all-files` clean; the relevant `dbt build` green (remember `dbt parse` first if running outside `dagster dev`); `PYTHONPATH=src uv run pytest` if a suite exists. Per-task greens can mask an integration regression — this catches it.
2. **Orchestration wiring (if touched):** the green check is **launching a run through the daemon/queued path** (UI/queued launch or at least `dagster definitions validate -w workspace.yaml`), not just `dagster definitions validate` — per CLAUDE.md, single-process validation misses daemon-workspace and `AssetSelection.all()` resolution failures, and `medallion_job` must still exclude the football assets.
3. **Traceability closed:** every spec scenario/AC in the plan's §10 maps to a committed task. Name any that don't — the plan isn't fully implemented until they do.
4. **Report:** tasks done, commits (hashes + messages), what's green, anything deferred to Open questions, and the natural next step — typically run `self-learn` to codify learnings into CLAUDE.md/a skill, and update the plan's `status:` frontmatter to `done`. Open a PR only if the user asks; you do not `git push`.
