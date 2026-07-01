---
title: "Implementation Plan: Subdir Install Layout"
---

# Implementation Plan: Subdir Install Layout

**Feature directory**: `specs/002-subdir-install-layout/`
**Date**: 2026-06-30
**Spec**: `spec.md`
**Status**: Draft

## Summary

Relocate the framework payloads that `install.sh` copies into a target project (`.agents`, `.specify`,
`telemetry`, `docs`, `AGENTS.md`) from the target **root** into a single `dark-factory/` subdirectory,
and wire root-level symlinks that resolve into `dark-factory/` so Claude Code (`.claude`, `CLAUDE.md`)
and the framework helpers (`.agents/skills/...`, `.specify/feature.json`) keep working from the root.
The change adds two **new** root symlinks (`.agents`, `.specify`) the relocation makes mandatory,
recomputes every relocated link's relative target from its own location (the depth-correctness class
applies to `.claude/skills` and `CLAUDE.md`, not only the docs-site links), adds a **one-time
migration** that *moves* a prior flat install's real payloads into `dark-factory/` (leaving no dual
layout, per Constitution I), and preserves every existing guarantee (idempotent, no-clobber,
`--dry-run` zero-change, `--force`, self-copy/nested guards). The behaviour is proven Test-First by a
new `tests/test_install.py` that runs the real `install.sh` against a `tmp_path` target via subprocess
and asserts the filesystem — reusing the repo's existing pytest+uv+ruff harness, adding no new tooling.

## Technical Context

**Language/Version**: Bash (installer, POSIX-portable BSD+GNU); Python 3.12 (tests, `>=3.12`)
**Primary Dependencies**: coreutils (`cp -RPp`, `ln`, `mv`, `find`, `git`); pytest>=8 (dev group)
**Storage**: filesystem only (no DB, no warehouse) — the artifact is `install.sh` + a layout on disk
**Testing**: pytest invoking `install.sh` via `subprocess` against `tmp_path`, asserting with `pathlib`/`os.path`
**Target Platform**: developer CLI — `bash /path/to/dark-factory/install.sh <target>`
**Project Type**: single project (framework installer + its test)
**Performance Goals**: N/A (one-shot install of a small payload tree)
**Constraints**: BSD/macOS + GNU portability for symlink/copy/relative-depth math; single `dark-factory/`
subdir; no dual layout (Constitution I); no reward-hacking (Constitution II); Test-First (III); the
installer is product code (may `mv`/`rm -f` the *target*), but my own build steps must not use
`rm`/`git reset`/`git checkout`/repo-wide `sed`
**Scale/Scope**: one shell file (`install.sh` ~224 lines) + one new test file; five payloads, seven links

## Constitution Check

| Principle (constitution) | Compliance in this plan |
|--------------------------|-------------------------|
| I. No Backward Compatibility | The flat-layout copy path is **replaced** by the subdir path; the migration **moves** (not copies) flat payloads so no dual layout survives (FR-007/FR-008). No dual mode is added. The old root-link targets are rewritten, not kept alongside. |
| II. No Reward Hacking | No stubbed/faked install steps — relocation + symlinking genuinely produce the layout, asserted on a real filesystem. No gate is weakened: ruff + pytest run as written via `uv`. Migration `mv` is real (verified empirically), not a printed no-op. No convention-audit row uses the word that trips the gate; drafted rules are recorded pending approval, never silently committed. |
| III. Test-First | Every step writes a failing pytest assertion against the real installer first (red), then implements (green). The harness already exists (`tests/`, `pyproject.toml`, `conftest.py`); S0 only adds the first red test, no harness bootstrap needed. |
| IV. Honesty & Permission to Fail | Migration **names each relocated payload** (FR-017). The absent pre-commit gate and the two undocumented conventions are surfaced as Open Questions / pending-approval drafts, not papered over. |
| V. Surface Contradictions & Beneficial Changes | Surfaces: (a) `install.sh`'s docs reference a non-existent pre-commit gate; (b) no written shell/test convention exists; (c) the `docs/CLAUDE.md` link is a *sibling* link (its target string must NOT change) — a correction to the brief's framing. Beneficial follow-up: add a `.pre-commit-config.yaml` (separate change). |

## Project Structure

```text
specs/002-subdir-install-layout/
├── spec.md
├── plan.md                              # this file
├── research.md                          # Phase 0 — R1..R7 decisions/rationale/alternatives
├── data-model.md                        # Phase 1 — filesystem entities + state transitions
├── contracts/
│   └── installed-layout.md              # Phase 1 — the assertable post-install layout contract
├── quickstart.md                        # Phase 1 — runnable validation scenarios
├── drafted-rules-PENDING-APPROVAL.md    # Phase 2 — two drafted conventions awaiting user sign-off
└── tasks.md                             # Phase 2 — produced later by the `tasks` skill, NOT here
```

**Source layout touched**:
- `install.sh` (repo root) — the only product file changed.
- `tests/test_install.py` (new) — the Test-First harness for the installer.

## Skills to use

