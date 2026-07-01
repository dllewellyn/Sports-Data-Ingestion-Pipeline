# Agent Skills

Project-local skills for agentic workflows. Each skill is a directory containing a `SKILL.md` with `name` / `description` frontmatter and a markdown body. Sub-skills are nested directories with their own `SKILL.md`.

## Phased workflow

These skills chain, front-to-back, across the lifecycle of a piece of work. Everything from the spec
onward lives in **one per-feature directory** `specs/NNN-<slug>/` (spec.md, plan.md, tasks.md, design
artifacts), located by every phase via `.specify/feature.json` (`_shared/spec-helpers/feature-dir.sh`).
The spec-kit gate tools (`speckit-clarify`, `speckit-checklist`, `speckit-analyze`, `speckit-converge`)
slot in as gates between the phases.

1. **`investigation`** — discovery. Turn an open question / unknown into evidence-backed conclusions. Proposes the Specification skill on completion. ✅ available
2. **`specification`** — definition. Turn a free-text feature description (and any investigation findings) into an implementable, outcome-focused `specs/NNN-<slug>/spec.md` + `checklists/requirements.md`; writes `.specify/feature.json`. ✅ available
   → gate: **`speckit-clarify`** (resolve underspecified areas) → **`speckit-checklist`** (requirements-quality gate)
3. **`plan`** — build preparation. Turn an approved spec into a guardrailed, test-first `<feature_dir>/plan.md` + design artifacts (research/data-model/contracts/quickstart): Constitution Check, skill discovery, a hard-gate convention audit before coding, BDD→testable-unit decomposition with a red/green loop, and a per-step self-review sub-agent. ✅ available
4. **`tasks`** — decomposition. Turn the plan into a dependency-ordered, story-phased `<feature_dir>/tasks.md` (TDD-ordered, `[P]` parallel markers, `[Sn]` plan-step refs). ✅ available
   → gate: **`speckit-analyze`** (cross-artifact consistency across spec/plan/tasks)
5. **`implementor`** — execution. Drive `tasks.md` to committed code, phase by phase: per-task implement → independent review → atomic commit → tick `[X]`, looping until done. ✅ available
   → gate: **`speckit-converge`** (append any unbuilt work as tasks)
6. **`improvement-review`** — post-implementation evaluation. Assess the changeset for architecture-quality, reuse, and repackaging upside; for every opportunity enumerate its ripple set. Propose-only — accepted refactors route back through `plan` → `tasks` → `implementor` as a new change. ✅ available

**`feature`** is the **orchestrator** over phases 2–6 (plus the gate tools and `self-learn`): one invocation runs `specification → speckit-clarify → speckit-checklist → plan → [capability-provisioning gate] → tasks → speckit-analyze → implementor → speckit-converge → improvement-review` as independent sub-agents, verifies each followed its own skill's logic, independently reviews every hand-off, runs `self-learn` after each phase, and pauses only on a genuine blocker. `speckit-clarify`/`speckit-checklist`/`speckit-analyze` are mandatory gates. ✅ available

Governance for the whole chain lives in `.specify/memory/constitution.md` (the canonical source every phase reads and checks against); `self-learn` keeps it updated.

## Skills

| Skill | Purpose |
|-------|---------|
| [`feature`](feature/SKILL.md) | Orchestrator. One-shots a feature end-to-end by running `specification → speckit-clarify → speckit-checklist → plan → tasks → speckit-analyze → implementor → speckit-converge → improvement-review` as independent sub-agents, with a per-phase adherence check, an independent output review at each hand-off, a capability-provisioning gate around planning, the `self-learn` loop after every phase, and a blocker protocol so it runs autonomously and pauses only when a decision is genuinely the user's. |
| [`investigation`](investigation/SKILL.md) | Interview-driven investigation of an open question; scaffolds a predefined structure, drives to conclusions, hands off to Specification. |
| ├─ [`investigation/scaffold`](investigation/scaffold/SKILL.md) | Create the predefined investigation directory & starter files. |
| └─ [`investigation/synthesize-findings`](investigation/synthesize-findings/SKILL.md) | Convert gathered evidence into conclusions + a Specification-ready summary. |
| [`specification`](specification/SKILL.md) | Turns a free-text feature description (+ investigation findings) into an implementable, outcome-focused `specs/NNN-<slug>/spec.md` + `checklists/requirements.md`, writing `.specify/feature.json`. Makes informed guesses with ≤3 clarification markers; prioritised user stories, BDD scenarios, edge cases, FR/SC, constraints. |
| [`plan`](plan/SKILL.md) | Turns an approved spec into a rigorous `<feature_dir>/plan.md` + design artifacts (research/data-model/contracts/quickstart): Constitution Check, skill discovery, a hard-gate convention/rule audit before coding, BDD→testable-unit decomposition with a red/green TDD loop (pytest / dbt tests / Pandera+Pydantic), a guardrail register, and a per-step independent self-review sub-agent. |
| [`tasks`](tasks/SKILL.md) | Turns an approved plan into a dependency-ordered, story-phased `<feature_dir>/tasks.md` (Setup→Foundational→per-user-story→Polish), TDD-ordered, with `[P]` file-disjoint parallel markers and `[Sn]` plan-step references so spec→plan→tasks traceability closes. |
| [`implementor`](implementor/SKILL.md) | Executes `<feature_dir>/tasks.md` phase by phase: delegates each task to an implementer sub-agent, has an independent reviewer verify it (plan/spec followed, test real, no reward-hacking, no constraint-bypass), commits atomically on PASS and ticks `[X]`, parallelises file-disjoint `[P]` tasks, and loops until done. |
| [`improvement-review`](improvement-review/SKILL.md) | Post-build evaluation. Reviews the just-landed changeset through three lenses (architecture quality, reuse, repackaging) and, for every opportunity, enumerates its **ripple set** — the coupled skills, `ARCHITECTURE.md`/`ERD.md` diagrams, `CLAUDE.md` constraints, dbt models and docs that must change with it. Propose-only and approval-gated (refactors route back through `plan` → `implementor`); distinct from `code-architecture-review` (conformance) and `self-learn` (process knowledge). |
| [`self-learn`](self-learn/SKILL.md) | Cross-cutting. At the end of a unit of work, mine the session, git changes, and existing skills for durable learnings and route each to `CLAUDE.md`, an updated skill, or a new skill (approval-gated). |
| [`missing-specification`](missing-specification/SKILL.md) | Cross-cutting / retrospective. Walks the git history one commit at a time, classifies each as covered by an existing spec, unspecified-substantive, or non-substantive, groups the gaps by delivered outcome, then writes one retrospective `specs/NNN-<slug>/spec.md` per feature (via a dedicated sub-agent, same template, `Status: Implemented`, traced to a `Source commits` line; does not set `feature.json`) and reviews each against the **current** codebase for accuracy. The reverse of `specification`: backfills the specs that were never written. |
| [`code-architecture-review`](code-architecture-review/SKILL.md) | Cross-cutting / conformance. Reviews code (a diff, a commit, or the whole repo) against this project's committed architecture contract in `ARCHITECTURE.md` — package structure, medallion layering, dependency-direction rules, per-module responsibilities — and flags when `ARCHITECTURE.md` itself has gone stale. Evidence-backed and approval-gated; may legitimately find nothing. Distinct from `improvement-review` (opportunity) and `self-learn` (process knowledge). |
| [`git-sync-extractor`](git-sync-extractor/SKILL.md) | Knowledge-extraction pipeline (stage 1). Incrementally extracts per-commit diffs and net-new file contents for paths matching configurable patterns (e.g. `architecture/`, `transcripts/`), writing them under `temp/<short_sha>/` to feed downstream processors. Run to sync, extract, or replay git history (run/status/reset). |
| [`architecture-processor`](architecture-processor/SKILL.md) | Knowledge-extraction pipeline (stage 2). Extracts structured knowledge (components, relationships, state models, rate limits, queue strategies) from the net-new architecture documents (C4-PlantUML `.puml` diagrams, design docs) produced by `git-sync-extractor`, writing `arch_extracted_<flat>.json` per file. The agent reads and extracts with its own tools — no external API calls. |

