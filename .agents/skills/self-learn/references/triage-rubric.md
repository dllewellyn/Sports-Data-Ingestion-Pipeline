# Triage rubric

How to decide whether a candidate learning is worth keeping, and if so, where it goes.

## Step A — does it survive the durability bar?

Keep only if **both** are true:

| Test | Keep if… | Drop if… |
|------|----------|----------|
| **Non-obvious** | A competent engineer/agent would *not* infer it from the file tree, the code, or generic knowledge. | It's restating the obvious, generic Python/git/dbt advice, or already written in CLAUDE.md or a skill. |
| **Reusable** | It will plausibly recur — a future instance or teammate will hit the same situation. | It was a one-off specific to this exact task and won't come up again. |

**Drop examples**
- "We installed dependencies with `uv sync`." → discoverable from CLAUDE.md.
- "Fixed a typo in a variable name." → one-off, not reusable.
- "Pydantic validates data." → generic knowledge.

**Keep examples**
- "Opening `warehouse.duckdb` read-write from a second process during a dbt run gives phantom 'schema does not exist' errors." → non-obvious failure mode, will recur.
- "dbt model asset keys are prefixed by their subfolder; cross-asset `deps` must use the prefixed key or the edge silently won't form." → non-obvious, cost us debugging time.

## Step B — route each survivor to exactly one destination

Ask the questions in order; the first "yes" wins.

### 1. Is it a declarative fact, constraint, command, or convention that applies across tasks? → **CLAUDE.md**

Signals:
- You'd want it loaded into *every* future session, not just when running a particular workflow.
- It's a sentence or two, not a procedure.
- It's a gotcha ("don't do X, it causes Y"), a version pin, a non-obvious command, or a house style rule.

Placement:
- Hard-won constraints / failure-modes → under the existing **"Non-obvious constraints"** heading.
- Commands → the **Commands** block. Conventions → **Python conventions**. Config/telemetry facts → that section.
- Keep it concise; delete any now-stale line it supersedes.

### 2. Does it improve a repeatable workflow we already have a skill for? → **Update that skill**

Signals:
- The learning is about *how to do* something the skill already covers — a better step, a missing guardrail, a corrected command, a sharper trigger.
- Find the closest skill by reading `description` / `USE WHEN` across `.claude/skills/*/SKILL.md`.

Do:
- Edit the specific step or add a guardrail line. Tighten the `description` only if the trigger was genuinely wrong.
Don't:
- Expand the skill's responsibility beyond its one job. If the learning is really a *new* job, it's a new skill (next question).

### 3. Did a repeatable, multi-step procedure with its own templates/scripts/best-practices emerge that nothing covers? → **New skill**

Signals:
- A new capability or subsystem landed (e.g. a new ingestion engine, a new export format, a new validation pattern) and "we'll do this kind of thing again."
- There's a *procedure* worth templating — not just a fact (that's CLAUDE.md) and not a tweak to an existing flow (that's an update).

Do:
- Scaffold from `new-skill-template.md`, give it a `USE WHEN` description, put templates/scripts in its `references/`, and register it in `.claude/skills/README.md`.

### Nothing fits cleanly?

- If it's "a fact a skill should mention," write the fact in CLAUDE.md and add a one-line pointer from the skill.
- If you're unsure between *update* and *new skill*, prefer **update** unless the new procedure is clearly its own responsibility — avoid skill sprawl.
