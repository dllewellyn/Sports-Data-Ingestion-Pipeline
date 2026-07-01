---
title: "Feature Specification: Subdir Install Layout"
---

# Feature Specification: Subdir Install Layout

**Feature directory**: `specs/002-subdir-install-layout/`
**Created**: 2026-06-30
**Status**: Draft
**Input**: "Update the install script (`install.sh` at the repo root of this dark-factory framework). Today it copies the framework payloads (`.agents`, `.specify`, `telemetry`, `docs`, `AGENTS.md`) directly into the *target* project's root and wires symlinks (`.claude/skills`, `CLAUDE.md`, docs-site links). Instead of putting these payloads directly into the target repository root, install them into a subdirectory called `dark-factory/` inside the target, and wire symlinks from the root into that subdirectory."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install the framework into a clean target without polluting its root (Priority: P1)

A developer runs `bash /path/to/dark-factory/install.sh ~/my-project` against a project that has never
had the framework installed. The framework payloads (`.agents`, `.specify`, `telemetry`, `docs`,
`AGENTS.md`) land **inside a single `dark-factory/` subdirectory** of the target, keeping the target's
root clean of vendored framework files. The root then exposes only the small set of symlinks that
Claude Code and the framework helpers require, each pointing into `dark-factory/`. The project's own
content directories (`specs/`, `plans/`) are created as **real directories at the target root** (not
inside `dark-factory/`, not symlinks), because they hold the user's project content. After the run, the
developer can open the target in Claude Code, skills resolve, `CLAUDE.md` is read, and the framework
helpers resolve `.specify/feature.json`, `.agents/skills/...` and `specs/NNN` from the root.

**Why this priority**: This is the feature — relocating the vendored framework into `dark-factory/`
while keeping every path Claude Code and the helpers depend on working from the root. Without it there
is nothing.

**Independent Test**: On a clean temp directory, run the installer; assert that the target root contains
no real `.agents`/`.specify`/`telemetry`/`docs`/`AGENTS.md`, that `dark-factory/` contains those
payloads, that the required root symlinks exist and resolve into `dark-factory/`, and that `specs/` and
`plans/` are real directories at the root. The slice is independently valuable: it proves a fresh
install produces the new layout and stays usable by Claude Code.

**Acceptance Scenarios**:

1. **Given** a clean target with no prior install, **When** the developer runs the installer, **Then**
   the framework payloads (`.agents`, `.specify`, `telemetry`, `docs`, `AGENTS.md`) exist under
   `dark-factory/` in the target and **no** real copy of any of them exists at the target root.
2. **Given** the same run, **When** it completes, **Then** the target root contains the required
   symlinks (at minimum `.claude/skills`, `CLAUDE.md`, `.agents`, `.specify`, plus the docs-site links)
   and each resolves to a path inside `dark-factory/`.
3. **Given** the same run, **When** it completes, **Then** `specs/` and `plans/` are real directories at
   the target root (each with a `.gitkeep`), not symlinks and not located under `dark-factory/`.
4. **Given** the installed target opened in Claude Code, **When** a framework helper resolves
   `.specify/feature.json`, an `.agents/skills/...` path, or a `specs/NNN` feature directory **from the
   target root**, **Then** it resolves successfully through the root symlinks / real directories.

---

### User Story 2 - Migrate a prior flat install into the subdirectory layout (Priority: P1)

A developer who previously installed the framework with the old flat layout (payloads copied directly
to the target root) re-runs the installer. The installer detects the prior flat install and performs a
one-time **relocation**: it moves the framework payloads from the target root into `dark-factory/` and
repoints the root symlinks at the new locations. After migration the old flat payloads are **gone** from
the root — only the subdir copies and the root symlinks remain. The migration does **not** leave both
layouts side by side.

**Why this priority**: Existing installs must not be stranded, and per Constitution I a change replaces
rather than accretes — leaving the flat payloads in place alongside the subdir copies would be exactly
the dual-layout accretion the constitution forbids. Co-equal P1 with the clean install because both are
required for the layout change to be safe to adopt.

