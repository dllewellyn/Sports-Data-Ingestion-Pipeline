# Plan template

This is the **exact output format** for `<feature_dir>/plan.md` (e.g. `specs/003-foo/plan.md`). Copy
the skeleton, keep heading text and order unchanged, and give **every implementation step the same
seven-field shape**. Remove `<!-- guidance -->` comments from the final file; keep headings even when
short (write "None." rather than deleting a section).

The plan lives **inside the feature directory** alongside the spec — there is no separate `plans/`
tree and no NNN-paired filename. The feature's identity is its directory (`.specify/feature.json`),
not frontmatter. The Phase-0/1 design artifacts (`research.md`, `data-model.md`, `contracts/`,
`quickstart.md`) are **sibling files**, referenced from *Project Structure*.

The structural linter is `_shared/spec-helpers/validate-plan.py` and traceability closure is
`_shared/spec-helpers/trace-check.py` — both key off the headings below.

---

```markdown
# Implementation Plan: [FEATURE]

**Feature directory**: `specs/NNN-<slug>/`
**Date**: YYYY-MM-DD
**Spec**: `spec.md`
**Status**: Draft   <!-- Draft | In-review | Approved | In-progress | Done -->

## Summary
<!-- One paragraph: what we're building and the shape of the approach. The primary requirement from the spec + the technical approach from research. -->

## Technical Context
<!-- The concrete technical decisions. Use NEEDS CLARIFICATION only for genuine unknowns to be resolved in research.md. -->

**Language/Version**: [e.g. Python 3.12]
**Primary Dependencies**: [e.g. Dagster, dbt, DuckDB, Pandera]
**Storage**: [e.g. Parquet on local FS, DuckDB]
**Testing**: [e.g. pytest, dbt tests, Pandera/Pydantic]
**Target Platform**: [e.g. local CLI / scheduled job]
**Project Type**: [single project | web | …]
**Performance Goals**: [domain-specific or N/A]
**Constraints**: [domain-specific bounds or N/A]
**Scale/Scope**: [volume/scope]

## Constitution Check
<!-- GATE: must pass before Phase 0 research; RE-CHECK after Phase 1 design. List each relevant constitution principle and how this plan complies. Any violation goes in Complexity Tracking with a justification, or the plan changes. -->

| Principle (constitution) | Compliance in this plan |
|--------------------------|-------------------------|
| II. No Reward Hacking | <how the plan avoids placeholders/mocks/gate-bypass> |
| III. Test-First | <every step has a falsifiable test first> |

## Project Structure
<!-- The design artifacts produced this run, plus the concrete source layout this feature touches. -->

```text
specs/NNN-<slug>/
├── spec.md
├── plan.md           # this file
├── research.md       # Phase 0 — decisions/rationale/alternatives for each unknown
├── data-model.md     # Phase 1 — entities, fields, relationships, validation rules
├── contracts/        # Phase 1 — interface/schema contracts (if any)
├── quickstart.md     # Phase 1 — runnable validation scenarios
└── tasks.md          # Phase 2 — produced later by the `tasks` skill, NOT here
```

**Source layout touched**: [real paths this feature adds/changes, e.g. `src/ingestion/…`, `models/silver/…`]

## Skills to use
<!-- Phase 1 skill discovery: which existing skills accelerate which work, and any missing-skill gaps. -->

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| <e.g. warehouse model + tests> | <skill name> | available |
| <e.g. create data ingestion pipeline> | <skill name or "—"> | MISSING — propose creating before relying on it |

## Convention & rule audit (resolved before implementation)
<!-- HARD GATE (Phase 2). Every artifact type this plan touches, its governing convention, and status. No step below may depend on a row still marked "gap". -->

| Artifact type | Governing convention | Status |
|---------------|----------------------|--------|
| <e.g. new Python ingestion module> | <constitution / CLAUDE.md / a new rule> | exists / created this run / **gap — must close first** |
| <e.g. pytest unit tests> | <test-harness convention> | <e.g. created this run> |

## Testable units (BDD → tests)
<!-- Phase 3. Each spec scenario/AC → the unit(s) that satisfy it → the test facility and the failing-first assertion. -->

| Unit | Spec trace (scenario / FR / SC) | Test facility | Failing-first assertion |
|------|----------------------------------|---------------|-------------------------|
| <behaviour> | Scenario "…" / FR-001 / SC-001 | pytest \| dbt test \| Pandera \| Pydantic \| artifact | <what must fail before, pass after> |

## Guardrail register
<!-- Phase 4. The gates protecting this change and how each is verified in place. A guardrail not yet in place becomes a setup step in Implementation Steps that runs before the work it guards. -->

| Guardrail | How verified in place | Covered by step |
|-----------|------------------------|-----------------|
| ruff check + format (pre-commit) | `uv run pre-commit run --all-files` clean | S0 |
| dbt tests run via `dbt build` | <models + tests present> | S… |
| Boundary validation (Pydantic/Pandera) | <contract> | S… |
| Idempotency / re-run safety | <how proven> | S… |
| Constitution principles respected | II No-reward-hacking · III Test-first · I No-backward-compat | all |

## Implementation Steps
<!-- Phase 5. Ordered, dependency-respecting. EVERY step uses the shape below. Setup steps (harness, conventions, guardrails) come first as S0, S1, … -->

### Step S0 — <setup: e.g. establish pytest harness / install pre-commit>
- **Goal:** <what this step achieves>
- **Spec trace:** <scenario / FR / SC, or "setup — enables S2–S4">
- **Red (failing test first):** <the test to write and watch fail>
- **Implementation:** <minimum to make it pass>
- **Green criterion:** <exact command(s) and the result that means done>
- **Guardrails to satisfy:** <from the guardrail register>
- **Self-review checkpoint:** <what the independent review sub-agent will confirm — see references/self-review.md>

### Step S1 — <next>
- **Goal:** …
- **Spec trace:** …
- **Red (failing test first):** …
- **Implementation:** …
- **Green criterion:** …
- **Guardrails to satisfy:** …
- **Self-review checkpoint:** …

<!-- repeat for every step -->

## Sequencing & dependencies
<!-- The order and why. Call out edges driven by repo gotchas. A short list or diagram. -->

## Complexity Tracking
<!-- Fill ONLY if Constitution Check has violations that must be justified; otherwise write "None." -->

| Violation | Why needed | Simpler alternative rejected because |
|-----------|------------|--------------------------------------|
| … | … | … |

## Assumptions
<!-- Everything taken as true to write this plan that wasn't confirmed. Visible so it can be challenged. -->

## Open Questions
<!-- Anything unresolved. Label blockers **BLOCKER**. If empty, write "None." -->

## Traceability
<!-- Prove coverage both ways: every spec scenario/FR/SC is implemented by a step, and every step traces to the spec. -->

| Spec scenario / FR / SC | Unit(s) | Step(s) | Guardrail(s) |
|-------------------------|---------|---------|--------------|
| Scenario "…" / FR-001 | <unit> | S2 | dbt test, ruff |
```
