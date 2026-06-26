# Specification template

This is the **exact output format**. Copy the skeleton below into `specs/NNN-<slug>-specification.md` and fill every section. Keep the frontmatter keys and the section order unchanged. Remove the `<!-- guidance -->` comments from the final file; keep the headings even if a section is short (write "None." rather than deleting it).

The frontmatter is the machine-readable contract — `id`, `slug` and `user_stories` must be accurate. See `authoring-guide.md` → *Numbering & naming* and *Linking user stories*.

---

```markdown
---
id: NNN                         # zero-padded spec number, matches the filename (e.g. 001)
title: <Human-readable spec title>
slug: <kebab-slug>              # matches the filename
status: draft                   # draft | in-review | approved | implemented
created: YYYY-MM-DD
user_stories: [US-001, US-002]  # source story identifiers (in THIS repo: numeric work-item ids like [1, 2], or filename slug for un-synced stories) — see authoring-guide.md
investigation: <slug or null>   # investigations/<slug> this spec draws on, or null
related_specs: []               # other spec ids this depends on or relates to
---

# <Spec title>

## 1. Summary
<!-- One paragraph. The outcome in plain language: who gets what result, and why it matters. No implementation. -->

## 2. Background & context
<!-- Why this exists. Link the source user stories and any investigation findings. State the problem being solved and any prior decisions already taken. -->

## 3. Goals & non-goals
**Goals**
- <Outcome 1 — observable, valuable>

**Non-goals (explicitly out of scope)**
- <Thing this spec deliberately does NOT cover, so scope is unambiguous>

## 4. Actors & triggers
<!-- Who or what initiates the behaviour (user role, scheduled job, upstream system) and the event/trigger that starts it. -->

## 5. Behaviour specification (BDD)
<!-- The core. Group scenarios by capability. Use Given/When/Then. Cover the happy path first, then variations driven by business rules. Each scenario must be independently testable. Reference the story it satisfies where helpful. -->

### Capability: <name>

**Scenario: <happy-path name>**
- **Given** <initial context / preconditions>
- **When** <the action / trigger>
- **Then** <the observable outcome>
- **And** <any further observable outcome>

**Scenario: <variation name>**
- **Given** …
- **When** …
- **Then** …

## 6. Edge cases & error handling
<!-- Boundaries and the unhappy paths: bad/empty/malformed input, encoding issues, partial failure, duplicates/re-runs (idempotency), limits exceeded, upstream unavailable. State the EXPECTED behaviour for each, not just the risk. A table works well. -->

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | <condition> | <what the system must do> |

## 7. Acceptance criteria
<!-- A testable checklist. Each item must be objectively pass/fail and map to a scenario and/or a source story's acceptance criteria. These are the gate for "done". -->

- [ ] AC1 — <objectively verifiable statement>
- [ ] AC2 — …

## 8. Things to be aware of / constraints
<!-- Anything an implementer must respect. Dependencies on other work/specs; non-functional constraints (volume, latency, throughput); data contracts, formats, encodings, partitioning, schema evolution, idempotency; domain/medallion-layer constraints; security/privacy. Reference repo constraints where relevant (e.g. CLAUDE.md "Non-obvious constraints"). -->

## 9. Assumptions
<!-- Everything taken as true to write this spec that wasn't confirmed. Make each one visible so it can be challenged. -->

## 10. Open questions
<!-- Anything the interview could not resolve. Mark any that BLOCK implementation. If empty, write "None." -->

## 11. Traceability
<!-- Prove coverage both ways: every source story lands in the spec, and every spec requirement traces to a story (or an agreed addition). -->

| User story | Story acceptance criteria covered | Scenarios | Spec acceptance criteria |
|------------|-----------------------------------|-----------|--------------------------|
| US-001 | <summary> | <scenario names> | AC1, AC2 |
```