**Independent Test**: Seed a target with the old flat layout (payloads at root + old root symlinks), run
the installer, and assert that the root no longer holds real framework payloads, that `dark-factory/`
now holds them, and that the root symlinks point into `dark-factory/`. The user's `specs/`/`plans/` and
any non-framework files are untouched.

**Acceptance Scenarios**:

1. **Given** a target with the old flat layout (real `.agents`/`.specify`/`telemetry`/`docs`/`AGENTS.md`
   at the root), **When** the developer re-runs the installer, **Then** those payloads are relocated
   under `dark-factory/` and **no** real copy of them remains at the target root.
2. **Given** the same migration, **When** it completes, **Then** the root symlinks
   (`.claude/skills`, `CLAUDE.md`, `.agents`, `.specify`, docs-site links) point into `dark-factory/`
   and resolve, and there is **no** surviving dual flat-plus-subdir layout.
3. **Given** the same migration, **When** it completes, **Then** the user's own `specs/`, `plans/`, and
   any other non-framework files at the target root are unchanged.

---

### User Story 3 - Preview the planned layout with a dry run (Priority: P2)

Before changing anything, a developer runs the installer with `--dry-run` (on a clean target or one
needing migration). The installer prints the **planned subdir layout** — which payloads go to
`dark-factory/`, which root symlinks will be wired and where they point, any migration relocations that
would occur — and makes **no** changes to disk.

**Why this priority**: Preview-before-apply is an existing installer guarantee that must survive the
change, and it lets a user inspect the new layout (and any migration) before committing. It builds on
the P1 behaviours, so it ranks below them.

**Independent Test**: Run the installer with `--dry-run` against both a clean target and a flat-layout
target; assert the printed plan describes the subdir layout (and, for the flat target, the relocation),
and that the target's filesystem is byte-for-byte unchanged afterwards.

**Acceptance Scenarios**:

1. **Given** a clean target, **When** the developer runs the installer with `--dry-run`, **Then** the
   output describes the planned `dark-factory/` payloads and the root symlinks (with their targets), and
   the target is unchanged on disk.
2. **Given** a flat-layout target, **When** the developer runs the installer with `--dry-run`, **Then**
   the output additionally describes the planned migration (which payloads relocate into
   `dark-factory/`), and the target is unchanged on disk.

---

### User Story 4 - Re-run safely: idempotent and non-clobbering (Priority: P2)

A developer re-runs the installer on a target that is already on the new subdir layout. The installer
makes no destructive change: it does not duplicate payloads, does not clobber existing files, and only
repoints symlinks when `--force` is given. A normal re-run reports nothing newly copied/relocated; with
`--force`, existing copied files are overwritten and existing root symlinks are repointed.

**Why this priority**: Idempotency, no-clobber, and the `--force` escape hatch are existing installer
guarantees the change must preserve. It builds on P1, so it ranks below it.

**Independent Test**: Run the installer twice on a clean target; assert the second run copies/relocates
nothing new and leaves the layout identical. Run once more with `--force`; assert copied files are
refreshed and root symlinks are repointed without error.

**Acceptance Scenarios**:

1. **Given** a target already on the subdir layout, **When** the developer re-runs the installer without
   `--force`, **Then** existing payload files and symlinks are left untouched (reported as skipped) and
   the layout is unchanged.
2. **Given** the same target, **When** the developer re-runs with `--force`, **Then** copied payload
   files are overwritten and existing root symlinks are repointed into `dark-factory/`, with no error.
3. **Given** a target root that contains a **real** file/dir where a framework symlink would go (not a
   symlink), **When** the installer runs without `--force`, **Then** it leaves that real file untouched
   and warns rather than clobbering it.

---

