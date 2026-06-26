---
name: changelog-generator
description: Maintain a repository-level CHANGELOG.md in Open Knowledge Format (OKF), one reverse-chronological entry per commit, by reading the per-commit manifests, the processors' extracted findings, and the raw changed_*.diff files. The agent authors the Markdown; helper scripts only report pending commits. Idempotent via per-entry okf:commit markers. Use when asked to update/generate the changelog or log a commit's knowledge changes.
compatibility: Requires Bash >= 4 (or PowerShell >= 7) for the discovery scripts; runs after git-sync-extractor and the processors. No az.
---

# Skill: Changelog Generator

## Purpose

Maintain a repository-level **`CHANGELOG.md`** written in the **Open Knowledge Format (OKF)** that records, per commit, what knowledge materials were added or changed and what each change means. It is the human- and agent-readable history layer over the knowledge-extraction pipeline. You (the agent) author the Markdown — the helper scripts only report which commits are pending.

This skill is the *consumer* end of the pipeline: it reads the per-commit manifests, the processors' extracted findings, **and** the raw `changed_*.diff` files (the one place modified materials get summarised, since the processors handle net-new files only).

## When to invoke

- User asks to "update the changelog", "generate the changelog", "log this commit's knowledge changes", "run the changelog generator"
- A pipeline step calls for recording knowledge changes after `git-sync-extractor` and the processors have run
- User asks what changed in the knowledge materials across recent commits

---

## OKF, briefly

[OKF](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing) is a minimally-opinionated, vendor-neutral format: **Markdown files with YAML frontmatter**, organised in directories, cross-linked with normal Markdown links. The only hard requirement is a `type` field in the frontmatter. OKF's chronological-history concept is exactly a changelog/`log` file — which is what we produce here.

`CHANGELOG.md` is **durable, committed knowledge** (unlike `temp/`, which is regenerated and gitignored). Keep it at the repo root and let it be committed.

---

## Inputs

For each commit, `git-sync-extractor` writes `temp/<short_sha>/`. You consume:

- `temp/<short_sha>/changed_files.json` — commit metadata (`commit`, `short_commit`, `author`, `timestamp`, `message`) **and** the per-file manifest (`files[]`, each with `path` + `status` of `added` / `modified` / `deleted`). This is the spine of each changelog entry.
- `temp/<short_sha>/extracted_<flat>.json` — transcript-processor findings for an **added** transcript (design decisions, requirements, terminology, trade-offs, open questions, timeline, `architecture_evolution`).
- `temp/<short_sha>/arch_extracted_<flat>.json` — architecture-processor findings for an **added** architecture doc (components, notes, relationships, state models, error handling, rate limiting, queues, health checks, etc.).
- `temp/<short_sha>/changed_<flat>.diff` — unified diff for a **modified** material. There is **no** extracted JSON for modified files, so this diff is your only source for "key changes from previous version" — read it directly.

> Flat-path scheme (shared with the rest of the pipeline): `architecture/payment.puml` → `new_architecture__payment.puml` → finding `arch_extracted_architecture__payment.puml.json`; modified → `changed_architecture__payment.puml.diff`.

---

## Output

A single OKF file at the repo root (override with `--changelog`):

```
CHANGELOG.md
```

### File-level frontmatter (write once, at the very top)

```yaml
---
type: OKF Changelog
title: Knowledge Changelog
description: Per-commit record of added and changed knowledge materials, extracted by the .agents pipeline.
timestamp: <ISO 8601 UTC of this update>
---
```

### Per-commit entry

Entries are **reverse-chronological** (newest first), so insert a new entry **below the frontmatter and above the existing entries**, ordered by the manifest `timestamp`. Every entry MUST begin with the detection marker so the helper script can tell it has been logged:

```markdown
## <short_sha> — <commit subject line>
<!-- okf:commit=<short_sha> -->

- **Commit:** `<full commit sha>`
- **Author:** <author>
- **Date:** <ISO 8601 date from manifest timestamp>
- **Message:** <full commit message>

### Created materials
<!-- one block per file with status "added"; omit this heading if none -->

#### `<source path>`
- **Name:** <human title — diagram/doc name, or the file's basename>
- **Date:** <commit date>
- **New requirements extracted:** <bulleted requirements/decisions drawn from the finding JSON; "None recorded" if the finding has none>
- **Architecture evolution notes:** <what this material establishes about the architecture; for a brand-new file this is the baseline it introduces>

### Changed materials
<!-- one block per file with status "modified"; omit this heading if none -->

#### `<source path>`
- **Name:** <human title>
- **Date:** <commit date>
- **Key changes from previous version:** <summary derived from changed_<flat>.diff — what was added/removed/altered>
- **New requirements extracted:** <any new requirement/constraint introduced by the diff; "None" if purely cosmetic>
- **Architecture evolution notes:** <how the architecture moved: what the prior version implied vs. what this revision implies, the driver if discernible>

### Removed materials
<!-- list files with status "deleted"; omit this heading if none -->
- `<source path>` — removed
```

