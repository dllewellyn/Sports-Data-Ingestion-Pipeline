# Specification authoring guide

How to interview for, write, and number a specification. The output format lives in `specification-template.md`; this file is the *how-to-write-it-well*.

## Numbering & naming

- Filename: `specs/NNN-<slug>-specification.md`.
- `NNN` is a zero-padded, monotonically increasing integer. To find the next one: list `specs/`, take the highest leading `NNN` across existing `*-specification.md` files, add one, zero-pad to three digits. The first spec is `001`. Never reuse a number, even if a spec is deleted.
- `<slug>` is kebab-case, derived from the **outcome**, not a verbatim story title (e.g. `football-main-bronze-ingestion`, not `implement-football-main-bronze-ingestion-and-validation-path`). Keep it short and stable.
- `id` and `slug` in the frontmatter must match the filename.
- If `specs/` does not exist yet, create it.

## Linking user stories

The frontmatter `user_stories` list links the spec back to its sources. Use the identifier that uniquely names each story **in this repo's backlog**:

- Stories live in `user_stories/` as Azure DevOps work-item JSON. A synced story has a numeric work-item `id` (and is usually saved as `<id>.json`, e.g. `1.json`, `2.json`) — use that number: `user_stories: [1, 2]`.
- A not-yet-synced story is saved under a slug filename (e.g. `new-implement-football-main-bronze-ingestion-and-validation-path.json`) with `"localStatus": "new"` and no numeric id — use the filename stem as its identifier until it gets a number.
- The template shows the generic `US-001` form; in this repo prefer the real identifiers above so the link resolves. Be consistent within a spec.

Always read each story before linking it (`System.Title`, `System.Description`, `Microsoft.VSTS.Common.AcceptanceCriteria`, `relations`). The `relations` array (e.g. `Hierarchy-Reverse` → parent epic, dependency links) tells you the story's place in the backlog — note parent epics and dependencies in *Background & context* and *Constraints*.

## Interview question bank

Ask only what the stories and inputs leave genuinely unclear. Prefer `AskUserQuestion` with concrete options over open prompts. Batch related questions.

**Outcome & scope**
- What observable result means this is done — what can the user/system do afterwards that it couldn't before?
- What is explicitly *out* of scope for this spec?
- Is this one outcome, or several that should be separate specs?

**Actors & triggers**
- Who or what starts this (user role, scheduled run, upstream event)?
- How often / under what conditions does it fire?

**Behaviour & rules**
- Walk the happy path step by step — what's the expected end state?
- What business rules cause the behaviour to vary (thresholds, categories, per-record policy)?
- Are there ordering, concurrency, or dependency constraints?

**Edge cases & failure**
- What inputs are invalid/malformed/empty, and what should happen to them — reject, quarantine, skip-and-continue, fail the run?
- What happens on partial failure or a re-run of the same input (idempotency)?
- Encoding, schema drift, missing fields, limits exceeded, upstream unavailable — expected behaviour for each?

**Acceptance & non-functional**
- What evidence proves it works (a passing test, a produced artifact, a metric)?
- Volume / latency / throughput expectations?
- Data contracts: required fields, types, formats, partitioning, layer (bronze/silver/gold)?

## Writing good BDD scenarios

- One scenario = one behaviour. Keep **Given/When/Then** crisp: Given sets context, When is the single trigger, Then is the observable outcome (and `And` for extra outcomes).
- Write outcomes you can **observe and assert** — "a bronze Parquet file is written under `football_main/` partitioning" beats "the data is processed".
- Cover the happy path first, then each rule-driven variation and each failure mode as its own scenario.
- Avoid implementation detail in Then ("the row is inserted via dbt" → instead "the row appears in the silver model and passes its dbt tests"). Name observable results, not mechanisms.
- Group scenarios under the capability they belong to so the spec reads top-down.

## Writing good acceptance criteria

- Each AC is a single, objectively pass/fail statement. If two people could disagree on whether it passed, split or sharpen it.
- Prefer the Given/When/Then phrasing the source stories already use where it fits — it keeps traceability obvious.
- Every source story's acceptance criteria must be represented by at least one AC and/or scenario here. The traceability table is where you prove it.
- ACs are the build's definition of done — they should be the things a reviewer literally checks off.

## Writing good edge cases & constraints

- Edge cases describe **expected behaviour under adverse conditions**, not just the risk. "Malformed row → surfaced per policy, valid rows continue" — state the policy.
- Constraints capture what an implementer must not violate: dependencies on other specs/stories, non-functional bounds, data contracts, and repo-specific gotchas. For this codebase, check `CLAUDE.md` → *Non-obvious constraints* and `ARCHITECTURE.md`, and carry forward anything relevant (e.g. DuckDB single-writer, dbt asset-key prefixing, no `from __future__ import annotations` in asset modules) rather than letting the spec contradict them.

## Quality bar (self-check before finishing)

- [ ] Every source story is linked in frontmatter and appears in the traceability table.
- [ ] Every story acceptance criterion maps to a scenario or an AC.
- [ ] Every spec requirement traces back to a story or an explicitly agreed addition.
- [ ] Happy path, rule variations, and failure modes all have scenarios.
- [ ] Edge cases state expected behaviour, not just risks.
- [ ] Acceptance criteria are each objectively pass/fail.
- [ ] No silent assumptions — they're in *Assumptions*; unresolved items are in *Open questions* (blockers flagged).
- [ ] The spec stays at outcome altitude except where domain vocabulary is the requirement.
- [ ] Contradictions between stories / with investigation findings are surfaced, not buried.