### Edge Cases

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | Target root already has a real (non-symlink) `CLAUDE.md` or other path where a framework symlink belongs | Leave the real file untouched and warn; do not clobber (existing no-clobber guarantee). |
| E2 | A root symlink already exists but points at the old flat location, on a **non-migration idempotent re-run** (no real payloads at the root, so no migration occurs) | Treated as a stale link on the idempotent path: under `--force` repoint it into `dark-factory/` (FR-012); without `--force`, report it as skipped (existing symlink-skip behaviour, FR-010) so a normal re-run is non-destructive. **This skip-without-`--force` behaviour is scoped to the non-migration re-run.** During an actual **migration** (real payloads found at the root and relocated), the stale managed root symlinks are instead repointed on the default (no-`--force`) path so nothing is left dangling — see FR-006. |
| E3 | Partial prior migration (some payloads already under `dark-factory/`, some still flat at root) | Complete the relocation: move the remaining flat payloads into `dark-factory/` and repoint symlinks, converging on the single subdir layout (no dual layout left). |
| E4 | A target file under `dark-factory/` already exists and differs | No-clobber unless `--force`; without `--force` skip and report, with `--force` overwrite. |
| E5 | `SOURCE` (the framework checkout) equals or nests with `TARGET`, or `dark-factory/` would collide with the framework source | Refuse with a clear error, as the installer already guards self-copy and nested source/target. |
| E6 | `docs/` payload moves down one directory level (now `dark-factory/docs/`), changing the relative depth from the docs-site link locations to the repo-root `specs/`/`plans/` | The docs-site symlinks are wired with the correct relative depth for the new location so they still resolve to the root `specs/`/`plans/`. |
| E7 | The user's own `specs/`/`plans/` already contain content before (re-)install | Preserve them as real root directories with their content; never move them under `dark-factory/` and never clobber. |
| E8 | `--dry-run` on a flat-layout target | Print the planned migration and layout; make zero filesystem changes (no relocation, no symlink writes). |

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The installer MUST place the framework payloads `.agents`, `.specify`, `telemetry`,
  `docs`, and `AGENTS.md` inside a single `dark-factory/` subdirectory of the target, not at the target
  root.
- **FR-002**: After a successful install, the target root MUST contain **no real** `.agents`,
  `.specify`, `telemetry`, `docs`, or `AGENTS.md` — only symlinks (where required) pointing into
  `dark-factory/`.
- **FR-003**: The installer MUST wire, at the target root, the symlinks that Claude Code and the
  framework helpers require, each resolving into `dark-factory/`. At minimum this MUST include
  `.claude/skills`, `CLAUDE.md`, `.agents`, and `.specify` (so skill invocations and helpers such as
  `feature-dir.sh` resolve `.agents/skills/...` and `.specify/feature.json` from the root), plus the
  docs-site links. The exact, complete set MUST be derived from the current `install.sh` so no
  previously-wired entry point is dropped.
- **FR-004**: The installer MUST keep the target's own content directories `specs/` and `plans/` as
  **real directories at the target root** (each ensured to exist with a `.gitkeep`); it MUST NOT place
  them under `dark-factory/` and MUST NOT replace them with symlinks.
- **FR-005**: The docs-site symlinks (e.g. the links from `docs/src/content/docs/...` to the repo-root
  `specs/`/`plans/`, and any `docs/CLAUDE.md` link) MUST be wired with the relative depth correct for
  the payloads' new location under `dark-factory/`, so they resolve to the intended root targets. The
  `docs/CLAUDE.md` link MUST remain **conditional on its presence in SOURCE** (wired only when the
  framework source itself carries that link, exactly as the current installer does), not made
  unconditional.
