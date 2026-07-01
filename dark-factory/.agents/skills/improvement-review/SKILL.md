---
name: improvement-review
description: Evaluate a just-landed changeset for forward-looking improvements — software-architecture quality, reuse potential, and repackaging opportunities that make code more reusable — and for every opportunity enumerate its ripple set: the coupled skills, ARCHITECTURE.md / ERD.md diagrams, CLAUDE.md constraints, dbt models and docs that must change with it. Propose-only and approval-gated; genuine refactors route back through plan→implementor as a new change. May legitimately find nothing. USE WHEN an implementation has just completed and you want to assess architecture/reuse/repackaging upside — "evaluate the changeset", "what should we refactor / extract / generalise", "improvement review" — or run /improvement-review.
---

# Improvement Review (the post-implementation evaluator)

The job of this skill is to look at a changeset that **just landed** and ask the
forward-looking question the build itself didn't: *now that this works, is it in
the right shape?* Specifically, across three lenses —

- **Software-architecture quality** — is the new code in the best home, cohesive,
  loosely coupled, and respecting the medallion data-flow — beyond merely *legal*?
- **Reuse potential** — did the change duplicate something (inside the diff or
  against existing code) that should be a single shared thing?
- **Repackaging / generalisation** — is a one-off now wanted generally, worth
  extracting into a reusable module (or flagging as a candidate skill)?

…and — the part that makes this skill distinctive — for **every** opportunity it
proposes, it enumerates the **ripple set**: the other artifacts coupled to that
change that must move *with* it. If the proposal is "refactor the data-flow" and
the repo has a data-flow skill and an `ARCHITECTURE.md` diagram that describes the
data-flow, both of those are part of the change, not afterthoughts. A proposal
without its complete ripple set is not finished.

This is **evaluation, not refactoring**, and it is **propose-only**. It never edits
the code that just landed. Each accepted opportunity becomes a new, properly-specced
change routed back through `plan` → `implementor` (with its ripple set as scope), so
the refactor gets the same tests/review/commit discipline as any other work.

**Finding nothing is a valid, common outcome.** A focused changeset is often
already well-placed, non-duplicative, and appropriately scoped. Do not manufacture
opportunities to look productive — speculative abstraction is the opposite of an
improvement, and it pollutes trust in the review.

## When to use

- An implementation just finished and you want the architecture/reuse/repackaging
  upside assessed before moving on. (`implementor` proposes this hand-off; `feature`
  runs it as a phase.)
- The user says "evaluate the changeset", "what should we refactor / extract /
  generalise here", "improvement review", or runs `/improvement-review`.
- After landing a new data source, asset, or dbt model and you want to know what's
  now duplicated or worth promoting to shared code.

Do **not** use it as a correctness/quality gate (that's the build's own tests +
reviews), nor for a one-line fix where there is nothing structural to evaluate.

## Relationship to the neighbouring skills (read this — the boundaries are sharp)

