# Skill discovery

Phase 1 of the plan skill. Goal: before planning steps, find the skills that already standardise the work so the plan **reuses** them instead of reinventing, and flag where a clearly-needed skill is **missing**.

## Why this matters

The spec implies kinds of work (ingestion pipeline, dbt model, API client, validation contract, telemetry, docs). For most of these the repo or the user's global setup already has a skill that does it the agreed way. Planning a step that hand-rolls something a skill already owns produces drift and re-review. Conversely, a missing skill for a core, repeatable kind of work is a gap worth closing once.

## Step 1 — Classify the work

From the spec, list the distinct kinds of work. For a data-ingestion repo, common classes:

- **Ingestion / network edge** — fetching from an API, the bronze layer, Pydantic-per-record + Pandera-per-frame validation.
- **Warehouse transform** — new dbt model (silver/gold), dbt tests, external/Parquet materialisation.
- **Orchestration** — new Dagster asset / wiring lineage, asset keys, translators.
- **Contracts** — new Pydantic schema / Pandera frame contract / config field.
- **Review & analysis** — architecture conformance, code quality, security, root cause.
- **Lifecycle** — investigation, specification, planning, self-learn, changelog, story/ticket sync.
- **Docs / telemetry** — developer docs, OTel spans, dashboards.

## Step 2 — Enumerate available skills (delegate)

Spawn an `Explore` (or `general-purpose`) sub-agent so the listing doesn't bloat the planner's context. Prompt template:

> List every agent skill available in this environment and return a compact table of `name → one-line purpose → location`. Cover all three sources: (1) project-local skills under `.agents/skills/` (read each `SKILL.md` frontmatter); (2) user/global skills under `~/.claude/` (skills, commands, plugins); (3) any plugin skills surfaced in the session. Do not load the skills — just inventory their names and descriptions. Return only the table.

(The session also surfaces available skills in system reminders; use that as a cross-check, but the sub-agent inventory is the source of truth because it includes project-local skills.)

## Step 3 — Match work → skill

For each work class from Step 1, pick the best-matching skill. Examples grounded in this repo's current skill set:

| Work class | Likely skill |
|------------|--------------|
| New dbt model + tests / warehouse change | (no dedicated build skill yet — see gaps) |
| Architecture conformance of the change | `code-architecture-review`, `analyze-architecture` |
| Code quality / debt of the change | `analyze-code-quality` |
| Security review of the change | `analyze-security` / `security-review` |
| Verify the change actually runs | `verify`, `run` |
| Establishing a missing rule | `create-rule` |
| Authoring a missing skill | `skill-creator` (global) |
| Capturing learnings afterwards | `self-learn` |
| Per-step diff review | `code-review` |

Record the chosen skill **per planned step** so §2 and §6 of the plan reference it.

## Step 4 — Flag missing skills (don't pretend)

If a work class is central and repeatable but has **no** matching skill, that's a gap. The canonical example the user gave: *the spec is a data-ingestion pipeline, but there's no "create data ingestion pipeline" skill.* When that happens:

1. Name the gap explicitly in the plan's §2 table (Status = MISSING).
2. Offer the options rather than silently proceeding:
   - **Create the skill first** via the global `skill-creator`, then have the plan steps invoke it — best when the work will recur.
   - **Proceed without**, planning the steps explicitly from the repo's existing patterns (`ARCHITECTURE.md` "add a new data source" guide, the existing `assets/bronze.py` edge), and run `self-learn` after the build to codify what was learned into a new skill.
3. Never list a skill as "available" that you have not confirmed exists in the Step 2 inventory.
