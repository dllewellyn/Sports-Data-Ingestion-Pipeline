---
name: missing-specification
description: Reconstruct the specifications that were never written. Walks the git history one commit at a time, classifies each commit as covered by an existing spec or unspecified, groups the unspecified work into candidate features, writes one retrospective specification per feature via a dedicated sub-agent, and reviews each against the current codebase for accuracy. USE WHEN the user wants to backfill missing specs, find work that shipped without a spec, retro-spec the history, or audit which commits aren't covered by anything under specs/.
---

# Missing specification (retrospective spec backfill)

Most of this repo's specs are written *before* the code, by the `specification`
skill. But work also lands without a spec — early commits, hot-fixes, whole data
sources built before the spec discipline existed. This skill **closes that gap in
reverse**: it reads the git history, finds the behaviour that shipped without a
specification, and reconstructs the missing specs from the code that actually exists.

The output is one or more new `specs/NNN-<slug>-specification.md` files —
identical in format to forward specs (same template) but marked
`status: implemented` and traced to the **commits** that delivered them rather than
to user stories. At the end, every substantive change in the history is covered by
a spec.

A good run is:
- **Evidence-driven** — every "this commit is/ isn't covered" call cites the spec it
  matches (or the absence of one) and the diff that proves it. No guessing.
- **Honest about altitude** — a retrospective spec describes the *observable
  behaviour the code now has*, not a line-by-line restatement of the diff. It still
  reads like a forward spec.
- **Accurate to the present** — code evolves after the commit that introduced it.
  Each reconstructed spec is reviewed against the **current** codebase, not just the
  commit it came from, and notes where later commits changed the behaviour.
- **Conservative about what needs a spec** — pure formatting, lint, dependency
  bumps, comment-only edits and skill/tooling changes are recorded but do **not**
  become specs. Only observable product behaviour, data contracts, and pipeline
  capability do.

## When to use this skill

- "Backfill the specs we never wrote." / "Which commits aren't covered by a spec?"
- "Retro-spec the history." / "Reconstruct the missing specifications."
- "Audit `specs/` against the git log and fill the gaps."
- After importing/inheriting a codebase whose `specs/` lags its history.

**When *not* to use it.** For *new* work that hasn't shipped yet, use the forward
`specification` skill. For checking whether code drifted from an *existing* spec,
that's a conformance review, not this. This skill only manufactures specs for work
that already landed and has none.

## The workflow

Phases 1–3 run in the main conversation (they need cheap, sequential judgement).
Phase 4 fans out **one sub-agent per candidate spec**. Phase 5 reviews each result.
Do not skip the classification pass — the spec set is only as trustworthy as the
coverage map underneath it.

### 1. Build the coverage baseline

Before classifying anything, know what already exists:

1. **List the history.** `git log --oneline --reverse` (oldest → newest, so feature
   arcs read in build order). Capture the full SHA list to iterate over.
2. **Read every existing spec.** For each `specs/NNN-<slug>-specification.md`, extract
   what it claims to cover: its summary, goals/non-goals, the capabilities in its BDD
   section, and its acceptance criteria. If a paired `specs/NNN-<slug>-plan.md`
   exists, skim it too — the plan often names the exact files/assets a spec touches,
   which makes commit→spec matching precise.
3. **Note the highest existing spec number.** New specs continue from there; increment
   as you create them within this run so two new specs never collide on a number.

### 2. Classify every commit, one at a time

Walk the history oldest → newest. For **each** commit, look at what it actually
changed (`git show --stat <sha>`, and the diff where the stat is ambiguous) and
assign exactly one class. The full decision rubric — including how a Conventional
Commit type is only a *hint*, never the decider — is in
[`references/classification-rubric.md`](references/classification-rubric.md).

- **Covered** — an existing spec's scope/scenarios/ACs (or its plan's steps) already
  describe this change. Record `sha → spec id`, with the matching capability as
  evidence.
- **Unspecified (substantive)** — introduces or changes observable behaviour, a data
  contract, a pipeline capability, a data source, or a schema, and **no** existing
  spec covers it. Record the SHA, subject, and a one-line description of the work.
  These are the gap.
- **Non-substantive** — pure `style`/lint/format, dependency bumps, comment- or
  doc-only edits, `.agents/skills` / tooling changes, CI/chore that alter no product
  behaviour. Record and move on — these do **not** get a spec.

