# Spec 003 — DuckLake Silver/Gold Model Migration: Implementation Plan

**Status:** Draft
**Date:** 2026-06-29
**Spec:** `specs/003-ducklake-model-migration-specification.md`

---

## Overview

This plan implements Spec 003, which migrates all dbt-owned silver and gold models
from `warehouse.duckdb` to the DuckLake PostgreSQL-backed catalog by switching
`profiles.yml` `path:` and removing the now-redundant `attach` stanza. It is
intentionally minimal: one file is functionally changed (`profiles.yml`), one
compose file gains a `depends_on` guard, and three documentation files are updated.

---

## Convention Audit

| Convention | Status | Notes |
|---|---|---|
| Config from `pydantic-settings` only | Compliant | `POSTGRES_CATALOG_URL` is already in `config.py` (Spec 002). No new `os.getenv` calls. |
| No `from __future__ import annotations` in asset modules | Compliant | `assets/dbt.py` is not modified. |
| `BronzeAwareTranslator` maps source names, not target databases | Compliant | No Python changes required. |
| dbt AssetKey prefix from schema folder only | Compliant | Switching `path:` changes `node.database` in the manifest but not `node.schema`; key derivation is unaffected (verified in Spec 003 AD 5.5). |
| dbt owns the warehouse; Python reads Parquet files, not tables | Compliant | `assets/gold.py` reads `data/gold/users_by_city.parquet`; unchanged. |
| CLAUDE.md updated in same commit as constraints change | Required | Step 5 covers this. |
| ERD.md updated when canonical tables change storage tier | Required | Step 7 covers this. |
| ARCHITECTURE.md updated when layer write targets change | Required | Step 6 covers this. |
| `ruff check/format` scoped to changed files | Required | Run on any `.py` touched (none in this plan). |
| No overengineering — KISS | Compliant | This plan introduces zero new abstractions. |

---

## Steps

### Step 1 — Update `profiles.yml`: switch `path:` to DuckLake, remove `attach`

**What changes**

File: `dbt/data_platform/profiles.yml`

Before:
```yaml
data_platform:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "{{ env_var('DUCKDB_PATH', '/app/data/warehouse.duckdb') }}"
      threads: 4
      extensions:
        - parquet
        - ducklake
      attach:
        - path: "ducklake:{{ env_var('POSTGRES_CATALOG_URL', 'postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake') }}"
          alias: lake
```

After:
```yaml
data_platform:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "ducklake:{{ env_var('POSTGRES_CATALOG_URL', 'postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake') }}"
      threads: 4
      extensions:
        - parquet
        - ducklake
```

Changes:
- `path:` changed from `env_var('DUCKDB_PATH', ...)` to `ducklake:<catalog URI>`.
- `attach:` stanza removed entirely (self-attachment of the primary connection would
  be a duplicate; OQ1 resolution confirms removal is the safe path).
- `extensions:` list is untouched (`parquet` for external Parquet sources, `ducklake`
  for the catalog connection).

Note on OQ2: `dbt-duckdb` 1.9.x passes the `path:` value directly to DuckDB's
`ATTACH` (or `OPEN`) call. The `ducklake:postgresql://...` URI scheme is native
DuckLake syntax. Try without `is_ducklake: true` first. If `dbt parse` produces a
`ducklake` extension error, add `is_ducklake: true` as a sibling key beneath `path:`
and retry — this is the only branch in the decision tree.

**Why this satisfies spec ACs**

Directly satisfies AC 1, 2, 3, and is the prerequisite for every other AC.

**Test gate (must fail before the change, pass after)**

```bash
# Before the change: this produces a manifest referencing warehouse.duckdb as the database.
# After the change: this must exit 0 and the manifest must reference the DuckLake catalog URI.
cd /Users/dllewellyn/Developer/Sports-Data-Ingestion-Pipeline/dbt/data_platform
uv run --project ../.. dbt parse --profiles-dir .
echo "Exit code: $?"
# Verify the manifest database field has changed:
python3 -c "
import json
with open('target/manifest.json') as f:
    m = json.load(f)
nodes = {k: v for k, v in m['nodes'].items() if not k.startswith('test.')}
sample = next(iter(nodes.values()))
print('database:', sample.get('database'))
print('schema:', sample.get('schema'))
"
```

