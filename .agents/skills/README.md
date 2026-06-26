# Agent Skills

Project-local skills for agentic workflows. Each skill is a directory containing a `SKILL.md` with `name` / `description` frontmatter and a markdown body. Sub-skills are nested directories with their own `SKILL.md`.

## Phased workflow

These skills are designed to chain, front-to-back, across the lifecycle of a piece of work:

1. **`investigation`** — discovery. Turn an open question / unknown into evidence-backed conclusions. Proposes the Specification skill on completion. ✅ available
2. **`specification`** — definition. Turn investigation findings into *what to build*. 🔜 next

## Skills

| Skill | Purpose |
|-------|---------|
| [`investigation`](investigation/SKILL.md) | Interview-driven investigation of an open question; scaffolds a predefined structure, drives to conclusions, hands off to Specification. |
| ├─ [`investigation/scaffold`](investigation/scaffold/SKILL.md) | Create the predefined investigation directory & starter files. |
| └─ [`investigation/synthesize-findings`](investigation/synthesize-findings/SKILL.md) | Convert gathered evidence into conclusions + a Specification-ready summary. |
| [`self-learn`](self-learn/SKILL.md) | Cross-cutting. At the end of a unit of work, mine the session, git changes, and existing skills for durable learnings and route each to `CLAUDE.md`, an updated skill, or a new skill (approval-gated). |

## Conventions

- One responsibility per skill; the `description` must make triggering unambiguous (start with what it does, add an explicit `USE WHEN …`).
- Reference material (templates, checklists) lives in a `references/` folder inside the skill and is linked from `SKILL.md`.
- Sub-skills name themselves with the parent prefix (e.g. `investigation-scaffold`) to keep them discoverable and clearly scoped.