- **FR-006**: When the installer detects a prior **flat** install (framework payloads present as real
  files/dirs at the target root), it MUST relocate those payloads into `dark-factory/` and repoint the
  root symlinks accordingly. "Repoint the root symlinks accordingly" means the migration MUST NOT leave
  a managed root symlink dangling: because relocating the payloads invalidates any root symlink that
  pointed at the old flat location, the migration MUST — **and only when a migration actually occurred
  (real payloads were found at the root and relocated)** — refresh the now-stale **managed** root
  framework symlinks so they resolve into `dark-factory/` on the **default (no-`--force`) path**,
  guaranteeing no managed root symlink is left dangling by the relocation. This refresh MUST operate on
  **symlinks only** — it MUST NOT remove or clobber a **real** file or directory at a managed root path
  (the no-clobber guarantee of FR-011 is preserved) — and it re-creates each cleared link fresh into
  `dark-factory/` using the same link-wiring as a fresh install. This migration-path repointing is
  distinct from the non-migration idempotency rule (FR-010/FR-012 and edge case E2), which governs a
  re-run where no relocation occurs and where an existing root symlink is left untouched without
  `--force` (FR-010, E2) and repointed only with `--force` (FR-012). For the `.agents` payload
  specifically, relocation MUST be **surgical**: only the skill directories the framework itself ships
  (enumerated from `SOURCE/.agents/skills`) are relocated into `dark-factory/.agents/skills` — or, when
  already present there, deleted from the root — so that user-authored skills at `.agents/skills` are
  left in place per FR-014. The root `.agents` symlink is created only when no user-authored skill
  survives there; when one does, root `.agents` stays a real dir holding only the user's skills, and
  `.claude/skills` still resolves to the framework set under `dark-factory/` (wiring user skills is the
  user's concern, not the installer's).
- **FR-007**: After migration, the installer MUST NOT leave both layouts in place: no real framework
  payload may remain at the target root once it has been relocated under `dark-factory/` (Constitution I
  — a change replaces, it does not accrete). A root `.agents` directory holding **only** user-authored
  skills is not a framework payload and does not constitute a surviving dual layout.
- **FR-008**: The installer MUST NOT offer or support a dual mode that installs the flat layout and the
  subdir layout simultaneously; the subdir layout is the only layout it produces.
- **FR-009**: `--dry-run` MUST print the planned subdir layout — the payloads bound for `dark-factory/`,
  the root symlinks and their targets, and any migration relocations — and MUST make zero changes to the
  target filesystem.
- **FR-010**: A re-run MUST be idempotent: without `--force`, existing payload files and existing
  symlinks are left untouched (reported as skipped) and the resulting layout is unchanged.
- **FR-011**: The installer MUST NOT clobber a pre-existing **real** (non-symlink) file or directory at
  a target path where a framework symlink would go; it MUST leave it untouched and warn.
- **FR-012**: `--force` MUST overwrite existing copied payload files and repoint existing root symlinks
  into `dark-factory/`, without erroring on the pre-existing entries.
- **FR-013**: The installer MUST preserve its existing safety guards — refusing when `SOURCE` and
  `TARGET` are the same directory or nested within one another — and MUST extend them so the new
  `dark-factory/` destination cannot collide with the framework source.
- **FR-014**: The installer MUST NOT move, clobber, or alter the user's own `specs/`, `plans/`, or other
  non-framework content during a fresh install or a migration. This explicitly includes user-authored
  skill directories under `.agents/skills` (any skill name the framework does not ship): a migration
  MUST leave them real and in place at the root, never relocating, deleting, or copying them.
- **FR-015**: The installer's `.gitignore` merge MUST continue to add the framework ignore entries
  without duplicating or rewriting the user's existing rules, adjusted for the new layout where a path
  is affected.
- **FR-016**: The installer's final summary and "next steps" MUST reflect the new layout (correct paths
  into `dark-factory/`), so the printed guidance points at locations that actually exist after install.
- **FR-017**: During migration, the installer MUST report which framework payloads it relocated into
  `dark-factory/` (naming the relocated payloads), not merely note that a prior install was detected.

### Key Entities *(include only if the feature involves data)*

