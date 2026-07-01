---
title: "Drafted rules — RESOLVED ✅ APPROVED & COMMITTED to the constitution (v1.1.0)"
---

# Drafted rules — RESOLVED ✅ APPROVED & COMMITTED to the constitution (v1.1.0)

**Status (2026-06-30):** Both rules below were **approved by the user** and are now **committed to the
project constitution** as the *"Shell / installer conventions"* subsection of *Development Workflow &
Quality Gates*, shipped in constitution **v1.1.0** (commit `713d42d`,
`docs(constitution): add shell/installer conventions (feature 002)`). This file is retained as a
planning/audit artifact only — it is **no longer pending** and the canonical source of these rules is
`.specify/memory/constitution.md`. The original drafting context is preserved below for the record.

These two conventions were **drafted** by the convention-audit gate of the `plan` skill because the
artifact types this feature touches (Bash installer code; pytest-via-subprocess test of a shell script)
had **no written governing convention** in this repo at the time (no `ARCHITECTURE.md`, no `.claude/rules/`,
no shell convention in the constitution; the root `CLAUDE.md` is the speckit stub). Per the
non-interactive plan brief and Constitution II, they were **recorded as blockers needing user approval**
rather than silently committed on the user's behalf — that approval has since been granted.

**Target file (where these belong once approved):** `.specify/memory/constitution.md` — under a new
*"Shell / installer conventions"* subsection of *Development Workflow & Quality Gates*. The project
keeps conventions in the constitution; there is no `CLAUDE.md`-conventions file or `.claude/rules/` dir.
`create-rule`'s default target (`./CLAUDE.md`) does not apply because the root `CLAUDE.md` is a
speckit-managed stub symlinked to `AGENTS.md`.

The convention-audit table in `plan.md` lists both as **created this run (pending approval)** so the
plan validates; implementation steps S1+ must not begin until these are approved + committed (the
self-review checkpoints reference them).

---

## DRAFT RULE 1 — Bash script conventions (governs edits to `install.sh`)

> **Shell scripts** (`install.sh`, `.agents/skills/**/scripts/bash/*.sh`):
> - **ALWAYS** start with `set -euo pipefail`.
> - **ALWAYS** quote every variable expansion (`"$var"`, `"${arr[@]}"`) and use `[ ... ]`/`[[ ... ]]`
>   tests, never unquoted word-splitting.
> - **ALWAYS** use `pathlib`-free POSIX-portable primitives that work on **both BSD (macOS) and GNU
>   coreutils**: `cp -RPp` to copy (preserving symlinks), `ln -s`/`ln -sfn` for links, literal
>   relative-target strings (NEVER `realpath --relative-to`, which is GNU-only).
> - **ALWAYS** route every filesystem mutation through the script's `--dry-run` wrapper (e.g. the `run`
>   helper) so a dry run makes **zero** changes.
> - **NEVER** dereference a symlink when copying a payload (use `-P`); **NEVER** clobber a pre-existing
>   real file where a link belongs — leave it and warn.

*Rationale / source:* Google Shell Style Guide (quoting, `set -euo pipefail`) + the repo's existing
`install.sh` and helper-script patterns (the strongest in-tree precedent). Codifies the BSD/GNU
portability constraint the spec pins (Symlink portability) so future installer edits stay portable.

---

## DRAFT RULE 2 — Testing shell scripts (governs `tests/test_install.py`)

> **Testing a shell script:** assert its behaviour with a **pytest** module under `tests/` that invokes
> the script via `subprocess.run(["bash", str(SCRIPT), ...])` against a `tmp_path` and asserts the
> resulting filesystem with `pathlib`/`os.path` (`Path.is_symlink()`, `Path.is_dir()`,
> `os.path.realpath`). **ALWAYS** reuse the repo's existing pytest+uv harness; **NEVER** introduce a
> separate shell-test framework (e.g. `bats`) — there is no in-repo precedent and it would be a tooling
> swap (Constitution: use the repo's own tooling). Each test builds its own seed state under `tmp_path`
> so it is deterministic and order-independent.

*Rationale / source:* the repo's existing `tests/test_telemetry_hooks.py` already exercises scripts/
hooks from pytest; `pyproject.toml` pins `pytest>=8`, `testpaths=["tests"]`; root `conftest.py` puts the
repo root on `sys.path`. This makes the installer's Test-First gate (Constitution III) real without new
tooling.

---

## Note on the absent pre-commit gate (surfaced, not a drafted rule)

The constitution and `install.sh`'s docs reference `uv run pre-commit run --all-files`, but **no
`.pre-commit-config.yaml` exists anywhere in the repo** (verified). The real, runnable gates are
`uv run ruff check` / `uv run ruff format` (ruff configured in `pyproject.toml`: line-length 100,
select E,W,F,I,UP,B,C4,SIM) and `uv run pytest`. The guardrail register in `plan.md` therefore names
**ruff + pytest run via `uv`** as the gates (not a non-existent pre-commit hook). This is surfaced as an
Open Question for the user: either (a) accept ruff+pytest-via-uv as the gate for this feature, or (b)
introduce a `.pre-commit-config.yaml` first (a separate change, not in this feature's scope). The plan
proceeds under (a) and records (b) as a beneficial follow-up.
