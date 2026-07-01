---
title: "Phase 0 Research: Subdir Install Layout"
---

# Phase 0 Research: Subdir Install Layout

**Feature directory**: `specs/002-subdir-install-layout/`
**Date**: 2026-06-30
**Spec**: `spec.md`

This document resolves every unknown the plan depends on, grounded in the **live** `install.sh`
(repo root) and the live framework tree. Each entry gives the Decision, Rationale, and Alternatives
considered.

---

## R1 — The exact, complete root-symlink set and each link's relative-target string (CHK022 / FR-003)

**Decision.** Reading the live `install.sh` (lines 191–196) the installer wires exactly five links
today; under the new `dark-factory/` layout the complete set becomes **seven** links. Each target
string is derived from the *link's own location* relative to where the payload now sits under
`dark-factory/`. Verified by constructing the layout in a temp dir and resolving every link
(`os.path.realpath`) to an existing path:

| Link (path written at TARGET) | Target text (the `ln -s` text) | vs today | Resolves to |
|---|---|---|---|
| `.claude/skills` | `../dark-factory/.agents/skills` | CHANGED (was `../.agents/skills`) | `dark-factory/.agents/skills` |
| `CLAUDE.md` (root) | `dark-factory/AGENTS.md` | CHANGED (was `AGENTS.md`) | `dark-factory/AGENTS.md` |
| `.agents` (root) | `dark-factory/.agents` | **NEW** | `dark-factory/.agents` |
| `.specify` (root) | `dark-factory/.specify` | **NEW** | `dark-factory/.specify` |
| `dark-factory/docs/src/content/docs/specs` | `../../../../../specs` | CHANGED (+1 `../`, was `../../../../specs`) | root `specs/` |
| `dark-factory/docs/src/content/docs/plans` | `../../../../../plans` | CHANGED (+1 `../`) | root `plans/` |
| `dark-factory/docs/CLAUDE.md` (conditional) | `AGENTS.md` | **UNCHANGED text**; location moved | `dark-factory/docs/AGENTS.md` |

**Rationale (the relative-depth-correctness class applies per link, not only the docs links):**

- **`.claude/skills`** stays at the *root* (`.claude/` is read by Claude Code from the repo root), but
  the skills payload moved from root `.agents/skills` to `dark-factory/.agents/skills`. The link's own
  dir is `.claude/`; one `../` reaches the root, then `dark-factory/.agents/skills`. Hence
  `../dark-factory/.agents/skills`.
- **`CLAUDE.md`** stays at the root; the `AGENTS.md` payload moved to `dark-factory/AGENTS.md`. The
  link's dir is the root, so the relative text is simply `dark-factory/AGENTS.md` (today it was the
  root sibling `AGENTS.md`).
- **`.agents` / `.specify` (new root links).** `feature-dir.sh` reads `.specify/feature.json` as a
  **relative path from the target repo root** (verified in
  `.agents/skills/_shared/spec-helpers/feature-dir.sh:25`), and skill invocations reference
  `.agents/skills/...` from the root. With the real payloads now under `dark-factory/`, the root must
  expose `.agents -> dark-factory/.agents` and `.specify -> dark-factory/.specify` or those helper
  paths break. The current installer never wired these (the payloads *were* the root dirs); the move
  makes them mandatory new links. Both are link-dir = root, so the text is the bare
  `dark-factory/.agents` / `dark-factory/.specify`.
- **docs-site `specs`/`plans` links.** Today they live at `docs/src/content/docs/{specs,plans}` and
  point `../../../../{specs,plans}` (four `../` climbs `docs/`→`src/`→`content/`→`docs/` to the root).
  After relocation the link source is `dark-factory/docs/src/content/docs/{specs,plans}` — one level
  deeper — so it needs **five** `../` (`../../../../../{specs,plans}`) to still reach the root
  `specs/`/`plans/`, which stay at the root (FR-004). This is the spec's Open Question #1, resolved:
  +1 `../`.
- **`docs/CLAUDE.md` (conditional).** In the live SOURCE, `docs/CLAUDE.md -> AGENTS.md` resolves to its
  **sibling** `docs/AGENTS.md` (a real 874-byte file copied by the `docs` payload), *not* the root
  `AGENTS.md`. So its target text is a sibling reference and must stay `AGENTS.md`: after relocation it
  becomes `dark-factory/docs/CLAUDE.md -> AGENTS.md`, resolving to `dark-factory/docs/AGENTS.md`. **The
  target string does not change**; only the link's location moves (handled automatically because the
  `docs` payload now lands under `dark-factory/`). It stays conditional on `[ -L "$SOURCE/docs/CLAUDE.md" ]`
  (FR-005). The earlier instinct to rewrite it to `../AGENTS.md` would have wrongly repointed it at the
  *root* `dark-factory/AGENTS.md`, changing its meaning — rejected.