- **Framework payload**: a vendored framework artifact (`.agents`, `.specify`, `telemetry`, `docs`,
  `AGENTS.md`) that, under the new layout, lives inside `dark-factory/` in the target.
- **Root symlink**: a link at the target root (`.claude/skills`, `CLAUDE.md`, `.agents`, `.specify`,
  docs-site links) that points into `dark-factory/` so Claude Code and the framework helpers resolve the
  paths they require from the root.
- **Project content directory**: the user's own `specs/` and `plans/`, real directories at the target
  root, owned by the project rather than vendored by the framework.
- **`dark-factory/` subdirectory**: the single directory inside the target that holds all relocated
  framework payloads.

## Success Criteria *(mandatory)*

- **SC-001**: After a fresh install, the target root contains no real `.agents`, `.specify`,
  `telemetry`, `docs`, or `AGENTS.md` directory/file — each is present only as (or behind) a symlink
  into `dark-factory/`, while those payloads exist under `dark-factory/`.
- **SC-002**: After a fresh install, every required root symlink resolves to an existing path inside
  `dark-factory/`, and `specs/` and `plans/` exist as real directories at the target root.
- **SC-003**: From the target root after install, resolving `.specify/feature.json`,
  `.agents/skills/<any-skill>`, and `specs/NNN-<slug>` each succeeds (the paths the helpers and Claude
  Code depend on are reachable).
- **SC-004**: A `--dry-run` against a clean target and against a flat-layout target prints the planned
  subdir layout (and, for the flat target, the migration) and leaves the target filesystem unchanged.
- **SC-005**: Running the installer against a flat-layout target results in zero real framework payloads
  remaining at the target root and all of them present under `dark-factory/`, with the root symlinks
  repointed — and the user's `specs/`/`plans`/other content unchanged.
- **SC-006**: Re-running the installer on an already-subdir-layout target without `--force` copies and
  relocates nothing new and leaves the layout identical; with `--force` it refreshes copied files and
  repoints symlinks without error.

## Constraints & things to be aware of *(mandatory)*

- **Hard constraint — root must expose helper/Claude-Code paths.** Claude Code reads `.claude/` and
  `CLAUDE.md` only from the target repo root, and the framework helpers resolve `.specify/feature.json`,
  `.agents/skills/...`, and `specs/NNN` relative to the target repo root. The new layout therefore MUST
  keep those paths reachable from the root via symlinks (or, for `specs/`/`plans/`, real directories).
  This is a requirement, not a design choice.
- **Scope = framework payloads only.** Only `.agents`, `.specify`, `telemetry`, `docs`, and `AGENTS.md`
  move into `dark-factory/`. The user's `specs/` and `plans/` are project content and stay as real
  directories at the root.
- **No backward compatibility / no accretion** (Constitution I): the migration is a one-time relocation
  that **replaces** the flat layout; it must not leave both layouts in place, and the installer must not
  carry a dual flat/subdir mode. The old flat-install code path is removed, not preserved alongside the
  new one.
- **No reward hacking** (Constitution II): no stubbed or faked install steps; relocation and symlinking
  must genuinely produce the described layout. Existing guarantees (idempotent, no-clobber, `--dry-run`,
  `--force`) must hold on their own terms, not be weakened to make the change "pass".
- **Test-First** (Constitution III): the new behaviour (subdir placement, root symlinks resolving,
  migration removing the flat payloads, dry-run making no changes, idempotency/no-clobber) must be
  covered by checks that can genuinely fail before the change exists. Prefer a deterministic
  script-driven check (run the installer against a temp target and assert the filesystem) over
  eyeballing.
- **Preserve existing installer guards**: self-copy refusal and nested SOURCE/TARGET refusal must
  remain, extended so `dark-factory/` cannot collide with the framework source.
- **Symlink portability**: the installer already preserves symlinks on both BSD (macOS) and GNU
  coreutils via `cp -RPp`; the relative-depth math for the relocated `docs/` links (E6/FR-005) must be
  computed for the new location and must work on both.
