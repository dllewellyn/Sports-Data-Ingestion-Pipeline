# Spec 003 — DuckLake Silver/Gold Model Migration

**Status:** Draft
**Date:** 2026-06-29
**Feature request:** Migrate existing silver and gold dbt models to write through DuckLake (the PostgreSQL-backed catalog added in Spec 002), replacing the current `warehouse.duckdb` single-writer approach.

---

## 1. Overview

Spec 002 wired the DuckLake infrastructure: a PostgreSQL catalog service (`ducklake-catalog`) runs as a base compose service, the `ducklake` DuckDB extension is loaded in `dbt/data_platform/profiles.yml`, and the catalog is attached as `lake` in every dbt session. However, `profiles.yml` still points `path:` at `warehouse.duckdb`, so all silver and gold dbt models continue writing there.

This spec migrates all dbt-owned silver and gold models to DuckLake by switching the dbt target's `path:` to the DuckLake Postgres catalog. After the migration:

- All silver views (`stg_users`, `stg_espn_events`, `stg_matchbook_odds`) are DuckLake-managed views.
- All silver canonical tables (`league`, `season`, `team`, `match`, `espn_match_link`, `matchbook_event_link`, `football_data_match_link`) are DuckLake-managed tables.
- The gold aggregate table (`dim_users_by_city`) is a DuckLake-managed table.
- The gold external export (`users_by_city_export`) continues to write a Parquet file on disk — unchanged.
- Bronze Parquet sources (`_sources.yml`) are unaffected: they reference files on disk, not catalog tables.
- `warehouse.duckdb` is no longer the primary dbt target; it can be kept as a read reference or removed from the compose startup command.

The migration eliminates the single-writer constraint that forced strict serialisation of all dbt runs and makes the silver/gold layer available for concurrent reads from the DuckDB UI and other DuckLake-aware clients without any `(READ_ONLY)` workaround.

---

## 2. Goals and Non-Goals

### Goals

- Switch `profiles.yml` `path:` from `warehouse.duckdb` to the DuckLake Postgres catalog URI so all dbt models are written to and read from DuckLake.
- Confirm that all silver views, silver canonical tables, and gold tables rebuild correctly after the switch.
- Confirm that the gold external (Parquet) export model is unaffected.
- Confirm that `BronzeAwareTranslator` and Dagster `AssetKey` derivation are unaffected.
- Confirm that `dbt parse` and `dbt build` succeed in the container environment after the switch.
- Drop `warehouse.duckdb` as a required runtime artifact from Dagster/dbt startup commands.
- Update `CLAUDE.md` to reflect the lifted single-writer constraint for dbt-owned tables and the new storage target.
- Update `ARCHITECTURE.md` layer table to record that silver and gold now write to DuckLake.
- Update `ERD.md` storage-engine note to reflect DuckLake as the canonical table store.

### Non-Goals

- **Making Dagster bronze assets write to DuckLake.** Bronze continues to write Parquet. Only the dbt layer migrates.
- **Removing `warehouse.duckdb` from the repository or all tooling.** The file may still be created by incidental DuckDB connections (e.g., the DuckDB UI in Spec 002 attaches it read-only); this spec does not mandate its removal, only that dbt no longer uses it as `path:`.
- **Changing any model SQL.** All `{{ ref(...) }}`, `{{ source(...) }}`, and `{{ config(...) }}` calls in `.sql` files remain exactly as they are.
- **Adding a new dbt target or profile.** One profile (`dev`) is updated in place; no second profile is created.
- **Data migration from `warehouse.duckdb`.** All silver/gold data is derived from bronze Parquet — it is re-created on the next `dbt build`. No ETL from the old warehouse is needed.
- **Migrating the DuckDB UI or any Python asset** — the UI already reads from both warehouse and DuckLake; once dbt targets DuckLake, the models appear under the `lake` attachment automatically.
- **Multi-writer Dagster runs (parallel dbt steps).** The single-writer constraint for a single dbt process is lifted by DuckLake. True parallel Dagster asset steps writing to DuckLake simultaneously are out of scope for this spec.

---

