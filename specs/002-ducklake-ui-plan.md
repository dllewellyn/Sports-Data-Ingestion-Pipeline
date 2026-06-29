# Plan 002 — DuckLake + DuckDB UI Integration

**Spec:** `specs/002-ducklake-ui-specification.md`
**Date:** 2026-06-29
**Status:** Ready for implementation

---

## Overview

Nine file changes in dependency order. Steps 1–3 are pure Python/config and have no
mutual dependencies; they can be done in any order but must be complete before the
compose changes are reviewed for correctness (Step 4 derives env-var defaults from
the config fields). Steps 5–7 depend on Step 4 (extend a service that Step 4
defines). Step 8 (profiles.yml) is independent of compose but should be done after
Step 1 so the dbt-duckdb version is confirmed. Step 9 (CLAUDE.md) is always last.

---

## Step 1 — Bump DuckDB version in `pyproject.toml`

### What changes

**File:** `pyproject.toml`

Diff summary:
- Change `"duckdb>=1.1"` to `"duckdb>=1.5.2"` (try `>=1.5.2` first; fall back to
  `>=1.2.0` only if `uv lock` reports a conflict with `dbt-duckdb>=1.9` or a
  dagster transitive pin).
- Add an inline comment on the next line:
  ```toml
  # DuckLake 1.0 requires the DuckDB runtime to be >=1.5.2; the duckdb/duckdb
  # Docker image (used by the duckdb-ui service) must satisfy this independently.
  ```

### Why

Satisfies AC 15 and AC 16. The spec (§5.4) explicitly calls out that `>=1.5.2` is
the DuckLake 1.0 requirement and that going directly to `>=1.5.2` is acceptable if
`uv lock` resolves cleanly.

### Test facility

```bash
uv lock
# Must exit 0 with no "version conflict" messages.
# Verify the resolved version:
uv run python -c "import duckdb; print(duckdb.__version__)"
# Output must be >= 1.5.2
```

A `uv lock` failure (conflicting resolution) is a genuine FAIL that blocks this
step. If it fails, fall back to `>=1.2.0` and add a comment explaining why
`>=1.5.2` could not be pinned in Python — but note that the DuckLake extension will
still require `>=1.5.2` at *runtime* (provided by the Docker image).

### Dependencies

None — this is the first step.

### Guardrails / self-review checkpoint

- Confirm the `uv.lock` diff shows a DuckDB upgrade, not a downgrade.
- Confirm no other dependency in `pyproject.toml` pins an upper-bound that would
  prevent `>=1.5.2`.
- Do NOT change `dbt-duckdb` or any other pin — scope is narrowly the `duckdb`
  line.

---

## Step 2 — Add new config fields to `src/data_platform/config.py`

### What changes

**File:** `src/data_platform/config.py`

Add two fields to the `Settings` class after the `duckdb_path` field (keep the
medallion-layout comment block intact):

```python
# DuckLake catalog
postgres_catalog_url: str = (
    "postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake"
)
ducklake_data_path: Path = Path("data/lake")
```

No import additions needed (`str` and `Path` are already imported).

### Why

Satisfies AC 12 and AC 13. Pydantic-settings convention (CLAUDE.md, ARCHITECTURE.md
§5) mandates all config as typed fields on `Settings` — no `os.getenv` elsewhere.

### Test facility

```bash
PYTHONPATH=src uv run python -c \
  "from data_platform.config import Settings; s = Settings(); \
   print(s.postgres_catalog_url); print(s.ducklake_data_path)"
# Expected:
# postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake
# data/lake
```

This will FAIL before the change (AttributeError on the new fields).

Override test — confirms env vars are honoured:
```bash
PYTHONPATH=src POSTGRES_CATALOG_URL=postgresql://test:test@localhost/test \
  uv run python -c \
  "from data_platform.config import Settings; print(Settings().postgres_catalog_url)"
# Expected: postgresql://test:test@localhost/test
```

### Dependencies

Step 1 (want a consistent lock file before running any Python).

### Guardrails / self-review checkpoint

- `config.py` already has `from __future__ import annotations` — this is acceptable
  because `config.py` is NOT a Dagster asset module (constraint only applies to
  asset modules).
