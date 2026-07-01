# Dark Factory Constitution

The canonical governance source for this project. Every phase of the workflow — `specification`,
`plan`, `tasks`, `implementor`, and the `speckit-*` gate tools — reads and enforces this file.
It is **kept continuously updated** as the project evolves: the `self-learn` skill routes durable,
project-wide rules here, and `speckit-constitution` keeps dependent templates in sync.

> Seeded from the standing global engineering principles (no concrete project `CLAUDE.md` /
> `ARCHITECTURE.md` constraints exist yet). Extend with project-specific principles — data contracts,
> medallion-layer rules, runtime constraints — as they are established.

## Core Principles

### I. No Backward Compatibility
Never implement backward compatibility. Never refactor code to serve both its new objective and a
legacy one — remove the legacy path. A change replaces; it does not accrete. This applies to this
workflow's own evolution as much as to product code.

### II. No Reward Hacking (NON-NEGOTIABLE)
Outside test fixtures, never use placeholders, mocks, hardcoded values, or stub implementations to
make work *appear* done. Never suppress, bypass, default-away, or add permissive variants to quality
gates, errors, deprecation warnings, or test failures. Never skip a failing task silently or
implement a fallback/temporary strategy to meet a requirement. Never bypass gates with `--skip` or
`--no-verify`. If a gate fails, fix the cause or stop and report it.

**Constraint-bypass requires escalation, never self-approval.** Weakening a constraint to make work
pass — adding a lint-ignore (`# noqa`, a ruff ignore entry), softening or skipping pre-commit,
loosening a hook, narrowing/`xfail`-ing a test, or pushing files that shouldn't be pushed — must be
escalated to the orchestrator (`feature`'s blocker protocol) or the user and explicitly approved. No
agent, implementer, or reviewer may approve such a change itself; a review that finds one fails it.

### III. Test-First (NON-NEGOTIABLE)
TDD is mandatory: a test that can genuinely fail is written and seen red before the code exists;
red → green → refactor. Tests must be real and useful — narrowing a test to pass is reward hacking
(see II). Each unit of behaviour maps to an objectively pass/fail check using the right facility
(pytest, dbt tests, Pydantic/Pandera validation, artifact assertions).

### IV. Honesty & Permission to Fail
Report outcomes faithfully: if tests fail, say so with the output; if a step was skipped, say so.
You have explicit permission to say "I don't know" or "I'm not confident" when information is
unavailable, verification is impossible, or multiple answers seem equally valid. Never bypass or
change a task that fails without the user's permission.

### V. Surface Contradictions & Beneficial Changes
Always raise contradictions and knock-on effects implied by the objective that the user has not
mentioned. Always include beneficial, objective-linked changes the user has not raised. Do not paper
over conflicts between a requirement and an existing principle — surface them.

## Security Requirements

- Never commit, echo, print, or log API keys, tokens, passwords, or secrets in command output or
  transcripts.
- Verify environment variables by presence, not by printing their value.
- If a sensitive value must be displayed, mask it (show first/last 4 characters only).

## Development Workflow & Quality Gates

- **Version control:** Conventional Commits (`feat|fix|refactor|build|ci|chore|docs|style|perf|test`).
  Commit atomically at the logical conclusion of a unit of work to checkpoint known-good states.
  Start work from `git status` / `git diff` / `git log`. Never `git push`, `git checkout`,
  `git switch`, `git reset --hard`, `git clean`, `git restore`, or `rm` as part of automated work.
  Never run repo-wide search/replace scripts (`sed -i`, `perl -pi -e`, `python -c`).
- **Tooling:** use the repo's own package manager/runtime — no swaps.
- **Gates as defined:** quality gates and tests are run as written and must pass on their own terms
  (see Principle II). Prefer a deterministic script/linter over pure-AI judgement wherever the thing
  being checked is mechanical.

### Shell / installer conventions

- **Bash scripts** (`install.sh`, `.agents/skills/**/scripts/bash/*.sh`): ALWAYS start with
  `set -euo pipefail`. ALWAYS quote every variable expansion (`"$var"`, `"${arr[@]}"`) and use
  `[ ... ]` / `[[ ... ]]` tests — NEVER rely on unquoted word-splitting. ALWAYS use POSIX-portable
  primitives that work on both BSD (macOS) and GNU coreutils: `cp -RPp` to copy (preserving
  symlinks), `ln -s` / `ln -sfn` for links, literal relative-target strings — NEVER
  `realpath --relative-to` (GNU-only). ALWAYS route every filesystem mutation through the script's
  `--dry-run` wrapper (e.g. the `run` helper) so a dry run makes zero changes. NEVER dereference a
  symlink when copying a payload (use `-P`); NEVER clobber a pre-existing real file where a link
  belongs — leave it and warn.
- **Testing shell scripts:** ALWAYS assert a shell script's behaviour with a `pytest` module under
  `tests/` that invokes the script via `subprocess.run(["bash", str(SCRIPT), ...])` against a
  `tmp_path` and asserts the resulting filesystem with `pathlib` / `os.path`
  (`Path.is_symlink()`, `Path.is_dir()`, `os.path.realpath`). ALWAYS reuse the repo's existing
  pytest+uv harness; NEVER introduce a separate shell-test framework (e.g. `bats`) — there is no
  in-repo precedent and it would be a tooling swap (see Tooling, above). Each test builds its own
  seed state under `tmp_path` so it is deterministic and order-independent.

### Code-defined audit checks (`@audit`)

- ALWAYS define an audit check as a single function decorated `@audit(name="…", **metadata)`; the
  decorator registers it in the module-level audit registry at import time. NEVER discover audits by
  scanning source text.
- ALWAYS signal a failure by raising the framework's `AuditFailure(evidence=…)` (and a soft finding by
  raising `AuditWarning`); a clean return is `pass`. NEVER signal pass/fail by return value alone, and
  NEVER swallow an unexpected exception inside an audit — an uncaught exception is reported as the
  distinct `error` verdict by the runner.
