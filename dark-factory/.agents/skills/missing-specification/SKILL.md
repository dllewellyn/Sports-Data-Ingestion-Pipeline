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

The output is one or more new feature directories `specs/NNN-<slug>/spec.md` —
identical in format to forward specs (same template) but with **Status: Implemented**
and a **Source commits** metadata line tracing them to the commits that delivered
them rather than to a forward description. At the end, every substantive change in the
history is covered by a spec.

Because this is a *batch backfill* of many historical features, it does **not** write
`.specify/feature.json` — that pointer names the single *active* forward feature for the
downstream chain, and a retrospective sweep has no single active feature. It only creates
the spec directories.

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

1. **List the history.** Use the shared **read-only** helper, which emits the full
   history oldest → newest as `<full_sha>\t<iso_date>\t<subject>` (so feature arcs
   read in build order and you have stable SHAs to iterate over):

   ```bash
   bash .agents/skills/_shared/git-helpers/bash/git-history.sh list   # --since <ref> to limit the range
   ```

   (PowerShell: `pwsh .agents/skills/_shared/git-helpers/powershell/git-history.ps1 list`.)
2. **Read every existing spec.** For each `specs/NNN-<slug>/spec.md`, extract what it
   claims to cover: its summary, user scenarios, functional requirements, and success
   criteria. If a sibling `plan.md` exists in the same feature directory, skim it too —
   the plan often names the exact files/assets a spec touches, which makes commit→spec
   matching precise.
3. **Note the highest existing spec number.** New specs continue from there. Don't
   eyeball it — `bash .agents/skills/_shared/spec-helpers/next-number.sh specs`
   prints the next number, and `--count N` prints a collision-free block of `N`
   consecutive numbers, which is exactly what you hand to the parallel writers in
   Phase 4 so two new specs never collide.

### 2. Classify every commit, one at a time

First, **pre-filter the history by changed-path footprint** so you only spend
judgement where it's needed. This is a deterministic pass, not a verdict:

```bash
bash .agents/skills/_shared/git-helpers/bash/classify-commits.sh   # --since <ref> to limit the range
```

It tags each commit `AUTO-NONSUBSTANTIVE` (every path is docs/skills/CI/meta — record
and skip, no spec), `DEP` (only dependency manifests/locks — confirm no behavioural
change), or `CANDIDATE` (touches code/data/schema/config — needs your call). It
never decides *covered vs unspecified* — that still needs the diff. Use it to drop
the `AUTO-NONSUBSTANTIVE` commits straight into the non-substantive ledger and
concentrate on the `DEP`/`CANDIDATE` rows.

Then walk the `DEP`/`CANDIDATE` commits oldest → newest. For **each**, look at what it
actually changed and assign exactly one class. Inspect a commit with the shared
helper — it prints the metadata, name-status, and `--stat`, plus the full patch with
`--diff` where the stat is ambiguous:

```bash
bash .agents/skills/_shared/git-helpers/bash/git-history.sh show <sha>          # stat
bash .agents/skills/_shared/git-helpers/bash/git-history.sh show <sha> --diff   # + full patch
``` The full decision rubric — including how a Conventional
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
2. Create the feature directory `specs/NNN-<slug>/` and write its `spec.md` using the
   **exact** template at
   [`.agents/skills/specification/references/specification-template.md`](../specification/references/specification-template.md)
   — same headings, same order — with the retrospective adaptations in
   [`references/retro-spec-guide.md`](references/retro-spec-guide.md) (**Status:
   Implemented**, a **Source commits** metadata line instead of a forward Input,
   background states it was reconstructed). Do **not** write `.specify/feature.json`.
3. Validate the written file structurally and fix anything flagged:
   `python3 .agents/skills/_shared/spec-helpers/validate-spec.py specs/NNN-<slug>/spec.md`
   — `Implemented` is an accepted status; it checks the mandatory sections, the
   prioritised stories / BDD / FR / SC content, and Open Questions. A clean run is
   template conformance, not accuracy — that's Phase 5's job.
4. Return its file path plus a list of any intent it could **not** recover from the
   code (these become Open questions, not silent guesses).

Assign each sub-agent its own pre-allocated `NNN` so parallel writers don't collide —
get the block in one shot with
`bash .agents/skills/_shared/spec-helpers/next-number.sh specs --count <number-of-clusters>`.
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