- The new `ducklake_data_path` default is a relative `Path("data/lake")`, consistent
  with the existing `data_dir: Path = Path("data")` default. Container workloads set
  `DATA_DIR=/app/data` via env — but `ducklake_data_path` is a standalone field not
  derived from `data_dir`, matching the pattern of `duckdb_path`.
- Run `uv run ruff check src/data_platform/config.py` and `uv run ruff format
  src/data_platform/config.py` — must be clean before proceeding.

---

## Step 3 — Update `.env.example`

### What changes

**File:** `.env.example`

Append a new section after the existing `# --- Self-hosted SigNoz ---` block:

```bash
# --- DuckLake catalog ---
# PostgreSQL-backed DuckLake catalog. The catalog Postgres container is defined in
# docker-compose.yml (base) and is shared by all overlays.
# Host-side path for DuckLake-managed Parquet files (mapped into containers as
# /app/data/lake). Set an absolute path if running outside Docker.
POSTGRES_CATALOG_URL=postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake
DUCKLAKE_DATA_PATH=data/lake
```

### Why

Satisfies AC 14 and AC 19. All env vars used by `Settings` must be documented in
`.env.example` (project convention; CLAUDE.md §Configuration & telemetry).

### Test facility

Visual check: `POSTGRES_CATALOG_URL` and `DUCKLAKE_DATA_PATH` both appear in the
file under the `# --- DuckLake catalog ---` heading. No automated gate here — the
test from Step 2 (env override) already verifies the variable names are correct.

### Dependencies

Step 2 (need the canonical field names from `Settings` before documenting them).

### Guardrails / self-review checkpoint

- Confirm both variable names exactly match the pydantic-settings auto-derived names
  from Step 2 (`postgres_catalog_url` → `POSTGRES_CATALOG_URL`,
  `ducklake_data_path` → `DUCKLAKE_DATA_PATH`).
- No sensitive defaults — the dev credentials (`ducklake:ducklake`) are fine for a
  local-only catalog container that holds no production data.

---

## Step 4 — Update `docker-compose.yml` (base)

### What changes

**File:** `docker-compose.yml`

Three additions:

**A. `ducklake-catalog` service** (insert before `volumes:` block):

```yaml
  # PostgreSQL catalog for DuckLake. All overlays inherit this service.
  # Credentials are dev defaults; override via .env for production.
  ducklake-catalog:
    image: postgres:16
    environment:
      POSTGRES_DB: ducklake
      POSTGRES_USER: ducklake
      POSTGRES_PASSWORD: ducklake
    volumes:
      - ducklake_catalog:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ducklake"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
```

**B. `duckdb-ui` service** (insert after `ducklake-catalog`):

```yaml
  # DuckDB UI — browser SQL interface on http://localhost:4213.
  # Opens warehouse.duckdb READ_ONLY (single-writer constraint preserved).
  # Also attaches the DuckLake catalog for browsing catalog-managed tables.
  duckdb-ui:
    image: duckdb/duckdb:latest
    ports:
      - "4213:4213"
    volumes:
      - ./data:/app/data:ro
    depends_on:
      ducklake-catalog:
        condition: service_healthy
    command: >
      sh -c "duckdb -cmd
        \"INSTALL ui; LOAD ui;
          INSTALL ducklake; LOAD ducklake;
          ATTACH '/app/data/warehouse.duckdb' AS warehouse (READ_ONLY);
          ATTACH 'ducklake:postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake'
            AS lake (DATA_PATH '/app/data/lake/');
          CALL start_ui({'listen': '0.0.0.0:4213'});\""
    healthcheck:
      test: ["CMD-SHELL", "wget --spider -q http://localhost:4213 || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped
```

**C. Named volume** (add to `volumes:` block):

```yaml
  ducklake_catalog:
```

### Why

Satisfies AC 1, 2, 3, 4, 17 (READ_ONLY in startup command), and AC 18. Both new
services are in the base so all overlays inherit them without repetition (spec §5.6,
CLAUDE.md compose overlay semantics).

### Test facility

