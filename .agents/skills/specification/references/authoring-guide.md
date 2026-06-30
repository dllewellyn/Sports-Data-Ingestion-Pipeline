# Specification authoring guide

How to write and locate a specification well. The output format lives in
`specification-template.md`; this file is the *how-to-write-it-well*.

## Numbering, naming & threading

- **Directory:** `specs/NNN-<slug>/`, containing `spec.md` and `checklists/requirements.md` (and,
  after planning, `plan.md`, `tasks.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`).
- **`NNN`** is a zero-padded, monotonically increasing integer. Find the next one with
  `bash .agents/skills/_shared/spec-helpers/next-number.sh specs` (scans existing `specs/NNN-*/`
  directories). The first feature is `001`. Never reuse a number, even if a feature is deleted.
- **`<slug>`** is kebab-case, derived from the **outcome** (a 2–4 word short name), not a verbatim
  description (e.g. `football-main-bronze-ingestion`, not
  `implement-football-main-bronze-ingestion-and-validation-path`). Keep it short and stable.
- **Threading:** the specification skill writes `{ "feature_directory": "specs/NNN-<slug>" }` to
  `.specify/feature.json`. This — not a git branch, not a filename convention — is how `plan`,
  `tasks`, `implementor`, and the `speckit-*` gate tools find the feature. Keep it accurate.

## Input: free-text, with optional investigation findings

There is no user-story backlog to link. The input is the user's free-text feature description.
Where an upstream **investigation** ran, read `investigations/<slug>/findings.md` and fold its
answer / recommended direction / constraints / rejected options into the spec rather than
re-deriving them; note unresolved investigation questions under *Open Questions*.

## Guess, don't interrogate

Make informed guesses from context and industry standards, and **document each as an assumption**.
Only emit `[NEEDS CLARIFICATION: specific question]` when a choice genuinely cannot be defaulted and
it materially affects scope/security/UX. **Hard cap: 3 markers total.** Prioritise
*scope > security/privacy > user experience > technical detail*. Promote anything that blocks build
to *Open Questions* as a **BLOCKER**.

**Reasonable defaults you should NOT ask about:** data retention (domain-standard), performance
targets (standard expectations unless stated), error handling (user-friendly messages with
fallbacks), integration patterns (project-appropriate). Record the default you chose in *Assumptions*.

## Writing prioritised user stories

- Each story is an **independently testable** journey: implementing just P1 should still deliver a
  viable, demonstrable slice of value.
- Assign priorities (P1 most critical). Order by importance.
- For each story give *Why this priority*, an *Independent Test* (how to test the slice alone and what
  value it proves), and BDD acceptance scenarios.

## Writing good BDD acceptance scenarios

- One scenario = one behaviour. **Given** sets context, **When** is the single trigger, **Then** is
  the observable outcome (`And` for extra outcomes).
- Write outcomes you can **observe and assert** — "a bronze Parquet file is written under
  `football_main/` partitioning" beats "the data is processed".
- Cover the happy path first, then each rule-driven variation and failure mode.
- Avoid implementation mechanism in *Then* ("the row is inserted via dbt" → "the row appears in the
  silver model and passes its dbt tests").

## Writing good functional requirements & success criteria

- **FR-NNN**: a single testable `MUST` statement. If two people could disagree on whether it passed,
  split or sharpen it.
- **SC-NNN** (success criteria) must be **measurable** (metric, count, rate, time), **technology-
  agnostic** (no framework/language/DB/tool), **user/business-focused**, and **verifiable** without
  knowing the implementation.
  - Good: "all valid rows from a source file land in the silver model and pass its tests";
    "95% of searches return results in under 1 second".
  - Bad: "API response under 200ms"; "Redis cache hit rate above 80%" (implementation-specific).

## Writing good edge cases & constraints

- Edge cases describe **expected behaviour under adverse conditions**, not just the risk: "malformed
  row → surfaced per policy, valid rows continue" — state the policy.
- Constraints capture what an implementer must not violate. Pull relevant principles from
  `.specify/memory/constitution.md` (the canonical governance source) and any project `CLAUDE.md` /
  `ARCHITECTURE.md` that exist — non-functional bounds, data contracts, layer constraints, repo
  gotchas — and never write the spec to contradict them. Reference the governing principle.

## Quality bar (self-check before finishing)

- [ ] `.specify/feature.json` points at the new `specs/NNN-<slug>/`.
- [ ] `validate-spec.py` passes on `spec.md`.
- [ ] Every mandatory section is present and filled (Open Questions says "None." if empty).
- [ ] Stories are prioritised and each is independently testable.
- [ ] Happy path, rule variations, and failure modes all have scenarios with observable outcomes.
- [ ] Edge cases state expected behaviour, not just risks.
- [ ] Functional requirements are each objectively testable; success criteria are measurable and tech-agnostic.
- [ ] At most 3 `[NEEDS CLARIFICATION]` markers; build-blockers promoted to *Open Questions* as **BLOCKER**.
- [ ] No silent assumptions — chosen defaults are in *Assumptions*.
- [ ] The spec stays at outcome altitude except where domain vocabulary is the requirement.
- [ ] No constitution principle is contradicted; contradictions are surfaced.
- [ ] `checklists/requirements.md` generated and validated; feature synced into `docs/`.