## 3. Scenarios

### Scenario 1: Developer runs dbt build after switching the profile

```
Given profiles.yml path: is set to the DuckLake Postgres catalog URI
And the ducklake-catalog Postgres service is running and healthy
And bronze Parquet files are present in data/bronze/
When a developer runs `dbt build` from dbt/data_platform/
Then all silver views are created in the DuckLake catalog
And all silver canonical tables are populated in the DuckLake catalog
And the gold dim_users_by_city table is created in the DuckLake catalog
And data/gold/users_by_city.parquet is written to disk (external materialization unchanged)
And no file warehouse.duckdb is created or required for the build to succeed
```

### Scenario 2: Dagster dbt_models asset runs successfully

```
Given the dagster-webserver and dagster-daemon start with the updated workspace
And the ducklake-catalog service is reachable at ducklake-catalog:5432
When a user triggers the medallion_hello_world job or the dbt_models asset in Dagster
Then the DbtCliResource runs `dbt build` with the updated profile
And silver and gold assets complete and reflect green status in the Dagster UI
And Dagster AssetKey derivation is unchanged (silver/ and gold/ prefixes unchanged)
```

### Scenario 3: BronzeAwareTranslator lineage is preserved

```
Given the dbt manifest is generated from the updated profile
When Dagster loads the manifest via @dbt_assets
Then BronzeAwareTranslator maps dbt source 'users' to AssetKey(["raw_users"])
And BronzeAwareTranslator maps dbt source 'espn_events' to AssetKey(["espn_bronze"])
And the bronze -> silver -> gold lineage edges render correctly in the Dagster asset graph
```

### Scenario 4: Gold external (Parquet) export is unaffected

```
Given profiles.yml path: points at DuckLake
When dbt builds the users_by_city_export model
Then the model writes data/gold/users_by_city.parquet to the host filesystem
And the publish_gold_parquet Dagster asset reads the Parquet file successfully
And no error is raised about an external materialization incompatibility with DuckLake
```

### Scenario 5: DuckDB UI shows DuckLake-backed silver and gold tables

```
Given dbt has run and silver/gold tables exist in the DuckLake catalog
And the duckdb-ui container is running (from Spec 002) with the lake attachment
When a developer opens http://localhost:4213
Then the silver and gold schemas and their tables are visible under the lake attachment
And SELECT queries against silver and gold tables return data without error
```

### Scenario 6: Fresh checkout + data ingest + dbt build produces a working warehouse

```
Given a clean checkout with no data/ directory or warehouse.duckdb
When the developer runs the bronze ingest (raw_users, espn_bronze) to populate Parquet
And then runs `dbt parse` followed by `dbt build`
Then dbt build succeeds (all silver/gold models pass)
And no warehouse.duckdb file is required
And the gold Parquet file is present at data/gold/users_by_city.parquet
```

### Scenario 7: DUCKDB_PATH env var is no longer required for dbt

```
Given the updated profiles.yml uses the DuckLake URI as path
When a developer runs dbt parse or dbt build without DUCKDB_PATH set
Then dbt does not fail because DUCKDB_PATH is absent
And the POSTGRES_CATALOG_URL env var drives the catalog connection
```

---

## 4. Acceptance Criteria

**profiles.yml change**

1. `dbt/data_platform/profiles.yml` `path:` is changed from `"{{ env_var('DUCKDB_PATH', ...) }}"` to `"ducklake:{{ env_var('POSTGRES_CATALOG_URL', 'postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake') }}"`.
2. The `ducklake` extension remains in the `extensions` list (already present from Spec 002).
3. The `attach` stanza for the `lake` alias is removed or repurposed — once `path:` is the DuckLake catalog, the existing `lake` attach is a self-attach and must be evaluated for whether it causes a conflict (see Open Questions). The simplest resolution is to remove the `attach` stanza entirely.
4. `dbt parse` succeeds without error after the change (does not require the Postgres service to be running; the ducklake extension is loaded but parse does not open a catalog connection).
5. `dbt build` succeeds when `ducklake-catalog` is running and bronze Parquet is present.