| Work area | Skill to use | Status |
|-----------|--------------|--------|
| Plan the implementation (this phase) | `plan` | available (running now) |
| Establish the two missing conventions before code | `create-rule` | available (used to draft; append deferred to user approval — non-interactive) |
| Decompose this plan into dependency-ordered tasks | `tasks` | available (next phase) |
| Cross-artifact consistency before build | `speckit-analyze` | available |
| Execute the tasks task-by-task with per-task review + commits | `implementor` | available |
| Per-step independent adversarial review (red/green verification) | `code-review` (or a fresh `general-purpose` reviewer per `references/self-review.md`) | available |
| Confirm the installer actually runs end-to-end | `verify` / `run` | available |
| Capture learnings after build | `self-learn` | available |
| Bespoke "test/edit a Bash installer" build skill | — | MISSING — no dedicated skill; proceed via `implementor` against the drafted shell+test conventions, then `self-learn` to codify if it recurs |

## Convention & rule audit (resolved before implementation)

Sources searched: `.specify/memory/constitution.md` (canonical), root `CLAUDE.md`/`AGENTS.md` (speckit
stub — no conventions), `pyproject.toml` (ruff E,W,F,I,UP,B,C4,SIM; line-length 100; `pytest>=8`;
`testpaths=["tests"]`), `conftest.py`, `.claude/settings.json` (telemetry hooks only), existing code
(`install.sh`, `.agents/skills/**/scripts/bash/*.sh`, `tests/test_telemetry_hooks.py`,
`tests/test_demo_emit.py`). No `ARCHITECTURE.md`, no `.claude/rules/`, **no `.pre-commit-config.yaml`**.

| Artifact type | Governing convention | Status |
|---------------|----------------------|--------|
| Edits to the Bash installer (`install.sh`) | DRAFT RULE 1 (Bash conventions: `set -euo pipefail`, quoting, `cp -RPp`/`ln`, literal relative targets, BSD/GNU portability, dry-run wrapper, no-clobber) — `drafted-rules-PENDING-APPROVAL.md`; backed by the existing `install.sh` + helper-script patterns | created this run (pending approval) |
| pytest test of a shell script (`tests/test_install.py`) | DRAFT RULE 2 (subprocess + `tmp_path` + `pathlib`/`os.path` assertions; reuse pytest+uv; no `bats`) — `drafted-rules-PENDING-APPROVAL.md`; backed by `tests/test_telemetry_hooks.py` precedent | created this run (pending approval) |
| pytest harness (collect + run under `uv`) | exists — `pyproject.toml` `testpaths=["tests"]`, `conftest.py`, `pytest>=8`; verified 17 tests pass today | exists |
| Lint/format of new Python | exists — ruff configured in `pyproject.toml`, run `uv run ruff check/format`; verified runnable | exists |
| `.gitignore` merge behaviour | exists — `merge_gitignore` in `install.sh` (append-without-duplicate); research R3 confirms no `dark-factory/temp/` entry needed | exists |
| Quality gate the build is reviewed against | ruff + pytest via `uv` (NOT pre-commit — none exists); recorded as Open Question for user confirmation | exists (named explicitly; pre-commit absence surfaced) |

**Gate status: zero unresolved rows.** Both missing conventions are **drafted and recorded pending
user approval** (a blocker in Open Questions), not left open and not silently committed. Implementation
steps S1+ depend on these being approved + committed first (S0 covers that gate).

## Testable units (BDD → tests)

All tests live in `tests/test_install.py`, run the real `install.sh` via `subprocess` against a
`tmp_path` TARGET (SOURCE = the repo root), and assert with `pathlib`/`os.path`. Contract refs are to
`contracts/installed-layout.md`.

