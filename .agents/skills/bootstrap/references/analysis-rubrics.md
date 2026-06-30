# Bootstrap analysis rubrics

The four fan-out sub-agents (step 2 of `bootstrap`) run **in parallel**, each read-only, each returning
the **same structured schema** so their findings compose into one principle-input payload. Give each
agent the `get-codebase-primer` output as shared context so it does not re-derive the basics.

## Shared output schema (every agent returns exactly this)

```
### Summary
<2-4 sentences: what this dimension looks like in THIS repo>

### Findings
- finding: <one concrete, declarative statement>
  evidence: <file path : line / config key that proves it>
  proposed_rule: <the MUST/SHOULD rule it implies, or "none — descriptive only">
- ...

### Gaps / absences
- <conventions a project like this normally has but this repo lacks — these are NOT rules,
  they are flagged so the constitution doesn't invent a rule with no basis>
```

**Hard requirement:** every `finding` carries `evidence` pointing at a real file/config. A finding with
no evidence is dropped — the independent reviewer (step 4) rejects unsupported principles.

## The four agents

### A. Guard-rails
Find the gates that already protect the code. Look for: `.pre-commit-config.yaml`, CI workflows
(`.github/workflows/`, `.gitlab-ci.yml`, etc.), linter/formatter configs (ruff, eslint, prettier,
black, gofmt…), type-checkers (mypy, tsc, pyright), the test runner and how it's invoked, coverage
thresholds, and any "required checks". Each gate → a *Quality Gates* entry and/or the test-discipline
principle. If there is **no** test harness, say so in Gaps (do not assert a test-first rule the repo
can't currently honour — flag it as a recommended gap instead).

### B. Architecture
Map structure without grading it. Look for: top-level package/module layout, layering (domain/app/
infra, MVC, medallion, etc.), explicit module boundaries, entry points (main, CLI, server, jobs),
and the dominant data/control flow. Findings feed structural principles AND the optional
`ARCHITECTURE.md`. Note the dependency-direction rule the layout implies (e.g. "infra may import
domain, never the reverse") only if the code actually exhibits it.

### C. Software patterns
Identify the frameworks and idioms in play: web/app frameworks, ORM/data-access, async model, DI,
config/secrets handling, notable design patterns, and dependency-management conventions
(lockfiles, pinning). These become technology-stack constraints ("use the repo's own package
manager — no swaps"-style rules, made concrete to this stack).

### D. Coding standards
Extract style and convention: formatter/lint rules actually configured, naming conventions visible
in the code, language/runtime version floors (`pyproject.toml`, `.nvmrc`, `go.mod`, `engines`),
docstring/comment conventions, and import ordering. These feed the *Additional Constraints* section.

## Principle-input payload handed to `speckit-constitution`

After synthesis, collapse the four schemas into this payload and pass it to `speckit-constitution`
(which fills `.specify/memory/constitution.md` and propagates to dependent templates):

```
PROJECT_NAME:        <derived from repo dir / package metadata>
RATIFICATION_DATE:   <today, ISO YYYY-MM-DD>
GUIDANCE_FILE:       AGENTS.md   # the symlinked CLAUDE.md target

PRESERVE_PRINCIPLES: I–V from the seed (No Backward Compatibility, No Reward Hacking, Test-First,
                     Honesty & Permission to Fail, Surface Contradictions) — keep verbatim.

PROJECT_PRINCIPLES:  # project-specific, each MUST cite evidence; 0..N — only what the repo supports
  - name: <e.g. "Layered dependency direction">
    rule: <declarative MUST/SHOULD statement>
    evidence: <file/config>

ADDITIONAL_CONSTRAINTS:  # → Security/Additional Constraints section (from C + D)
  - <stack + coding-standard constraints with evidence>

DEVELOPMENT_WORKFLOW:    # → Quality Gates section (from A)
  - <each existing gate, named, with how it's run>

DEFERRED:                # gaps surfaced (no harness, no CI, etc.) — recorded as TODO, not as rules
  - <gap + why it's deferred>
```

Tell `speckit-constitution` to: amend (not replace) the existing constitution, keep principles I–V,
append `PROJECT_PRINCIPLES`, fill the section content from `ADDITIONAL_CONSTRAINTS`/
`DEVELOPMENT_WORKFLOW`, set the ratification date, bump the version per its own semver rules, propagate
to `spec-template.md`/`plan-template.md`/`tasks-template.md`, and prepend the Sync Impact Report.
`DEFERRED` items become `TODO(<FIELD>)` notes in that report — never fabricated rules.
