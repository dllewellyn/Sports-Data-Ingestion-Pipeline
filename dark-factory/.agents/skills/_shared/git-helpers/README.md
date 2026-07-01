# Shared git helpers

**This directory is not a skill** (it has no `SKILL.md`). It is a small library of
deterministic git wrappers that several skills call instead of hand-rolling git in
prose. The goal is to push the fiddly, error-prone, or safety-critical git plumbing
into one tested place — so a skill works out *what* it wants, not *how* to drive git.

Each helper ships in both shells, mirroring the repo convention:
`bash/<name>.sh` and `powershell/<name>.ps1`.

| Helper | Read/Write | Used by | Replaces (inline git) |
|--------|-----------|---------|-----------------------|
| `git-changeset` | read-only | `code-architecture-review`, `improvement-review`, `self-learn`, `implementor` (resume) | the `git status` / `git diff` / `git diff main...HEAD` / `git log` trio, with a real default-branch + merge-base resolver instead of a hardcoded `main` |
| `git-history` | read-only | `missing-specification` | `git log --oneline --reverse` + per-commit `git show --stat` history walking |
| `git-commit-safe` | **write (guarded)** | `implementor`, `self-learn` (optional commit) | the atomic-commit protocol: stage only the footprint, Conventional-Commits gate, co-author trailer, hooks always run |
| `git-audit-commits` | read-only | `feature` (adherence meta-reviewer) | the mechanical half of "commits are clean" — conventional format, no merges, atomicity heuristic |
| `classify-commits` | read-only | `missing-specification` (§2 pre-filter) | the mechanical half of commit classification — tags each commit `AUTO-NONSUBSTANTIVE` / `DEP` / `CANDIDATE` by changed-path footprint so the agent only judges the ambiguous ones (it never decides covered-vs-unspecified) |

## Why these enforce the rules structurally

The project's git rules (global `CLAUDE.md`) forbid `push`, `checkout`, `switch`,
`reset --hard`, `clean`, `restore`, `rm`, and bypassing gates with `--no-verify` /
`--skip`. The read-only helpers only ever run inspection verbs. `git-commit-safe`
only ever runs `git add` + `git commit` (hooks enabled) — it **exposes none of the
forbidden verbs**, so a skill calling it cannot do the wrong thing even by mistake.
That makes the guardrail load-bearing rather than advisory.

`git-commit-safe` deliberately **refuses** rather than guessing when:
- the subject isn't a Conventional Commit;
- the index has changes staged **outside** the paths you named (it won't sweep them in,
  and it can't unstage them — `reset`/`restore` are forbidden — so it stops and reports);
- HEAD is on the default branch and you didn't pass `--allow-default-branch`
  (the branch decision is the user's; the script never switches branches);
- a hook rejects the commit (the task isn't green — fix and re-review, never bypass).

## Quick reference

```bash
# What changed on this branch / in the tree (auto-resolves base + merge-base):
bash .agents/skills/_shared/git-helpers/bash/git-changeset.sh [--stat] [--base <ref>] [--section all|log|status|diff]

# Walk full history (retro-spec backfill):
bash .agents/skills/_shared/git-helpers/bash/git-history.sh list [--since <ref>]
bash .agents/skills/_shared/git-helpers/bash/git-history.sh show <sha> [--diff]

# Guarded atomic commit (stages ONLY the listed paths):
bash .agents/skills/_shared/git-helpers/bash/git-commit-safe.sh -m "feat(scope): summary" path/one path/two

# Audit branch commits for mechanical hygiene (exit≠0 if a commit fails the gate):
bash .agents/skills/_shared/git-helpers/bash/git-audit-commits.sh [--base <ref>]

# Pre-filter history by changed-path footprint (retro-spec classification):
bash .agents/skills/_shared/git-helpers/bash/classify-commits.sh [--since <ref>]
```

PowerShell equivalents live in `powershell/` with the same names and `-PascalCase`
flag spellings (e.g. `-Stat`, `-Base`, `-Section`).

> The bash helpers are smoke-tested. The PowerShell mirrors reproduce the same logic
> but were authored without a local `pwsh` to run them — verify on first use in a
> PowerShell environment.
