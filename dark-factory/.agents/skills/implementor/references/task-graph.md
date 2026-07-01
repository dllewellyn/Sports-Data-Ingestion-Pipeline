# Footprint analysis & parallelisation

Phase 1–2 of the implementor skill. The decomposition into a task list has already happened — `<feature_dir>/tasks.md` (produced by the `tasks` skill) is the dependency-ordered task graph. The implementor's job here is **footprint analysis** and the **conservative parallelisation decision**: for the `[P]`-marked tasks already in tasks.md, work out which are genuinely safe to run concurrently and which must stay serial.

## The principle

The `tasks` skill already did the decomposition: `<feature_dir>/tasks.md` holds one task per line, each with its dependencies, its phase, a `[P]` marker where it judged the task file-disjoint, and a `[Sn]` reference back to the plan step it implements (the steps live in `<feature_dir>/plan.md`). The implementor's job is **not to re-decompose** — it's to validate and harden the parallel groups: confirm each `[P]` task's footprint really is disjoint and touches no shared serial resource before letting it run concurrently, and otherwise drive the graph in order.

## Step 1 — Read the task list

- **The task list is `<feature_dir>/tasks.md`.** Each `- [ ] T### ...` line carries its task id, the phase it belongs to, its dependencies, a `[P]` marker where the `tasks` skill judged it parallel-safe, and a `[Sn]` reference to the plan step in `<feature_dir>/plan.md` it implements.
- **Do not re-decompose.** Splitting the plan into tasks is the `tasks` skill's job, not the implementor's. If a task looks wrong (bundles two independent units, or duplicates another), that's feedback to surface — re-run `tasks` or raise it; don't silently re-cut the graph here.
- **Trust the ids, verify the footprints.** Keep the `T###` ids and their `[Sn]` plan-step references as written; what this reference adds is the footprint check below before honouring any `[P]` marker.

## Step 2 — Confirm the dependency edges

tasks.md already records each task's dependencies (in its `## Dependencies & Execution Order` section). Confirm they hold before dispatch. Sources to cross-check against, in order:

1. **The plan's sequencing & dependencies section** in `<feature_dir>/plan.md` — the authoritative order.
2. **Setup-before-work** — Setup-phase tasks (pytest harness, pre-commit install, a `create-rule` convention commit) block every task that relies on them.
3. **Repo ordering gotchas** (from CLAUDE.md / ARCHITECTURE.md):
   - **bronze → silver → gold** — a silver model task depends on the bronze asset task; gold depends on silver.
   - **Derive Parquet inside dbt, then read the file in Python** — the Python-reads-file task depends on the dbt external-materialisation task (not on the warehouse table).
   - **Prefixed dbt asset keys** — a task wiring a Python `deps=[AssetKey([...])]` depends on the dbt model task that creates that prefixed key.
   - **Lineage links** (e.g. `BronzeAwareTranslator` mapping the dbt source to the bronze `AssetKey`) — wiring tasks depend on the assets they connect.

A task is **ready** when all its dependency tasks are `done`.

## Step 3 — Record each task's footprint

For every task — especially every `[P]`-marked one — note:
- **Files it will create/edit** (its write set).
- **Shared serial resources it touches** — see the parallelisation rules below.
- **Test facility** (pytest / Pydantic / Pandera / dbt test / artifact assertion) from its `[Sn]` plan step's testable-units field in `<feature_dir>/plan.md`.

## Step 4 — The run checklist

Materialise the graph as the run's progress spine — a `TaskList` (preferred, so the user sees live status) or a short table:

| Task | Plan step | Depends on | Parallel group | Footprint (write set) | Status |
|------|-----------|------------|----------------|-----------------------|--------|
| T001 | S0 harness   | —       | —              | `pyproject.toml`, `tests/` | done |
| T002 | S2 stg model | T001    | —              | `dbt/.../silver/stg_x.sql` + tests | ready |
| T003 | S3 parser    | T001    | P1             | `src/.../parse.py`, `tests/.../test_parse.py` | ready |
| T004 | S4 mapper    | T001    | P1             | `src/.../map.py`, `tests/.../test_map.py` | ready |

This is also the **resume** record (see `execution-loop.md`): on restart, anything already committed is `done`.

## Parallelisation rules (conservative by design)

Parallelism is an optimisation; correctness and clean review come first. The `tasks` skill marks file-disjoint tasks `[P]`, but that marker is a *candidate*, not a licence — confirm a set of `[P]` tasks may actually run concurrently by checking that **all** of these hold:

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