| Unit | Spec trace (scenario / FR / SC) | Test facility | Failing-first assertion |
|------|----------------------------------|---------------|-------------------------|
| U1 fresh install puts payloads under `dark-factory/`, none real at root | US1 AS1 / FR-001, FR-002 / SC-001 / C-LAYOUT-1 | pytest+subprocess+fs | After a clean-target install, `dark-factory/{.agents,.specify,telemetry,docs,AGENTS.md}` are real and **no** real copy exists at root — fails today (installer copies to root) |
| U2 required root symlinks exist and resolve into `dark-factory/` | US1 AS2 / FR-003 / SC-002 / C-LAYOUT-2 | pytest+subprocess+fs | `.claude/skills`, `CLAUDE.md`, `.agents`, `.specify` are symlinks whose `realpath` is under `dark-factory/` — fails today (`.agents`/`.specify` not links; `.claude/skills`/`CLAUDE.md` target the old flat paths) |
| U3 docs-site links wired with +1 `../` and resolve to root specs/plans | US1 AS2 / FR-005, E6 / C-LAYOUT-2 | pytest+subprocess+fs | `dark-factory/docs/src/content/docs/{specs,plans}` `readlink` == `../../../../../{specs,plans}` and resolve to root `specs/`/`plans/` — fails today (links at old depth/location) |
| U4 `docs/CLAUDE.md` stays conditional + sibling target unchanged | FR-005, CHK025 / C-LAYOUT-2 | pytest+subprocess+fs | When SOURCE carries the link, `dark-factory/docs/CLAUDE.md` is a symlink with text `AGENTS.md` resolving to `dark-factory/docs/AGENTS.md` — fails today (wrong location) |
| U5 `specs/`/`plans/` real dirs at root with `.gitkeep`, never under subdir | US1 AS3 / FR-004 / SC-002 / C-LAYOUT-3 | pytest+subprocess+fs | Root `specs/`/`plans/` are real dirs with `.gitkeep`; not symlinks; `dark-factory/specs` absent — passes-as-is risk: assert also that they are NOT relocated |
| U6 helper paths resolve from root | US1 AS4 / SC-003 | pytest+subprocess+fs | From TARGET root, `.agents/skills/<a skill>` and `.specify` resolve to existing paths under `dark-factory/` — fails today |
| U7 migration moves flat payloads into subdir, none real at root | US2 AS1 / FR-006, FR-007 / SC-005 / C-LAYOUT-4 | pytest+subprocess+fs | Seed flat layout; after run, zero real payloads at root, all under `dark-factory/` — fails today (no migration) |
| U8 migration repoints root symlinks (default path, resolve) + names relocated payloads | US2 AS2 / FR-006, FR-017 / SC-005 / C-LAYOUT-4 | pytest+subprocess+fs(+stdout) | After migration on the **default (no-`--force`) path**, the stale managed root links (incl. `CLAUDE.md`) are refreshed and `realpath`-resolve into `dark-factory/` (no dangling link); stdout names each relocated payload — fails today |
| U9 migration preserves user content | US2 AS3 / FR-014, E7 / C-LAYOUT-3 | pytest+subprocess+fs | Seed `specs/mine.txt`; after migration it is byte-identical and still at root — must hold |
| U10 partial migration converges (mixed flat+subdir) | E3 | pytest+subprocess+fs | Seed some payloads real-at-root, some already symlinked; after run, single subdir layout, no real at root — fails today |
| U11 dry-run makes zero filesystem changes (clean + flat seeds) | US3 AS1/AS2 / FR-009 / SC-004 / C-LAYOUT-5 | pytest+subprocess+fs-snapshot | `find`+stat snapshot identical before/after `--dry-run` on both seeds — must hold; today dry-run exists but doesn't cover migration/new layout |
| U12 dry-run output describes subdir payloads, links+targets, relocations | US3 / FR-009 / C-LAYOUT-5 | pytest+subprocess+stdout | Dry-run stdout mentions `dark-factory/` payloads, each link + target, and (flat seed) the relocations — fails today |
| U13 idempotent no-`--force` re-run leaves layout identical (incl. E2 non-migration stale-link skip) | US4 AS1 / FR-010, E2 / SC-006 / C-LAYOUT-6 | pytest+subprocess+fs | Second run (no real payloads at root → no migration) copies/relocates nothing new; fs identical to after first run; a root symlink at the old flat location is left untouched and reported skipped without `--force` (E2, non-migration path) — must hold. (The migration-path repoint of a stale link is U8, not this unit.) |
| U14 no-clobber of a real file where a link belongs (warn) | US4 AS3 / FR-011, E1 / C-LAYOUT-6 | pytest+subprocess+fs(+stderr) | Pre-place a real `CLAUDE.md`; run without `--force` → left untouched + warning on stderr — must hold |
| U15 `--force` repoints links + overwrites copied payloads, no error | US4 AS2 / FR-012 / SC-006, E2, E4 / C-LAYOUT-6 | pytest+subprocess+fs(+rc) | After `--force` re-run, stale links repointed into `dark-factory/`, copied files refreshed, exit 0 — fails today (no repoint to subdir) |
| U16 guards: self-copy / nested / subdir-collision refusal | E5 / FR-013 / C-LAYOUT-7 | pytest+subprocess+rc | SOURCE==TARGET, nested either way, and `dark-factory/` colliding with SOURCE each exit non-zero with an error — extends today's guards |
| U17 `.gitignore` merge unchanged for `temp/` (no `dark-factory/temp/`) | FR-015 / research R3 | pytest+subprocess+fs | After install, `.gitignore` contains `temp/`/`__pycache__/`/`*.pyc` once each, no `dark-factory/temp/`, user rules intact — must hold |
| U18 final summary / next-steps point into `dark-factory/` | FR-016 | pytest+subprocess+stdout | Post-install stdout's "Next steps" reference `dark-factory/docs` and `dark-factory/telemetry` (paths that exist) — fails today (points at root paths) |
| U19 docs-site links are the corrected 5-level target on the **default (no `--force`) path** | US1 AS2 / FR-005, E6 / SC-002 | pytest+subprocess+fs | After a **no-`--force`** clean install, `dark-factory/docs/src/content/docs/specs` `readlink` == `../../../../../specs` (5 levels) and resolves to root `specs/` — fails today because `cp -RPp` copies SOURCE's stale 4-level link in and `link_one` only repoints under global `--force`; pins that the copied-in original was excluded and the link created fresh |

## Guardrail register

