# Retrospective spec guide

A retrospective spec uses the **same template** as a forward spec
([`../../specification/references/specification-template.md`](../../specification/references/specification-template.md))
— the same body-metadata lines (`**Feature directory**`, `**Created**`, `**Status**`,
`**Input**`) and the same keyword `## H2` sections. There is **no frontmatter** in
either model. What differs is the *source of truth* and a few field values, because
there were no user stories and the code already exists. The output path is a feature
directory: `specs/NNN-<slug>/spec.md`. Unlike a forward spec, a retrospective spec
does **not** write `.specify/feature.json` — it documents already-shipped work, it
doesn't hand off to the downstream plan→tasks→implement chain.

## Source of truth: code + diffs, not stories

A forward spec is written from user stories and describes behaviour that *will*
exist. A retrospective spec is reverse-engineered from the commits that delivered
the feature **and the current state of the files they touch**. Two consequences:

- **Stay at outcome altitude anyway.** Describe the observable behaviour the system
  now has (e.g. "ingests latin-1 main CSVs into one Parquet per source file,
  partitioned by family") — *not* a line-by-line narration of the diff. It must read
  like a spec an engineer could have built from, not a changelog.
- **Recover intent honestly.** The *what* is in the code; the *why* often isn't.
  Where you can't recover intent from the code, comments, or commit messages, put it
  in **Open questions** — never fabricate a confident requirement. You have explicit
  permission to write "intent not recoverable from the history".

## Metadata adaptations

Use the same body-metadata lines as a forward spec, and set:

- `**Status**: Implemented` — the code already ships; this isn't a draft of future work.
- `**Created**:` — today's date (the date the spec was reconstructed).
- Add one extra metadata line, `**Source commits**:`, listing the short SHAs the spec
  back-fills, in build order — e.g. `**Source commits**: 93f44d1, cb09e53, eba8f84,
  5147116`. This replaces user stories as the anchor for traceability (there were no
  stories — do not invent story ids).
- Note any existing specs this feature builds on or feeds (e.g. a provider spec
  relates to the canonical-domain spec it populates) in the Background & context
  section.

## Section adaptations

Most sections are written exactly as the template says. The ones that change:

- **§2 Background & context** — state plainly that this is a **retrospective
  specification reconstructed from commits `<first>..<last>`**, written after the
  fact to document already-shipped behaviour. Note if it relates to other specs.
- **§5 Behaviour (BDD)** — derive Given/When/Then scenarios from what the code
  actually does today (assets, models, validation, jobs/schedules). Each scenario
  must still be independently testable; prefer behaviour the existing tests already
  assert.
- **§9 Assumptions** — record where you inferred intent that the code makes
  *probable* but not *certain*.
- **§10 Open questions** — every piece of intent you could not recover. Mark none as
  "blocking implementation" (it's already implemented); frame them as "unverified
  intent" for a human to confirm.
- **Traceability** — replace the *User story* column with **Source commit(s)**:
  map each source commit (or group) → the scenarios it introduced → the functional
  requirements / success criteria (`FR-NNN` / `SC-NNN`). Coverage still runs both
  ways: every source commit's behaviour lands in the spec, and every spec requirement
  traces to a commit (or an agreed addition).

## Codebase accuracy review (Phase 5)

Run by an agent **other than the writer**, against the **current** codebase — not
the commit the spec was reconstructed from. For each spec, verify:

- [ ] Every **functional requirement / success criterion** (`FR-NNN` / `SC-NNN`) is
      true of the code as it stands now. Open the referenced file/asset/model and confirm.
- [ ] Every **BDD scenario** matches current behaviour — not behaviour a later commit
      changed. Where a source commit's behaviour was **later superseded**, the spec
      describes the *current* behaviour and notes the supersession explicitly (in the
      scenario, Assumptions, or Open questions) rather than asserting the old one.
- [ ] **Constraints (§8)** reflect real, current constraints — cross-check against
      `CLAUDE.md` *Non-obvious constraints* where relevant (single-writer DuckDB,
      asset-key vs dbt-selector naming, encodings, canonical match-id macro, etc.).
- [ ] **No fabricated requirement** — every statement traces to code or a diff;
      anything that doesn't is moved to Open questions.
- [ ] **Source commits are accurate** — the `**Source commits**:` SHAs are real
      commits in the history, in build order, and the feature `NNN-<slug>` directory
      name matches the work the spec documents.
- [ ] **Altitude** — the spec reads as outcome-focused behaviour, not a diff
      restatement.

Report drift back to the writer (or fix directly) and re-check until the spec
matches today's code. A spec that describes superseded behaviour as current is a
defect, not a stylistic nit.