**Silver layer**

6. `dbt build --select silver.*` creates all eight silver models (three staging views + five canonical tables + two empty-scaffold canonical tables) in the DuckLake catalog.
7. `stg_users`, `stg_espn_events`, and `stg_matchbook_odds` are materialised as views in the DuckLake catalog, reading external bronze Parquet via their `external_location` source definitions (unchanged).
8. `league`, `season`, `team`, `match`, `espn_match_link` are materialised as tables in the DuckLake catalog and are populated when ESPN bronze Parquet is present.
9. `matchbook_event_link` and `football_data_match_link` remain empty-scaffold tables in the DuckLake catalog (typed but zero rows), matching their pre-migration behaviour.
10. All existing dbt schema tests (`_schema.yml`, `canonical/_schema.yml`) pass against the DuckLake-backed tables.

**Gold layer**

11. `dbt build --select gold.*` creates `dim_users_by_city` as a table in the DuckLake catalog.
12. `users_by_city_export` writes `data/gold/users_by_city.parquet` to the host filesystem (external materialization is unaffected by the DuckLake `path:` change).
13. The gold external model does not error with a DuckLake incompatibility (confirmed by a successful `dbt build --select gold.users_by_city_export`).

**Dagster integration**

14. `dagster definitions validate -w workspace.yaml` passes after the profile change and a fresh `dbt parse`.
15. The Dagster asset graph contains the same `AssetKey` values for all dbt models as before the migration — specifically `["silver", "stg_users"]`, `["silver", "stg_espn_events"]`, `["silver", "league"]`, `["silver", "match"]`, `["silver", "team"]`, `["silver", "season"]`, `["silver", "espn_match_link"]`, `["gold", "dim_users_by_city"]`, etc. (the dbt `database` field change does not affect key derivation because keys are derived from the `schema` folder prefix, not the database name — see Architectural Decision 6.3).
16. `BronzeAwareTranslator` requires no code change — it maps source names, not target databases.
17. The `medallion_hello_world` job executes successfully end-to-end in the container stack.

**Startup commands**

18. The `dagster-webserver` and `dagster-daemon` compose service startup commands no longer require `dbt parse` to be run against a `DUCKDB_PATH` path before startup. If `dbt parse` is still in the startup command, it succeeds without `DUCKDB_PATH` being set (the manifest is written to `dbt/data_platform/target/manifest.json` regardless of the storage backend).
19. `DUCKDB_PATH` is no longer a required env var for dbt. It may remain in `.env.example` for the DuckDB UI service (which still attaches `warehouse.duckdb` read-only from Spec 002), but the Dagster services do not require it.

**Documentation**

20. `CLAUDE.md` "Non-obvious constraints" section is updated: the single-writer constraint note for `warehouse.duckdb` is qualified to reflect that it no longer applies to dbt silver/gold tables (they now live in DuckLake), but the DuckDB UI READ_ONLY pattern for `warehouse.duckdb` (if retained) still applies.
21. `ARCHITECTURE.md` layer table Silver and Gold rows are updated to show "DuckLake (via dbt)" as the Write target, replacing "DuckDB view/table".
22. `ERD.md` storage-engine note is updated: `season` (previously `DuckDB`) and `football_data_match_link` (previously `DuckDB`) now live in DuckLake; the table reflects DuckLake for all canonical models.

---

## 5. Architectural Decisions

### 5.1 Full migration via path: switch (Option A)

**Decision:** Switch `profiles.yml` `path:` from `warehouse.duckdb` to the DuckLake Postgres URI. All dbt models migrate simultaneously.

**Alternatives considered:**

- **Option B — per-model `database: lake` config:** Keep `path: warehouse.duckdb` as the default; add `+database: lake` to `dbt_project.yml` model configs to route specific models to DuckLake. This gives fine-grained staged migration but introduces two storage backends in one dbt session, which complicates `ref()` resolution (dbt must know which database a referenced model lives in) and cross-model `ref()` calls between models on different databases need explicit `database` qualifiers.
- **Option C — new `ducklake` dbt target:** Create a second entry in `outputs` and migrate model by model by switching the active `--target`. Adds profile maintenance overhead; once the migration is complete, the `dev` target is deleted anyway.