```bash
docker compose config --services
# Must list: dagster-webserver, dagster-daemon, jupyter, matchbook-ingestor,
#            ducklake-catalog, duckdb-ui

docker compose up ducklake-catalog -d
docker compose ps ducklake-catalog
# Status must be "healthy" within ~30s

docker compose up duckdb-ui -d
# After start_period: curl or wget http://localhost:4213 must return HTTP 200
```

The first `docker compose config --services` will FAIL before the change (neither
service exists). The healthcheck FAIL of `ducklake-catalog` before the service
exists is also a meaningful gate.

### Dependencies

Steps 1–3 (all config/Python changes complete so we can cross-reference env vars
accurately in the command string).

### Guardrails / self-review checkpoint

- Confirm `warehouse.duckdb` is opened with `(READ_ONLY)` in the `duckdb-ui`
  command — this is the single-writer guard (AC 17, CLAUDE.md).
- Confirm `./data:/app/data:ro` — the volume mount is read-only at the OS level for
  extra protection.
- The `duckdb-ui` command string uses `sh -c "duckdb -cmd \"...\"` — verify the
  quoting is shell-safe with `docker compose config` (it will expand and normalise
  the command).
- Confirm the `ducklake_catalog` volume appears in `volumes:` at the top level —
  named volumes must be declared even if unused by overlays.
- Do NOT add `signoz-net` or `sports-quant` to either service here — that violates
  the base file's environment-neutral rule (CLAUDE.md).

---

## Step 5 — Update `docker-compose.signoz.yml`

### What changes

**File:** `docker-compose.signoz.yml`

Add a `duckdb-ui` service stanza in the `services:` section (inside the
`# --- App services: dev overrides ---` block, alongside the existing webserver/
daemon/jupyter overrides):

```yaml
  duckdb-ui:
    networks:
      - signoz-net
```

No other change — the base definition already has the port, volume, command, and
healthcheck. This stanza only joins the service to `signoz-net` so it can reach
`ducklake-catalog` by hostname when `ducklake-catalog` is also on `signoz-net`.

> Note: `ducklake-catalog` is defined in the base file without a network. In the
> signoz overlay, add `ducklake-catalog` to `signoz-net` too so the hostname
> resolves from `duckdb-ui`:

```yaml
  ducklake-catalog:
    networks:
      - signoz-net
```

### Why

Satisfies AC 5. Without joining `signoz-net`, the `duckdb-ui` container is on the
default bridge and cannot resolve `ducklake-catalog` by hostname in the signoz
overlay.

### Test facility

```bash
docker compose -f docker-compose.yml -f docker-compose.signoz.yml config \
  | grep -A 10 "duckdb-ui:"
# Must show signoz-net in the networks list for duckdb-ui

docker compose -f docker-compose.yml -f docker-compose.signoz.yml up duckdb-ui -d
# Container must start; DuckDB UI must be reachable on :4213
```

### Dependencies

Step 4 (service must exist in base before it can be extended).

### Guardrails / self-review checkpoint

- Confirm the stanza is placed inside the `services:` block, not at the top level.
- Confirm `signoz-net` already exists in the `networks:` section of this file
  (it does — `networks: signoz-net: name: signoz-net`).
- Do NOT copy the base `command:`, `ports:`, or `volumes:` into this override —
  Compose merges those automatically; duplicating them creates noise and future
  divergence risk.

---

## Step 6 — Update `docker-compose.prod.yml`

### What changes

**File:** `docker-compose.prod.yml`

Add a `duckdb-ui` service stanza in the `services:` block (alongside the existing
dagster/jupyter/matchbook-ingestor overrides):

```yaml
  duckdb-ui:
    <<: *prod-app
```

This applies the `OTEL_EXPORTER_OTLP_ENDPOINT` environment override from the
`x-prod-app` anchor. The base service definition (port, volume, command) is
inherited.

> If the prod overlay's commented-out `otel-external` network is enabled in future,
> `duckdb-ui` should be added to that network too — add a comment noting this.

### Why

Satisfies AC 6. Every overlay must include the `duckdb-ui` service so `docker
compose up` with any overlay brings up the UI (spec §2 Goals, AC 8).

