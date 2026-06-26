---
name: specification
description: Turn one or more user stories (plus any investigation findings and the user's initial information) into a single implementable, outcome-focused Specification stored under specs/ as NNN-<slug>-specification.md, with frontmatter linking the source user stories. Uses an interview to resolve anything unclear, then writes BDD scenarios, edge cases, acceptance criteria and constraints. USE WHEN the user wants to define WHAT to build — to spec out, write a specification for, or formalise one or more user stories before implementation.
---

# Specification

Specification is the **definition phase that comes after investigation and before build**. Its job is to turn one or more user stories — plus any initial information the user gives and any upstream investigation findings — into a single, implementable **Specification** that describes *what to build and how we'll know it's done*, not how to build it.

The output is one Markdown file in `specs/`, numbered and named `NNN-<slug>-specification.md`, with frontmatter that links back to the source user stories.

A good specification is:
- **Outcome-focused** — it describes observable behaviour and the result the user gets, not the implementation. It generally does *not* prescribe libraries, classes, or internal design. (See the domain exception below.)
- **Implementable** — an engineer can build from it without guessing. Every requirement is concrete and testable.
- **Verifiable** — its acceptance criteria and BDD scenarios map onto tests that can pass or fail.

> **Domain exception.** Stay tech-agnostic *unless the domain vocabulary is the requirement*. For a data-ingestion project like this one, outcomes are naturally expressed in domain terms — bronze/silver/gold layers, Parquet artifacts, partitioning, encoding (e.g. latin-1), schema/frame validation, idempotency. Use that vocabulary where it defines the outcome; still avoid prescribing the internal code design.

## When to use this skill

- "Write a specification for US-001 / story #2 / these stories"
- "Spec out <feature> from these user stories"
- "Turn this story (and the investigation findings) into something we can build"
- A completed **investigation** proposes the hand-off to specification.

If the question of *whether* something is feasible or *which* approach to take is still open, that is the **investigation** skill's job first. If the spec already exists and the user wants an implementation plan or to build, that is downstream of this skill.

## The workflow

Follow these phases in order. Do not skip the interview.

### 1. Gather the inputs

Collect everything that feeds the spec before interviewing:

1. **The user stories.** Read each referenced story from `user_stories/`. Stories are Azure DevOps work items as JSON — pull `System.Title`, `System.Description`, `Microsoft.VSTS.Common.AcceptanceCriteria`, and `relations` (parent epic / dependencies). Record each story's identifier (see `references/authoring-guide.md` → *Linking user stories*).
2. **The user's initial information** — whatever they pasted or described alongside the request.
3. **Upstream investigation findings**, if any — check `investigations/<slug>/findings.md` for a Specification hand-off summary (answer, recommended direction, constraints, rejected options, open questions). Fold these in rather than re-deriving them.

If a referenced story can't be found, say so and ask for the right identifier — don't invent its contents.

### 2. Interview the user (mandatory where unclear)

Read the stories and inputs first, then interview **only on what they leave genuinely unclear** — don't re-ask anything the stories already answer. Use the `AskUserQuestion` tool. The question bank is in `references/authoring-guide.md` → *Interview question bank*; cover at minimum, where not already known:

1. **The outcome & scope boundary** — what observable result counts as success, and what is explicitly out of scope.
2. **Actors & triggers** — who/what initiates the behaviour and when.
3. **Behaviour & rules** — the happy path plus the business rules that govern variations.
4. **Edge cases & failure handling** — boundaries, bad input, partial failure, what the system should do when things go wrong.
5. **Acceptance & done** — what evidence proves it's built correctly; any non-functional constraints (volume, latency, encoding, idempotency, data contracts).

End the interview by playing back a one-paragraph summary of the spec's scope and the proposed filename, and ask the user to confirm before you write the file.

### 3. Determine the number, slug and filename

- **Number:** scan `specs/` for existing `NNN-*-specification.md`, take the highest `NNN`, add one, zero-pad to three digits. First spec is `001`. (Details in `references/authoring-guide.md` → *Numbering & naming*.)
- **Slug:** kebab-case, derived from the outcome (e.g. `football-main-bronze-ingestion`), not a verbatim story title.
- **Filename:** `specs/NNN-<slug>-specification.md`.

### 4. Write the specification

Create the file using the template in `references/specification-template.md` exactly — same frontmatter keys and section order. Fill every section:

- Frontmatter `user_stories` lists the source story identifiers (see *Linking user stories*).
- Behaviour is expressed as **Given / When / Then** BDD scenarios grouped by capability.
- Include **edge cases & error handling**, **acceptance criteria** (testable checklist), and **things to be aware of / constraints**.
- End with a **traceability** table mapping each user story → scenarios → acceptance criteria, so nothing in the stories is dropped and nothing in the spec is unsourced.
- Anything the interview could not resolve goes under **Open questions** — never guess and bury an assumption silently. Make assumptions explicit in the **Assumptions** section.

Quality bar and how to write each section well: `references/authoring-guide.md`.

### 5. Report and propose the next step

Show the created path and a short summary (outcome, number of scenarios, open questions). If the spec has unresolved open questions, flag them as blockers to resolve before build. Then propose the natural next step — an implementation plan / build — rather than stopping silently.

## Guardrails

- **One spec per file, one outcome per spec.** If the stories pull in clearly different directions, say so and propose splitting into multiple specs rather than forcing one.
- **Trace, don't drop.** Every acceptance criterion in the source stories must land somewhere in the spec (a scenario or an acceptance criterion). Every requirement in the spec must trace back to a story or a stated, agreed addition.
- **Surface contradictions and knock-on effects** between stories, or between the stories and the investigation findings — don't paper over them.
- **No silent assumptions.** If you had to assume something to proceed, it goes in *Assumptions* or *Open questions*, visibly.
- **Stay at the outcome altitude.** Resist specifying implementation unless the domain vocabulary is itself the requirement (see the domain exception above).

## References

- [`references/specification-template.md`](references/specification-template.md) — the exact output format (frontmatter + sections). Copy it verbatim and fill it in.
- [`references/authoring-guide.md`](references/authoring-guide.md) — interview question bank, how to write good BDD / acceptance criteria / edge cases, numbering & naming, and how to link user stories.
