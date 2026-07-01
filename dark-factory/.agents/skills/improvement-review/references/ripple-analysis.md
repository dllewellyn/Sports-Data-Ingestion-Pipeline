# Ripple analysis — finding the artifacts coupled to a proposal

The defining discipline of this skill: a code improvement is never *just* a code
change. Each proposal must list every coupled artifact, why it's coupled, and what
update it needs — so when the refactor is later driven through `plan` → `implementor`,
the data-flow skill and the `ARCHITECTURE.md` diagram are edited **in the same change**
as the code, not discovered stale months later.

Walk **all** classes below for every opportunity. Searches are read-only signals —
open each hit and confirm the coupling in context before listing it. Delegate broad
sweeps to a read-only `Explore`/`general-purpose` sub-agent.

---

## The artifact-dependency map

### 1. Dependent code (the change's blast radius)
Anything that imports, calls, or is wired to the code you'd move/rename/reshape.
- **Python importers/consumers:**
  ```bash
  grep -rnE "import +<module>|from +<pkg> +import|<symbol>\(" src/data_platform
  ```
- **Dagster wiring:** cross-asset `deps=[AssetKey([...])]` in `definitions.py` and the
  asset modules — remember dbt model keys are **prefixed** (`["gold","<model>"]`). A
  rename/move that doesn't update the prefixed key silently breaks the edge.
- **dbt lineage:** `ref('<model>')` / `source('<src>')` usages downstream:
  ```bash
  grep -rn "ref('<model>')\|source('<src>')" dbt/data_platform/models
  ```
- **Tests:** `tests/**` that exercise the touched code (basenames are unique — importlib
  mode). A reshape ripples into its tests.

### 2. ARCHITECTURE.md (the structural contract + diagrams)
Couples when the proposal changes structure or data-flow:
- new/moved/renamed top-level package or module → package-structure section;
- a changed layering/dependency rule → §3–§4;
- an added/removed/reshaped stage in **bronze→silver→gold**, a new external-Parquet
  boundary, or a new asset edge → the **medallion data-flow diagram** (the user's
  load-bearing example);
- a new repeatable extension pattern → the §6 "add a new data source" guide.

### 3. ERD.md (living data-model docs)
Couples when the proposal touches the relational model: canonical entities
(`team`/`league`/`match`/…), the `*_match_link`/`*_event_link` tables, or any
`dbt/data_platform/models/silver/canonical/*`. Per `CLAUDE.md`, ERD.md updates in the
**same change** as a canonical/link-table change.

### 4. CLAUDE.md (constraints, config, commands)
Couples when the proposal:
- invalidates or adds a **Non-obvious constraint** (e.g. consolidating the two football
  encodings, or the atomic-write rule);
- changes the **Configuration & telemetry** flow (new setting, changed env_var contract,
  compose overlay);
- changes a documented **command** or workflow.
Also honour CLAUDE.md's own "Maintaining this file" rule: the doc edit lands with the code.

### 5. Skills (the procedure contracts)
Scan every skill whose *domain* the change touches — this is what the user explicitly
asked for ("a skill to do with data-flows … we should update that too").
- Inventory: `.agents/skills/**/SKILL.md`, plus `~/.claude/**` and any plugin skills.
- Match the changed subsystem against skill `description`s and bodies:
  ```bash
  grep -rilE "<subsystem keywords e.g. data.flow|ingest|bronze|dbt|deploy>" .agents/skills
  ```
- Typical couplings here: a **data-flow / ingestion** skill if you reshape the flow;
  the **`deploy`** skill if you change run/topology; the dbt/test guidance if you change
  how models/tests are laid out; this repo's phased skills (`plan`/`implementor`) if you
  change a convention they assume.
- For each matched skill, state precisely which step/guardrail/example goes stale and
  the edit it needs. If the change reveals a *missing* skill, that's a `self-learn`
  candidate (note it; don't author it here).

### 6. dbt / config / infra / other docs
- `schema.yml` tests and model `config()` tied to a model you'd move/rename;
- `profiles.yml` / the gold `external` model `env_var(...)` if `DATA_DIR`/`DUCKDB_PATH`
  usage shifts;
- `docker-compose*.yml` overlays, `.env.example`, `pyproject.toml` (ruff set, Python pin)
  if config/tooling changes;
- `notebooks/**`, `README.md`, and any other prose that documents the touched behaviour.

---

## The completeness rule

An opportunity is **ready to present** only when every class above has been checked and
each coupled artifact is listed with *why* + *what update*. If a coupling is uncertain,
list it as an **open question** in the ripple set — never drop it to make the proposal
look clean. Forgetting the coupled skill/diagram/ERD is precisely the failure this skill
exists to prevent.

## Delegating the sweep

For breadth, spawn one read-only sub-agent per opportunity (or a batched one) with: the
proposed change, the file(s) it touches, and this map — asking it to return the coupled
artifacts with `path:line` and the needed update per class. The sub-agent searches; you
confirm each coupling before it enters the report.
