---
title: "Data Model: Subdir Install Layout"
---

# Data Model: Subdir Install Layout

**Feature directory**: `specs/002-subdir-install-layout/`
**Date**: 2026-06-30

There is **no application data model** here (no records, schemas, or persisted domain objects) — this
is a filesystem-layout change to a shell installer. The spec's *Key Entities* are filesystem objects,
so this document models them as entities with their **states** and the **state transition** the
installer performs, which is what `data-model.md` is for in this feature. The assertable post-states
are formalised in `contracts/installed-layout.md`.

## Entities (filesystem objects)

### Framework payload
A vendored framework artifact: one of `.agents`, `.specify`, `telemetry`, `docs`, `AGENTS.md`.
- **Identity:** its relative name (the five names above — a closed set).
- **States at the TARGET root:** `absent` · `real` (copied dir/file) · `symlink` (link into `dark-factory/`).
- **Canonical post-install location:** `dark-factory/<name>` (real).
- **Validation rule:** after install, **no** payload may be `real` at the TARGET root (FR-002, SC-001);
  each must be `real` under `dark-factory/`.

### Root symlink
A link at the TARGET root (or under `dark-factory/docs/...`) that points into `dark-factory/` so Claude
Code and the helpers resolve required paths from the root.
- **Identity:** its path (`.claude/skills`, `CLAUDE.md`, `.agents`, `.specify`, the two docs-site links,
  conditional `docs/CLAUDE.md`).
- **Attributes:** target text (the relative `ln -s` string) + resolved absolute path.
- **States:** `absent` · `correct` (resolves into `dark-factory/`) · `stale` (resolves at the old flat
  location) · `blocked` (a **real** file/dir occupies the path).
- **Validation rule:** after install every required symlink is `correct` (SC-002); a `blocked` path is
  left untouched + warned (FR-011); a `stale` link is skip-reported without `--force`, repointed with
  `--force` (E2, FR-012).

### Project content directory
The user's own `specs/` and `plans/`.
- **States:** `absent` · `real` (dir, possibly with user content).
- **Validation rule:** always `real` at the TARGET root with a `.gitkeep`; never relocated under
  `dark-factory/`, never replaced by a symlink, never clobbered (FR-004, FR-014, E7).

### `dark-factory/` subdirectory
The single directory holding all relocated framework payloads.
- **States:** `absent` · `present` (holds the five payloads).
- **Validation rule:** must not collide with the framework SOURCE (FR-013 extended guard, E5).

## State transitions (the installer's job)

| Entity | From (pre) | Trigger | To (post) |
|---|---|---|---|
| Framework payload | `absent` (clean target) | fresh install | `real` under `dark-factory/` + root `symlink`/behind-link |
| Framework payload | `real` at root (flat install) | migration | `real` under `dark-factory/` (moved); root `real` → gone, replaced by `symlink` |
| Framework payload | already `real` under `dark-factory/` (re-run) | idempotent re-run | unchanged (skip) unless `--force` (overwrite) |
| Root symlink | `absent` | install | `correct` |
| Root symlink | `stale` (old flat target) | migration + `--force` | `correct` (repointed); without `--force` → skip-reported |
| Root symlink path | `blocked` (real file) | install | unchanged + warn (no clobber) |
| Project content dir | `absent`/`real` | install/migration | `real` at root (ensured `.gitkeep`), content preserved |

The migration transition is a **move** (not copy-then-leave) so no flat copy survives (FR-007) — the
"no dual layout" invariant. Detection of the `real`-at-root state (vs an already-migrated `symlink`)
is the `-e && ! -L` test (research R4).