**Rationale:** Option A is the simplest, lowest-risk path. All model SQL (`ref`, `source`, `config`) is unchanged; only the connection target changes. Silver/gold data is 100% derived from bronze Parquet — there is no data to migrate and no rollback complexity. If a rollback is needed (DuckLake incompatibility discovered), reverting `profiles.yml` restores the previous behaviour immediately.

### 5.2 No data migration from warehouse.duckdb

**Decision:** No ETL from the old `warehouse.duckdb` into DuckLake. The first `dbt build` after the switch rebuilds all tables from bronze Parquet.

**Rationale:** The medallion architecture guarantees that all data in silver and gold is reproducible from bronze Parquet (the source of truth). Attempting to migrate data from the old warehouse introduces a second DuckDB writer and risks phantom catalog errors (the exact failure mode documented in CLAUDE.md). Rebuild from source is both safer and simpler.

**Implication:** The first `dbt build` after migration will see empty DuckLake schemas. Bronze Parquet must be present before `dbt build` runs, as it was before this migration. This is a pre-existing constraint (documented in CLAUDE.md under "dbt build is NOT green from a clean checkout").

### 5.3 Remove the attach stanza after the path: switch

**Decision:** Remove the `attach` stanza from `profiles.yml` once `path:` points at DuckLake.

**Rationale:** When `path:` is already the DuckLake Postgres URI, dbt's primary connection IS the DuckLake catalog. Attaching the same catalog a second time under the alias `lake` is either a no-op or an error. The `lake` alias was only needed when `path:` was `warehouse.duckdb` and DuckLake was a secondary attachment. Removing it simplifies the config.

**Risk:** If existing model SQL references `lake.<schema>.<table>` explicitly, those references break. A search of all model `.sql` files confirms there are no such explicit references — all cross-model references use `{{ ref(...) }}` or `{{ source(...) }}`. The `lake` alias was never used in model SQL in Spec 002.

### 5.4 External materialization is unaffected

**Decision:** The `users_by_city_export` model's `external` materialization (writing Parquet to disk) requires no changes.

**Rationale:** The dbt-duckdb `external` materialization writes a file to the path given by `location:`. It does not write a catalog entry to the `path:` database. Switching `path:` to DuckLake does not affect how external materializations write their output file. The `location: env_var('DATA_DIR', ...) ~ '/gold/users_by_city.parquet'` path resolves the same way regardless of storage backend.

**Verification:** Confirm by running `dbt build --select gold.users_by_city_export` after the migration and asserting `data/gold/users_by_city.parquet` exists.

### 5.5 Dagster AssetKey derivation is stable across the migration

**Decision:** No changes are required to `BronzeAwareTranslator` or any `AssetKey` construction in Python.

**Rationale:** The `@dbt_assets` decorator derives `AssetKey` values from the dbt manifest node properties. The key prefix is determined by the **schema** folder in `dbt_project.yml` (`+schema: silver`, `+schema: gold`), not the `database` field. Switching `path:` changes the `database` in the manifest's node properties from the DuckDB default schema name to the DuckLake catalog name, but `DagsterDbtTranslator.get_asset_key()` uses the schema, not the database, to build the prefix. The CLAUDE.md constraint "dbt model Dagster asset keys are prefixed by their schema folder only" confirms this.

**Verification:** After `dbt parse` with the new profile, inspect `dbt/data_platform/target/manifest.json` and confirm that all node `fqn` values and schema assignments are unchanged. Then run `dagster definitions validate -w workspace.yaml` and confirm no `AssetKey` conflicts are reported.

### 5.6 DUCKDB_PATH env var lifecycle

**Decision:** `DUCKDB_PATH` remains in `.env.example` and `config.py` for backward compatibility and because the DuckDB UI service (Spec 002) still attaches `warehouse.duckdb` read-only. No code removal is required in this spec.

