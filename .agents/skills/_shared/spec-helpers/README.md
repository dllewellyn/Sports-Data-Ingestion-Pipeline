# Shared spec/plan helpers

**This directory is not a skill** (no `SKILL.md`). Like `../git-helpers`, it is a
small library of **deterministic** checks that the spec/plan skills call instead of
re-deriving them in prose. The principle is the user's: *prefer a deterministic
check (a linter, a script) over pure-AI judgement wherever the thing being checked
is mechanical.* Authoring a spec is judgement; confirming it matches the template,
numbering it, and proving traceability closes are not — those live here.

The shell helper ships in both shells (`*.sh` + `powershell/*.ps1`, the repo
convention). The validators are **stdlib-only Python 3** — a single file is already
cross-platform, so they need no PowerShell mirror, and they add no dependency to the
target repo (run them with a bare `python3`).

| Helper | Lang | Used by | Replaces (AI eyeballing) |
|--------|------|---------|--------------------------|
| `next-number.sh` | bash + ps1 | `specification`, `missing-specification`, `feature` | "list the dir, find the highest `NNN`, add one" over the `NNN-*` **feature directories** under `specs/` — and, with `--count`, collision-free **parallel** pre-allocation for `missing-specification`'s parallel writers. (No longer used by `plan` — plan no longer allocates a number; it writes into the existing feature directory.) |
| `feature-dir.sh` | bash | every phase after `specification` (`clarify`, `plan`, `tasks`, `analyze`, `implementor`, `converge`) | "work out which feature is active" — resolves `.specify/feature.json` (`{ "feature_directory": "specs/NNN-<slug>" }`) to the feature-dir path, honouring `$SPECIFY_FEATURE_DIRECTORY` as an override. `--require-file <name>` also asserts `<dir>/<name>` exists, so a phase fails fast if its prerequisite (e.g. `spec.md`, `plan.md`) is missing. |
| `validate-spec.py` | python3 | `specification`, `missing-specification`, `feature` §A adherence | "the file matches `specification-template.md`" — checks `specs/NNN-<slug>/spec.md`: body-metadata lines (`**Feature directory**`/`**Created**`/`**Status**`/`**Input**`, **no frontmatter**), filename + `NNN-<slug>` parent agreement, the mandatory keyword `## H2` sections present + ordered, and that user stories / BDD scenarios / `FR-NNN` / `SC-NNN` / open questions are actually filled (handles the retrospective `Implemented` status variant) |
| `validate-plan.py` | python3 | `plan`, `implementor` §0 gate, `feature` §B adherence/gate | "the file matches `plan-template.md`" for `<feature_dir>/plan.md` — body-metadata lines, keyword `## H2` sections present + ordered, the **convention-audit hard gate** (no audit-table row marked `gap`), every `### Step Sn` carrying the seven mandated fields, and a filled Traceability table |
| `validate-tasks.py` | python3 | `tasks`, `implementor` §0 gate, `feature` §B adherence/gate | "the file matches `tasks-template.md`" for `<feature_dir>/tasks.md` — location, the `**Feature directory**`/`**Plan**` metadata lines, the `## Phase ...` + `## Dependencies & Execution Order` sections, well-formed and unique `T###` task ids, and that tasks carry a `[Sn]` plan-step reference so traceability can close |
| `trace-check.py` | python3 | `implementor` §0 gate, `feature` §B/§E | the set arithmetic of "every spec `FR-NNN`/`SC-NNN` reaches a plan step; every step traces back" — and, with a third `tasks.md` argument, "every plan step is covered by a task" |
| `docs-sync.sh` | bash | docs publishing for a feature | mirrors a feature dir (`specs/NNN-<slug>/`) into `docs/src/content/docs/features/<slug>/` so the Astro/Starlight site renders it, injecting the `title:` frontmatter Starlight's docsSchema requires. **Copy-only — it never deletes** (no `rm`), so removing a feature from the site is a manual step. |
| `_specdoc.py` | python3 | (internal) the validators + trace-check | the shared `## H2` heading parser and Markdown-table parser (rule of three) |

## What these do NOT do

They check **structure and coverage arithmetic**, never **quality**. A spec can pass
`validate-spec.py` and still have weak BDD, the wrong altitude, or a meaningless
traceability mapping — that is the writer's craft and the reviewer's judgement, and
no script should pretend otherwise. `trace-check.py` matches `FR-NNN` / `SC-NNN` /
`Sn` ids as text; whether a mapping is *meaningful* stays with the reviewer. Treat a green run as
"the mechanical preconditions are met," not "the document is good."

## Quick reference

```bash
# Next feature-directory number (003); or a block of three for parallel writers:
bash .agents/skills/_shared/spec-helpers/next-number.sh specs
bash .agents/skills/_shared/spec-helpers/next-number.sh specs --count 3

# Resolve the active feature directory (and assert a prerequisite file exists):
bash .agents/skills/_shared/spec-helpers/feature-dir.sh
bash .agents/skills/_shared/spec-helpers/feature-dir.sh --require-file plan.md

# Structural lint (exit 1 on any error; warnings are non-fatal):
python3 .agents/skills/_shared/spec-helpers/validate-spec.py  specs/003-foo/spec.md
python3 .agents/skills/_shared/spec-helpers/validate-plan.py  specs/003-foo/plan.md
python3 .agents/skills/_shared/spec-helpers/validate-tasks.py specs/003-foo/tasks.md

# Traceability closure — spec → plan (2-arg) or spec → plan → tasks (3-arg):
python3 .agents/skills/_shared/spec-helpers/trace-check.py \
  specs/003-foo/spec.md specs/003-foo/plan.md
python3 .agents/skills/_shared/spec-helpers/trace-check.py \
  specs/003-foo/spec.md specs/003-foo/plan.md specs/003-foo/tasks.md

# Mirror a finished feature dir into the Starlight docs site (copy-only):
bash .agents/skills/_shared/spec-helpers/docs-sync.sh specs/003-foo
```

PowerShell: `pwsh .../spec-helpers/powershell/next-number.ps1 specs -Count 3`. The
Python validators run identically under `python3` / `python` on any platform.

> The bash + Python helpers are smoke-tested. The PowerShell mirror of
> `next-number` was authored without a local `pwsh` to run it — verify on first use.