No existing entry point is dropped: all five original links are carried (with corrected targets), and
two new root links are added for the helper paths the relocation would otherwise break.

**Alternatives considered.** (a) Adding root `telemetry`/`docs` symlinks too — rejected: nothing reads
`telemetry/` or `docs/` from the root the way Claude Code reads `.claude`/`CLAUDE.md` and the helpers
read `.agents`/`.specify`; the spec scopes root links to "what Claude Code and helpers require". The
installer's own "Next steps" point at `$TARGET/dark-factory/docs` and `$TARGET/dark-factory/telemetry`
directly (FR-016). (b) Making `.agents`/`.specify` real dirs at root and copying — rejected: that
re-pollutes the root and contradicts FR-002 (no real payload at root).

---

## R2 — `CLAUDE.md` / `docs/CLAUDE.md` → AGENTS.md resolution chain (Obligation 2)

**Decision.** Two *independent* resolution targets, because today they already point at different files:

- **Root `CLAUDE.md`** points at the **root** `AGENTS.md` today (`realpath` →
  `<root>/AGENTS.md`). Under relocation the root `AGENTS.md` becomes `dark-factory/AGENTS.md`, so the
  root link text becomes `dark-factory/AGENTS.md`.
- **`docs/CLAUDE.md`** points at its **sibling** `docs/AGENTS.md` today (`realpath` →
  `<root>/docs/AGENTS.md`, an 874-byte real file). After relocation that sibling is
  `dark-factory/docs/AGENTS.md`; the link text stays the sibling reference `AGENTS.md` and resolves
  correctly with no string change. It remains conditional on the SOURCE carrying the link
  (`[ -L "$SOURCE/docs/CLAUDE.md" ]`), per FR-005.

**Rationale.** Verified empirically against the live tree: the two `CLAUDE.md` links are *not* the same
target — conflating them (e.g. wiring both to the root payload) would break the docs-site `CLAUDE.md`
content. Keeping each link's target computed from its own location preserves both.

**Alternatives considered.** Treating both as "→ the single root AGENTS.md" — rejected; the docs one is
a sibling link to `docs/AGENTS.md`, a distinct file.

---

## R3 — `temp/` .gitignore knock-on (Obligation 3 / Open Question #2)

**Decision.** **No `dark-factory/temp/` entry is needed.** Keep the existing root-level `temp/`
`.gitignore` entry exactly as-is; the `.gitignore` merge requires **no change** for `temp/`. The
extractor writes its output at the **git toplevel of the target repo** (= the target root), not under
the framework subtree.

**Evidence (exact path-determination lines, `.agents/skills/git-sync-extractor/scripts/bash/git-sync-extractor.sh`):**

```
4:  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
5:  GIT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || echo "${SCRIPT_DIR}")"
7:  TEMP_BASE="${GIT_ROOT}/temp"
188:  local commit_dir="${TEMP_BASE}/${short_sha}"
```

`TEMP_BASE` is `"$(git rev-parse --show-toplevel)/temp"`. In an installed target the script lives at
`dark-factory/.agents/skills/git-sync-extractor/scripts/bash/git-sync-extractor.sh`; `git -C <that dir>
rev-parse --show-toplevel` returns the **target repo root** (verified empirically: from a nested subdir
of a git repo, `--show-toplevel` returns the repo root, not the subdir). Therefore the output lands at
`<target-root>/temp/<short_sha>/`, which the existing root `temp/` ignore already covers.

**Rationale.** The spec's Open Question #2 best-guessed "add `dark-factory/temp/` if the extractor
writes relative to the framework tree." The deterministic check shows it does **not** — it writes
relative to the git toplevel — so the root `temp/` entry is correct and complete. Adding
`dark-factory/temp/` would be a dead/never-matched rule (the extractor never writes there in a git
target), so it is omitted (Constitution II — no superfluous accretion).

**Edge note (non-blocking, out of scope for FR-015).** If the target is **not** a git repo,
`git rev-parse` fails and `GIT_ROOT` falls back to `SCRIPT_DIR` (`.../git-sync-extractor`), so temp
would land deep under `dark-factory/.agents/...`. That is an extractor behaviour, not an installer
`.gitignore` concern (a non-git target has no `.gitignore` to honour), and is outside this feature's
scope (FR-015 governs the merge into an existing/created `.gitignore`, which only matters for git
targets). Recorded for honesty; no installer change implied.

**Alternatives considered.** Add both `temp/` and `dark-factory/temp/` "to be safe" — rejected: the
second never matches in a git target; it is noise, and Constitution I/II discourage speculative
accretion.

---

## R4 — Real-vs-symlink migration detection logic (Assumptions / E2 / E3)