**Rationale:** Removing `DUCKDB_PATH` entirely would break the DuckDB UI startup command from Spec 002 and any existing developer `.env` files. Keeping it in config.py as a `settings.duckdb_path` field costs nothing. The `profiles.yml` change simply stops using `env_var('DUCKDB_PATH', ...)` as the `path:` value.

---

## 6. Constraints (from CLAUDE.md)

These constraints are non-negotiable. Where this spec modifies a constraint, the modification is stated explicitly.

- **DuckDB single-writer on `warehouse.duckdb`:** This constraint is **lifted for dbt silver/gold models** once the `path:` switch is made. DuckLake uses the Postgres catalog to coordinate writes, enabling safe concurrent access. The constraint still applies to `warehouse.duckdb` if it is kept for the DuckDB UI (it must remain READ_ONLY for that service). If `warehouse.duckdb` is no longer opened by any process, the constraint is moot.
- **dbt owns the warehouse; Python reads files, not tables.** This continues to hold. `assets/gold.py` reads `data/gold/users_by_city.parquet` (the external materialization output), not any DuckLake table directly. This constraint is unchanged.
- **Canonical match identity through `canonical_match_id` macro.** All canonical model SQL is unchanged. The macro and its usage in `match.sql`, `espn_match_link.sql`, etc. are not touched.
- **dbt model Dagster asset keys are prefixed by their schema folder only.** Verified in Architectural Decision 5.5 above. No key prefix changes.
- **No `from __future__ import annotations` in Dagster asset modules.** `assets/dbt.py` is not modified.
- **Config comes from `pydantic-settings`.** No new `os.getenv()` calls. `POSTGRES_CATALOG_URL` is already in `config.py` (added in Spec 002).
- **dbt build is NOT green from a clean checkout.** This constraint is UNCHANGED. Bronze Parquet must be materialized first. The migration does not change this.
- **The daemon and webserver must load the SAME workspace.yaml.** Unchanged. The profile change is in `profiles.yml`, not in the Dagster workspace definition.
- **Do not overengineer.** This migration is a single-line change to `profiles.yml` plus documentation updates. No new abstractions, no new Python modules, no new dbt models are introduced.

---

## 7. Implementation Checklist

These are the discrete changes required, in dependency order:

1. **`dbt/data_platform/profiles.yml`**
   - Change `path:` from `"{{ env_var('DUCKDB_PATH', '/app/data/warehouse.duckdb') }}"` to `"ducklake:{{ env_var('POSTGRES_CATALOG_URL', 'postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake') }}"`.
   - Remove the `attach:` stanza entirely (it is no longer needed; `lake` aliased to the same DuckLake catalog would be a duplicate attachment).
   - Keep `ducklake` in the `extensions` list (already present).
   - Keep `parquet` in the `extensions` list (required for external source reads).

2. **Verify `dbt parse` succeeds** (no `ducklake-catalog` connection required at parse time). Run locally or in CI before proceeding.

3. **Verify `dbt build` succeeds** with `ducklake-catalog` running and bronze Parquet present. Check all models pass; confirm `data/gold/users_by_city.parquet` is written.

4. **Verify Dagster asset keys are stable.** Run `dagster definitions validate -w workspace.yaml` and confirm `AssetKey` values match the pre-migration set.

5. **Update compose startup commands** — if the Dagster service startup commands in any `docker-compose*.yml` file reference `DUCKDB_PATH` in a `dbt parse` invocation, update them to pass `POSTGRES_CATALOG_URL` instead (or confirm the existing env var passthrough already covers it via the default in `profiles.yml`).

6. **`CLAUDE.md`** — update the single-writer constraint note: qualify it as applying only to `warehouse.duckdb` (still relevant for the DuckDB UI attachment), not to DuckLake-managed tables. Add a note that `profiles.yml` `path:` now points at DuckLake.

7. **`ARCHITECTURE.md`** — update the Silver and Gold rows in the layer table to reflect DuckLake as the write target.

8. **`ERD.md`** — update the storage-engine note: `season`, `matchbook_event_link`, `football_data_match_link` (previously DuckDB) now live in DuckLake alongside `league`, `team`, `match`, `espn_match_link`.

---

## 8. Open Questions

