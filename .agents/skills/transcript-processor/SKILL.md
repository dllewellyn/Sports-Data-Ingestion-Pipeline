---
name: transcript-processor
description: Extract structured knowledge (design decisions, trade-offs, open questions, regulatory constraints) from net-new transcript/session files produced by git-sync-extractor, writing extracted_<flat>.json per file. The agent does the reading and extraction with its own tools — no external API calls. Use when asked to process transcripts, extract knowledge from sessions, or run the transcript processor.
compatibility: Requires Bash >= 4 (or PowerShell >= 7) for the discovery scripts; runs after git-sync-extractor.
---

# Skill: Transcript Processor

## Purpose

Process net-new files produced by `git-sync-extractor` and extract structured knowledge from each one. You (the agent) do the reading and extraction using your tools — no external API calls.

## When to invoke

- User asks to "process transcripts", "extract knowledge", "run the transcript processor"
- User asks what design decisions, trade-offs, open questions, or regulatory constraints were captured in a commit or session
- A pipeline step calls for processing after `git-sync-extractor` has run

---

## Inputs

`git-sync-extractor` writes to `temp/<short_sha>/` for each commit. You consume:

- `temp/<short_sha>/changed_files.json` — manifest; read to find added files and their source paths
- `temp/<short_sha>/new_<flat_path>` — full content of each added file (e.g. `new_transcripts__session-42.txt`)

A file is "net-new" when its `status` field in `changed_files.json` is `"added"`.

---

## Output

For every net-new file you process, write:

```
temp/<short_sha>/extracted_<flat_path>.json
```

where `<flat_path>` is the `new_*` filename with the `new_` prefix removed.

Example: `new_transcripts__session-42.txt` → `extracted_transcripts__session-42.txt.json`

---

## Step-by-step instructions

### 1. Discover pending work

Run the status script to see what needs processing:

```bash
./scripts/bash/transcript-processor.sh list
```

This prints one line per pending file: `<short_sha>  <flat_path>  <source_path>`.

If `--commit <sha>` is passed by the user, only process that commit.

### 2. For each pending file

**a. Read the manifest**
```
Read: temp/<short_sha>/changed_files.json
```
Confirm the file's status is `"added"`. Note its original `path` value for use in the output envelope.

**b. Read the file content**
```
Read: temp/<short_sha>/new_<flat_path>
```

**c. Extract the seven knowledge categories**

Study the content carefully and extract only what is explicitly stated or clearly implied. Do not infer, embellish, or fabricate. Use empty arrays `[]` for categories with no content.

| Category | What to extract |
|----------|----------------|
| `design_decisions` | Explicit choices about system behaviour, structure, APIs, data models, or patterns — each with the decision, why it was chosen, and surrounding context |
| `regulatory_requirements` | Named regulations or standards (GDPR, SOC2, HIPAA, PCI-DSS, FIPS, accessibility, data residency) and how each constrains the system |
| `terminology` | Domain terms, acronyms, or project-specific vocabulary that were defined or clarified in this document |
| `trade_offs` | Moments where multiple options were weighed; capture all options considered, which was accepted, and why the others were rejected |
| `open_questions` | Items explicitly flagged as uncertain, needing input, or deferred — typed as `UNKNOWN` (not yet known), `CLARIFY` (needs stakeholder clarification), or `TBD` (decision explicitly deferred) |
| `timeline_decisions` | Ordering of work, phase gates, milestones, sequencing dependencies, and the rationale for that ordering |
| `architecture_evolution` | What the current architecture looks like, what is being changed, the driver for the change, and any historical or strategic context |

**d. Write the output file**

```
Write: temp/<short_sha>/extracted_<flat_path>.json
```

Use this exact schema:

```json
{
  "source_file":  "<original path from changed_files.json, e.g. transcripts/session-42.txt>",
  "commit":       "<short_sha>",
  "extracted_at": "<ISO 8601 UTC timestamp>",
  "agent":        "claude",

  "design_decisions": [
    { "decision": "...", "rationale": "...", "context": "..." }
  ],
  "regulatory_requirements": [
    { "requirement": "...", "regulation": "...", "constraint": "..." }
  ],
  "terminology": [
    { "term": "...", "definition": "...", "context": "..." }
  ],
  "trade_offs": [
    {
      "description": "...",
      "options_considered": ["...", "..."],
      "accepted_approach": "...",
      "rationale": "..."
    }
  ],
  "open_questions": [
    { "question": "...", "type": "UNKNOWN|CLARIFY|TBD", "context": "..." }
  ],
  "timeline_decisions": [
    { "decision": "...", "sequence": "...", "dependencies": "...", "rationale": "..." }
  ],
  "architecture_evolution": [
    { "current_state": "...", "proposed_change": "...", "driver": "...", "context": "..." }
  ]
}
```

### 3. Confirm and move to next file

After writing each file, report: `✓ extracted temp/<short_sha>/<filename>`.
Continue until all pending files are processed.

---

## Idempotency

Skip any `new_*` file that already has a corresponding `extracted_*.json` unless the user explicitly asks to re-extract (`--force`).

---

## Guardrails

- Extract only what is in the document. If a fact is ambiguous, omit it rather than guess.
- Never commit extracted files to git.
- `temp/` should be listed in `.gitignore`.
- If a file is binary or unparseable (image, compiled artifact), write a minimal JSON with all seven arrays empty and add a `"skipped_reason": "binary or unparseable"` field.

---

## Helper scripts

The scripts do not perform extraction — they handle file-system discovery and status reporting only.

| Script (Bash) | Script (PowerShell) | Purpose |
|---|---|---|
| `transcript-processor.sh list` | `transcript-processor.ps1 list` | Print pending files |
| `transcript-processor.sh status` | `transcript-processor.ps1 status` | Show done vs pending counts |

Options accepted by both:
- `--commit <sha>` / `-Commit <sha>` — scope to one commit
- `--filter <str>` / `-Filter <str>` — only files whose flat path contains this substring
- `--temp <dir>` / `-Temp <dir>` — override temp base dir
