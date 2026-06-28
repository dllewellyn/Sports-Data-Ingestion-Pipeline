# Task graph & parallelisation

Phase 1–2 of the implementor skill. Turn the plan's ordered steps into an executable, dependency-aware task graph, and decide — conservatively — what may run in parallel.

## The principle

The plan already did the hard decomposition: each `### Step S…` in `specs/NNN-<slug>-plan.md` carries a goal, spec trace, failing-first test, implementation outline, green criterion, guardrails, and a self-review checkpoint. The implementor's job is **not to re-plan** — it's to make that sequence executable: attach dependencies, footprints, and parallel groups, then drive it.

## Step 1 — One task per plan step (default)

- **Default mapping: task = plan step.** A plan step is already the right unit — it's independently testable and independently committable. Keep the step's `S…` id as the task id so traceability is trivial.
- **Split only when a step bundles independent units.** If a single step's §4 testable-units row actually lists two units that have their own tests and could fail independently, split into `S3a`/`S3b`. Splitting must preserve, not invent, traceability — each sub-task still points at the same spec scenario/AC.
- **Never merge steps.** Merging breaks per-task atomic commits and lets two behaviours hide behind one review. If two steps feel redundant, that's plan feedback to surface — not something to collapse silently.

## Step 2 — Draw the dependency edges

For each task, list the tasks that must be `done` before it can start. Sources, in order:

1. **The plan's §7 sequencing & dependencies** — the authoritative order.
2. **Setup-before-work** — S0/S1 setup tasks (pytest harness, pre-commit install, a `create-rule` convention commit) block every task that relies on them.
3. **Repo ordering gotchas** (from CLAUDE.md / ARCHITECTURE.md):
   - **bronze → silver → gold** — a silver model task depends on the bronze asset task; gold depends on silver.
   - **Derive Parquet inside dbt, then read the file in Python** — the Python-reads-file task depends on the dbt external-materialisation task (not on the warehouse table).
   - **Prefixed dbt asset keys** — a task wiring a Python `deps=[AssetKey([...])]` depends on the dbt model task that creates that prefixed key.
   - **Lineage links** (e.g. `BronzeAwareTranslator` mapping the dbt source to the bronze `AssetKey`) — wiring tasks depend on the assets they connect.

A task is **ready** when all its dependency tasks are `done`.

## Step 3 — Record each task's footprint

For every task, note:
- **Files it will create/edit** (its write set).
- **Shared serial resources it touches** — see the parallelisation rules below.
- **Test facility** (pytest / Pydantic / Pandera / dbt test / artifact assertion) from the plan's §4.

## Step 4 — The run checklist

Materialise the graph as the run's progress spine — a `TaskList` (preferred, so the user sees live status) or a short table:

| Task | Plan step | Depends on | Parallel group | Footprint (write set) | Status |
|------|-----------|------------|----------------|-----------------------|--------|
| S0   | harness   | —          | —              | `pyproject.toml`, `tests/` | done |
| S2   | stg model | S0         | —              | `dbt/.../silver/stg_x.sql` + tests | ready |
| S3a  | parser    | S0         | P1             | `src/.../parse.py`, `tests/.../test_parse.py` | ready |
| S3b  | mapper    | S0         | P1             | `src/.../map.py`, `tests/.../test_map.py` | ready |

This is also the **resume** record (see `execution-loop.md`): on restart, anything already committed is `done`.

## Parallelisation rules (conservative by design)

Parallelism is an optimisation; correctness and clean review come first. A set of tasks may run concurrently **only if all** of these hold:

1. **Disjoint write sets** — no two concurrent tasks edit the same file. (Concurrent edits to one file race even in separate worktrees once you merge.)
2. **No shared serial resource** — none of them touches any of:
   - **`warehouse.duckdb` / `dbt build`** — DuckDB is single-writer; two `dbt build`s at once corrupt the file or hit phantom catalog errors. **All warehouse/dbt-test tasks are serial.**
   - **The dbt manifest** — anything that runs `dbt parse`/`dbt build` rebuilds the manifest; concurrent runs race it.
   - **`definitions.py` / asset–job / schedule / `AssetSelection` wiring** — Dagster introspects these globally; serialize and verify via a real queued run.
   - **Shared config** — `config.py`, `pyproject.toml`, `.env*`, `uv.lock`, `workspace.yaml`.
3. **No dependency edge between them** — parallel tasks must be mutually independent (same readiness, neither blocks the other).

**Mechanics when you do parallelise:**
- Give each concurrent implementer its **own git worktree** — spawn with `Agent` `isolation: "worktree"` — so edits never collide on disk.
- **Review and commit in dependency order** as agents return; don't batch-commit. Each commit still goes through the independent review gate.
- Cap concurrency to a handful; more agents rarely helps and complicates review ordering.

**Default to serial.** Most multi-step plans in this repo are mostly sequential because the warehouse, the manifest, and `definitions.py` are shared state. Parallelise only the genuinely independent islands (e.g. several unrelated pure-Python modules each with their own pytest file, or docs). When unsure, run serial — a correct slow build beats a raced fast one.

**No silent caps.** If you decide to serialize tasks that *could* have run in parallel (e.g. to keep review tractable), say so — don't let the user assume everything fanned out.
