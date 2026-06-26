# Plan template

This is the **exact output format**. Copy the skeleton into `specs/NNN-<slug>-plan.md` and fill every section. Keep the frontmatter keys and section order unchanged, and give **every step the same shape**. Remove the `<!-- guidance -->` comments from the final file; keep headings even when short (write "None." rather than deleting a section).

`NNN` and `slug` **must match the specification this plan implements** — the plan and spec are a pair (`specs/003-foo-specification.md` ↔ `specs/003-foo-plan.md`).

---

```markdown
---
id: NNN                          # SAME number as the specification this implements
title: <Human-readable plan title>
slug: <kebab-slug>               # SAME slug as the specification
status: draft                    # draft | in-review | approved | in-progress | done
created: YYYY-MM-DD
specification: NNN-<slug>-specification.md   # the spec this plan implements
user_stories: [1, 2]             # carried from the spec frontmatter
---

# <Plan title>

## 1. Summary
<!-- One paragraph: what we're building and the shape of the approach. No step detail yet. -->

## 2. Skills to use
<!-- From Phase 1. Which existing skills accelerate which part of the work, and any missing-skill gaps. -->

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| <e.g. warehouse model + tests> | <skill name> | available |
| <e.g. create data ingestion pipeline> | <skill name or "—"> | MISSING — propose creating before relying on it |

## 3. Convention & rule audit (resolved before implementation)
<!-- From Phase 2 — the HARD GATE. Every artifact type this plan touches, its governing convention, and the status. No step below may depend on a row still marked "gap". -->

| Artifact type | Governing convention | Status |
|---------------|----------------------|--------|
| <e.g. new Python ingestion module> | <CLAUDE.md §… / a new rule> | exists / created this run / **gap — must close first** |
| <e.g. pytest unit tests> | <test-harness convention> | <e.g. created this run: pytest harness + layout rule> |

## 4. Testable units (BDD → tests)
<!-- From Phase 3. Each spec scenario/AC → the unit(s) that satisfy it → the test facility and the failing-first assertion. -->

| Unit | Spec trace (scenario / AC) | Test facility | Failing-first assertion |
|------|----------------------------|---------------|-------------------------|
| <behaviour> | Scenario "…" / AC3 | pytest \| dbt test \| Pandera \| Pydantic \| artifact | <what must fail before, pass after> |

## 5. Guardrail register
<!-- From Phase 4. The gates protecting this change and how each is verified to be in place. A guardrail not yet in place becomes a setup step in §6 that runs before the work it guards. -->

| Guardrail | How verified in place | Covered by step |
|-----------|------------------------|-----------------|
| ruff check + format (pre-commit) | `uv run pre-commit run --all-files` clean | S0 |
| dbt tests run via `dbt build` | <models + tests present> | S… |
| Pydantic/Pandera boundary validation | <contract> | S… |
| Idempotency / re-run safety | <how proven> | S… |
| OTel span emitted | <where> | S… |
| Repo non-obvious constraints respected | single-writer DuckDB · prefixed dbt asset keys · no `from __future__` in asset modules | all |

## 6. Implementation steps
<!-- From Phase 5. Ordered, dependency-respecting. EVERY step uses the shape below. Setup steps (harness, conventions, guardrails) come first as S0, S1, … -->

### Step S0 — <setup: e.g. establish pytest harness / install pre-commit>
- **Goal:** <what this step achieves>
- **Spec trace:** <scenario / AC, or "setup — enables steps S2–S4">
- **Red (failing test first):** <the test to write and watch fail; for setup steps, the check that currently fails>
- **Implementation:** <minimum to make it pass>
- **Green criterion:** <exact command(s) and the result that means done — e.g. `uv run pytest tests/test_x.py` passes; `dbt build --select …` green>
- **Guardrails to satisfy:** <from §5, the ones this step must honour>
- **Self-review checkpoint:** <what the review sub-agent will independently confirm — meets which scenario/AC, test genuinely fails-then-passes, conventions honoured, no reward-hacking. See references/self-review.md>

### Step S1 — <next>
- **Goal:** …
- **Spec trace:** …
- **Red (failing test first):** …
- **Implementation:** …
- **Green criterion:** …
- **Guardrails to satisfy:** …
- **Self-review checkpoint:** …

<!-- repeat for every step -->

## 7. Sequencing & dependencies
<!-- The order and why. Call out edges driven by repo gotchas (bronze→silver→gold; derive Parquet inside dbt then read the file; prefixed dbt asset keys). A short list or diagram. -->

## 8. Assumptions
<!-- Everything taken as true to write this plan that wasn't confirmed. Visible so it can be challenged. -->

## 9. Open questions
<!-- Anything unresolved. Mark blockers. If empty, write "None." -->

## 10. Traceability
<!-- Prove coverage both ways: every spec scenario/AC is implemented by a step, and every step traces to the spec. -->

| Spec scenario / AC | Unit(s) | Step(s) | Guardrail(s) |
|--------------------|---------|---------|--------------|
| Scenario "…" / AC1 | <unit> | S2 | dbt test, ruff |
```
