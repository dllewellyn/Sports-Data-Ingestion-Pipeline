---
name: specification
description: Turn a free-text feature description (plus any investigation findings) into a single implementable, outcome-focused Specification stored as specs/NNN-<slug>/spec.md inside a per-feature directory, with a quality checklist and the feature directory persisted to .specify/feature.json for the downstream chain. Makes informed guesses and uses at most 3 clarification markers rather than a blocking interview. USE WHEN the user wants to define WHAT to build — to spec out, write a specification for, or formalise a feature before planning.
---

# Specification

Specification is the **definition phase**: it turns a free-text feature description — plus any upstream
investigation findings — into a single, implementable **Specification** that describes *what to build
and how we'll know it's done*, not how to build it.

The output is a **per-feature directory** `specs/NNN-<slug>/` containing `spec.md` and
`checklists/requirements.md`. The directory path is persisted to `.specify/feature.json` so every
downstream phase (`speckit-clarify`, `plan`, `tasks`, `speckit-analyze`, `implementor`,
`speckit-converge`) locates the feature without relying on git branch names.

A good specification is:
- **Outcome-focused** — observable behaviour and the user-visible result, not implementation. (See the domain exception below.)
- **Implementable** — an engineer can build from it without guessing; every requirement is concrete and testable.
- **Verifiable** — its acceptance scenarios and success criteria map onto tests that pass or fail.

> **Domain exception.** Stay tech-agnostic *unless the domain vocabulary is the requirement*. For a
> data project, outcomes are naturally expressed in domain terms — bronze/silver/gold layers, Parquet
> artifacts, partitioning, encoding (e.g. latin-1), schema/frame validation, idempotency. Use that
> vocabulary where it defines the outcome; still avoid prescribing internal code design.

## Philosophy: guess, don't interrogate

Unlike a blocking interview, this skill **makes informed guesses** from context and industry
standards, documents them in *Assumptions*, and only emits a `[NEEDS CLARIFICATION]` marker when a
choice genuinely cannot be defaulted. **Maximum 3 markers total**, prioritised
*scope > security/privacy > user experience > technical detail*. Anything that blocks build is
promoted to *Open Questions* and labelled **BLOCKER**.

## When to use this skill

- "Write a specification for <feature>" / "spec out <feature>"
- "Turn this idea (and the investigation findings) into something we can build"
- A completed **investigation** proposes the hand-off to specification.

If *whether* something is feasible or *which* approach to take is still open, that is the
**investigation** skill's job first. If the spec exists and the user wants a plan or to build, that is
downstream of this skill.

## The workflow

### 0. Pre-execution

1. **Load governance.** Read `.specify/memory/constitution.md` — the canonical source of project
   principles and constraints. If a project `CLAUDE.md` or `ARCHITECTURE.md` exists, read them too as
   supplementary context; do **not** depend on them existing.
2. **Ingest investigation findings**, if any — check `investigations/<slug>/findings.md` for a
   Specification hand-off summary (answer, recommended direction, constraints, rejected options, open
   questions). Fold these in rather than re-deriving them.
3. **Check `before_specify` hooks.** If `.specify/extensions.yml` exists, read `hooks.before_specify`
   (enabled, non-`false`). Execute mandatory hooks and wait; surface optional ones. *(No branch hook
   is registered in this project — specification never creates or switches a git branch.)*

### 1. Name and locate the feature

1. **Short name** (2–4 words) from the description, action-noun where possible, preserving acronyms
   (e.g. "add user auth" → `user-auth`; "OAuth2 for the API" → `oauth2-api-integration`).
2. **Number:** scan `specs/` for existing `NNN-*/` directories via
   `bash .agents/skills/_shared/spec-helpers/next-number.sh specs`; zero-pad to three digits. First
   feature is `001`. Never reuse a number.
3. **Create the directory and seed the file:**
   - `mkdir -p specs/NNN-<slug>`
   - Copy `.specify/templates/spec-template.md` (or `references/specification-template.md` if the
     active template is unresolved) to `specs/NNN-<slug>/spec.md`.
