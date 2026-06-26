# TDD & guardrails (in this repo's setup)

Phases 3–4 of the plan skill. How to turn BDD scenarios into a real red/green loop **given the testing facilities this repo actually has**, and how to register the guardrails that protect the change.

## The honest starting point

`CLAUDE.md` states plainly: **"There is no Python unit-test suite; data correctness is asserted by dbt tests (run inline via `dbt build`) plus Pydantic/Pandera validation at ingest."**

So "red/green TDD" here is **not** one uniform pytest cycle. It's a per-unit choice of the right falsifiable check. Don't pretend a pytest suite exists. Pick the facility that fits the unit, and where pure-Python logic genuinely needs unit tests, **establishing the pytest harness is a planned setup step, not an assumption** (see *No test suite yet*).

## Choosing the test facility per unit

| Unit kind | Facility | Red (fails first) | Green (passes after) |
|-----------|----------|-------------------|----------------------|
| Pure-Python function/logic (parsing, mapping, pure transforms) | **pytest** | Write the test; it fails because the function doesn't exist / returns wrong value | Implement; `uv run pytest <path>` passes |
| Data entering the system, per record | **Pydantic** (`models/schemas.py`) | A test feeding a bad record expects a `ValidationError` that isn't raised yet | Add/extend the model; the invalid record is rejected, valid one coerced |
| DataFrame contract, per frame | **Pandera** (`models/validation.py`) | A frame violating the schema isn't caught yet | Add the schema check; violation raises, conforming frame passes |
| Warehouse transform / aggregate | **dbt test** run via `dbt build` | Add the model + its schema/data tests; `dbt build --select <model>` fails (model missing or test red) | Implement the model SQL; `dbt build --select <model>` green (model builds + tests pass) |
| End-to-end produced artifact | **artifact assertion** | Assert the expected Parquet/output exists and conforms — fails before the pipeline step exists | Run the asset/job; the file is produced and conforms |

Rules for writing the failing test:
- **It must be able to fail.** Run it and *see red for the right reason* before implementing. A test that passes against no implementation is a reward-hack — the self-review will reject it.
- **Assert the observable outcome from the spec scenario**, not the mechanism (mirror the spec's BDD `Then`).
- **One behaviour per test.** Cover happy path, each rule-driven variation, and each failure mode as its own check.
- Don't weaken a test to make it pass. If green is hard, fix the code, not the assertion.

## The red/green/refactor loop, per step

1. **Red** — write the test for the step's unit; run it; confirm it fails for the intended reason.
2. **Green** — write the minimum implementation; run the test and the step's guardrails (`ruff`, `dbt build` as applicable) until green.
3. **Refactor** — clean up with the tests still green; re-run guardrails. Remove any legacy/duplicate path (no backward-compat scaffolding).
4. Hand to the per-step **self-review** sub-agent (`self-review.md`) before the next step.

## No test suite yet (the harness is a convention to establish)

If Phase 3 produced any **pytest** units, the harness must exist before the first red step. Plan a setup step (S0) that — with user agreement and via the convention audit — does the following, and **only** the following the project will accept:

- Add `pytest` as a dev dependency through the repo's package manager (`uv`, respecting `uv.lock` / the Python pin `>=3.12,<3.13`). Do not swap tooling.
- Establish a `tests/` layout convention and write it down as a rule (Phase 2).
- Decide how tests run in CI/pre-commit and whether `pytest` joins the pre-commit gate. Wire it without weakening existing gates.
- Confirm the harness works with a trivial known-failing then known-passing test before relying on it.

If the user does **not** want a pytest suite, then pure-Python units must be expressed through the existing facilities (push validation into Pydantic/Pandera, push logic into dbt models with dbt tests) — or the unit is flagged as untestable-as-planned in Open Questions. Never silently ship Python logic with no falsifiable check.

## Guardrail register (Phase 4)

For each guardrail, the plan names it **and** how it's verified to be in place. A guardrail not yet in place becomes a setup step that runs before the work it guards.

- **Lint/format** — `uv run ruff check --fix src` + `uv run ruff format src`; enforced on commit via pre-commit. Verify: `uv run pre-commit run --all-files` clean. Fix findings, never blanket-`# noqa`.
- **Pre-commit installed** — `uv run pre-commit install` (once per clone). Verify the hook runs.
- **dbt tests** — every new/changed model has schema and/or data tests; run inline via `dbt build`. Verify: `dbt build --select <model>` green (remember to `dbt parse` first when running outside `dagster dev`).
- **Boundary validation** — Pydantic per record + Pandera per frame for anything entering the system. Verify a bad input is rejected.
- **Idempotency / re-run safety** — re-running the same input doesn't duplicate or corrupt artifacts. Verify by running twice and comparing output.
- **Telemetry** — where the spec implies it, an OTel span is emitted (`otel.py`); absence of a collector is harmless (spans dropped), so don't add a `depends_on` on it.
- **Non-obvious constraints (always)** — single-writer DuckDB (derive Parquet *inside* dbt, read the file in Python; never open `warehouse.duckdb` read-write in a second process); prefixed dbt asset keys (`AssetKey(["gold","users_by_city_export"])`); the bronze→silver link via `BronzeAwareTranslator`; **no `from __future__ import annotations` in Dagster asset modules**; `pathlib.Path` for paths; config via `pydantic-settings` in `config.py`, not ad-hoc `os.getenv`.

Use `code-architecture-review` / `analyze-architecture` to confirm structural guardrails, and `verify` / `run` to confirm the change actually runs, as planned review steps.