| Guardrail | How verified in place | Covered by step |
|-----------|------------------------|-----------------|
| ruff check + format clean (Python tests) | `uv run ruff check tests/ && uv run ruff format --check tests/` clean | S0, all |
| pytest harness collects + runs under uv | `uv run pytest -q` (existing 17 + new) green | S0, all |
| Installer behaviour asserted on a real filesystem (no eyeballing) | `uv run pytest tests/test_install.py` red→green per unit | S1–S6 |
| Dry-run zero-change invariant | snapshot-compare in U11 green | S5 |
| Idempotency / re-run safety | U13 green (run twice, compare) | S6 |
| No-clobber of real files | U14 green (warn, not clobber) | S6 |
| BSD/GNU portability of symlink/copy/relative-depth math | tests run on macOS (BSD); literal target strings; `cp -RPp` retained | S1–S3 |
| Installer guards preserved + extended | U16 green | S6 |
| Conventions committed before dependent code | S0 gate: drafted rules approved + committed (BLOCKER) | S0 |
| Constitution principles respected | I no-dual-layout (U7/U10) · II no faked steps / gate intact · III red-first · IV migration names payloads (U8) | all |

## Implementation Steps

Setup (S0) lands the conventions + first red test. S1–S6 follow the red→green→refactor loop, each with
an independent self-review (`references/self-review.md`) before the atomic commit. Steps are ordered so
the fresh-install layout exists before migration (which reuses the link-wiring), and guards/idempotency
land last as they wrap the whole behaviour.

### Step S0 — Establish conventions + first failing installer test (setup gate)
- **Goal:** Close the convention-audit gate (get DRAFT RULE 1 & 2 approved and committed to the
  constitution) and add the first red test proving the harness exercises the real `install.sh`.
- **Spec trace:** setup — enables S1–S6; satisfies the Phase-2 hard gate + Constitution III harness check.
- **Red (failing test first):** add `tests/test_install.py` with a helper that runs
  `subprocess.run(["bash", str(INSTALL_SH), str(tmp_path)], capture_output=True, text=True)` and one
  assertion that `dark-factory/AGENTS.md` exists under the target after a clean install. Run
  `uv run pytest tests/test_install.py -q` and confirm it **fails red** (today the installer writes
  `AGENTS.md` to the target root, not `dark-factory/`).
- **Implementation:** none for the installer yet. The only "implementation" here is: (a) **BLOCKER** —
  obtain user approval for the two drafted rules and commit them into
  `.specify/memory/constitution.md` (`docs:` commit) as their own atomic commit; (b) commit the new
  test file's scaffolding. No installer behaviour changes in S0.
- **Green criterion:** `uv run ruff check tests/test_install.py` clean; the test file collects under
  `uv run pytest tests/test_install.py -q` and the single assertion is **red** for the right reason
  (AGENTS.md at root, not subdir). (Green for this assertion arrives in S1 — S0's "done" is: harness
  wired, rule committed, red confirmed.)
- **Guardrails to satisfy:** conventions committed before dependent code; ruff clean; harness runs.
- **Self-review checkpoint:** an independent reviewer confirms the two rules were *approved by the user*
  (not self-approved) and committed; the test genuinely shells out to the real `install.sh` (not a
  copy/mock) and the red is for the intended reason; no `bats`/new tooling introduced; no gate weakened.

### Step S1 — Place payloads under `dark-factory/` on fresh install
- **Goal:** Make `copy_payload` write into `dark-factory/<rel>` so the five payloads land under the
  subdir and nothing real is written at the target root.
- **Spec trace:** US1 AS1 / FR-001, FR-002 / SC-001 — units U1.
- **Red (failing test first):** U1 — clean-target install asserts `dark-factory/{.agents,.specify,
  telemetry,docs,AGENTS.md}` real and **no real** copy of any at root. Confirm red.
- **Implementation:** introduce a `SUBDIR="dark-factory"` constant; change `copy_payload`'s `dest` to
  `"$TARGET/$SUBDIR/$relitem"` (the payload tree now roots at `$TARGET/$SUBDIR`). Extend the
  SOURCE/TARGET guards so `$TARGET/$SUBDIR` cannot equal/contain SOURCE (FR-013 — implemented fully in
  S6 but the path constant is introduced here). Keep `cp -RPp` (R6). **Handoff note for S3:** `cp -RPp`
  preserves SOURCE's three internal docs symlinks (`docs/CLAUDE.md`,
  `docs/src/content/docs/{specs,plans}`) verbatim with their **old 4-level** target text — do **not**
  rely on the copy producing correct docs links; S3 excludes those three from `copy_payload` and
  re-creates them with corrected targets.
- **Green criterion:** `uv run pytest tests/test_install.py -k U1 -q` green; `uv run ruff check tests/`
  clean.