Keep a running ledger (a scratchpad table is fine) of `sha | class | spec or note`.
For a long history, you may delegate the read of a contiguous range to an `Explore`
sub-agent to keep classification details out of the main context — but the
covered/unspecified/non-substantive *call* and the ledger stay here.

After the pass, **report the coverage map** to the user: counts per class, and the
list of unspecified-substantive commits. This is the moment to surface surprises
(e.g. "a whole data source shipped unspecified").

### 3. Group the unspecified work into candidate specs

Cluster the unspecified-substantive commits by the **outcome they jointly deliver** —
same data source, same subsystem, same capability — not by commit boundary. A
feature built across ten commits is *one* spec; a single self-contained change can
be its own. Grouping heuristics are in the rubric.

For each candidate cluster, draft a one-line scope (outcome + the commits in it) and
a proposed `NNN-<slug>` (slug from the outcome, kebab-case). **Play this grouping
back to the user and get confirmation before writing** — the cluster boundaries
decide how many specs you create and what each contains. If a cluster is ambiguous
(could be one spec or two), say so and propose the split.

### 4. Write each missing spec (one sub-agent per spec)

For **each** confirmed cluster, spawn a dedicated sub-agent (`general-purpose`) that
reconstructs the spec. Sub-agents can't interview the user, so hand each one
everything it needs up front. The sub-agent must:

1. Read the cluster's commits in full (diffs) **and** the current state of the files
   they touch — the spec describes what the code does *now*.
2. Write `specs/NNN-<slug>-specification.md` using the **exact** template at
   [`.agents/skills/specification/references/specification-template.md`](../specification/references/specification-template.md)
   — same frontmatter keys, same section order — with the retrospective adaptations
   in [`references/retro-spec-guide.md`](references/retro-spec-guide.md) (status
   `implemented`, traced to `source_commits` instead of user stories, background
   states it was reconstructed, traceability maps commits → scenarios → ACs).
3. Return its file path plus a list of any intent it could **not** recover from the
   code (these become Open questions, not silent guesses).

Assign each sub-agent its own pre-allocated `NNN` so parallel writers don't collide.
File-disjoint sub-agents (different spec files) can run in parallel.

### 5. Review each spec against the current codebase

A spec reconstructed from a diff can describe behaviour that a *later* commit already
changed. So every new spec gets an **independent** accuracy review — not by its
writer. Spawn a read-only reviewer (`Explore` or `general-purpose`) per spec that
checks each scenario and acceptance criterion against the **current** code and
reports drift. The accuracy checklist is in
[`references/retro-spec-guide.md`](references/retro-spec-guide.md) → *Codebase
accuracy review*. Feed the findings back to the writer (or fix directly) until the
spec matches today's code, with any "behaviour X was later superseded by Y" noted
explicitly rather than asserted as still-true.

### 6. Report

Show, for the run:
- the **coverage map** (commits per class; which existing spec covers what);
- the **new specs created** (path, the commits each one back-fills);
- any **open questions** where intent couldn't be recovered from the code;
- the new highest spec number.

Then state the gap is closed (or name the residual). Propose updating
[`specs/README.md`](../../../specs/README.md) only if its conventions changed.

## Guardrails

- **Never invent intent.** A spec is reconstructed from code + diffs; where the
  *why* isn't recoverable, it goes in Open questions, not into a confident-sounding
  fabricated requirement. You have explicit permission to say "intent unknown".
- **Don't spec the non-substantive.** Resist turning every `style`/`chore`/lint
  commit into a spec. Group by delivered outcome; record the rest and move on.
- **One outcome per spec.** Same rule as the forward skill — if a cluster pulls in
  two directions, split it rather than forcing one bloated spec.
- **Match the present, not the past.** The accuracy review against current code is
  mandatory; a spec that describes superseded behaviour as current is a defect.
- **Don't double-cover.** If, mid-run, you find an existing spec *does* cover a
  commit you'd flagged, reclassify it — don't create an overlapping spec.
- **Writer never certifies itself.** The Phase 5 accuracy review is always a separate
  agent from the Phase 4 writer.

## References

- [`references/classification-rubric.md`](references/classification-rubric.md) — the covered / unspecified / non-substantive decision rules, commit→spec matching, and grouping heuristics.
- [`references/retro-spec-guide.md`](references/retro-spec-guide.md) — how a retrospective spec differs from a forward one (frontmatter, source-commit traceability, reconstructing behaviour from code) and the codebase accuracy review checklist.
- [`.agents/skills/specification/references/specification-template.md`](../specification/references/specification-template.md) — the output format, shared verbatim with the forward `specification` skill.