## Shared helpers

The `_shared/` directories are **not skills** (no `SKILL.md`). They are small libraries of
**deterministic** checks the skills call instead of re-deriving them in prose — the principle
being *prefer a script/linter over pure-AI judgement wherever the thing being checked is
mechanical* (numbering, template conformance, traceability arithmetic, layering, commit
footprint). Authoring stays judgement; verifying structure does not.

- [`_shared/git-helpers/`](_shared/git-helpers/README.md) — git wrappers (bash + PowerShell):
  `git-changeset` (read-only change-set gathering, used by `code-architecture-review`,
  `improvement-review`, `self-learn`, `implementor` resume), `git-history` (read-only history
  walking, used by `missing-specification`), `git-commit-safe` (guarded atomic commit that
  exposes none of the forbidden git verbs, used by `implementor` and `self-learn`),
  `git-audit-commits` (read-only commit-hygiene audit, used by `feature`), and `classify-commits`
  (read-only commit footprint pre-filter, used by `missing-specification` §2).
- [`_shared/spec-helpers/`](_shared/spec-helpers/README.md) — `feature-dir` (resolves the active
  feature directory from `.specify/feature.json`, used by every phase after `specification`),
  `next-number` (next/parallel-block feature numbering by scanning `specs/NNN-*/`, used by
  `specification`, `missing-specification`, `feature`), `validate-spec` / `validate-plan` /
  `validate-tasks` (stdlib-Python structural linters for the spec/plan/tasks templates, incl. the
  plan's convention-audit hard gate), `trace-check` (spec→plan→tasks traceability closure), and
  `docs-sync` (mirror a feature dir into the Starlight site, injecting `title:` frontmatter;
  copy-only, never deletes).
- [`_shared/arch-helpers/`](_shared/arch-helpers/README.md) — `arch-lint` (stdlib-Python AST
  conformance check for the mechanical ARCHITECTURE.md rules 1/3/4/5/7, used by
  `code-architecture-review` §2; rules 2/6/8 stay agent judgement).

See each README for the contract. The validators are stdlib-only Python 3 (no target-repo
dependency, no PowerShell mirror needed since one file is already cross-platform); the git/number
helpers ship bash + PowerShell.

## Conventions

- One responsibility per skill; the `description` must make triggering unambiguous (start with what it does, add an explicit `USE WHEN …`).
- Reference material (templates, checklists) lives in a `references/` folder inside the skill and is linked from `SKILL.md`.
- Sub-skills name themselves with the parent prefix (e.g. `investigation-scaffold`) to keep them discoverable and clearly scoped.
- Deterministic or safety-critical plumbing belongs in a `_shared/` helper (called from `SKILL.md`), not in prose the agent must re-derive: git in `_shared/git-helpers/`, spec/plan numbering + template/traceability checks in `_shared/spec-helpers/`, ARCHITECTURE.md conformance in `_shared/arch-helpers/`. A skill should state *what* it wants checked and call the helper; only genuine judgement (authoring, classification of intent, reuse/ripple calls) stays in prose.
- A `_shared/` helper that encodes a contract (a template, ARCHITECTURE.md's rules) is **coupled to that contract** — when the template or the architecture rules change, the helper changes in the same change (it is part of that change's ripple set).
