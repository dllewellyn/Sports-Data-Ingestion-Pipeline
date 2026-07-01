---
name: investigation-scaffold
description: Create the predefined directory and starter files for an investigation (README charter, findings log, decisions, code/ and evidence/ folders). USE WHEN starting a new investigation, after the scoping interview is confirmed. Sub-skill of the Investigation skill.
---

# Investigation — Scaffold

Creates the predefined investigation structure (see `../references/structure.md`) from the confirmed interview answers.

## Preconditions

Only run this **after** the user has confirmed the scoped investigation (the interview from the parent `investigation` skill). You need: the question, why-now, hypotheses/options, done criteria, and scope/constraints.

## Steps

1. **Derive the slug** — kebab-case from the question (e.g. `can-we-stream-from-api`). Confirm with the user if ambiguous.
2. **Confirm the location** — default `investigations/<slug>/` at repo root. Ask if the user wants it elsewhere.
3. **Show the layout before creating it** — print the tree from `../references/structure.md` so the user can adjust.
4. **Create the structure:**
   - `README.md` — fill the charter template with the interview answers (question, why now, hypotheses, done criteria, scope). Set `Status: scoping`, today's date, owner.
   - `findings.md` — empty log with the `Conclusion` and `Log` headers; conclusion left as TODO.
   - `decisions.md` — empty `Made` / `Open questions` sections; seed open questions from the interview if any.
   - `code/README.md` — note that this holds disposable spikes only.
   - `evidence/.gitkeep`
5. **Gitignore check** — if `code/` or `evidence/` shouldn't be committed (large data, secrets, scratch output), propose adding them to `.gitignore`. Never commit credentials or sample data containing secrets.
6. **Report** — show the created paths and tell the user the investigation is ready to run.

## After scaffolding

Hand back to the parent `investigation` skill to run the investigation, logging into `findings.md` as you go.