| # | Question | Status | Notes |
|---|----------|--------|-------|
| 1 | Does attaching the same DuckLake catalog twice (once as `path:`, once as `lake` in the `attach` stanza) cause an error, or is it silently ignored by dbt-duckdb? | **BLOCKER** | Determines whether the `attach` stanza must be removed (recommended) or can be left. Must be verified before merging the profiles.yml change. The safe answer is to remove it. |
| 2 | Does `dbt-duckdb` support `ducklake:postgresql://...` as the `path:` value, or does it require the DuckLake connection to be established via `attach` only? The `dbt-duckdb` connector may have version-specific handling for the `ducklake:` URI scheme in the `path` field. | **BLOCKER** | If `dbt-duckdb` does not pass a `ducklake:` URI as-is to DuckDB's `ATTACH`, the profiles.yml approach may need adjustment (e.g., using `type: ducklake` if that becomes a supported adapter, or using a custom `connect_args`). Must be verified against the installed `dbt-duckdb` version. |
| 3 | Does switching `path:` to DuckLake change the `database` field in the dbt manifest for all models, and does that affect how `dagster-dbt` derives `AssetKey` values? The CLAUDE.md analysis says keys come from schema folders, but the manifest `database` field change should be verified empirically. | **BLOCKER** | Run `dbt parse` with the new profile and diff the manifest against the current one. Specifically check all `node.database` fields and confirm `DagsterDbtTranslator.get_asset_key()` still produces the expected prefixes. |
| 4 | Does the `external` materialization in `dbt-duckdb` work correctly when `path:` is a DuckLake catalog? The external materialization uses `COPY TO` or a `CREATE TABLE ... AS SELECT` with an external location — does this work inside a DuckLake-connected session? | **BLOCKER** | Must be verified by running `dbt build --select gold.users_by_city_export` with the new profile and confirming the Parquet file is written. If the external materialization has a bug with DuckLake connections, a workaround (e.g., a post-hook `COPY TO`) would be needed. |
| 5 | Should `DUCKDB_PATH` be removed from the compose service environment sections now that dbt no longer uses it? | **NON-BLOCKER** | Keeping it is safe and backward-compatible. The DuckDB UI service still needs it. Remove from Dagster service envs only if it causes confusion. |
| 6 | Does `dbt parse` inside the container (before dbt-catalog connection is available) fail if the `ducklake` extension cannot load at parse time? Spec 002 open question 7 raised this; the answer was "should be fine" but was not confirmed empirically. | **NON-BLOCKER** | If parse fails without a live catalog, the compose startup sequence must ensure `ducklake-catalog` is healthy before the Dagster services start. Add `depends_on: ducklake-catalog: condition: service_healthy` to the Dagster compose services if needed. |
| 7 | Do the `team_aliases` dbt seed commands need any change? Seeds are materialised in the same target database as models. After the switch, `team_aliases` will be seeded into DuckLake. Does `dbt seed` work the same way against DuckLake? | **NON-BLOCKER** | Likely fine — seeds use the same connection as models. Verify with `dbt seed` after the profile change. |

---

## 9. Traceability Table

| Requirement | Scenario | Acceptance Criteria |
|---|---|---|
| Switch dbt target from warehouse.duckdb to DuckLake | S1, S6 | AC 1–5 |
| All silver models write to DuckLake | S1, S2 | AC 6–10 |
| All gold models write to DuckLake | S1, S2 | AC 11–13 |
| Dagster asset graph and AssetKey values unchanged | S2, S3 | AC 14–16 |
| Gold external Parquet export unaffected | S4 | AC 12, 13 |
| DuckDB UI shows DuckLake-backed tables | S5 | AC 5 (profiles), AC 11 (gold table visible) |
| Fresh checkout flow works without warehouse.duckdb | S6 | AC 5, AC 18, AC 19 |
| DUCKDB_PATH no longer required for dbt | S7 | AC 18, AC 19 |
| CLAUDE.md / ARCHITECTURE.md / ERD.md updated | — | AC 20, AC 21, AC 22 |

---

*End of Spec 003*
