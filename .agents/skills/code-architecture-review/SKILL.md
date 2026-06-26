---
name: code-architecture-review
description: Review code (a diff, a commit, or the whole repo) for conformance to this project's documented architecture contract in ARCHITECTURE.md — package structure, layering, and dependency-direction rules — and flag when ARCHITECTURE.md itself has gone stale. Evidence-backed and approval-gated; may legitimately find nothing. USE WHEN the user asks to review architecture, check layering/structure, validate a change against the architecture, or run "/code-architecture-review".
---

# Code Architecture Review

The job of this skill is to **check the code against the architecture this repo
has committed to**, not against generic best practice. The contract lives in
[`ARCHITECTURE.md`](../../../ARCHITECTURE.md): package structure, the medallion
layering, the dependency-direction rules, and per-module responsibilities. This
skill verifies the code still obeys those rules and surfaces drift in either
direction:

- **Code drifted from the contract** — a rule in ARCHITECTURE.md is violated.
- **Contract drifted from the code** — ARCHITECTURE.md describes a structure that
  no longer matches reality and must be updated.

This is review, not refactoring. **Finding nothing is a valid, common outcome.**
Do not invent findings to look productive — that pollutes trust in the review.
Every finding must cite evidence (`path:line`); never report a violation you
have not located in a file.

## When to use

- The user says "review the architecture", "check this against ARCHITECTURE.md",
  "does this change respect the layering", or runs `/code-architecture-review`.
- A new data source / asset / dbt model was added and you want to confirm it
  followed the §6 extension steps.
- Before merging structural changes (new package, new layer, moved module).

This skill is the project-specific complement to the generic `analyze-architecture`
skill: that one scores structural risk with deterministic analyzers; this one
checks conformance to *our* written rules. Use both when you want breadth + the
local contract.

## Scope

Default to the **pending changes** (uncommitted + this branch vs the default
branch). Review the whole repo only when the user asks for a full audit or when
there is no diff. State the scope you chose in the first line of the report.

```bash
git status --short
git diff                       # uncommitted
git diff main...HEAD           # branch changes (read-only; never push/checkout/reset)
```

## The rules to check (from ARCHITECTURE.md §3–§4)

Read `ARCHITECTURE.md` first — it is the source of truth; the list below is a
checklist of what it currently mandates. If ARCHITECTURE.md and this list
disagree, ARCHITECTURE.md wins and this skill is the thing that's stale.

1. **Single network edge.** Only `src/data_platform/assets/bronze.py` may make
   outbound network calls. Flag `requests`/`httpx`/`urllib`/socket use anywhere
   else (assets, models, config, dbt-side Python).
2. **Validate at the boundary, in order.** Any new ingest path defines a Pydantic
   record model (`models/schemas.py`) **and** a Pandera frame schema
   (`models/validation.py`), and the bronze asset applies record-then-frame
   before writing Parquet. Flag ingest that skips a gate or validates after write.
3. **dbt owns the warehouse; Python reads files.** No module other than the dbt
   layer opens `warehouse.duckdb` read-write. Python consumers (e.g. `gold.py`,
   notebooks) read the **Parquet artifacts**, not warehouse tables. Flag
   `duckdb.connect(<warehouse>)` for writing, or reads of warehouse tables from
   Python.
4. **Composition root is `definitions.py` only.** Asset modules must not import
   each other to wire dependencies; cross-asset edges go through
   `deps=[AssetKey(...)]` (with the **prefixed** key for dbt models, e.g.
   `["gold", "<model>"]`). Flag asset-to-asset imports and unprefixed dbt keys.
5. **Dependency direction.** `config.py` and `models/*` are leaves — they import
   nothing from `assets/` or `definitions.py`; `otel.py` depends only on
   `config`. `assets/*` may import `models`/`config`/`otel`. Flag any import that
   points "upward" or sideways between assets.
6. **Transformation lives in dbt, not Python.** New aggregation/joins/derivations
   belong in dbt SQL; Python assets do ingest (edge) and publish (consume) only.
   Flag pandas/DuckDB transformation logic that should be a dbt model.
7. **Config discipline.** New settings are typed fields in `config.py`
   (pydantic-settings), not ad-hoc `os.getenv` / `os.environ`. Flag scattered env
   reads.
8. **Structure changes update the contract.** A new top-level package, a new
   layer, a moved module, or a changed dependency rule must be reflected in
   ARCHITECTURE.md in the same change (routine model/asset additions that follow
   §6 do not). If the diff changes structure but not ARCHITECTURE.md, that is a
   finding.

## Workflow

### 1. Establish scope and load the contract
Determine diff vs full-repo (above). Read `ARCHITECTURE.md` in full so you review
against the live contract, not your memory of it.

### 2. Gather evidence
For each in-scope module, check the rules above. Prefer precise searches over
guesswork, e.g.:

```bash
# Rule 1 — network use outside bronze
grep -rnE "requests|httpx|urllib|socket" src/data_platform --include=*.py | grep -v "assets/bronze.py"
# Rule 4/5 — asset-to-asset or upward imports
grep -rnE "from \.\.assets|from \.assets|import .*assets\." src/data_platform/assets
# Rule 3 — Python opening the warehouse
grep -rnE "duckdb\.connect|warehouse\.duckdb" src/data_platform
# Rule 7 — ad-hoc env reads
grep -rnE "os\.getenv|os\.environ" src/data_platform | grep -v config.py
```
Searches are signals, not verdicts: open each hit and confirm it is a real
violation in context before reporting it. A grep match inside a comment, a
docstring, or `config.py` itself is not a finding.

### 3. Triage findings
For every confirmed finding record: the rule (by number/name), the evidence
(`path:line` + a short quote), why it breaks the contract, and a concrete fix.
Assign severity:
- **Blocker** — violates a hard rule that has caused real bugs (network edge,
  single-writer, unprefixed dep key, upward import).
- **Drift** — code and ARCHITECTURE.md disagree; one must change.
- **Advisory** — borderline / stylistic against the documented patterns.

Separate "code should change" from "ARCHITECTURE.md should change" — rule 8
findings are the latter.

### 4. Report (and gate any writes)
Output a concise report: scope line, then findings grouped by severity, each with
evidence and fix. End with an explicit verdict: **conforms** / **findings to
address**. If you found nothing, say so plainly — do not manufacture findings.

This skill **proposes**; it does not silently edit. If the user wants fixes
applied (code or an ARCHITECTURE.md update), make those changes only after they
approve, following the repo's normal conventions (ruff, conventional commits, no
quality-gate bypass). Never edit ARCHITECTURE.md to "make the review pass" without
the user agreeing that the contract — not the code — was wrong.

## Report template

```
# Architecture review — <scope: pending changes | branch vs main | full repo>

Verdict: <conforms | N findings>

## Blockers
- [Rule N: <name>] path/to/file.py:LL — <what> — fix: <how>

## Drift (code ↔ ARCHITECTURE.md)
- [Rule 8] <structure change in diff> not reflected in ARCHITECTURE.md §X — update <which section>

## Advisory
- ...

(If a section is empty, omit it. If all empty: "No architecture violations found.")
```
