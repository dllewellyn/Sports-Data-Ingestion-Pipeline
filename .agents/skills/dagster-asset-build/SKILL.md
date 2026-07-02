---
name: dagster-asset-build
description: >
  Add a new Dagster @asset (especially a thin Python wrapper over pure
  business logic, following the assets/intermediate/ pattern) and/or wire it
  into definitions.py's AssetSelections, jobs, and schedules in the
  Sports-Data-Ingestion-Pipeline. Codifies the bootstrap-empty-Parquet
  discipline, the no-future-annotations rule, explicit-AssetSelection job
  convention, and the mandatory daemon/queued-run verification standard for
  any orchestration-wiring change. USE WHEN adding a new asset that isn't a
  bronze ingest source (see bronze-ingest-source) or a dbt model (see
  dbt-model-build), or when changing which jobs/schedules select which
  assets, or when an asset needs a new same-run dependency on another asset.
---

# dagster-asset-build

Adds a new Dagster asset (a thin wrapper over pure Python logic, not a bronze
ingest edge and not a dbt model) and/or wires assets into
`definitions.py`'s jobs, schedules, and `AssetSelection`s. Confirmed pattern:
`src/data_platform/assets/intermediate/matchbook_conform.py` (the reference
implementation) and `src/data_platform/definitions.py` (the wiring
reference). Read both before writing — the job-selection shape and the set
of registered assets change as providers are added.

## When to use

- User says "add an asset for X", "wire X into the matchbook/espn job",
  "make X run after Y in the same job".
- A new intermediate-layer Python asset (not touching the network, not a dbt
  model) is being added — e.g. a conform/enrichment/reconciliation step.
- Do NOT use for a new bronze network-edge source (`bronze-ingest-source`)
  or for the dbt SQL side of a model change (`dbt-model-build`) — though a
  single feature often needs all three, in that order: dbt formula/macro
  first (if the asset's output feeds a model), then the asset, then the
  wiring.

## The thin-wrapper pattern

The asset function itself does almost nothing — it resolves config, calls a
pure-Python engine function (no Dagster imports in that function), and wraps
the result in a `MaterializeResult`. Read
`assets/intermediate/matchbook_conform.py` end to end:

```python
# NO: from __future__ import annotations
# Dagster introspects context/return annotations at runtime; a stringized
# annotation raises DagsterInvalidDefinitionError. This bites people because
# ruff's pyupgrade rule wants you to add it everywhere else in the codebase.

from dagster import AssetKey, MaterializeResult, asset
from ...config import settings
from ...otel import get_tracer

@asset(
    key=AssetKey(["your_asset_name"]),
    group_name="intermediate",   # or "bronze" / "marts" as appropriate
    compute_kind="python",
    deps=[AssetKey(["upstream_asset"])],   # see "same-run ordering" below
    description="...",
)
def your_asset_name(context) -> MaterializeResult:
    tracer = get_tracer()
    with tracer.start_as_current_span("your_asset_name"):
        result = run_your_engine(...)  # pure function, unit-testable alone
    return MaterializeResult(metadata={...})
```

### Bootstrap-empty-Parquet discipline

If any dbt model reads this asset's output via `read_parquet(...)` (literal
or through `source()`), that call **errors on a missing file** — it does not
silently return zero rows. If the asset might legitimately produce zero rows
on its first run (nothing to write yet), **write the file empty first**
(correct columns, zero rows) before doing real work, so downstream `dbt
build` stays green from a clean state. Mirror `matchbook_conform.py`'s
`_ensure_empty_parquet` / `_bootstrap_additions` helpers — atomic write
(`tmp` suffix + `rename`), called unconditionally at the top of the asset
body.

## Job/`AssetSelection` wiring (`definitions.py`)