- ALWAYS give each audit a unique `name`; NEVER register two audits under the same name (the registry
  refuses the duplicate).
- ALWAYS read a run's telemetry through the provided query helpers
  (`get_all_reads_from_code_review_agent()`, `all_diffs_for_feature()`, …); NEVER hand-roll a Loki
  query inside an audit body.
- ALWAYS resolve "which agent" by the telemetry `role` attribute, NEVER by `agent_id`.
- ALWAYS import the framework as `from audit import audit, AuditFailure, AuditWarning` (the runner
  injects `.agents/skills/_shared/telemetry` onto `sys.path` before importing the audit file); NEVER
  assume a `telemetry.audit` package path or a `[project.scripts]` console entry point — the runner is
  invoked by path (`uv run python .agents/skills/_shared/telemetry/audit/runner.py …`), mirroring
  `emit.py` (the repo's `pyproject.toml` sets `[tool.uv] package = false`).

Minimal example:

```python
from audit import audit, AuditFailure

@audit(name="all_changed_files_code_reviewed", severity="high", category="review-integrity")
def all_changed_files_code_reviewed(run):
    reviewed = run.get_all_reads_from_code_review_agent()
    unreviewed = [f for f in run.all_diffs_for_feature() if f not in reviewed]
    if unreviewed:
        raise AuditFailure(evidence={"unreviewed_files": sorted(unreviewed)})
```

## Governance

This constitution supersedes other practices where they conflict. Amendments are made by updating
this file (via `self-learn` or `speckit-constitution`), which must also propagate to dependent
templates (`spec-template.md`, `plan-template.md`, `tasks-template.md`). All phases verify compliance;
complexity must be justified against these principles.

**Version**: 1.2.0 | **Ratified**: 2026-06-29 | **Last Amended**: 2026-07-01
