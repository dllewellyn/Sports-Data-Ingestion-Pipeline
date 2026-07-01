---
title: "Contract: Installed Layout (post-install filesystem state)"
---

# Contract: Installed Layout (post-install filesystem state)

**Feature directory**: `specs/002-subdir-install-layout/`
**Date**: 2026-06-30

This feature exposes no API and consumes no data model — but it **does** have a precise, assertable
contract: the filesystem state of the TARGET after the installer runs. This is the contract the
`tests/test_install.py` suite asserts. Each row is an objective, machine-checkable post-condition.

`real` = exists and is **not** a symlink (`-e && ! -L`). `symlink` = `-L`. `payload` = a real file/dir
copied from SOURCE.

## C-LAYOUT-1 — Payloads under `dark-factory/` (FR-001, FR-002, SC-001)

| Path (relative to TARGET) | Required state after install |
|---|---|
| `dark-factory/.agents` | real dir (payload) |
| `dark-factory/.specify` | real dir (payload) |
| `dark-factory/telemetry` | real dir (payload) |
| `dark-factory/docs` | real dir (payload) |
| `dark-factory/AGENTS.md` | real file (payload) |
| `.agents` (root) | symlink into `dark-factory/.agents` when the target holds no user-authored skills; otherwise a **real dir holding only user-authored skills** — the installer relocates only the skills it created (see C-LAYOUT-4) |
| `.specify` (root) | **NOT real** — symlink only |
| `telemetry` (root) | **absent** — no real, no symlink (nothing reads it from root) |
| `docs` (root) | **absent** — no real, no symlink |
| `AGENTS.md` (root) | **NOT real** — only reachable behind the `CLAUDE.md` symlink |

## C-LAYOUT-2 — Root symlinks resolve into `dark-factory/` (FR-003, SC-002, SC-003)

| Symlink path | Link target text | Must `realpath`-resolve to (existing) |
|---|---|---|
| `.claude/skills` | `../dark-factory/.agents/skills` | `<TARGET>/dark-factory/.agents/skills` |
| `CLAUDE.md` | `dark-factory/AGENTS.md` | `<TARGET>/dark-factory/AGENTS.md` |
| `.agents` | `dark-factory/.agents` | `<TARGET>/dark-factory/.agents` |
| `.specify` | `dark-factory/.specify` | `<TARGET>/dark-factory/.specify` |
| `dark-factory/docs/src/content/docs/specs` | `../../../../../specs` | `<TARGET>/specs` |
| `dark-factory/docs/src/content/docs/plans` | `../../../../../plans` | `<TARGET>/plans` |
| `dark-factory/docs/CLAUDE.md` (only if SOURCE carries it) | `AGENTS.md` | `<TARGET>/dark-factory/docs/AGENTS.md` |

Assertion form: each `Path(link).is_symlink()` is true, `os.readlink(link)` equals the target text, and
`Path(link).resolve()` (or `os.path.realpath`) exists and equals the expected absolute path.

**Default-path requirement (the three docs symlinks).** SOURCE carries `docs/CLAUDE.md`,
`docs/src/content/docs/specs`, and `docs/src/content/docs/plans` as symlinks. `cp -RPp` would copy them
verbatim with their old 4-level text, and `link_one` only repoints a pre-existing link under `--force`.
So the contract requires the corrected docs-site links (`../../../../../{specs,plans}`, 5 levels) and
the conditional `dark-factory/docs/CLAUDE.md -> AGENTS.md` to be produced on a **default install with no
`--force`** — the installer must exclude those three from the payload copy and create them fresh. Assert
the exact `readlink` text on a no-`--force` install so the stale 4-level copy cannot pass (plan unit U19).

Helper-resolution corollary (SC-003): from `<TARGET>`, `.specify/feature.json` (when present),
`.agents/skills/<any>`, and `specs/NNN-<slug>` all resolve.

## C-LAYOUT-3 — Project content stays real at root (FR-004, FR-014, SC-002, E7)

| Path | Required state |
|---|---|
| `specs/` | real dir at root, contains `.gitkeep`; never a symlink; never under `dark-factory/` |
| `plans/` | real dir at root, contains `.gitkeep`; never a symlink; never under `dark-factory/` |
| pre-existing user content under `specs/`/`plans/` | byte-for-byte unchanged after install or migration |

## C-LAYOUT-4 — Migration leaves no dual layout (FR-006, FR-007, SC-005)

After running against a flat-layout TARGET:

| Assertion |
|---|
| No **framework-created** payload remains real at the TARGET root: `-e && ! -L` is false for each of the four wholesale payloads (`.specify`/`telemetry`/`docs`/`AGENTS.md`), and no framework skill dir (a name shipped in `SOURCE/.agents/skills`) remains real under root `.agents/skills`. |
| `.agents` is migrated **surgically**: only the skills the installer created are relocated into `dark-factory/.agents/skills` (or, when already present there, deleted from the root). User-authored skills — names not shipped in SOURCE — stay REAL under root `.agents/skills` and are never moved, deleted, or copied under `dark-factory/`. |
| When no user-authored skill survives, the now-empty root `.agents` is dropped and repointed as a symlink into `dark-factory/.agents` (single layout, per C-LAYOUT-2). When one survives, root `.agents` stays a real dir and `.claude/skills` still resolves to the framework set under `dark-factory/` (wiring user skills is the user's concern). |
| All framework payloads are present under `dark-factory/`. |
| The installer output names each relocated payload/skill (FR-017). |
| Non-framework files at the root are unchanged. |

## C-LAYOUT-5 — Dry-run zero-change (FR-009, SC-004)

| Assertion |
|---|
| `find . \| sort` (paths) + a per-entry stat snapshot of the TARGET are byte-for-byte identical before and after a `--dry-run` invocation, on both a clean and a flat-layout seed. |
| The dry-run stdout describes: payloads bound for `dark-factory/`, each root symlink + its target text, and (flat seed) the migration relocations. |

## C-LAYOUT-6 — Idempotency, no-clobber, `--force` (FR-010, FR-011, FR-012, SC-006, E1/E2/E4)

| Assertion |
|---|
| A second no-`--force` run copies/relocates nothing new (skip-reported) and leaves the layout identical. |
| A pre-existing **real** file where a symlink would go is left untouched and warned about (not clobbered). |
| A root symlink pointing at the old flat location is skip-reported without `--force`, repointed with `--force`. |
| `--force` overwrites copied payload files and repoints existing root symlinks, with no error on pre-existing entries. |

## C-LAYOUT-7 — Guards preserved + extended (FR-013, E5)

| Assertion |
|---|
| SOURCE == TARGET → installer refuses with an error (exit non-zero). |
| TARGET nested in SOURCE, or SOURCE nested in TARGET → refuses. |
| The new `dark-factory/` destination cannot collide with the framework source (extended guard). |