4. **Persist threading** to `.specify/feature.json`:
   ```json
   { "feature_directory": "specs/NNN-<slug>" }
   ```
   Write the resolved path literally. This is how every downstream phase finds the feature.

Only one feature per invocation.

### 2. Write the specification

Fill `spec.md` using `references/specification-template.md` — same headings, same order. Follow the
execution flow:

1. Extract actors, actions, data, constraints from the description.
2. Write **User Scenarios & Testing**: prioritised user stories (P1/P2/P3…), each independently
   testable, each with BDD **Given/When/Then** acceptance scenarios describing observable outcomes.
3. Write **Edge Cases** with the *expected behaviour* for each adverse condition, not just the risk.
4. Write **Functional Requirements** (testable `FR-NNN MUST …`). Use reasonable defaults for silent
   details and record them in *Assumptions*; emit `[NEEDS CLARIFICATION]` only for genuine blockers
   (max 3 total).
5. Write **Success Criteria** — measurable and technology-agnostic (`SC-NNN`).
6. Identify **Key Entities** if data is involved.
7. Write **Constraints & things to be aware of**, pulling relevant principles from the constitution
   (and project docs if present). Never contradict the constitution — reference it.
8. Write **Assumptions** (visible defaults) and **Open Questions** (with **BLOCKER** labels where
   build is blocked; "None." if empty).

### 3. Quality validation

1. **Generate the checklist** at `specs/NNN-<slug>/checklists/requirements.md` from
   `.specify/templates/checklist-template.md`, covering: Content Quality (no implementation detail
   beyond the domain exception, user-value focus, all mandatory sections present), Requirement
   Completeness (no stray `[NEEDS CLARIFICATION]`, testable/unambiguous requirements, measurable
   tech-agnostic success criteria, acceptance scenarios defined, edge cases identified, scope bounded,
   dependencies/assumptions identified), and Feature Readiness.
2. **Run the structural linter:** `python3 .agents/skills/_shared/spec-helpers/validate-spec.py specs/NNN-<slug>/spec.md`.
3. **Validate against the checklist**, quoting offending spec sections. If items fail (excluding
   clarification markers), fix the spec and re-validate (max 3 iterations); record any residue in the
   checklist notes and warn the user.
4. **Resolve clarification markers (max 3).** Present each as a short question with suggested options
   (use `AskUserQuestion`), then replace the marker with the answer and re-validate. Promote any
   build-blocking unknown to *Open Questions* as a **BLOCKER**.

### 4. Sync to docs

Run `bash .agents/skills/_shared/spec-helpers/docs-sync.sh specs/NNN-<slug>` to copy the feature
directory into `docs/src/content/docs/features/` so the Starlight site picks it up. Repo-root
`specs/` stays the canonical source.

### 5. Post-execution hooks

If `.specify/extensions.yml` registers `hooks.after_specify` (enabled), execute mandatory hooks and
wait (e.g. `speckit.agent-context.update`); surface optional ones.

### 6. Report and propose the next step

Report `feature_directory`, `spec.md` path, checklist results, and any **BLOCKER** open questions
(flag them as gating). Propose the next step: `speckit-clarify` if anything is underspecified,
otherwise `plan`.

## Guardrails

- **One feature per directory, one outcome per spec.** If the description pulls in clearly different
  directions, say so and propose splitting into separate features rather than forcing one.
- **No silent assumptions.** Defaults go in *Assumptions*; unresolved items go in *Open Questions*
  (blockers flagged) — never buried inline beyond the 3-marker budget.
- **Stay at outcome altitude** except where domain vocabulary is itself the requirement.
- **Respect the constitution.** Surface any contradiction between the description and a constitution
  principle rather than papering over it.
- **Never create a git branch.**

## References

- [`references/specification-template.md`](references/specification-template.md) — the exact output format.
- [`references/authoring-guide.md`](references/authoring-guide.md) — how to write good prioritised stories, BDD scenarios, success criteria, edge cases, constraints, and how numbering/threading work.
