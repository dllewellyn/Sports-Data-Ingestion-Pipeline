# Delegating a task to an implementer sub-agent

Phase 3.1 of the implementor skill. How to scope one task and hand it to a fresh implementer sub-agent so it builds exactly that task — test-first — and reports back enough for an independent reviewer to judge it.

## Why a sub-agent per task

Each task is delegated to its **own fresh agent** for two reasons: (1) it keeps the driver's context lean so the run can span many tasks without losing the plan; (2) it bounds scope — an agent given one task's contract is far less likely to wander into other steps or gold-plate than one holding the whole plan. The driver stays the orchestrator: it dispatches, reviews (via a *different* agent), and commits.

## Scope: exactly one task, nothing more

Hand the implementer **only its task's contract** — not the full plan, not licence to touch other steps:

- Goal (the one behaviour this task delivers).
- Spec trace — the scenario / FR / SC from `<feature_dir>/spec.md` it must satisfy (quote it).
- The failing-first test to write (path + the assertion intent from the plan's §4).
- Implementation outline (the plan's "minimum to pass").
- Green criterion (exact commands + expected result).
- Guardrails it must satisfy (the §5 rows for this task).
- Governing conventions (the §3 audit rows + the CLAUDE.md/ARCHITECTURE.md rules for this artifact type).

If the task touches the network edge, warehouse, or asset wiring, include the specific non-obvious constraint it must honour (latin-1 vs utf-8-sig for football families; single-writer DuckDB → read the Parquet file not the table; prefixed dbt asset keys; no `from __future__ import annotations` in asset modules).

## Choosing the agent

- **Serial task:** `general-purpose` agent (fresh context).
- **Parallel task:** `general-purpose` with `isolation: "worktree"` so its edits don't collide with other concurrent implementers (see `task-graph.md` → *Parallelisation rules*).
- A task may legitimately invoke a project skill the plan's §2 named (e.g. `create-rule` for a convention, a dbt build helper). Tell the implementer which skill its step expects, rather than re-deriving the work.

## Implementer prompt template

**Telemetry:** immediately before spawning, run `python3 .agents/skills/_shared/telemetry/emit.py label-next --role implement:<task_id> --phase implementor` so this implementer appears as its own labelled span in the feature-run trace (best-effort no-op if telemetry is off).

Spawn with a prompt of this shape (fill the `<…>`):

> You are implementing **one task** from an approved plan. Build only this task — do not touch other plan steps, do not refactor unrelated code, do not add features the spec didn't ask for.
>
> **Task contract:**
> - Goal: `<task goal>`
> - Spec scenario / FR / SC to satisfy (verbatim): `<…>` from `<feature_dir>/spec.md`
> - Plan step: the task's `[Sn]` step in `<feature_dir>/plan.md`
> - Failing-first test to write: `<path>` — assertion: `<what must fail before, pass after>`
> - Implementation outline: `<minimum to pass>`
> - Green criterion: `<exact command(s) + expected result>`
> - Guardrails to satisfy: `<from plan §5>`
> - Governing conventions / constraints: `<from plan §3 + CLAUDE.md/ARCHITECTURE.md; include any non-obvious constraint this task touches>`
>
> **Do, in this order (red → green → refactor):**
> 1. **Red** — write the failing test first; run it; confirm it fails *for the intended reason* (the behaviour doesn't exist yet), not for an unrelated error. Paste the failing output.
> 2. **Green** — implement the minimum to make it pass. Run the test until green.
> 3. **Guardrails** — run the named guardrails (e.g. `uv run ruff check src && uv run ruff format src`, `dbt build --select <model>`, `uv run pytest <path>`). Fix findings; never suppress them (`--no-verify`/`--skip`/blanket `# noqa` are forbidden).
> 4. **Refactor** — tidy with tests still green; remove any legacy/duplicate path this task replaces (no backward-compat scaffolding).
>
> **Rules:** No placeholders, mocks, hardcoded values, stubs, or defaults-on-failure outside the test. No silent fallbacks where the spec demands a raise. Use `pathlib.Path` for paths and `pydantic-settings` (`config.py`) for config — not ad-hoc `os.getenv`. Do **not** commit — the orchestrator commits after an independent review.
>
> **Report back exactly:**
> - **Files changed:** path list (created/modified/deleted).
> - **Test:** path + the failing output you saw (red) and the passing output (green).
> - **Guardrail results:** each command run + its result.
> - **Conventions/constraints honoured:** brief confirmation of the ones listed above.
> - **Anything you could not do / deviations:** if you had to depart from the outline, say why (do not hide it).

## After it returns

- If the implementer reports a deviation, a guardrail it couldn't satisfy, or that the test couldn't be made to fail-first — treat that as **input to the review**, not a reason to skip it. Pass it straight to the reviewer.
- Do **not** commit yet. Hand the result to an independent reviewer (`review-and-commit.md`). Only a PASS verdict leads to a commit.
- Keep the implementer's report; the reviewer needs the red/green evidence and the change list.