### Test facility

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --services
# Must list duckdb-ui

docker compose -f docker-compose.yml -f docker-compose.prod.yml config \
  | grep -A 5 "duckdb-ui:"
# Must show OTEL_EXPORTER_OTLP_ENDPOINT set
```

### Dependencies

Step 4 (service must exist in base). Step 5 is independent.

### Guardrails / self-review checkpoint

- Confirm the prod overlay does not inadvertently set `COMPOSE_FILE` or add
  SigNoz-specific config.
- The `*prod-app` anchor requires `OTEL_EXPORTER_OTLP_ENDPOINT` to be set — this
  is already the existing prod contract; no new risk.

---

## Step 7 — Update `docker-compose.remote.yml`

### What changes

**File:** `docker-compose.remote.yml`

Add a `duckdb-ui` service stanza in the `services:` block (alongside dagster/
jupyter):

```yaml
  duckdb-ui:
    networks:
      - sports-quant
```

Also add `ducklake-catalog` to `sports-quant` (same pattern as Step 5):

```yaml
  ducklake-catalog:
    networks:
      - sports-quant
```

The `sports-quant` network is already declared in this overlay's `networks:` block
as an external network.

### Why

Satisfies AC 7. The remote overlay joins the shared `sports-quant` Docker network
so the sports-gaming-engine infra is reachable. `duckdb-ui` needs the same network
membership for DNS resolution of `ducklake-catalog`.

### Test facility

```bash
docker compose -f docker-compose.yml -f docker-compose.remote.yml config --services
# Must list duckdb-ui

docker compose -f docker-compose.yml -f docker-compose.remote.yml config \
  | grep -A 10 "duckdb-ui:"
# Must show sports-quant in networks
```

### Dependencies

Step 4 (base service must exist).

### Guardrails / self-review checkpoint

- Confirm `sports-quant` is defined as `external: true` in this file's `networks:`
  block (it already is).
- Do NOT add env-var overrides here unless required by the remote environment — keep
  the stanza minimal.

---

## Step 8 — Update `dbt/data_platform/profiles.yml`

### What changes

**File:** `dbt/data_platform/profiles.yml`

Two additions inside the `dev:` output block:

**A. Add `ducklake` to the `extensions` list:**

```yaml
      extensions:
        - parquet
        - ducklake
```

**B. Add an `attach` stanza** (after `extensions`):

```yaml
      attach:
        - path: "ducklake:{{ env_var('POSTGRES_CATALOG_URL', 'postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake') }}"
          alias: lake
          read_only: false
          config:
            data_path: "{{ env_var('DUCKLAKE_DATA_PATH', '/app/data/lake/') }}"
```

> The exact key names (`attach`, `path`, `alias`, `read_only`, `config`,
> `data_path`) must match the `dbt-duckdb` docs for the attach stanza. At the time
> of writing, `dbt-duckdb>=1.9` supports this syntax — verify against the changelog
> if the extension fails to load. The `is_ducklake: true` flag is NOT needed for
> local Postgres paths (only for MotherDuck — confirmed in upstream research).

### Why

Satisfies AC 9, 10, 11. The `ducklake` extension must be in the `extensions` list
so `dbt-duckdb` installs and loads it at connection time. The `attach` stanza makes
the catalog available as `lake` for future DuckLake-managed model queries without
any further profiles change (Spec 003).

### Test facility

```bash
cd dbt/data_platform
uv run --project ../.. dbt parse --profiles-dir .
# Must exit 0. dbt parse does NOT open a DB connection — safe to run without
# the Postgres catalog running (confirmed in upstream research / spec open question 7).
```

This will FAIL before the change if the `ducklake` extension keyword is malformed
(dbt-duckdb validates the profiles structure at parse time). It should PASS even
with no live Postgres, because `dbt parse` only builds the manifest from SQL files.

### Dependencies

Step 1 (DuckDB >=1.5.2 in the Python environment ensures `dbt-duckdb` can load the
`ducklake` extension).

### Guardrails / self-review checkpoint

- Run `dbt parse` — must be green.
- Confirm the YAML indentation is consistent (2-space, matching the file's existing
  style).
- Confirm the `path` value uses `ducklake:postgresql://...` prefix, not a bare
  Postgres URL — that prefix is what tells DuckDB to use the DuckLake catalog
  adapter.
