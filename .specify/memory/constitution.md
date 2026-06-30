<!--
SYNC IMPACT REPORT
==================
Version change: 1.0.0 → 1.1.0  (MINOR — five project-specific principles added; two
                sections materially expanded with project constraints/gates)
Bump rationale: Bootstrap tailored the generic Dark Factory seed to this repository.
                Framework principles I–V are preserved verbatim; project principles
                VI–X are added; the "Additional Constraints" section is introduced and
                "Development Workflow & Quality Gates" is expanded with named, evidenced
                gates. Additive, backward-compatible governance → MINOR.

Modified principles:
  - (none renamed/removed) — I–V preserved verbatim.
Added principles:
  - VI.   Medallion Layering & Downstream-Only Dependencies
  - VII.  The Network Edge Lives Only in Bronze
  - VIII. Validate at the Boundary — Pydantic → Pandera → dbt tests
  - IX.   dbt Owns the Catalog; Python Reads Parquet Files
  - X.    definitions.py Is the Only Composition Root
Added sections:
  - "Additional Constraints (Technology Stack & Coding Standards)"
Expanded sections:
  - "Development Workflow & Quality Gates" — added pre-commit / pytest / dbt-test gates.

Templates requiring updates:
  - ✅ .specify/templates/plan-template.md  — no edit needed; its "Constitution Check"
        gate (line 43: "[Gates determined based on constitution file]") references the
        constitution dynamically and derives gates at plan time.
  - ✅ .specify/templates/spec-template.md  — no edit needed; it instructs pulling
        principles from .specify/memory/constitution.md dynamically (lines 130-137).
  - ✅ .specify/templates/tasks-template.md — no edit needed; contains no constitution
        references to keep in sync.

Deferred follow-ups (gaps surfaced by bootstrap analysis — NOT yet rules):
  - TODO(CI): No CI/CD pipeline (no .github/workflows, GitLab CI). Gates run only locally
        via pre-commit + at ingest time; nothing enforces test-on-push / merge-gating.
  - TODO(TYPECHECK): No static type-checker (mypy/pyright) configured; only ruff F catches
        undefined names. No type-discipline rule asserted until a checker is adopted.
  - TODO(COVERAGE): No coverage threshold / reporting configured; pytest runs un-gated on %.
  - TODO(DEPSCAN): No dependency/security scanning (pip-audit, bandit, safety);
        detect-private-key (pre-commit) is the only secret guard.
-->

# Data Platform Constitution

The canonical governance source for this project. Every phase of the workflow — `specification`,
`plan`, `tasks`, `implementor`, and the `speckit-*` gate tools — reads and enforces this file.
It is **kept continuously updated** as the project evolves: the `self-learn` skill routes durable,
project-wide rules here, and `speckit-constitution` keeps dependent templates in sync.

This is a medallion (bronze → silver → gold → publish) data-ingestion platform: Dagster orchestrates
Python assets, dbt-duckdb transforms and tests on a DuckLake (PostgreSQL-backed) catalog, every layer
is persisted as Parquet, and work is traced via OpenTelemetry into a self-hosted SigNoz. Runtime
guidance lives in `CLAUDE.md`; structure in `ARCHITECTURE.md`; the data model in `ERD.md`.

## Core Principles

### I. No Backward Compatibility
Never implement backward compatibility. Never refactor code to serve both its new objective and a
legacy one — remove the legacy path. A change replaces; it does not accrete. This applies to this
workflow's own evolution as much as to product code.

### II. No Reward Hacking (NON-NEGOTIABLE)
Outside test fixtures, never use placeholders, mocks, hardcoded values, or stub implementations to
make work *appear* done. Never suppress, bypass, default-away, or add permissive variants to quality
gates, errors, deprecation warnings, or test failures. Never skip a failing task silently or
implement a fallback/temporary strategy to meet a requirement. Never bypass gates with `--skip` or
`--no-verify`. If a gate fails, fix the cause or stop and report it.