- **Guardrails to satisfy:** payloads-under-subdir; BSD/GNU `cp -RPp`; no real payload at root.
- **Self-review checkpoint:** reviewer confirms U1 asserts the **absence** of real payloads at root
  (not just presence under subdir), the test can fail (revert the dest change → red), `cp -RPp` retained
  (non-link payload files preserved), no hardcoded target path that would only pass for one fixture.
  (The copied-in docs symlinks are knowingly stale here and are corrected in S3 — not S1's concern.)

### Step S2 — Wire root symlinks (`.claude/skills`, `CLAUDE.md`, new `.agents`, `.specify`) into the subdir
- **Goal:** Repoint/ add the root links so each resolves into `dark-factory/`.
- **Spec trace:** US1 AS2, AS4 / FR-003 / SC-002, SC-003 — units U2, U6.
- **Red (failing test first):** U2 + U6 — assert `.claude/skills -> ../dark-factory/.agents/skills`,
  `CLAUDE.md -> dark-factory/AGENTS.md`, new `.agents -> dark-factory/.agents`,
  `.specify -> dark-factory/.specify`, each `realpath` existing under `dark-factory/`; and that
  `.agents/skills/<a real skill dir>` resolves from root. Confirm red.
- **Implementation:** replace the `link_one` calls (`install.sh:192-193`) with the corrected targets and
  **add** `link_one ".agents" "$SUBDIR/.agents"` and `link_one ".specify" "$SUBDIR/.specify"`
  (research R1). Targets are literal strings (R6).
- **Green criterion:** `uv run pytest tests/test_install.py -k "U2 or U6" -q` green; ruff clean.
- **Guardrails to satisfy:** every required link resolves into subdir; literal targets (portability).
- **Self-review checkpoint:** reviewer confirms all four link targets match research R1 exactly, the
  test asserts **resolution** (`realpath` exists) not mere existence, no previously-wired link dropped,
  and `.agents`/`.specify` are genuinely new links (not accidentally pointing at a stale flat path).

### Step S3 — Wire the docs-site links at the corrected depth (+ conditional `docs/CLAUDE.md`)
- **Goal:** Move the docs-site link wiring under `dark-factory/docs/...` with +1 `../`, keeping
  `docs/CLAUDE.md` conditional and its sibling target string unchanged — **and ensure the corrected
  links win on the DEFAULT (no `--force`) path**.
- **Spec trace:** US1 AS2 / FR-005, E6, E1/FR-011 / SC-002 — units U3, U4, **U19**.
- **Red (failing test first):** U3 + U4 + **U19** — assert (on a **default, no-`--force`** install)
  `dark-factory/docs/src/content/docs/{specs,plans}` have text `../../../../../{specs,plans}` resolving
  to root `specs/`/`plans/`; and (when SOURCE carries it) `dark-factory/docs/CLAUDE.md` text `AGENTS.md`
  resolving to `dark-factory/docs/AGENTS.md`. U19 specifically pins that the link is the **corrected
  5-level** one, not the copied-in stale 4-level link. Confirm red (today the installer copies SOURCE's
  docs links verbatim, so on the default path the link is the broken 4-level original).
- **Implementation (pinned mechanism — option c, exclude-then-link-fresh):**
  - **The hazard:** `copy_payload "docs"` uses `cp -RPp`, which preserves symlinks; SOURCE's three
    docs symlinks (`docs/CLAUDE.md`, `docs/src/content/docs/specs`, `docs/src/content/docs/plans` — the
    *only* three copied symlinks under `docs/`; `node_modules` is pruned, verified) would land in
    `dark-factory/docs/...` carrying their **old 4-level** text. `link_one` only repoints an existing
    symlink when global `FORCE=1` (`install.sh:129-137`: `[ -L "$full" ]` → SKIPPED otherwise), so a
    normal run would ship the broken 4-level link. Merely changing the target strings in the `link_one`
    calls does **not** fix this — the copied-in link pre-exists and wins.
  - **The fix:** in `copy_payload`, **exclude those three exact relitems from being copied** (a path
    skip alongside the existing `*.pyc`/`.DS_Store` skip, e.g.
    `case "$relitem" in docs/CLAUDE.md|docs/src/content/docs/specs|docs/src/content/docs/plans) continue ;; esac`
    — note these are matched at the **subdir-relative** payload path; adjust to the actual `relitem`
    form used). Because they are never copied, the `dark-factory/docs/...` link paths do **not**
    pre-exist, so `link_one` creates them **fresh** with the corrected targets on the **default path**
    (no `--force`, no `rm`).
  - Then wire the links: `link_one "$SUBDIR/docs/src/content/docs/specs" "../../../../../specs"`,
    `link_one "$SUBDIR/docs/src/content/docs/plans" "../../../../../plans"` (five `../`, research R1),
    and keep `[ -L "$SOURCE/docs/CLAUDE.md" ] && link_one "$SUBDIR/docs/CLAUDE.md" "AGENTS.md"`
    (conditional preserved, sibling target unchanged — research R1/R2).
  - **No-clobber preserved:** if a user has placed a **real** (non-symlink) file at one of those three
    paths, `link_one` already leaves it untouched and warns (`install.sh:138-141`) — excluding the
    SOURCE copy does not change that (E1/FR-011 still honoured). `--force` still repoints if a stale
    link somehow pre-exists.
- **Green criterion:** `uv run pytest tests/test_install.py -k "U3 or U4 or U19" -q` green (U19 run
  **without** `--force`); ruff clean.
- **Guardrails to satisfy:** docs links resolve to root specs/plans **on the default path**; conditional
  preserved; no-clobber of a real file at those paths; BSD/GNU.
- **Self-review checkpoint:** reviewer confirms (1) the three docs symlinks are **excluded from
  `copy_payload`** so they are never copied in (grep the diff for the skip), and the links are created
  fresh — verified by a **no-`--force`** install producing the 5-level target (U19), not the copied-in
  4-level one; (2) the implementer did **not** merely change target strings while leaving the
  copy-then-skip hazard in place (that would regress U19); (3) the +1 `../` math resolves on this (BSD)
  platform; (4) `docs/CLAUDE.md` target string is **not** changed to `../AGENTS.md` (sibling link;
  research R2) and stays conditional; (5) a pre-existing **real** file at those paths is still left +
  warned (E1).

### Step S4 — Keep `specs/`/`plans/` real at root; `.gitignore`/summary correct for the new layout
- **Goal:** Preserve `ensure_keepdir` for `specs`/`plans` at root, confirm `.gitignore` needs no
  `dark-factory/temp/`, and update the final summary / "Next steps" to point into `dark-factory/`.
- **Spec trace:** US1 AS3 / FR-004, FR-015, FR-016 / SC-002 — units U5, U17, U18.
- **Red (failing test first):** U5 (real dirs + `.gitkeep`, not symlinks, no `dark-factory/specs`),
  U17 (`.gitignore` has `temp/` once, no `dark-factory/temp/`, user rules intact), U18 (Next-steps
  stdout references `dark-factory/docs` + `dark-factory/telemetry`). Confirm U18 red (today it prints
  root paths); U5/U17 may pass partly — assert the not-relocated/no-extra-entry negatives so they bite.
- **Implementation:** leave `ensure_keepdir "specs"` / `"plans"` at root unchanged; leave
  `merge_gitignore` entries unchanged (research R3); update the heredoc "Next steps" (`install.sh:215-223`)
  to `dark-factory/docs` / `dark-factory/telemetry` and the skills line to the corrected link.
- **Green criterion:** `uv run pytest tests/test_install.py -k "U5 or U17 or U18" -q` green; ruff clean.
- **Guardrails to satisfy:** project content real at root; `.gitignore` merge unchanged; summary honest.
- **Self-review checkpoint:** reviewer confirms `specs`/`plans` are asserted to be **real and at root**
  (negative: not symlinks, not under subdir), no `dark-factory/temp/` was added (matches R3), and the
  Next-steps paths actually exist post-install (FR-016 — no dangling guidance).

### Step S5 — `--dry-run` covers the new layout + migration with zero changes
- **Goal:** Ensure every new mutation (subdir copy, new links, migration moves) routes through the
  `run`/dry-run wrapper so `--dry-run` prints the full plan and changes nothing.
- **Spec trace:** US3 AS1/AS2 / FR-009 / SC-004, E8 — units U11, U12.
- **Red (failing test first):** U11 (snapshot identical before/after `--dry-run` on clean **and** flat
  seeds) + U12 (dry-run stdout describes subdir payloads, each link+target, and flat-seed relocations).
  Confirm red (migration printing doesn't exist yet; written in S6 — so order S6 before the migration
  half of U11/U12, or gate U11/U12's flat-seed cases behind S6; see Sequencing).
- **Implementation:** route the new link calls and (S6's) migration `mv` through `run`; add dry-run
  print lines naming the planned `dark-factory/` payloads, the links + targets, and the relocations.
- **Green criterion:** `uv run pytest tests/test_install.py -k "U11 or U12" -q` green; ruff clean.
- **Guardrails to satisfy:** dry-run zero-change invariant (snapshot compare); output completeness.
- **Self-review checkpoint:** reviewer confirms the snapshot compare includes the **flat-seed** case
  (the one most likely to mutate), every new mutation is wrapped by `run` (grep the diff for un-wrapped
  `mv`/`ln`/`cp`), and dry-run truly writes nothing (inode/mtime unchanged), not merely "looks unchanged".

### Step S6 — Migration (move flat→subdir, repoint, name payloads), idempotency, no-clobber, guards, `--force`
- **Goal:** Add the one-time migration (detect real-at-root, `mv` into subdir, repoint links, name each
  relocated payload), the extended subdir-collision guard, and verify idempotency/no-clobber/`--force`.
- **Spec trace:** US2 AS1/AS2/AS3, US4 AS1/AS2/AS3, E1–E5, E7 / FR-006, FR-007, FR-010, FR-011, FR-012,
  FR-013, FR-014, FR-017 / SC-005, SC-006 — units U7, U8, U9, U10, U13, U14, U15, U16.
- **Red (failing test first):** U7 (no real at root post-migration), U8 (links repointed + stdout names
  payloads), U9 (user content preserved), U10 (partial converges), U13 (idempotent re-run), U14
  (no-clobber real file + warn), U15 (`--force` repoints + refreshes, rc 0), U16 (guards refuse incl.
  subdir collision). Confirm red.
- **Implementation:** add migration detection `for p in .agents .specify telemetry docs AGENTS.md:
  if [ -e "$TARGET/$p" ] && [ ! -L "$TARGET/$p" ]` (research R4); for each, `run mkdir -p
  "$TARGET/$SUBDIR"` then `run mv "$TARGET/$p" "$TARGET/$SUBDIR/$p"` with no-clobber/`--force` semantics
  (R5), and `info "relocated: $p -> $SUBDIR/$p"` (FR-017). Track whether any relocation happened
  (`migrated=1`). Replace the existence-only prior-install note (`install.sh:180-182`) with this
  real-payload detection. **Repoint stale managed root symlinks during migration (FR-006):** when
  `migrated=1`, clear (`rm -f`) any **managed** root link (`.claude/skills`, `CLAUDE.md`, `.agents`,
  `.specify`) that currently exists **as a symlink** (`[ -L ]` only — never a real file/dir, so
  no-clobber FR-011 is preserved), routing the clear through the `run`/dry-run wrapper (dry-run safe), so
  the unchanged `link_one` wiring recreates each fresh into `dark-factory/` on the **default (no-`--force`)
  path** — no dangling `CLAUDE.md` after the root `AGENTS.md` is relocated. This fires **only** when a
  migration occurred (`migrated=1`); a non-migration idempotent re-run (`migrated=0`) never clears an
  existing link, so E2's skip-without-`--force` and FR-010 stay intact (that case is unit U13).
  `link_one` itself is **not** modified. Add the subdir-collision guard
  (`case "$SOURCE/" in "$TARGET/$SUBDIR/"*) die ...`). `link_one` already handles no-clobber-of-real
  (warn) and `--force` repoint; verify it covers the new links.
- **Green criterion:** `uv run pytest tests/test_install.py -q` (the whole file incl. U7–U16) green;
  full suite `uv run pytest -q` green; `uv run ruff check tests/ && uv run ruff format --check tests/` clean.
- **Guardrails to satisfy:** no dual layout (U7/U10); migration names payloads (U8); user content safe
  (U9); idempotent (U13); no-clobber (U14); `--force` (U15); guards (U16).
- **Self-review checkpoint:** reviewer hunts hardest here — confirms migration is a real `mv` (not a
  printed no-op), **no real payload remains at root** after migration (the Constitution-I invariant),
  detection uses `-e && ! -L` (not existence-only, which would misfire on a migrated target), the
  partial-migration case genuinely converges, no user file is moved/clobbered, `--force`/no-clobber are
  not weakened to pass, and the new subdir-collision guard actually refuses (rc != 0). Additionally
  confirms the **migration repoint (FR-006)**: when a migration occurs (`migrated=1`) the stale
  managed root symlinks are cleared (`rm -f`) **only if they are symlinks** (`[ -L ]`; a real file at a
  managed path is never removed — grep the diff to confirm the guard) and recreated fresh into
  `dark-factory/` on the **default (no-`--force`) path** so post-migration `CLAUDE.md` and the other
  root links resolve (no dangling link — U8 asserts resolution on the default path); that this repoint
  is **gated on `migrated=1`** and does **not** fire on a non-migration idempotent re-run (`migrated=0`),
  so E2's skip-without-`--force` and FR-010 remain intact (U13); and that `link_one` itself is
  unmodified. Any gate-bypass or faked step is an automatic REWARD-HACKING verdict → escalate, do not
  self-approve.

## Sequencing & dependencies

```
S0 (conventions approved+committed; first red test)        [BLOCKER gate]
  └─> S1 (payloads → dark-factory/)        # subdir must exist before links point into it
        └─> S2 (root links: .claude/skills, CLAUDE.md, new .agents/.specify)
        └─> S3 (docs-site links +1 ../, conditional docs/CLAUDE.md)
              └─> S4 (specs/plans real at root; .gitignore; summary)
                    └─> S6 (migration + idempotency + no-clobber + guards + --force)
                          └─> S5 (dry-run covers everything incl. migration)
```

- **S0 is a hard gate**: S1+ cannot start until the two drafted conventions are user-approved and
  committed (Phase-2 hard gate; the self-review checkpoints reference them).
- **S1 before S2/S3**: links must resolve into a subdir that already holds the payloads.
- **S6 before the flat-seed half of S5**: the dry-run *migration* output (U11/U12 flat-seed cases) can
  only be asserted once migration printing exists. The clean-seed dry-run half of S5 can land right
  after S4; the flat-seed half is verified after S6. Net: write S5's clean-seed dry-run early, complete
  S5 (flat-seed) immediately after S6. (The `tasks` skill will split this into two task rows.)
- Repo gotcha (the S3 correction): `cp -RPp` in `copy_payload "docs"` preserves SOURCE's three internal
  docs symlinks (`docs/CLAUDE.md`, `docs/src/content/docs/{specs,plans}`) verbatim with their old
  4-level text. `link_one` only repoints a pre-existing link under global `--force`, so on the default
  path the broken 4-level link would ship. S3 therefore **excludes those three from `copy_payload`** so
  the link paths don't pre-exist and `link_one` creates them fresh with the corrected 5-level targets on
  the default (no-`--force`) path — no `rm`, no `--force` dependency. U19 pins this on the default path.

## Complexity Tracking

None. No Constitution Check violation requires justification; the design replaces the flat path with no
dual mode and adds no backward-compat scaffolding.

## Assumptions

- The subdirectory is literally `dark-factory/` (spec Assumption; the description names it).
- SOURCE for the tests is the repo root itself (where `install.sh` lives); running it against an
  external `tmp_path` TARGET satisfies the nested guards (verified).
- The user accepts **ruff + pytest via `uv`** as the quality gate for this feature (no pre-commit config
  exists). Recorded as an Open Question; the plan proceeds under this assumption.
- The two drafted conventions will be approved as written (or amended) by the user before S1; they are
  not committed without that approval (non-interactive constraint).
- `git-sync-extractor` writes `temp/` at the target git-root (verified, research R3), so the existing
  root `temp/` `.gitignore` entry suffices and the merge is unchanged.
- The docs-site `specs`/`plans` links keep their SOURCE form but gain one `../`; `docs/CLAUDE.md` keeps
  its sibling `AGENTS.md` target string unchanged (verified, research R1/R2).

## Open Questions

- **BLOCKER — convention approval.** Two conventions (DRAFT RULE 1: Bash; DRAFT RULE 2: shell-script
  testing) are **drafted, pending user approval** in `drafted-rules-PENDING-APPROVAL.md`. They must be
  approved and committed to `.specify/memory/constitution.md` before S1. They are not committed silently
  (Constitution II — constraint changes require approval, never self-approval). The convention-audit gate
  is closed *for plan-validation* by recording them as "created this run (pending approval)", but the
  *build* must not begin until they are signed off.
- **Quality gate clarification (non-blocking).** `install.sh`'s docs and the constitution reference
  `uv run pre-commit run --all-files`, but **no `.pre-commit-config.yaml` exists**. The plan uses
  `uv run ruff` + `uv run pytest` as the gate. Confirm this is acceptable, or introduce a pre-commit
  config first (a separate, beneficial follow-up change — not in this feature's scope).
- **Correction surfaced (resolved, non-blocking).** The planning brief framed the `docs/CLAUDE.md` link
  as needing a recomputed `../`-target like the docs-site links. In the live SOURCE it is a **sibling**
  link (`docs/CLAUDE.md -> AGENTS.md` → `docs/AGENTS.md`), so its target string must **not** change;
  only its location moves under `dark-factory/`. Resolved in research R1/R2; flagged here per
  Constitution V.

## Traceability

| Spec scenario / FR / SC | Unit(s) | Step(s) | Guardrail(s) |
|-------------------------|---------|---------|--------------|
| US1 AS1 / FR-001 / FR-002 / SC-001 | U1 | S1 | payloads-under-subdir; no real at root; ruff/pytest |
| US1 AS2 / FR-003 / SC-002 | U2 | S2 | links resolve into subdir; pytest |
| US1 AS2 / FR-005 / E6 | U3, U4, U19 | S3 | docs-link depth resolves on default path; copied-in stale link excluded; conditional preserved; BSD/GNU |
| US1 AS3 / FR-004 / SC-002 | U5 | S4 | specs/plans real at root; pytest |
| US1 AS4 / SC-003 | U6 | S2 | helper paths resolve from root; pytest |
| US2 AS1 / FR-006 / FR-007 / SC-005 | U7 | S6 | no dual layout; pytest |
| US2 AS2 / FR-006 / FR-017 / SC-005 | U8 | S6 | migration repoints managed root links on default path (rm-symlink-only, never real file, then link_one fresh; gated migrated=1); names payloads; pytest |
| US2 AS3 / FR-014 / E7 | U9 | S6 | user content preserved; pytest |
| E3 (partial migration) | U10 | S6 | converges to single layout; pytest |
| US3 AS1/AS2 / FR-009 / SC-004 / E8 | U11, U12 | S5 (clean) / S6→S5 (flat) | dry-run zero-change; output completeness |
| US4 AS1 / FR-010 / E2 (non-migration stale-link skip) / SC-006 | U13 | S6 | idempotency; non-migration skip-without-force; pytest |
| US4 AS3 / FR-011 / E1 | U14 | S6 | no-clobber + warn; pytest |
| US4 AS2 / FR-012 / SC-006 / E2 / E4 | U15 | S6 | --force repoint + refresh; pytest |
| E5 / FR-013 | U16 | S6 (constant in S1) | guards refuse incl. subdir collision; pytest |
| FR-015 | U17 | S4 | .gitignore merge unchanged; pytest |
| FR-016 | U18 | S4 | summary points into dark-factory/; pytest |
| FR-008 (no dual mode) | U7, U10 | S1, S6 | replace not accrete (Constitution I); all |
| Constitution III (test-first) | all U1–U18 | S0 | red-before-green per step |
```
