# Specifications

Implementable, outcome-focused specifications generated from one or more user
stories (in [`../user_stories/`](../user_stories/)) by the **`specification`**
skill ([`.agents/skills/specification`](../.agents/skills/specification/SKILL.md)).

## Convention

- One file per spec: `NNN-<slug>-specification.md`, where `NNN` is a
  zero-padded, monotonically increasing number (first is `001`) and `<slug>` is
  a kebab-case name derived from the outcome.
- Frontmatter carries the machine-readable contract — `id`, `slug`, `status`,
  `created`, and `user_stories` (the source story identifiers this spec
  satisfies). See the skill's
  [`specification-template.md`](../.agents/skills/specification/references/specification-template.md).
- Each spec describes **what** to build (BDD scenarios, edge cases, acceptance
  criteria, constraints) and stays outcome-focused — it avoids prescribing
  implementation except where domain vocabulary (e.g. medallion layers, data
  formats) is itself the requirement.

To create or update a spec, run the `specification` skill.
