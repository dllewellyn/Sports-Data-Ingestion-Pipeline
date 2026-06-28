# Evaluation lenses

The three lenses to run over each subject in the changeset. Each check is tuned to
*this* repo. Every lens ends with the **don't-overengineer caveat** — the project's
`CLAUDE.md` says "Do not overengineer this project", so the bar for proposing an
abstraction is a *real, present* need, not a hypothetical.

A finding from any lens is only worth raising if it (a) cites `path:line` evidence
and (b) carries its ripple set (see `ripple-analysis.md`). Conformance violations
belong to `code-architecture-review`, not here — if you find one, note it and point
there.

---

## Lens 1 — Architecture quality (beyond conformance)

Conformance ("is it legal per ARCHITECTURE.md?") is `code-architecture-review`'s job.
Here you ask whether a *legal* change is nonetheless in a sub-optimal shape.

- **Placement / better home.** Is the new code in the module that owns its
  responsibility, or did it land somewhere convenient? E.g. a season/date helper
  added inside an asset module that really belongs in `football/season.py`; a
  validation rule inline in `bronze.py` that belongs in `models/validation.py`.
- **Cohesion / single responsibility.** Does each new file/function do one thing? A
  fat function that fetches *and* parses *and* validates *and* writes is a split
  candidate. Prefer the repo's existing "top level reads like prose" altitude.
- **Coupling that could be inverted.** Did the change introduce a hidden dependency
  (a module reaching into another's internals, config read ad-hoc instead of via
  `config.py`, an asset importing another asset to wire a dependency instead of a
  prefixed `deps=[AssetKey(...)]`)? Flag couplings that a small inversion removes.
- **Transformation in the wrong layer.** Aggregation/joins/derivations done in pandas
  or a raw DuckDB query in a Python asset that belong in a dbt model (ARCHITECTURE
  rule 6). This is both an architecture smell and a reuse/testability win (dbt tests).
- **Data-flow shape.** Did the change add/alter a stage in the bronze→silver→gold flow,
  a new external Parquet boundary, or a new asset edge? If the *shape* of the flow
  changed, the `ARCHITECTURE.md` data-flow diagram is part of the ripple set — this is
  the user's load-bearing example.

**Don't overengineer:** a direct, readable function is not a defect because it could
be "more layered". Only flag a split/inversion when the current shape is actually
hurting cohesion, testability, or the documented layering — not for symmetry.

---

## Lens 2 — Reuse potential (DRY, earned)

- **Duplication within the diff.** The same block copy-pasted across two new files /
  two asset branches. Candidate for a single shared helper *if* it recurs (see below).
- **Near-duplicates against existing code.** The new code reimplements something the
  repo already has. High-value targets in this repo: the **atomic temp-file + rename**
  write (used in football bronze), **season rollover** (`football/season.py`),
  **encoding handling** (latin-1 vs utf-8-sig), **skip-existing / discovery** logic,
  **Pydantic-record-then-Pandera-frame** validation wiring. If the new source
  hand-rolls any of these, propose consolidating on the existing implementation.
- **Diverged copies.** Two implementations of the *same* idea that have drifted (subtly
  different season math, two different "is current season" rules). Converging them is a
  correctness win as well as reuse.

**Rule of three / earned reuse:** propose an extraction only when there is a **real
second caller now** (or one inside this very changeset). Do *not* extract a helper "in
case" a future source needs it — that's speculative generality the project rule forbids.
One clean call-site is not duplication.

**Don't overengineer:** prefer promoting code to an existing shared module over
inventing a new abstraction layer. The goal is one obvious home for a thing, not a
framework.

---

## Lens 3 — Repackaging / generalisation

- **Source-specific → shared.** A helper written for one provider (e.g. football) that
  the data model clearly wants for others. Promote it from the source package to a
  shared module *when a second source is real or imminent*, not pre-emptively.
- **Reusable contract / IO / registry pattern.** A validation contract, file-IO
  routine, or registry shape that other ingest paths will reuse. Repackaging it as a
  named, importable unit (with its Pydantic/Pandera contract) pays off across sources.
- **Candidate skill (flag, don't build).** If the changeset reveals a *repeatable,
  multi-step procedure* nothing yet captures (e.g. "the full ritual for adding a new
  data source" beyond what ARCHITECTURE §6 documents), flag it as a **candidate skill**
  and route the authoring to `self-learn` — skill creation is `self-learn`'s job, not
  this skill's. Note it in the report's route column; don't scaffold it here.

**Don't overengineer:** generalisation is justified by a concrete consumer, not by
elegance. A one-off that genuinely serves one source is correct as a one-off. "This
*could* be a plugin system" is a red flag, not an opportunity.

---

## Quick triage heuristic

For each candidate, before it reaches the report, sanity-check:

1. **Evidence?** Can you point to `path:line`? If not, drop it.
2. **Earned?** Real second caller / concrete need / actual layering harm? If
   speculative, drop it.
3. **Ripple known?** Have you traced its coupled artifacts (`ripple-analysis.md`)? If
   not, it isn't ready.
4. **Right skill?** Conformance → `code-architecture-review`; new skill → `self-learn`.
   Only product-code improvement with a ripple set stays here.