- **Honesty about destructive steps** (Constitution IV): migration moves files at the target root. The
  installer must report what it relocated, and (per the project workflow rules) any move/relocation must
  be auditable — no silent deletion of user content.

## Assumptions *(mandatory)*

- The subdirectory is literally named `dark-factory/` at the target root, holding all relocated
  framework payloads. (Default chosen: the description names it explicitly.)
- The full set of root symlinks to wire is exactly the set the current `install.sh` wires (`.claude/skills`,
  `CLAUDE.md`, the docs-site links, and the conditional `docs/CLAUDE.md`), each with a **repointed
  relative target computed from that link's own location** so it resolves into `dark-factory/`, plus the
  newly-required `.agents` and `.specify` root links into `dark-factory/` so helpers that read
  `.agents/...` and `.specify/...` from the root keep resolving. The exact relative-target strings are
  derived in planning — the relative-depth-correctness class (E6 / FR-005) applies to `.claude/skills`
  and `CLAUDE.md` as much as to the docs-site links, since each link's relative target depends on its
  own location once the payloads sit under `dark-factory/`. (Default chosen: FR-003's "derive from
  current install.sh" — the plan phase confirms the exact list and strings against the live script.)
- `specs/` and `plans/` continue to be ensured as real root directories with `.gitkeep`, exactly as the
  current `ensure_keepdir` does, and are never relocated. (Default chosen: they are project content.)
- Migration relocates payloads with a move (not copy-then-leave), so no flat copy survives; the user's
  non-framework files are identified by exclusion (anything not a framework payload or its root symlink
  is left alone). (Default chosen: satisfies FR-007 "no dual layout".)
- The `.gitignore` entries the installer merges (`temp/`, `__pycache__/`, `*.pyc`) remain at the target
  root unless a specific entry is tied to a relocated path; relocation does not change which ignore
  rules the project needs at its root. (Default chosen: those ignores are project-root concerns,
  unaffected by where the framework payloads sit.)
- Migration is detected by the presence of a **real (non-symlink)** framework payload at the target root,
  not by a stored marker file. This is genuinely new detection logic, not the current installer's check:
  the current installer flags a prior install when `.specify` or `.agents` merely *exists* regardless of
  whether it is real or a symlink, which would misfire on an already-migrated target (where those are
  symlinks). Detection therefore MUST distinguish a real payload from a symlink so a re-run on the new
  layout is not mistaken for a flat install needing migration. (Default chosen: avoids introducing new
  state; aligns with E2/E3, which already require detecting REAL payloads.)

## Open Questions *(mandatory)*

- The docs-site symlinks currently point from `docs/src/content/docs/{specs,plans}` up to the repo-root
  `specs`/`plans` with a fixed relative depth (`../../../../specs`). Once `docs/` lives at
  `dark-factory/docs/`, the link **source** is one level deeper, so its relative target must gain one
  `../` to still reach the root `specs`/`plans`. **Best-guess answer**: compute the relative target from
  the relocated link location to the root `specs`/`plans` (one extra `../` than today), so it resolves
  to the same real root directories. *Rationale*: `specs`/`plans` stay at the root (FR-004), only the
  link's own location moved deeper, so only the depth changes. Not a build blocker — verifiable by
  resolving the link after install.
- Does the `temp/` `.gitignore` entry need to become `dark-factory/temp/` (or both)? The
  `git-sync-extractor` writes its `temp/` output under the framework tree; with the framework now at
  `dark-factory/`, that output may land at `dark-factory/temp/`, which a root-level `temp/` ignore might
  not cover. **Best-guess answer**: keep the root `temp/` entry and add `dark-factory/temp/` if the
  extractor writes relative to the framework tree. *Rationale*: ignore coverage should follow wherever
  the extractor actually writes. Resolve in planning by checking where `git-sync-extractor` writes its
  temp output relative to its run directory. Not a build blocker.
