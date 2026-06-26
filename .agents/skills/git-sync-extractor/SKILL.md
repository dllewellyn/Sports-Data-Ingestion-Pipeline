---
name: git-sync-extractor
description: Incrementally extract per-commit diffs and net-new file contents for paths matching configurable patterns (e.g. architecture/, transcripts/), writing them under temp/<short_sha>/ to feed the downstream knowledge-extraction pipeline. Use when asked to sync, extract, or replay git history for the processors, or to run/status/reset the extractor.
compatibility: Requires git >= 2.x and Bash >= 4 (or PowerShell >= 7); python3 used for JSON escaping in the Bash variant (has a fallback).
---

# Skill: Git Sync Extractor

## Purpose

Incrementally extract per-commit diffs and new-file contents for files matching configurable path patterns (e.g. `architecture/`, `transcripts/`). Designed to feed downstream processing pipelines that need to replay repository changes file-by-file.

## When invoked

This is a **deterministic CLI** — the script already implements everything below. Your job is to **run it and report what it did**, not to build or change it.

1. Pick the operation from the user's request (`run` is the default; `status` to inspect; `reset` to reprocess from scratch) and run the entrypoint:
   ```bash
   ./scripts/bash/git-sync-extractor.sh run        # or: status | reset
   ./scripts/powershell/git-sync-extractor.ps1 run # PowerShell equivalent
   ```
2. Pass through any patterns/refs the user named (`--pattern <p>`, `--from <ref>`, etc. — see Options).
3. Summarise the output for the user: which commits were processed, what landed in `temp/<short_sha>/`, and the new `.last-sync` value.

**Do NOT** read, audit, "verify against the contract", or edit the scripts unless the user explicitly asks you to change the tool itself. Everything from `## How it works` down is the **behavioural contract the script already satisfies** — reference material, not a task list.

## How it works

1. Reads `.last-sync` from the repository root for the last processed commit hash.
2. If absent or empty, prompts the user to choose a starting point (first commit or a specific ref).
3. Walks every commit since that point **in chronological order**.
4. For each commit, any file matching one of the configured patterns is categorised:
   - **Added** → full file content written to `temp/<short_sha>/new_<flat_path>`
   - **Modified / renamed / copied** → unified diff written to `temp/<short_sha>/changed_<flat_path>.diff`
   - **Deleted** → recorded in JSON only (no output file)
5. A manifest `temp/<short_sha>/changed_files.json` is written for every commit that has matching files.
6. `.last-sync` is updated to the latest processed commit so subsequent runs only process new commits.

### File name flattening

Path separators (`/`) are replaced with `__` in output filenames to avoid nested directories inside each commit folder.

Example: `architecture/sequence/login.puml` →
- if added: `temp/a1b2c3d4/new_architecture__sequence__login.puml`
- if modified: `temp/a1b2c3d4/changed_architecture__sequence__login.puml.diff`

### `changed_files.json` structure

```json
{
  "commit": "<full SHA>",
  "short_commit": "<8-char SHA>",
  "author": "Name",
  "author_email": "email@example.com",
  "timestamp": "2024-01-15T10:30:00+00:00",
  "message": "feat: update login sequence diagram",
  "patterns": ["architecture", "transcripts"],
  "files": [
    { "path": "architecture/sequence/login.puml", "status": "modified", "output": "changed_architecture__sequence__login.puml.diff" },
    { "path": "transcripts/session-42.txt",       "status": "added",    "output": "new_transcripts__session-42.txt" },
    { "path": "architecture/old.puml",             "status": "deleted",  "output": null }
  ]
}
```

## Command Entrypoints

- Bash:       `scripts/bash/git-sync-extractor.sh`
- PowerShell: `scripts/powershell/git-sync-extractor.ps1`

Both scripts must be run from within the target git repository, or will auto-detect the repo root from their own location.

## Operation Mapping

### Run (default — extract new commits)

```bash
# Bash — default patterns (architecture, transcripts)
./scripts/bash/git-sync-extractor.sh run

# Bash — custom patterns
./scripts/bash/git-sync-extractor.sh run --pattern docs --pattern diagrams

# Bash — force start from a specific commit
./scripts/bash/git-sync-extractor.sh run --from abc1234

# PowerShell
./scripts/powershell/git-sync-extractor.ps1 run
./scripts/powershell/git-sync-extractor.ps1 run -Pattern docs -Pattern diagrams
./scripts/powershell/git-sync-extractor.ps1 run -From abc1234
```

### Status — inspect sync state without processing

```bash
./scripts/bash/git-sync-extractor.sh status
./scripts/powershell/git-sync-extractor.ps1 status
```

### Reset — clear `.last-sync` to reprocess all commits

```bash
./scripts/bash/git-sync-extractor.sh reset
./scripts/powershell/git-sync-extractor.ps1 reset
```

## Options

| Option (Bash)     | Option (PowerShell) | Default                         | Description                              |
|-------------------|---------------------|---------------------------------|------------------------------------------|
| `--pattern <p>`   | `-Pattern <p>`      | `architecture`, `transcripts`   | Path prefix to match (repeatable)        |
| `--temp <dir>`    | `-Temp <dir>`       | `<repo_root>/temp`              | Output directory                         |
| `--last-sync <f>` | `-LastSync <f>`     | `<repo_root>/.last-sync`        | Path to the sync state file              |
| `--from <ref>`    | `-From <ref>`       | _(reads `.last-sync`)_          | Override start commit; skips prompt      |

## Output directory layout

```
temp/
  <short_sha>/
    changed_files.json
    new_<flat_path>                   ← added files (full content)
    changed_<flat_path>.diff          ← modified files (unified diff)
```

## Guardrails

- Never deletes or modifies files inside `temp/` — only appends new commit folders.
- Never rewrites `.last-sync` unless at least one commit was processed successfully.
- Commits with no matching files produce no output and are silently skipped.
- If a file cannot be read from git (e.g. binary, missing blob), a warning is printed and the file is skipped; processing continues.
- The first commit of a repository has no parent; for modified files in that commit the full file content is written instead of a diff.

## Dependencies

- `git` ≥ 2.x in PATH
- Bash ≥ 4 (for associative arrays) **or** PowerShell ≥ 7 (`pwsh`)
- `python3` in PATH (Bash script only — used for JSON string escaping; falls back to simple substitution if absent)