Expected: exit 0; `database` field is no longer `data_platform` (DuckDB default) but
reflects the DuckLake catalog name.

**Dependencies:** None — this is the root step.

**Guardrails / self-review checkpoint**

- Confirm the `attach:` block is fully absent from the file after editing.
- Confirm `extensions:` still contains both `parquet` and `ducklake`.
- Confirm the default fallback URL in `env_var(...)` matches the `ducklake-catalog`
  service credentials in `docker-compose.yml`
  (`postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake`).
- Do NOT add a new `outputs:` target or a second profile — one profile, in place.

---

### Step 2 — Verify `dbt build` against a live DuckLake catalog

**What changes**

No code change. This is a verification gate run locally after Step 1 merges.
It confirms ACs 4–13 (all silver and gold models rebuild correctly in DuckLake;
external Parquet export is unaffected).

**Why this satisfies spec ACs**

AC 4: `dbt parse` exit 0.
AC 5: `dbt build` succeeds with live catalog.
AC 6–10: Silver models (views + canonical tables) exist in DuckLake.
AC 11–13: Gold models exist in DuckLake; `data/gold/users_by_city.parquet` is written.

**Verification commands (run in order)**

```bash
# 1. Ensure the catalog service is up and healthy
docker compose up ducklake-catalog -d
docker compose ps ducklake-catalog
# Wait until Health shows "healthy" (up to ~30 s)

# 2. dbt parse (does not require bronze data; does not open catalog connection)
cd /Users/dllewellyn/Developer/Sports-Data-Ingestion-Pipeline/dbt/data_platform
uv run --project ../.. dbt parse --profiles-dir .

# 3. If bronze Parquet is present, run dbt build for silver
POSTGRES_CATALOG_URL="postgresql://ducklake:ducklake@localhost:5432/ducklake" \
  DATA_DIR="$(pwd)/../../data" \
  uv run --project ../.. dbt build --profiles-dir . --select silver.stg_users

# 4. Run gold external export and confirm Parquet file is written
POSTGRES_CATALOG_URL="postgresql://ducklake:ducklake@localhost:5432/ducklake" \
  DATA_DIR="$(pwd)/../../data" \
  uv run --project ../.. dbt build --profiles-dir . --select gold.users_by_city_export
ls -lh ../../data/gold/users_by_city.parquet  # must exist

# 5. Full build (requires all bronze Parquet to be present)
POSTGRES_CATALOG_URL="postgresql://ducklake:ducklake@localhost:5432/ducklake" \
  DATA_DIR="$(pwd)/../../data" \
  uv run --project ../.. dbt build --profiles-dir .
```

**Note:** If `data/bronze/users.parquet` does not exist (clean checkout with no
ingest run), skip steps 3–5 and rely on `dbt parse` + `dagster definitions validate`
(Step 3) as the build gate. The existing CLAUDE.md constraint "dbt build is NOT
green from a clean checkout" still applies — this is environmental, not a regression.

**Dependencies:** Step 1 must be complete.

**Guardrails / self-review checkpoint**

- `data/gold/users_by_city.parquet` must exist after the gold build. If it does not,
  investigate the `external` materialization compatibility (OQ4 from spec).