Every job uses an **explicit** `AssetSelection.assets(...)` — never
`AssetSelection.all()` or an `all() - X - Y` subtraction pattern (that
pattern exists in `bronze-ingest-source`'s older template but has been
superseded here; check `definitions.py`'s current jobs before copying an
older pattern). A new asset that several jobs legitimately need (e.g. a
canonical model rebuilt by more than one provider's job) is added to
**every** relevant job's selection — that's intentional shared rebuilding,
not duplication to clean up. Read the comments above `espn_assets` and
`matchbook_assets` in `definitions.py` for two worked examples of *why* a
model is deliberately excluded from one job to avoid a dependency cycle
back through a Python asset — the same reasoning applies to any new asset
whose output another selected node also consumes.

### Same-run ordering between two Python assets

A plain `deps=[AssetKey(["upstream"])]` on a Python asset is always safe —
it's a normal Dagster dependency edge, no dbt-graph interaction, no
`CircularDependencyError` risk. Use this whenever a asset's output must be
visible to another asset **within the same job run** (not just "eventually,
next run"). This is the *only* mechanism for guaranteed same-run ordering
between two Python steps; if the ordering only matters "eventually," you
don't need the edge at all and can rely on the next scheduled run.

If the ordering constraint is actually between a Python asset and a **dbt**
model (not another Python asset), that's `dbt-model-build`'s territory —
see its `source()`-vs-raw-literal section and the `CircularDependencyError`
ceiling before adding a `source()` edge into a model that already has one.

### Config wiring

New settings are `@property` methods on the `pydantic-settings` `Settings`
class in `config.py` — never ad-hoc `os.getenv`. **Check for property-name
collisions with an existing provider before adding one** — e.g. Matchbook
already has `matchbook_bronze_dir` for the odds ingestor, so a second
Matchbook property needs a more specific name
(`matchbook_events_bronze_dir`). Silently overwriting a live property breaks
whatever already used it; CLAUDE.md documents this as a real, previously-hit
bug, not a hypothetical.

### `BronzeAwareTranslator._SOURCE_ASSET_KEYS` (`assets/dbt.py`)

This dict maps a dbt source name to the upstream Dagster `AssetKey` that
produces it — it's what makes `BronzeAwareTranslator.get_asset_key` return
your asset's key for that source, forming the Dagster-visible edge. Add an
entry here whenever a dbt model's `{{ source('bronze', '<name>') }}` should
resolve to your asset. **Registering an entry here does NOT by itself mean
any model actually uses `source()` for it** — a source can be registered
purely for documentation while every model that reads that same file uses a
raw `read_parquet()` literal instead (see `dbt-model-build`'s
`CircularDependencyError` section for why that's sometimes the deliberate
choice). Don't assume "it's in `_SOURCE_ASSET_KEYS`" means "there's a live
dependency edge" — check the model SQL itself.

## The mandatory verification standard for orchestration-wiring changes

**`dagster definitions validate` is necessary but NOT sufficient.** It loads
the code location in a single process and will NOT catch:

- A daemon-workspace mismatch (`dagster-daemon run` and the webserver must
  load the same `workspace.yaml`; a queued run launched from the UI can fail
  with `DagsterCodeLocationNotFoundError` in a way `validate` never sees,
  since it never goes through `QueuedRunCoordinator`).
- A `CircularDependencyError` from dagster-dbt's step-subsetting hitting the
  ceiling described above — this is a `Definitions`-build-time error, so
  `validate` **should** catch this specific one; treat a clean `validate`
  result as confirming *this* class of error is absent, not as a full
  green light for the change.

The real green criterion for any change to `definitions.py`'s assets, jobs,
schedules, or `AssetSelection`s is: **launch a run through the real
daemon/queued path** (the Dagster UI's "Launch Run", or `dagster-daemon run`
+ a programmatically queued run) — not `dagster job execute` (which runs
in-process and skips the daemon entirely) and not `dagster definitions
validate` alone. Confirm the run actually launches, and if you added a
same-run ordering dependency, confirm the step order in the run's logs
matches what you intended.

## Reference implementations

- Thin wrapper + bootstrap-empty: `src/data_platform/assets/intermediate/matchbook_conform.py`
- Job/`AssetSelection` wiring + cycle-avoidance comments: `src/data_platform/definitions.py`
- Source-to-asset-key mapping: `src/data_platform/assets/dbt.py` (`BronzeAwareTranslator`)
- Config property convention: `src/data_platform/config.py`