**Decision.** Detect a prior **flat** install by testing each framework payload at the target root for
"**exists and is not a symlink**": `[ -e "$TARGET/$p" ] && [ ! -L "$TARGET/$p" ]` for `p` in
`.agents .specify telemetry docs AGENTS.md`. If *any* such real payload exists, migration is needed;
relocate every real payload (only the real ones) into `dark-factory/` with `mv`, leaving any already-a-symlink
entry alone (it is already migrated). This handles partial migration (E3) by construction: only the
real ones move, symlinks are skipped, converging on the single subdir layout.

**Rationale.** The current installer's detection (`install.sh:180`,
`[ -e "$TARGET/.specify" ] || [ -e "$TARGET/.agents" ]`) is **existence-only** and would misfire on an
already-migrated target where `.specify`/`.agents` are *symlinks* into `dark-factory/` — it would
report "prior install detected" and could attempt to re-migrate. The spec's Assumptions section calls
this out explicitly as genuinely new logic. Verified empirically: seeding a flat target, the
`-e && ! -L` test flags exactly the real payloads; after `mv` into `dark-factory/`, re-running the same
test reports zero real payloads (migration complete, no dual layout — FR-007).

**Alternatives considered.** (a) A stored marker file (e.g. `.dark-factory-version`) — rejected: adds
new persistent state the spec explicitly avoids, and a user deleting the marker would desync. (b)
Existence-only (current behaviour) — rejected: misfires on migrated targets (the bug above).

---

## R5 — Move (relocation) mechanics that satisfy FR-007 (no dual layout) and the honesty constraint

**Decision.** Relocate with `mv "$TARGET/$p" "$TARGET/dark-factory/$p"` per real payload — a **move**,
not copy-then-leave — so no flat copy survives (FR-007). Before moving, ensure `dark-factory/` exists
(`mkdir -p`). Each relocated payload is **named in the output** (FR-017), e.g.
`relocated: .agents -> dark-factory/.agents`. Under `--dry-run` the moves are printed via the existing
`run` wrapper and **not executed** (FR-009). On no-clobber: if `dark-factory/$p` already exists and
differs, without `--force` skip-and-report (E4), with `--force` overwrite.

**Rationale.** `mv` within the same target filesystem is atomic per entry and leaves nothing behind,
satisfying "move (not copy-then-leave)". Naming each relocated payload satisfies the honesty constraint
(Constitution IV) — the user sees exactly what moved at their repo root. Verified empirically (temp
target): post-`mv`, `ls` shows no real payload at root, all under `dark-factory/`.

**Note on the project workflow constraint vs the installer.** The constitution forbids *automated work*
(my own implementation steps) from using `rm`/`git reset`/`git checkout`/repo-wide `sed`. That governs
how **I** edit the repo while building this feature — it does **not** forbid the *installer* (product
code, run by an end user against their own target) from using `mv`/`rm -f` on the target. The installer
already uses `rm -f "$dest"` under `--force` (`install.sh:93`); the migration's `mv` is consistent with
that product-code behaviour. My build steps will edit `install.sh` and add a test via Edit/Write only —
no `rm`/`git reset` in the build itself.

**Migration also refreshes stale managed root symlinks (FR-006).** Relocating the real payloads
invalidates any managed root symlink that pointed at the old flat location — most sharply the root
`CLAUDE.md`, which a prior flat install wired as `CLAUDE.md -> AGENTS.md`; once the root `AGENTS.md` is
moved into `dark-factory/`, that link **dangles**. So when (and only when) a migration actually occurs
(`migrated=1`), the installer clears (`rm -f`) each **managed** root link (`.claude/skills`, `CLAUDE.md`,
`.agents`, `.specify`) that exists **as a symlink** (`[ -L ]` test — a **real** file/dir at a managed
path is never removed, preserving no-clobber FR-011), routed through the `run`/dry-run wrapper, so the
unchanged `link_one` wiring recreates each fresh into `dark-factory/` on the **default (no-`--force`)
path**. Rationale: this is the concrete meaning of FR-006's "repoint the root symlinks accordingly" —
avoiding a dangling `CLAUDE.md` after a migration — and it is **gated on `migrated=1`** so a
non-migration idempotent re-run (`migrated=0`, no real payloads at root) never clears an existing link,
keeping E2's skip-without-`--force` and FR-010 intact. `link_one` itself is not modified. Verified
empirically: seeding a flat target with `CLAUDE.md -> AGENTS.md`, after migration the root `CLAUDE.md`
resolves into `dark-factory/AGENTS.md` on the default path (no `--force`), and re-running on the migrated
target (no real payloads) leaves the now-correct links untouched.

