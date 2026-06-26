# New-skill template

Use this when triage routes a learning to a **new skill**. Follow the conventions in
`.claude/skills/README.md`: one responsibility per skill, a `description` that starts
with what it does and ends with an explicit `USE WHEN …`, reference material in a
`references/` folder, and parent-prefixed sub-skill names.

## 1. Pick the shape

- **Single skill** — one `SKILL.md` (+ optional `references/`). The default; prefer it.
- **Skill with sub-skills** — only when the procedure has genuinely separable phases,
  each its own responsibility (mirror the `investigation` skill's `scaffold` /
  `synthesize-findings` layout). Sub-skill dirs nest inside and name themselves
  `<parent>-<child>`.

## 2. Scaffold

```
.claude/skills/<skill-name>/
  SKILL.md
  references/            # templates, checklists, scripts the skill links to
```

## 3. SKILL.md skeleton

```markdown
---
name: <skill-name>
description: <what it does, one line>. USE WHEN <unambiguous trigger conditions>.
---

# <Skill Title>

<One paragraph: the skill's single responsibility and the durable knowledge it encodes.>

## When to use
- <concrete trigger phrasings>
- <when NOT to use it, if there's an adjacent skill it could be confused with>

## The workflow
### 1. <step>
<what to do; link templates as [`references/<file>`](references/<file>)>
### 2. <step>
...

## Guardrails
- <invariants that must hold; failure modes to avoid; what's out of scope>
```

## 4. Fill it from the evidence

The new skill exists because a procedure *actually happened this session*. Encode what
you learned doing it for real:

- The exact commands/paths that worked (and any that didn't — record the gotcha).
- Any template or starter file the next run should copy — put it in `references/`.
- The non-obvious constraints you hit, so the next instance doesn't rediscover them.
- A `USE WHEN` precise enough that it triggers on the right requests and *only* those.

## 5. Register it

Add the skill to `.claude/skills/README.md`:
- A row in the **Skills** table (and an indented row per sub-skill).
- A bullet in the **Phased workflow** list if it belongs to a lifecycle phase.

## Worked example — a data-ingestion engine

Say the session added a new ingestion source end-to-end. A good resulting skill:

```markdown
---
name: add-ingestion-source
description: Add a new validated data-ingestion source to the bronze layer following this repo's medallion + Pydantic/Pandera patterns. USE WHEN onboarding a new API/file source into the pipeline.
---
# Add Ingestion Source
Encodes the repeatable path from "new upstream source" to a wired bronze asset:
the Pydantic record model, the Pandera frame contract, the bronze asset shape, and
the dbt source/staging wiring — with the constraints that bit us last time.

## The workflow
### 1. Define the contracts
Copy [`references/schema-template.py`](references/schema-template.py) … (Pydantic per-record, Pandera per-frame).
### 2. Write the bronze asset
… the only asset that touches the network; emit Parquet, not warehouse writes.
### 3. Wire silver + dbt source
… remember asset keys are subfolder-prefixed; map the dbt source via the translator.

## Guardrails
- DuckDB is single-writer — read the Parquet file, never open the warehouse read-write mid-run.
- No `from __future__ import annotations` in asset modules.
```

Note how the skill *pulls forward the exact CLAUDE.md constraints relevant to that
procedure* rather than restating all of them — concise, scoped, and tied to evidence.