- Do NOT change the `path: "{{ env_var('DUCKDB_PATH', ...) }}"` line — the warehouse
  target must remain `warehouse.duckdb` for existing models (spec §5.1).

---

## Step 9 — Update `CLAUDE.md`

### What changes

**File:** `CLAUDE.md`

Add three bullet points to the "Non-obvious constraints" section (under the existing
constraint bullets, before the football-data section):

```markdown
- **DuckDB UI must open `warehouse.duckdb` READ_ONLY.** The `duckdb-ui` container
  attaches `warehouse.duckdb` with `(READ_ONLY)` to preserve the single-writer
  invariant. Any future service or notebook that browses the warehouse must do the
  same. The DuckLake catalog Postgres service is independent and does not touch the
  `.duckdb` file.

- **DuckLake adoption is incremental: catalog in Spec 002, model migration in
  Spec 003.** The `ducklake-catalog` Postgres service and the `ducklake` dbt
  extension are wired in Spec 002, but no existing silver/gold models are migrated.
  The catalog is available as the `lake` attachment in dbt sessions. Do not move
  models to DuckLake until Spec 003 lands.

- **DuckDB runtime >=1.5.2 required for the DuckLake 1.0 extension.** The Python
  package in `pyproject.toml` is pinned `>=1.5.2`; the `duckdb/duckdb:latest`
  Docker image must also satisfy this (it does as of 2026-06-29). If the image is
  pinned to an older tag, bump it before enabling the `ducklake` extension.
```

### Why

CLAUDE.md is living documentation of non-obvious constraints (CLAUDE.md §Maintaining
this file). All three bullet points are exactly the category of hard-won constraint
that a future agent would otherwise rediscover.

### Dependencies

All prior steps complete (document what was built, not what is planned).

### Guardrails / self-review checkpoint

- Keep bullets concise — link to the spec for full rationale rather than
  restating it.
- Ensure the DuckDB UI bullet is adjacent to the existing single-writer bullet for
  discoverability.

---

## Convention audit

| Change type | Convention in CLAUDE.md / ARCHITECTURE.md | Gap? |
|---|---|---|
| `pyproject.toml` dependency bump | CLAUDE.md mentions Python is pinned `>=3.12,<3.13`; no explicit convention for bumping lower bounds | No gap — bump is mechanical; `uv lock` is the gate |
| `config.py` new fields | "Add new settings as typed fields" (CLAUDE.md, ARCHITECTURE.md §5) | No gap |
| `.env.example` | "All runtime config flows through config.py … dbt profiles.yml … read `env_var(…)`" implies `.env.example` must document them | No gap |
| `docker-compose.yml` new services | "base is environment-NEUTRAL … no env-specific values in base" (CLAUDE.md) | No gap — credentials in base are dev defaults, consistent with existing pattern |
| `docker-compose.signoz.yml` / `prod.yml` / `remote.yml` overlays | "Overlay merge relies on Compose semantics" (CLAUDE.md); only add env-specific things in overlays | No gap |
| `profiles.yml` extensions + attach | No explicit convention for dbt profiles extension additions | Minor gap — no existing guidance on `attach` stanza format. Mitigated by `dbt parse` test gate. |
| `CLAUDE.md` additions | "Treat CLAUDE.md as living documentation … add in same commit" (CLAUDE.md) | No gap |

**One missing convention identified:** There is no documented convention for testing
compose changes locally (beyond `docker compose config`). The test facilities in
Steps 4–7 provide this; the implementor should add a brief note in CLAUDE.md
(covered by Step 9) if the pattern is non-obvious.

---

## Traceability closure