> If a commit's manifest has files but **none** match the knowledge patterns you care about, still write the entry with the commit metadata and note "No knowledge materials changed in this commit." Skip commits with no manifest entirely (they are not in `temp/`).

---

## Field → source mapping

Fill each requested field from these sources. **Extract only what is present — never invent requirements or evolution notes.**

| Changelog field | Added material (status `added`) | Changed material (status `modified`) |
|---|---|---|
| **Name** | `source_file` basename / diagram title in the doc | same |
| **Date** | manifest `timestamp` | manifest `timestamp` |
| **Key changes from previous version** | n/a (new file — state "new material") | **read `changed_<flat>.diff`**: summarise added/removed/changed lines |
| **New requirements extracted** | transcript: `regulatory_requirements`, `design_decisions`; architecture: `error_handling.requirement`, `health_checks.requirement`, `rate_limiting`, `reconciliation_logic` | derive from the diff's added lines only (new notes, new `Rel_`, new constraints) |
| **Architecture evolution notes** | transcript: `architecture_evolution` (`current_state` → `proposed_change`, `driver`); architecture: `components`, `state_models`, `relationships`, dated `notes` | contrast diff before/after: new/removed components, relationships, states |

If a finding JSON does not yet exist for an `added` file (the processor hasn't run), say so explicitly in the entry ("finding not yet extracted") rather than guessing — do not block.

---

## Step-by-step instructions

### 1. Discover pending commits

```bash
./scripts/bash/changelog-generator.sh list
```

Prints one line per commit in `temp/` not yet in `CHANGELOG.md`: `<short_sha>\t<manifest_path>`. Use `--commit <sha>` to scope to one commit; `--changelog <path>` to target a different file.

### 2. Order the work

Read each pending manifest's `timestamp`. Process oldest→newest internally but **insert newest-first** into the file so the changelog reads reverse-chronologically.

### 3. For each pending commit

a. **Read the manifest** `temp/<short_sha>/changed_files.json` — capture commit metadata and the `files[]` list (path + status).

b. **For each `added` file**, read its finding (`extracted_<flat>.json` or `arch_extracted_<flat>.json`) and fill the *Created materials* block. If no finding exists, read the `new_<flat>` content lightly or note it is unextracted.

c. **For each `modified` file**, read `changed_<flat>.diff` and fill the *Changed materials* block — this diff is the authority for "key changes from previous version".

d. **For each `deleted` file**, add it to *Removed materials*.

e. **Compose the entry** per the template above, including the `okf:commit=<short_sha>` marker.

### 4. Write CHANGELOG.md

- If the file doesn't exist, create it with the frontmatter, then the entries.
- If it exists, update the frontmatter `timestamp` and insert the new entries in reverse-chronological position. **Never rewrite or reorder existing entries** — append/insert only.

### 5. Report

Print a short summary: `✓ logged <n> commit(s) to CHANGELOG.md` and list the short_shas added.

---

## Idempotency

A commit is already logged when `CHANGELOG.md` contains `<!-- okf:commit=<short_sha> -->`. The `list` command hides logged commits; do not re-add them unless the user explicitly asks to regenerate (in which case remove the existing entry first, then re-author).

---

## Guardrails

- **Author only — never mutate source.** Read `temp/` inputs and the findings; the only file you write is `CHANGELOG.md` (or the `--changelog` target).
- **No fabrication.** Requirements and evolution notes must trace to a finding JSON or a diff line. If a field has no source, write "None recorded" rather than inventing content.
- **CHANGELOG.md is committed, `temp/` is not.** Do not write the changelog into `temp/`, and do not add it to `.gitignore`.
- **Modified-file knowledge comes from the diff.** Because the processors extract net-new files only, the `changed_*.diff` is the sole structured-knowledge source for modified materials — read it, don't skip it.
- **Preserve history.** Existing entries are immutable; only insert new ones (newest-first) and bump the frontmatter `timestamp`.

---

## Helper scripts

The scripts do not author the changelog — they handle discovery and status only.

| Script (Bash) | Script (PowerShell) | Purpose |
|---|---|---|
| `changelog-generator.sh list` | `changelog-generator.ps1 list` | Print commits in `temp/` not yet in CHANGELOG.md |
| `changelog-generator.sh status` | `changelog-generator.ps1 status` | Show logged vs pending commits |

Options accepted by both:
- `--commit <sha>` / `-Commit <sha>` — scope to one commit
- `--changelog <path>` / `-Changelog <path>` — target a different changelog file
- `--temp <dir>` / `-Temp <dir>` — override the temp base dir
