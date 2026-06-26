# Agent Skills

Project-local skills for agentic workflows. Each skill is a directory containing a `SKILL.md` with `name` / `description` frontmatter and a markdown body. Sub-skills are nested directories with their own `SKILL.md`.

## Phased workflow

These skills are designed to chain, front-to-back, across the lifecycle of a piece of work:

1. **`investigation`** — discovery. Turn an open question / unknown into evidence-backed conclusions. Proposes the Specification skill on completion. ✅ available
2. **`specification`** — definition. Turn one or more user stories (and any investigation findings) into an implementable, outcome-focused spec under `specs/`. ✅ available
3. **`plan`** — build preparation. Turn an approved spec into a guardrailed, test-first implementation plan (`specs/NNN-<slug>-plan.md`): discovers helpful skills, audits & establishes missing conventions before coding, decomposes BDD into testable units with a red/green loop, and gives each step an independent self-review sub-agent. ✅ available

## Skills

| Skill | Purpose |
|-------|---------|
| [`investigation`](investigation/SKILL.md) | Interview-driven investigation of an open question; scaffolds a predefined structure, drives to conclusions, hands off to Specification. |
| ├─ [`investigation/scaffold`](investigation/scaffold/SKILL.md) | Create the predefined investigation directory & starter files. |
| └─ [`investigation/synthesize-findings`](investigation/synthesize-findings/SKILL.md) | Convert gathered evidence into conclusions + a Specification-ready summary. |
| [`specification`](specification/SKILL.md) | Interview-driven; turns one or more user stories (+ investigation findings) into an implementable, outcome-focused spec (`specs/NNN-<slug>-specification.md`) with BDD scenarios, edge cases, acceptance criteria and traceability. |
| [`plan`](plan/SKILL.md) | Turns an approved spec into a rigorous implementation plan (`specs/NNN-<slug>-plan.md`): skill discovery, a hard-gate convention/rule audit done before coding, BDD→testable-unit decomposition with an explicit red/green TDD loop for this repo's facilities (pytest / dbt tests / Pandera+Pydantic), a guardrail register, and a per-step independent self-review sub-agent. |
| [`self-learn`](self-learn/SKILL.md) | Cross-cutting. At the end of a unit of work, mine the session, git changes, and existing skills for durable learnings and route each to `CLAUDE.md`, an updated skill, or a new skill (approval-gated). |

## Conventions

- One responsibility per skill; the `description` must make triggering unambiguous (start with what it does, add an explicit `USE WHEN …`).
- Reference material (templates, checklists) lives in a `references/` folder inside the skill and is linked from `SKILL.md`.
- Sub-skills name themselves with the parent prefix (e.g. `investigation-scaffold`) to keep them discoverable and clearly scoped.