**Alternatives considered (repoint mechanism).** (a) Rely on `link_one`'s global `--force` to repoint the
stale links — rejected: it would require every migration to be run with `--force`, and the migration
must self-heal on the default path (a dangling `CLAUDE.md` is a broken install, not something to defer
to a flag). (b) Modify `link_one` to always repoint a stale-target link — rejected: that would change
the non-migration idempotency contract (E2/FR-010) which requires leaving an existing link alone without
`--force`; clearing symlinks only in the migration block keeps `link_one` and the idempotency rule
unchanged. (c) `mv`/copy the old link — rejected: unnecessary; recreating fresh via the existing wiring
is simpler and reuses the fresh-install link targets.

**Alternatives considered (relocation).** Copy then delete the originals — rejected: a crash between
copy and delete leaves the dual layout the constitution forbids; `mv` is atomic per entry.

---

## R6 — BSD vs GNU symlink / `cp -RPp` portability (Constraints: Symlink portability)

**Decision.** Keep the existing `cp -RPp` for payload copy (preserves symlinks, never dereferences, on
both BSD/macOS and GNU coreutils — already relied on, `install.sh:84-85`). Keep `ln -s` / `ln -sfn`
for link creation. The relative-target **strings** are computed by the installer as literals (no
`realpath --relative-to`, which differs/absents on BSD); the depth math is done by counting path
segments, identical on both platforms. The `docs` payload contains its own internal symlinks
(`docs/CLAUDE.md`, and the live `docs/src/content/docs/{specs,plans}` links in SOURCE) — `cp -RPp`
preserves them as-is; the installer then *overwrites/repoints* the docs-site links to the corrected
+1-`../` targets via `link_one` (with `--force` semantics for the repoint), so the copied-in stale
links don't win.

**Rationale.** The repo's CLAUDE-level constraint and the spec both pin `cp -RPp` as the
already-working portable primitive; literal target strings avoid the BSD/GNU `realpath` divergence.
Tests run on macOS (BSD) in this environment; the strings are plain and POSIX-portable.

**Alternatives considered.** `realpath --relative-to=` to compute targets — rejected: not portable to
BSD/macOS without coreutils; brittle. `cp -a` — rejected: GNU-only flag.

---

## R7 — How the installer is tested (test-harness convention — Constitution III)

**Decision.** Add `tests/test_install.py`, a **pytest** module that invokes `install.sh` via
`subprocess.run(["bash", str(INSTALL_SH), str(target), ...])` against a `tmp_path` target and asserts
the resulting filesystem with `pathlib` (`Path.is_symlink()`, `Path.is_dir()`,
`Path.resolve()`/`os.path.realpath`, existence). This reuses the repo's **existing** pytest + uv + ruff
harness (`pyproject.toml` `testpaths=["tests"]`, root `conftest.py`, dev dep `pytest>=8`) and adds **no
new tooling** (no bats, no bespoke shell-test framework). The installer's stdout (`copied=`,
`skipped=`, `linked=`, the `relocated:` lines) is parsed where a behavioural count is the cleanest
assertion; filesystem state is the primary assertion.

**Rationale.** The convention audit (Phase 2) confirms there is **no** precedent for shell-test
tooling in this repo and an established pytest precedent (`tests/test_telemetry_hooks.py`,
`tests/test_demo_emit.py` already shell out / exercise scripts). Test-First requires a check that can
fail red before the change; a subprocess+filesystem-assertion test fails today (the installer still
produces the flat layout) and passes after. Determinism: each test gets its own `tmp_path`, builds the
needed seed state, runs the installer, asserts — no reliance on machine state.

**Rationale for SOURCE in tests.** The test must run the *real* `install.sh` against a *real* SOURCE
tree. The SOURCE is the repo root itself (`install.sh` lives there). Running the installer with the
repo root as SOURCE and a `tmp_path` as TARGET is exactly the supported invocation
(`bash /path/to/dark-factory/install.sh <target>`), and the nested-guard (`install.sh:71-72`) is
satisfied because `tmp_path` is outside the repo. Verified the guards permit this.

**Alternatives considered.** (a) `bats` shell-test framework — rejected: introduces new tooling with no
repo precedent (convention audit), against the "no swaps / reuse the harness" rule. (b) Asserting by
eyeballing dry-run output — rejected: the spec's Test-First constraint demands a deterministic
script-driven check, not eyeballing. (c) A copy of the framework into a fixture SOURCE — rejected as
unnecessary; the repo root is a valid SOURCE and avoids drift between fixture and real payloads.

---

## R3-RESULT — git-sync-extractor temp output location (summary)

`temp/` lands at the **target repo root** (`git rev-parse --show-toplevel` from the nested skill dir
returns the repo root), so the existing root `temp/` `.gitignore` entry is sufficient. See R3 for the
full evidence. No `.gitignore` change required for this feature.