- **`code-architecture-review`** asks *"is this **legal**?"* — does the code conform
  to the rules already written in `ARCHITECTURE.md` (single network edge, layering,
  dbt owns the warehouse, …). **improvement-review** asks *"could this be **better**?"*
  — a fully-conformant change can still have a better home, a duplicated helper, or
  an extractable module. Run `code-architecture-review` for conformance; this for
  upside. (If you find an outright violation, that's a code-architecture-review
  finding — note it and point there; don't relabel it as an "improvement".)
- **`self-learn`** codifies **process / institutional knowledge** (a gotcha, a
  command, a convention) into `CLAUDE.md` or skills. **improvement-review** improves
  the **product code's structure** and flags which docs/skills must follow. When this
  skill spots a *repeatable procedure* worth becoming a brand-new skill, it **flags**
  it as a candidate and routes the creation to `self-learn` — it does not author
  skills itself.

In short: conformance → `code-architecture-review`; product-code improvement +
ripple → here; process knowledge & skill authoring → `self-learn`.

## Scope

Default to the **changeset that just landed**: uncommitted work plus the commits
this build produced (since the paired plan/spec, or this branch vs the default
branch). Evaluate the whole repo only when the user asks for a broad audit. State
the scope you chose in the first line of the report.

Gather it with the shared **read-only** helper — it resolves the default branch and
merge-base and emits status + log + both diffs in one pass:

```bash
bash .agents/skills/_shared/git-helpers/bash/git-changeset.sh
# --stat for a compact overview first; --base <ref> to compare against the plan/spec point
```

(PowerShell: `pwsh .agents/skills/_shared/git-helpers/powershell/git-changeset.ps1`.)
It is strictly read-only — never pushes/checks out/resets.

The changeset is the *subject*; the **whole codebase + its skills + its docs** are
the *context* — reuse and ripple analysis both reach across the entire repo.

## The three evaluation lenses

Summarised here; the repo-tuned checklist for each (with worked examples and the
"don't overengineer" caveat) is in
[`references/evaluation-lenses.md`](references/evaluation-lenses.md).

1. **Architecture quality** — placement (better home, even if the current one is
   legal), cohesion/SRP, coupling that could be inverted, and whether transformation
   logic crept into Python that belongs in dbt. Also: did the change alter the
   bronze→silver→gold data-flow in a way a diagram should reflect?
2. **Reuse potential** — duplication introduced *within* the diff, and near-duplicates
   *against existing code* (the new code reimplements an atomic temp-file write, a
   season rollover, an encoding-handling path that already exists). Apply the rule of
   three: only flag extraction when there's a real second caller, not a hypothetical.
3. **Repackaging / generalisation** — a source-specific helper now wanted by other
   sources (promote to a shared module); a reusable contract/IO/registry pattern; or
   a repeatable multi-step procedure that's a **candidate skill** (flag → `self-learn`).

## Ripple / dependency analysis (the heart of this skill)

For **every** opportunity, walk the artifact-dependency map and list each coupled
artifact, *why* it's coupled, and *what* update it needs. The full map and the
read-only search recipe are in
[`references/ripple-analysis.md`](references/ripple-analysis.md). The classes to
check, every time:

- **Dependent code** — importers/consumers of the touched module, dbt `ref()`
  lineage, `definitions.py` prefixed-`AssetKey` deps, tests.
- **`ARCHITECTURE.md`** — package structure, layering rules, the medallion diagram,
  the §6 "add a new data source" guide.
- **`ERD.md`** — if the change touches canonical/link tables or
  `models/silver/canonical/*`, ERD.md is living docs and updates in the same change.
- **`CLAUDE.md`** — *Non-obvious constraints*, *Configuration & telemetry*, commands:
  any constraint/command/config-flow the change invalidates or adds.
- **Skills** — scan `.agents/skills/**` (and `~/.claude`, plugin skills) for any skill
  whose domain the change touches (a data-flow / ingestion skill, `deploy`, the dbt
  guidance). This is the user's load-bearing example: refactor the data-flow → the
  data-flow skill **and** the ARCHITECTURE data-flow diagram both update.
- **dbt / config / infra / other docs** — `schema.yml` tests, `profiles.yml`
  `env_var`, docker-compose overlays, `.env.example`, `pyproject.toml`, notebooks,
  READMEs.

**Completeness rule:** an opportunity whose ripple set hasn't been checked across all
classes is *not ready to present*. If a coupling is uncertain, list it as an open
question — never silently omit it.

## Workflow

### 0. Establish scope and load context (gate)

1. Determine the changeset scope (above) and state it.
2. Read the repo's contract + living-docs in full and keep them open: `CLAUDE.md`
   (*Non-obvious constraints*, *Python conventions*, *Do not overengineer*),
   `ARCHITECTURE.md` (layering, the data-flow diagram, §6), `ERD.md` (data model).
3. If the build came from a feature, read `<feature_dir>/spec.md` and `<feature_dir>/plan.md`
   (resolve `<feature_dir>` via `.specify/feature.json` /
   `_shared/spec-helpers/feature-dir.sh`) — the *intended* design tells you whether
   something is a deliberate choice or an accidental shape worth flagging.
4. Inventory the skills (`.agents/skills/**`, `~/.claude`, plugins) and the doc map so
   the ripple analysis in Phase 3 knows what can be coupled.

### 1. Map what landed

Build the changeset picture the lenses evaluate: new/changed Python modules, new
functions/classes, new dbt models/tests, new Dagster assets/jobs/wiring, new config.
This inventory is the list of subjects you run the three lenses over.

### 2. Evaluate across the three lenses

Apply `references/evaluation-lenses.md` to each subject. Delegate the *breadth*
searches — duplication and near-duplicate detection across the whole repo,
generalisation candidates — to a read-only `Explore`/`general-purpose` sub-agent so
coverage is real, not from memory. Collect candidate opportunities with `path:line`
evidence.

### 3. Ripple analysis per opportunity (the gate)

For each surviving candidate, run the ripple analysis (`references/ripple-analysis.md`)
across all artifact classes — delegating the cross-repo coupling search to a read-only
sub-agent where it's broad. Attach the complete ripple set. Drop or downgrade any
candidate whose ripple cost clearly outweighs its value, and say so.

### 4. Triage (value vs effort vs risk; keep it KISS)

Rank opportunities by value/effort/risk. Apply the project's **"Do not overengineer"**
rule as a hard filter: only keep an extraction/generalisation that is *earned* — a
real second caller (rule of three), a concrete imminent need — not speculative
flexibility. A clean, simple one-off is not a defect. Separate "worth doing now",
"worth doing later", and "intentionally not worth it".

### 5. Report and route (approval-gated)

1. Produce the report using [`references/report-template.md`](references/report-template.md):
   ranked opportunities, each with lens, evidence, the proposed change, its **complete
   ripple set**, a route, and the KISS justification. If nothing is warranted, say so
   plainly — that is a complete, honest result.
2. **Route each accepted opportunity, do not apply it.** Genuine refactors become a
   new change driven through `plan` → `implementor`, **carrying the ripple set as the
   scope** (so the data-flow skill and the ARCHITECTURE diagram are edited in the same
   change as the code, not forgotten). A candidate-for-skill goes to `self-learn`. A
   pure conformance violation goes to `code-architecture-review`.
3. This skill **proposes**; it never edits the just-landed code, never silently edits a
   skill or doc, and never auto-spawns the follow-up build. The user picks what to
   pursue.

## Guardrails

- **Empty is valid; never manufacture.** A well-shaped changeset gets an honest "no
  improvements warranted." Speculative abstraction is a finding *against*, not for.
- **Evidence or it doesn't go in.** Every opportunity cites `path:line`; every ripple
  entry names the coupled artifact and the update it needs.
- **No opportunity without its complete ripple set.** Checking only the code and
  forgetting the coupled skill/diagram/ERD is the failure mode this skill exists to
  prevent. Uncertain couplings are listed as open questions, not omitted.
- **Propose-only — never touch the just-landed code here.** Accepted refactors run
  through `plan` → `implementor` with the ripple set as scope, getting the normal
  test/review/commit discipline. No direct edits, no auto-applied changes.
- **KISS is a hard filter (project rule: "Do not overengineer this project").** Only
  earned reuse/extraction (real second caller, concrete need). Reject speculative
  generality, deep abstractions, and any **backward-compat scaffolding** (replace
  legacy paths; don't make code serve old and new — global design principle).
- **Stay in your lane.** Conformance violations → `code-architecture-review`; new-skill
  authoring → `self-learn`. Reference them; don't duplicate or relabel their work.
- **Respect the repo's serial/non-obvious constraints in every proposal** (CLAUDE.md /
  ARCHITECTURE.md): never propose a second `warehouse.duckdb` writer, transformation in
  Python that belongs in dbt, unprefixed dbt asset keys, `from __future__ import
  annotations` in asset modules, or ad-hoc `os.getenv` over `pydantic-settings`.
- **Surface contradictions & knock-on effects** you spot while evaluating, even when
  they're outside the three lenses.

## References

- [`references/evaluation-lenses.md`](references/evaluation-lenses.md) — the repo-tuned
  checklist for the three lenses (architecture quality, reuse, repackaging), with
  worked examples and the "don't overengineer" caveat per lens.
- [`references/ripple-analysis.md`](references/ripple-analysis.md) — the artifact-
  dependency map (code, ARCHITECTURE.md, ERD.md, CLAUDE.md, skills, dbt/config/docs),
  the read-only search recipe for finding couplings, and the completeness rule.
- [`references/report-template.md`](references/report-template.md) — the exact output
  format: ranked opportunities, evidence, ripple sets, routes, and the empty-result form.