**Constraint-bypass requires escalation, never self-approval.** Weakening a constraint to make work
pass — adding a lint-ignore (`# noqa`, a ruff ignore entry), softening or skipping pre-commit,
loosening a hook, narrowing/`xfail`-ing a test, or pushing files that shouldn't be pushed — must be
escalated to the orchestrator (`feature`'s blocker protocol) or the user and explicitly approved. No
agent, implementer, or reviewer may approve such a change itself; a review that finds one fails it.

### III. Test-First (NON-NEGOTIABLE)
TDD is mandatory: a test that can genuinely fail is written and seen red before the code exists;
red → green → refactor. Tests must be real and useful — narrowing a test to pass is reward hacking
(see II). Each unit of behaviour maps to an objectively pass/fail check using the right facility
(pytest, dbt tests, Pydantic/Pandera validation, artifact assertions).

### IV. Honesty & Permission to Fail
Report outcomes faithfully: if tests fail, say so with the output; if a step was skipped, say so.
You have explicit permission to say "I don't know" or "I'm not confident" when information is
unavailable, verification is impossible, or multiple answers seem equally valid. Never bypass or
change a task that fails without the user's permission.

### V. Surface Contradictions & Beneficial Changes
Always raise contradictions and knock-on effects implied by the objective that the user has not
mentioned. Always include beneficial, objective-linked changes the user has not raised. Do not paper
over conflicts between a requirement and an existing principle — surface them.

### VI. Medallion Layering & Downstream-Only Dependencies
Code MUST be organised as the bronze → silver → gold → publish medallion, and dependencies MUST flow
strictly downstream — a layer never imports or reads from a layer above it. Asset modules MUST NOT
import each other; inter-asset ordering is expressed only through Dagster `deps=[AssetKey(...)]`,
never Python imports. `models/`, `config.py`, and `otel.py` are leaf modules and MUST NOT import from
`assets/` or `definitions.py`. *Evidence:* `ARCHITECTURE.md` §3 (layering table + "Module dependency
direction"); verified in code — `assets/bronze.py`, `assets/football_main.py`, `assets/gold.py`,
`assets/matchbook_conform.py` import only config/models/otel/helpers and express edges via
`deps=[AssetKey(...)]`; `models/schemas.py`, `models/validation.py`, `config.py` import no asset.

### VII. The Network Edge Lives Only in Bronze
Outbound network I/O (HTTP / `requests`) MUST be confined to the bronze ingest assets
(`assets/bronze.py`, `assets/football_*.py`, `assets/espn.py`, `assets/matchbook_*.py`) and their
per-source helper packages (`football/`, `espn/`, `matchbook/`). No silver, gold, publish, `models/`,
or `config` module may make outbound calls. A new external source is a new bronze asset + helper
package — never a network call bolted onto a downstream layer. *Evidence:* only `assets/bronze.py:9`,
`football/http_client.py:26`, `espn/http_client.py:23`, `matchbook/ingest.py:32` import `requests`;
no other `src/data_platform` module does. `ARCHITECTURE.md` §3 rule 1.

### VIII. Validate at the Boundary — Pydantic → Pandera → dbt tests
Every record entering the system MUST be parsed by a Pydantic v2 model in `models/schemas.py`; the
assembled frame MUST pass a Pandera schema in `models/validation.py` before it is written to Parquet;
warehouse-level invariants MUST be asserted by dbt tests. These three complementary gates run in that
order. Faithful-to-source bronze: a nested source MUST persist the complete original payload verbatim
(e.g. a `raw_event` column) so a future field is recoverable without a re-fetch. *Evidence:*
`assets/bronze.py:34` (`User.model_validate` per record) → `:40` (`bronze_users_schema.validate`);
`models/validation.py:12-113`; dbt `not_null`/`unique`/`relationships` tests in
`models/silver/_schema.yml` and `models/silver/canonical/_schema.yml`; `raw_event` preservation in
`espn/ingest.py` and `models/schemas.py`.

### IX. dbt Owns the Catalog; Python Reads Parquet Files
dbt is the single writer to the DuckLake/DuckDB warehouse. Python assets and notebooks MUST read the
Parquet artifacts dbt produces (via `read_parquet(...)`), never catalog tables — **not even
read-only**. To expose canonical/warehouse data to a Python asset, add a dbt external Parquet export
and read the file. This is the structural expression of the documented single-writer constraint.
*Evidence:* `ARCHITECTURE.md` §3 rule 3; `assets/gold.py:30` reads via `read_parquet` (no catalog
table); `gold/users_by_city_export.sql` materialized `external` → Parquet; `CLAUDE.md` "Non-obvious
constraints" (DuckDB single-writer; "Python assets must NOT open a DuckLake connection — even
read-only").

### X. definitions.py Is the Only Composition Root
`definitions.py` MUST contain only imports and the `Definitions(...)` assembly (assets, jobs,
schedules, resources) — no ingest, transform, or validation logic. Asset modules declare WHAT they
are; `definitions.py` decides HOW they fit together. Heavy/standalone sources MUST get their own job
and be excluded from `AssetSelection.all()`-based jobs (e.g. `medallion_job` subtracts the
football/espn/matchbook assets so the demo job and daily schedule don't trigger a multi-hundred-file
backfill). *Evidence:* `definitions.py:14-22` (imports only), `:143-173` (Definitions assembly),
`:31-96` (`medallion_job` subtracts heavy source assets); `ARCHITECTURE.md` §3 rule 4; `CLAUDE.md`
note on `AssetSelection.all()` sweeping in football assets.

## Security Requirements

- Never commit, echo, print, or log API keys, tokens, passwords, or secrets in command output or
  transcripts.
- Verify environment variables by presence, not by printing their value.
- If a sensitive value must be displayed, mask it (show first/last 4 characters only).

## Additional Constraints (Technology Stack & Coding Standards)

These constraints are derived from the repository's own configuration and idioms. They are binding;
changing one is a governance change (see Governance), not a casual refactor.

- **Python is pinned `>=3.12,<3.13`.** Do not raise the floor or cross to 3.13 — dbt/mashumaro fails
  to build serializers there. *Evidence:* `.python-version`, `pyproject.toml` `requires-python`.
- **`uv` is the package manager/runtime; `uv.lock` is authoritative.** Containers use
  `uv sync --frozen`. `[tool.uv] package = false` — code is imported from `src/` via `PYTHONPATH=src`,
  not built as a wheel; the container venv lives at `/opt/venv` so the `./src` bind-mount doesn't
  shadow dependencies. Use the repo's own tooling — no swaps. *Evidence:* `pyproject.toml:50`,
  `Dockerfile:8-25`, `docker-compose.yml`.
- **Lint/format is ruff** (config in `pyproject.toml`): `select = E,W,F,I,UP,B,C4,SIM`; line-length
  100; target `py312`. Let `ruff format` decide layout — do not hand-format. Scope ruff to the files
  you changed (the pre-commit hook runs on staged files); `pre-commit run --all-files` is the
  full-repo gate. A `# noqa` MUST cite the design reason and is a last resort, never a blanket
  suppress (and is subject to Principle II's escalation rule). *Evidence:* `pyproject.toml:64-71`,
  `.pre-commit-config.yaml`, `football/ingest.py:197` (`# noqa: BLE001 — per-file isolation is the
  design`).
- **Modern typing.** Use PEP 604 unions (`X | None`), never `typing.Optional`; type-annotate public
  functions including return types; use `pathlib.Path` for filesystem paths, never `os.path`/strings.
  Module and public-function docstrings are expected. *Evidence:* `models/schemas.py:222,265`;
  `football/ingest.py:46-48`; `config.py:9` + its path properties.
- **No `from __future__ import annotations` in Dagster asset modules.** Dagster introspects runtime
  annotations; stringized annotations raise `DagsterInvalidDefinitionError`. Other modules MAY use
  it. This is guarded by a test. *Evidence:* `tests/test_no_future_annotations.py`;
  `assets/football_main.py:9`; `config.py:7` / `definitions.py:3` / `otel.py:8` use it freely.
- **Validate at boundaries with Pydantic v2** (`BaseModel` + `field_validator`) — never plain
  dataclasses or `NamedTuple` for external/API payloads. Dataclasses are for internal value objects
  only (e.g. `FileResult`, `IngestionReport`). Frame contracts go through Pandera (open
  `strict=False` for wide historical sources; `strict=True`/closed where the schema is fixed).
  *Evidence:* `models/schemas.py`, `models/validation.py`, `football/ingest.py:52-71`.
- **All runtime config flows through the single `Settings` (pydantic-settings) object in
  `config.py`** — never ad-hoc `os.getenv`. dbt reads the same values via `env_var(...)` in
  `profiles.yml` / the gold external model; Python, Docker, and dbt MUST agree on
  `DATA_DIR`/`DUCKDB_PATH`/`POSTGRES_CATALOG_URL`. New config is a new typed field on `Settings`.
  *Evidence:* `config.py:14-129`, dbt `profiles.yml` `env_var` usage, `ARCHITECTURE.md` §5.
- **Parquet writes MUST be atomic** (write to a `.tmp` sibling then `Path.replace`) so an interrupted
  run leaves no partial/empty artifact. **Per-source-file ingest failures MUST be isolated:** the
  unit-level ingest returns a failure count (no partial Parquet written for a failed file) and the
  outer runner re-raises at the end, so run status reflects failures while valid files persist.
  *Evidence:* `football/ingest.py:149-203`; `CLAUDE.md` per-file failure-isolation notes;
  `espn`/`matchbook` ingest mirror this.
- **Telemetry is best-effort.** `configure_telemetry()` is idempotent and runs once at code-location
  import; assets open spans via `get_tracer()` and never configure the provider themselves; a missing
  collector never blocks the pipeline. *Evidence:* `otel.py:25-56`, `definitions.py:29`.

## Development Workflow & Quality Gates

- **Version control:** Conventional Commits (`feat|fix|refactor|build|ci|chore|docs|style|perf|test`).
  Commit atomically at the logical conclusion of a unit of work to checkpoint known-good states.
  Start work from `git status` / `git diff` / `git log`. Never `git push`, `git checkout`,
  `git switch`, `git reset --hard`, `git clean`, `git restore`, or `rm` as part of automated work.
  Never run repo-wide search/replace scripts (`sed -i`, `perl -pi -e`, `python -c`).
- **Tooling:** use the repo's own package manager/runtime (`uv`) — no swaps.
- **Gates as defined:** quality gates and tests are run as written and must pass on their own terms
  (see Principle II). Prefer a deterministic script/linter over pure-AI judgement wherever the thing
  being checked is mechanical.
- **pre-commit gate** (install once per clone via `uv run pre-commit install`): ruff lint `--fix`,
  ruff-format, plus `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`,
  `check-added-large-files`, `check-merge-conflict`, `detect-private-key`. `uv run pre-commit run
  --all-files` is the full-repo gate and MUST stay green. *Evidence:* `.pre-commit-config.yaml`.
- **pytest gate** (pure-Python logic): tests live under `tests/` mirroring `src/data_platform/`,
  importlib mode, `pythonpath=["src"]`, with unique test basenames (no `__init__.py` in `tests/`).
  Run `PYTHONPATH=src uv run pytest`. pytest is a local/CI gate, NOT part of the ruff pre-commit hook.
  *Evidence:* `pyproject.toml:56-62`, `tests/conftest.py`.
- **dbt test gate:** warehouse correctness is asserted inline via `dbt build` (`not_null`, `unique`,
  `relationships`, and singular tests). `dbt parse` MUST run before importing `definitions` / starting
  Dagster (the manifest is read at import time). *Evidence:* dbt `models/**/_schema.yml`, `CLAUDE.md`
  dbt-parse note, the compose `dbt parse`-before-service-start command.

## Governance

This constitution supersedes other practices where they conflict. Amendments are made by updating
this file (via `self-learn` or `speckit-constitution`), which must also propagate to dependent
templates (`spec-template.md`, `plan-template.md`, `tasks-template.md`). All phases verify compliance;
complexity must be justified against these principles. Project-specific principles (VI–X) and the
constraints/gates above are evidenced against the codebase — when the code they cite changes, amend
the cited evidence in the same change. Version bumps follow semver: MAJOR for incompatible
governance/principle removals or redefinitions, MINOR for added or materially expanded
principles/sections, PATCH for clarifications. Runtime development guidance lives in `CLAUDE.md`
(with `ARCHITECTURE.md` for structure and `ERD.md` for the data model).

**Version**: 1.1.0 | **Ratified**: 2026-06-30 | **Last Amended**: 2026-06-30
