---
title: "Quickstart: Subdir Install Layout"
---

# Quickstart: Subdir Install Layout

**Feature directory**: `specs/002-subdir-install-layout/`
**Date**: 2026-06-30

Runnable validation scenarios proving the installer produces the new `dark-factory/` layout and that
the layout stays usable by Claude Code and the framework helpers. These are validation *scenarios* (how
to prove it works end-to-end), not the test code — the automated tests live in `tests/test_install.py`.

## Prerequisites

- The Dark Factory checkout (this repo) as **SOURCE**; `install.sh` lives at its root.
- `uv` available (the repo's package manager); `pytest>=8` in the dev group (already present).
- A scratch directory **outside** the repo to use as TARGET (the installer refuses a nested/identical
  SOURCE/TARGET).

## Run the automated tests (primary gate)

```bash
cd /path/to/dark-factory
uv run pytest tests/test_install.py -q
```

Expected: all `test_install.py` cases pass (fresh install, migration, dry-run zero-change, idempotency,
no-clobber, `--force`, guard refusal). Before the implementation lands, these fail red (the installer
still produces the flat layout).

The full suite (existing telemetry tests + the new installer tests) must stay green:

```bash
uv run pytest -q
```

## Manual end-to-end scenarios

### Scenario A — fresh install into a clean target (US1)

```bash
TARGET="$(mktemp -d)"
bash /path/to/dark-factory/install.sh "$TARGET"
```

Expected on disk:
- `dark-factory/` contains `.agents`, `.specify`, `telemetry`, `docs`, `AGENTS.md` (real payloads).
- **No real** `.agents`/`.specify`/`telemetry`/`docs`/`AGENTS.md` at `$TARGET` root.
- Root symlinks exist and resolve into `dark-factory/`:
  `.claude/skills` → `dark-factory/.agents/skills`; `CLAUDE.md` → `dark-factory/AGENTS.md`;
  `.agents` → `dark-factory/.agents`; `.specify` → `dark-factory/.specify`.
- `dark-factory/docs/src/content/docs/{specs,plans}` resolve to root `specs/`/`plans/`.
- `specs/` and `plans/` are **real** directories at the root, each with `.gitkeep`.

Verify helper resolution from the root:
```bash
cd "$TARGET"
test -e .specify/feature.json -o -d .specify        # .specify resolves
ls .agents/skills >/dev/null                          # a skill path resolves
```

### Scenario B — migrate a prior flat install (US2)

```bash
TARGET="$(mktemp -d)"
# Seed an old flat install: real payloads + old-style root links at the root
mkdir -p "$TARGET"/{.agents/skills,.specify,telemetry,docs}; echo x > "$TARGET/AGENTS.md"
mkdir -p "$TARGET/.claude"; ln -s ../.agents/skills "$TARGET/.claude/skills"; ln -s AGENTS.md "$TARGET/CLAUDE.md"
mkdir -p "$TARGET/specs"; echo keep > "$TARGET/specs/mine.txt"   # user content
bash /path/to/dark-factory/install.sh "$TARGET"
```

Expected: the installer **names each relocated payload** in its output; afterwards no real payload
remains at the root, all are under `dark-factory/`, root symlinks repoint into `dark-factory/`, and
`$TARGET/specs/mine.txt` is untouched. No dual layout survives.

### Scenario C — dry-run makes zero changes (US3)

```bash
TARGET="$(mktemp -d)"; mkdir -p "$TARGET/.agents"   # flat seed (optional)
before="$(cd "$TARGET" && find . | sort)"
bash /path/to/dark-factory/install.sh "$TARGET" --dry-run
after="$(cd "$TARGET" && find . | sort)"
[ "$before" = "$after" ] && echo "UNCHANGED (pass)" || echo "CHANGED (fail)"
```

Expected: the printed plan describes the `dark-factory/` payloads, the root symlinks and their targets,
and (for a flat seed) the migration relocations; the filesystem is unchanged.

### Scenario D — idempotent re-run + `--force` (US4)

```bash
bash /path/to/dark-factory/install.sh "$TARGET"            # second run: copies/relocates nothing new
bash /path/to/dark-factory/install.sh "$TARGET" --force    # refreshes copied files, repoints symlinks, no error
```

Expected: the no-`--force` re-run reports skipped (nothing newly copied/relocated) and leaves the
layout identical; `--force` overwrites copied payloads and repoints root symlinks without erroring.

## Cleanup

```bash
rm -rf "$TARGET"   # manual cleanup of the scratch target (pytest tmp_path is auto-cleaned)
```