| Spec scenario / AC | Plan step(s) |
|---|---|
| S1 — Developer starts stack, browses UI | Steps 4, 5, 8 |
| S2 — Developer queries warehouse while ingestion runs (READ_ONLY) | Step 4 (AC 17); Step 9 (documents constraint) |
| S3 — Developer uses UI on prod overlay | Step 6 |
| S4 — Developer uses UI on remote overlay | Step 7 |
| S5 — dbt connects to DuckLake catalog | Steps 4 (catalog service), 8 (profiles) |
| S6 — New config settings available at runtime | Steps 2, 3 |
| S7 — DuckDB version constraint satisfied | Step 1 |
| AC 1 (ducklake-catalog service, postgres:16, named volume) | Step 4 |
| AC 2 (duckdb-ui service, port 4213, ./data:ro) | Step 4 |
| AC 3 (startup command: ui extension, ATTACH warehouse, ATTACH lake, start_ui) | Step 4 |
| AC 4 (duckdb-ui depends_on ducklake-catalog healthy) | Step 4 |
| AC 5 (signoz overlay: duckdb-ui joins signoz-net) | Step 5 |
| AC 6 (prod overlay: duckdb-ui entry) | Step 6 |
| AC 7 (remote overlay: duckdb-ui joins sports-quant) | Step 7 |
| AC 8 (any overlay brings up duckdb-ui on :4213) | Steps 4–7 together |
| AC 9 (profiles.yml: ducklake in extensions) | Step 8 |
| AC 10 (profiles.yml: attach stanza for lake) | Step 8 |
| AC 11 (dbt parse succeeds with new profiles) | Step 8 (test facility) |
| AC 12 (config.py: postgres_catalog_url) | Step 2 |
| AC 13 (config.py: ducklake_data_path) | Step 2 |
| AC 14 (.env.example: DuckLake section) | Step 3 |
| AC 15 (pyproject.toml: duckdb>=1.2.0) | Step 1 |
| AC 16 (pyproject.toml: comment about runtime >=1.5.2) | Step 1 |
| AC 17 (duckdb-ui opens warehouse READ_ONLY) | Step 4 |
| AC 18 (no new service opens warehouse read-write) | Steps 4–7 all respect this; Step 9 documents it |
| AC 19 (.env.example: DUCKLAKE_DATA_PATH note) | Step 3 |

All 19 ACs and all 7 scenarios are covered. No AC is left unmapped.

---

## Red tests (tests that should be written)

These tests should be added under `tests/` to prove the infrastructure contracts
hold. They are "red before implementation" — they will fail before the relevant step
is applied.

### T1 — Config fields exist and have correct defaults (Step 2)

**File:** `tests/test_config_ducklake.py`

```python
"""Verify DuckLake config fields have correct defaults (Spec 002)."""
from data_platform.config import Settings


def test_postgres_catalog_url_default():
    s = Settings()
    assert s.postgres_catalog_url == (
        "postgresql://ducklake:ducklake@ducklake-catalog:5432/ducklake"
    )


def test_ducklake_data_path_default():
    from pathlib import Path
    s = Settings()
    assert s.ducklake_data_path == Path("data/lake")


def test_postgres_catalog_url_env_override(monkeypatch):
    monkeypatch.setenv("POSTGRES_CATALOG_URL", "postgresql://x:y@host/db")
    s = Settings()
    assert s.postgres_catalog_url == "postgresql://x:y@host/db"
```

Status before Step 2: **RED** (AttributeError).
Status after Step 2: **GREEN**.

### T2 — DuckDB version meets minimum (Step 1)

**File:** `tests/test_duckdb_version.py`

```python
"""Verify DuckDB runtime version satisfies the DuckLake 1.0 minimum (Spec 002)."""
import duckdb
from packaging.version import Version


def test_duckdb_version_meets_ducklake_minimum():
    # DuckLake 1.0 requires >= 1.5.2 per spec 002 §5.4
    assert Version(duckdb.__version__) >= Version("1.5.2"), (
        f"duckdb {duckdb.__version__} is too old; DuckLake 1.0 requires >=1.5.2"
    )
```

> Note: add `packaging` to `[dependency-groups] dev` if not already present.
> Check with `uv run python -c "import packaging"` before adding.

Status before Step 1 (with current `duckdb>=1.1` resolving to e.g. 1.1.x): **RED**.
Status after Step 1: **GREEN** (assuming `uv lock` resolved to >=1.5.2).

---

*End of Plan 002*