- If `dbt build` fails with a DuckLake-specific error (e.g., "catalog object already
  exists"), check if a stale `warehouse.duckdb` write-locked the catalog — restart
  the `ducklake-catalog` container and retry.
- If the `external` materialization errors against DuckLake (OQ4), a `post-hook`
  `COPY TO` workaround may be needed in `users_by_city_export.sql` — but do not
  add it preemptively; confirm the failure mode first.

---

### Step 3 — Verify Dagster AssetKey stability

**What changes**

No code change. Verification gate to confirm ACs 14–16.

**Why this satisfies spec ACs**

AC 14: `dagster definitions validate` exits 0.
AC 15: AssetKey values for all dbt models are unchanged.
AC 16: `BronzeAwareTranslator` requires no code change.

**Verification commands**

```bash
# From repo root — ensure dbt manifest is fresh from Step 1/2 first
cd /Users/dllewellyn/Developer/Sports-Data-Ingestion-Pipeline
PYTHONPATH=src DUCKDB_PATH="$PWD/data/warehouse.duckdb" DATA_DIR="$PWD/data" \
  DAGSTER_HOME="$PWD/.dagster" \
  uv run dagster definitions validate -w workspace.yaml
# Must exit 0 with no AssetKey conflicts reported.

# Diff the manifest to confirm database field change does not affect key derivation
python3 -c "
import json
with open('dbt/data_platform/target/manifest.json') as f:
    m = json.load(f)
for k, v in m['nodes'].items():
    if any(x in k for x in ('stg_users', 'league', 'dim_users', 'espn_match_link', 'match', 'team', 'season')):
        print(k, '->', 'database:', v.get('database'), '| schema:', v.get('schema'), '| fqn:', v.get('fqn'))
"
# Expected: schema values remain 'silver'/'gold'; only database field differs.
```

**Dependencies:** Step 1 (fresh `dbt parse` must have run to produce the updated manifest).

**Guardrails / self-review checkpoint**

- If `dagster definitions validate` reports `AssetKey` conflicts, check whether
  `BronzeAwareTranslator.get_asset_key()` relies on any `database` field. The current
  implementation in `assets/dbt.py` uses `resource_type` and `name` only — it does
  not inspect `database`. If there is a conflict, it is from a different cause;
  read the error carefully before modifying any Python.
- The expected stable keys are: `["silver", "stg_users"]`, `["silver", "stg_espn_events"]`,
  `["silver", "stg_matchbook_odds"]`, `["silver", "league"]`, `["silver", "season"]`,
  `["silver", "team"]`, `["silver", "match"]`, `["silver", "espn_match_link"]`,
  `["silver", "matchbook_event_link"]`, `["silver", "football_data_match_link"]`,
  `["gold", "dim_users_by_city"]`, `["gold", "users_by_city_export"]`.

---

### Step 4 — Update `docker-compose.yml`: startup commands and `depends_on`

**What changes**

File: `docker-compose.yml`

Two changes:

**4a. Add `POSTGRES_CATALOG_URL` to the shared `x-app` environment block.**

The `x-app` anchor currently sets `DUCKDB_PATH` but not `POSTGRES_CATALOG_URL`.
After Step 1, the `dbt parse` command in the startup scripts resolves
`POSTGRES_CATALOG_URL` from the `env_var(...)` default fallback in `profiles.yml`
(which points at `ducklake-catalog` — correct for container networking). However,
explicitly setting the env var in the compose environment makes the dependency
visible and allows `.env` overrides in production.

Add to the `environment:` block under `x-app`:
```yaml
    POSTGRES_CATALOG_URL: "postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake"
```

**4b. Add `depends_on` for `ducklake-catalog` to `dagster-webserver` and
`dagster-daemon`.**

`dbt parse` does not connect to the catalog and will succeed whether or not
`ducklake-catalog` is running. However, the first `dbt build` (which runs when
Dagster triggers the `dbt_models` asset) DOES require a live catalog. Adding
`depends_on: ducklake-catalog: condition: service_healthy` to both Dagster
services ensures the catalog is ready before Dagster could attempt a run, and
makes the dependency explicit in the compose definition.

```yaml
  dagster-webserver:
    <<: *app
    depends_on:
      ducklake-catalog:
        condition: service_healthy
    command: >
      sh -c "cd /app/dbt/data_platform && dbt parse --profiles-dir . &&
             cd /app && dagster-webserver -h 0.0.0.0 -p 3000 -w /app/workspace.yaml"
    ports:
      - "${DAGSTER_UI_PORT:-3000}:3000"

  dagster-daemon:
    <<: *app
    depends_on:
      ducklake-catalog:
        condition: service_healthy
    command: >
      sh -c "cd /app/dbt/data_platform && dbt parse --profiles-dir . &&
             cd /app && dagster-daemon run -w /app/workspace.yaml"
```

Note: `DUCKDB_PATH` in `x-app` is retained — the `duckdb-ui` service still attaches
`warehouse.duckdb` read-only (Spec 002 READ_ONLY pattern). Removing it would break
the UI service entrypoint and any developer `.env` files. This satisfies AC 19
(dbt no longer requires it) without breaking anything else.

**Why this satisfies spec ACs**

AC 18: Startup commands still run `dbt parse` (succeeds without catalog connection);
`POSTGRES_CATALOG_URL` is available for `dbt build` at runtime.
AC 19: `DUCKDB_PATH` is not required for dbt; the compose `environment` still sets
it for the DuckDB UI service inheritance path.

**Test gate**

```bash
# Confirm the compose stack starts cleanly with the updated file
cd /Users/dllewellyn/Developer/Sports-Data-Ingestion-Pipeline
docker compose config --quiet  # validates compose YAML; must exit 0
docker compose up ducklake-catalog dagster-webserver --no-start 2>&1 | grep -i "error" || echo "No errors"
```

**Dependencies:** Step 1.

**Guardrails / self-review checkpoint**

- The `x-app` environment block is a YAML anchor shared by all services. Adding
  `POSTGRES_CATALOG_URL` here means `jupyter` and `matchbook-ingestor` also receive
  it — this is harmless (they do not use it), but verify no unintended side effect.
- Confirm `DUCKDB_PATH: /app/data/warehouse.duckdb` is still present in the `x-app`
  block after editing.
- Do NOT remove the `dbt parse` step from the startup command — it remains the
  mechanism that writes `target/manifest.json` before Dagster loads the code
  location (as documented in `assets/dbt.py` comments).

---

### Step 5 — Update `CLAUDE.md`: qualify the single-writer constraint

**What changes**

File: `CLAUDE.md`, section "Non-obvious constraints".

Three targeted updates (do not rewrite the whole section):

**5a.** Find the paragraph beginning "DuckDB is single-writer; dbt owns the warehouse
file." Add a qualification sentence at the end:

> After Spec 003, this constraint applies only to `warehouse.duckdb` (still kept
> READ_ONLY by the DuckDB UI service). Silver and gold dbt models now write to
> DuckLake (the PostgreSQL-backed catalog), which supports concurrent readers.

**5b.** Find the sentence "DuckDB is single-writer; dbt owns the warehouse file. Do
NOT add a second process/Dagster step that opens `warehouse.duckdb` read-write during
a run". Update the note to clarify scope:

Replace "dbt owns the warehouse file" with "dbt now owns the DuckLake catalog" and
make explicit that `warehouse.duckdb` is kept only for the DuckDB UI read-only
attachment.

**5c.** Add a new bullet under the heading (or append to the existing DuckDB
single-writer bullet):

> **After Spec 003:** `profiles.yml` `path:` points at
> `ducklake:<POSTGRES_CATALOG_URL>`. The `DUCKDB_PATH` env var is no longer used by
> dbt but is kept in `config.py` and `docker-compose.yml` for the DuckDB UI service
> (which still attaches `warehouse.duckdb` READ_ONLY from Spec 002).

**Why this satisfies spec ACs**

AC 20: CLAUDE.md updated with the qualified single-writer constraint and the new
storage target.

**Test gate**

There is no automated gate for documentation. Self-review: read the updated paragraph
aloud — it must be internally consistent and not contradict any other CLAUDE.md
paragraph.

**Dependencies:** Steps 1–3 (the constraint qualification is only accurate once
the migration is verified working).

**Guardrails / self-review checkpoint**

- Do not delete the single-writer constraint paragraph — qualify it, do not remove it.
  `warehouse.duckdb` still exists (DuckDB UI) and the second-writer failure mode
  is still relevant if someone opens it read-write.
- Keep the note about `dbt build is NOT green from a clean checkout` unchanged;
  the prerequisite (bronze Parquet must exist) is unaffected by this migration.

---

### Step 6 — Update `ARCHITECTURE.md`: Silver and Gold layer write targets

**What changes**

File: `ARCHITECTURE.md`, section "3. Layering & dependency rules", layer table.

Update the `Writes` column for the Silver and Gold rows:

| Layer | Current `Writes` | New `Writes` |
|---|---|---|
| Silver | `DuckDB view` | `DuckLake view (via dbt)` |
| Gold | `DuckDB table + data/gold/*.parquet` | `DuckLake table + data/gold/*.parquet` |

Also update the Hard Rule 3 text "dbt owns the warehouse; Python reads files, not
tables" — rephrase to "dbt owns the DuckLake catalog; Python reads Parquet files,
not catalog tables" to avoid the stale reference to `warehouse.duckdb`.

In the directory listing under `dbt/data_platform/profiles.yml`, update the comment
from "DuckDB target; reads DUCKDB_PATH/DATA_DIR via env_var" to "DuckLake target;
reads POSTGRES_CATALOG_URL/DATA_DIR via env_var".

**Why this satisfies spec ACs**

AC 21: ARCHITECTURE.md Silver and Gold layer write targets updated to DuckLake.

**Test gate**

No automated gate. Self-review: the table must not reference `warehouse.duckdb`
as the write target for Silver or Gold after the edit.

**Dependencies:** Steps 1–3 (must be certain the migration works before updating
the structural truth).

**Guardrails / self-review checkpoint**

- The Bronze and Publish rows are unchanged — do not touch them.
- The Hard Rules (section 3) use short, scannable language — match the existing style.
- Do not add new architectural rules; only update the storage tier description.

---

### Step 7 — Update `ERD.md`: storage-engine note and table

**What changes**

File: `ERD.md`, section "Implementation Status: Physical vs. Conceptual".

Two updates:

**7a.** In the table, update the `Storage Tier` column for rows that previously said
`DuckDB`:

| Entity | Current `Storage Tier` | New `Storage Tier` |
|---|---|---|
| `season` | `DuckDB` | `DuckLake` |
| `football_data_match_link` | `DuckDB` | `DuckLake` |

Also update their `Physical Storage Mapping / Notes` cells to replace "dbt-owned
DuckDB warehouse" with "dbt-owned DuckLake catalog".

**7b.** Update the "Storage-engine note" block (the blockquote at the bottom of the
table). Replace the sentence:

> In *this* repository the canonical schema (`team`, `league`, `season`, `match`,
> `espn_match_link`, `matchbook_event_link`, `football_data_match_link`) is
> materialized in the **dbt-owned DuckDB warehouse** as typed dbt models...

With:

> In *this* repository the canonical schema (`team`, `league`, `season`, `match`,
> `espn_match_link`, `matchbook_event_link`, `football_data_match_link`) is
> materialized in the **dbt-owned DuckLake catalog** (PostgreSQL-backed, accessed
> via `ducklake:` URI in `profiles.yml`) as typed dbt models...

**Why this satisfies spec ACs**

AC 22: ERD.md storage-engine note updated; `season` and `football_data_match_link`
now correctly reflect DuckLake as their storage tier.

**Test gate**

No automated gate. Self-review: grep ERD.md for "DuckDB" — any remaining occurrences
should only be in the Matchbook Odds Parquet section (which is a physical lake, not
catalog-managed) and in historical description of Spec 002 state, not in the
current-state table or storage-engine note.

**Dependencies:** Steps 1–3.

**Guardrails / self-review checkpoint**

- Only `season` and `football_data_match_link` change storage tier in this spec.
  Do not change `team`, `league`, `match`, `espn_match_link`, `matchbook_event_link`
  — their ERD rows already say `Postgres` (reflecting the upstream gaming-engine
  schema origin); the storage-engine *note* is what clarifies this repo materializes
  them in DuckLake.
- The Matchbook Parquet lake section is unrelated — do not touch it.

---

## Red Tests to Write

There are no pure-Python logic changes in this migration (no new functions, no new
Pydantic models, no new assets). The verification gates in Steps 2–3 are the
functional regression check. However, the following test is worth adding if the
codebase gains an integration test layer for dbt:

**Test: gold external Parquet is written after DuckLake dbt build**

Location: `tests/dbt/test_ducklake_external.py` (only if an integration test
convention exists; do not create for this migration alone).

Assertion: after `dbt build --select gold.users_by_city_export` with a live
DuckLake catalog, `data/gold/users_by_city.parquet` exists and is readable by pandas.

This test is already implicitly covered by `dbt build` returning exit 0 and the
`ls` check in Step 2. Do not create a new test file for this migration unless the
team decides to add a dbt integration test suite.

---

## Traceability Closure Table

| AC | Description (abbreviated) | Plan Step |
|---|---|---|
| AC 1 | `profiles.yml` `path:` changed to DuckLake URI | Step 1 |
| AC 2 | `ducklake` extension remains in `extensions` list | Step 1 |
| AC 3 | `attach:` stanza removed | Step 1 |
| AC 4 | `dbt parse` succeeds after change | Step 1 (test gate) |
| AC 5 | `dbt build` succeeds with live catalog | Step 2 |
| AC 6 | `dbt build --select silver.*` creates all eight silver models | Step 2 |
| AC 7 | Staging views materialised in DuckLake reading bronze Parquet | Step 2 |
| AC 8 | `league/season/team/match/espn_match_link` tables populated | Step 2 |
| AC 9 | `matchbook_event_link` and `football_data_match_link` are empty scaffolds | Step 2 |
| AC 10 | All dbt schema tests pass against DuckLake-backed tables | Step 2 |
| AC 11 | `dbt build --select gold.*` creates `dim_users_by_city` in DuckLake | Step 2 |
| AC 12 | `users_by_city_export` writes `data/gold/users_by_city.parquet` | Step 2 |
| AC 13 | External model does not error with DuckLake incompatibility | Step 2 |
| AC 14 | `dagster definitions validate -w workspace.yaml` passes | Step 3 |
| AC 15 | Dagster AssetKey values are unchanged after migration | Step 3 |
| AC 16 | `BronzeAwareTranslator` requires no code change | Step 3 |
| AC 17 | `medallion_hello_world` job executes end-to-end in container stack | Step 4 (startup wiring enables this) |
| AC 18 | Startup commands work without `DUCKDB_PATH` for dbt | Step 4 |
| AC 19 | `DUCKDB_PATH` not required for dbt; retained for DuckDB UI | Step 4 |
| AC 20 | `CLAUDE.md` single-writer constraint qualified | Step 5 |
| AC 21 | `ARCHITECTURE.md` Silver/Gold layer table updated to DuckLake | Step 6 |
| AC 22 | `ERD.md` storage-engine note updated; `season`/`football_data_match_link` tiers corrected | Step 7 |

---

## Execution Order and Dependencies

```
Step 1 (profiles.yml)
  └── Step 2 (dbt build verification gate)
        └── Step 3 (Dagster AssetKey verification gate)
              ├── Step 4 (docker-compose.yml — safe to do in parallel with Steps 5/6/7)
              ├── Step 5 (CLAUDE.md)
              ├── Step 6 (ARCHITECTURE.md)
              └── Step 7 (ERD.md)
```

Steps 4–7 can be done in a single commit after Steps 1–3 are verified. The
recommended commit boundary is:

- **Commit 1:** `dbt/data_platform/profiles.yml` only (the functional change).
- **Commit 2:** `docker-compose.yml` + `CLAUDE.md` + `ARCHITECTURE.md` + `ERD.md`
  (documentation and infrastructure follow-up, after verification passes).

---

## Open Questions from Spec (Resolution Status)

| # | OQ | Resolution in this plan |
|---|---|---|
| OQ1 | Does attaching the same DuckLake catalog twice cause an error? | Resolved: remove the `attach` stanza in Step 1. Safe unconditionally. |
| OQ2 | Does `dbt-duckdb` support `ducklake:postgresql://...` as `path:`? | Resolved: try without `is_ducklake: true`; add it only if `dbt parse` fails. Step 1 test gate catches this. |
| OQ3 | Does the `database` field change affect Dagster `AssetKey` derivation? | Resolved: Step 3 manifest diff + `dagster definitions validate` confirms. Key derivation uses `schema`, not `database`. |
| OQ4 | Does `external` materialization work with DuckLake `path:`? | Resolved: Step 2 `dbt build --select gold.users_by_city_export` + `ls` check confirms. |
| OQ5 | Should `DUCKDB_PATH` be removed from compose Dagster service envs? | Resolved: keep in `x-app` (inherited by all services). Removing it is out of scope; the DuckDB UI still needs it. |
| OQ6 | Does `dbt parse` inside the container fail without a live catalog? | Resolved: `dbt parse` never opens a catalog connection. Step 4 `depends_on` covers `dbt build` timing. |
| OQ7 | Do `dbt seed` commands need changes? | Resolved: seeds use the same connection as models; they will seed into DuckLake automatically. Verify with `dbt seed` during Step 2 if the `team_aliases` seed is exercised. |

---

*End of Plan 003*
