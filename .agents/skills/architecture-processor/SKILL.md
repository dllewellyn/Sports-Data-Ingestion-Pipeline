---
name: architecture-processor
description: Extract structured knowledge (components, relationships, state models, rate limits, queue strategies) from net-new architecture documents (C4-PlantUML .puml diagrams, design docs) produced by git-sync-extractor, writing arch_extracted_<flat>.json per file. The agent does the reading and extraction with its own tools — no external API calls. Use when asked to process architecture docs/diagrams or run the architecture processor.
compatibility: Requires Bash >= 4 (or PowerShell >= 7) for the discovery scripts; runs after git-sync-extractor.
---

# Skill: Architecture Processor

## Purpose

Process net-new architecture documents produced by `git-sync-extractor` and extract structured knowledge from each one. Architecture documents are typically C4-PlantUML diagrams (`.puml`), markdown design docs, or similar. You (the agent) do the reading and extraction using your tools — no external API calls.

## When to invoke

- User asks to "process architecture docs", "extract the architecture", "run the architecture processor"
- User asks what components, relationships, state models, rate limits, or queue strategies are defined in a commit or diagram
- A pipeline step calls for processing architecture files after `git-sync-extractor` has run

---

## Inputs

`git-sync-extractor` writes to `temp/<short_sha>/` for each commit. You consume:

- `temp/<short_sha>/changed_files.json` — manifest; read to find added files and their source paths
- `temp/<short_sha>/new_<flat_path>` — full content of each added architecture file (e.g. `new_architecture__payment-service.puml`)

A file is "net-new" when its `status` field in `changed_files.json` is `"added"`.

> **Scope note:** this skill processes net-new files only. Architecture documents that were *modified* appear as `changed_*.diff` files, which this skill does not currently process. See the manifest if you need to know which files changed vs were added.

---

## Output

For every net-new architecture file you process, write:

```
temp/<short_sha>/arch_extracted_<flat_path>.json
```

where `<flat_path>` is the `new_*` filename with the `new_` prefix removed.

Example: `new_architecture__payment-service.puml` → `arch_extracted_architecture__payment-service.puml.json`

The `arch_extracted_` prefix keeps this skill's output distinct from `transcript-processor`'s `extracted_` output, so the two skills can share the same `temp/` tree without interfering.

---

## Step-by-step instructions

### 1. Discover pending work

Run the list script to see what needs processing (defaults to files matching `architecture`):

```bash
./scripts/bash/architecture-processor.sh list
```

This prints one line per pending file: `<short_sha>  <flat_path>  <source_path>`.

If `--commit <sha>` is passed by the user, only process that commit.

### 2. For each pending file

**a. Read the manifest**
```
Read: temp/<short_sha>/changed_files.json
```
Confirm the file's status is `"added"`. Note its original `path` value for the output envelope.

**b. Read the file content**
```
Read: temp/<short_sha>/new_<flat_path>
```

**c. Extract the knowledge categories**

Study the content carefully and extract only what is explicitly present. Do not infer, embellish, or fabricate. Use empty arrays `[]` for categories with no content. Many of these map to specific PlantUML / C4-PlantUML syntax — examples below.

| Category | What to extract | Typical source syntax |
|----------|----------------|----------------------|
| `components` | Each component's name, type, and purpose | `Container(...)`, `Component(...)`, `System(...)`, `ContainerDb(...)`, `Component_Ext(...)` |
| `notes` | Every attached note, categorised as `DEV`, or `BUSINESS`, with any date mentioned | `note right of X`, `note as N`, notes prefixed `DEV:`, `BW:`, `Business:` |
| `json_schema_examples` | JSON Schema definitions or examples embedded in the doc | fenced ```json blocks, schema notes |
| `relationships` | Data flows and relationships — capture the raw `Rel_*` statement plus parsed source/target/description/technology/data flow | `Rel(...)`, `Rel_D(...)`, `Rel_U(...)`, `Rel_Back(...)`, `BiRel(...)` |
| `state_models` | State machines: states, substates, and transitions | `state X { ... }`, `[*] --> Active`, nested states |
| `reconciliation_logic` | How data/state is reconciled — trigger and resolution | notes, dedicated reconciliation components or sequences |
| `error_handling` | Error scenarios and the required handling behaviour | error notes, failure-path relationships, retry/DLQ annotations |
| `rate_limiting` | Rate-limit algorithm (token bucket, leaky bucket, sliding window, fixed window), limits, and configuration | rate-limit notes, throttle annotations |
| `queue_management` | Queue strategy — FIFO, prioritization, masking, dead-lettering — and rationale | queue components, `Queue(...)`, ordering/priority notes |
| `health_checks` | Health/liveness/readiness check requirements | health-check endpoints, probe notes |
| `example_configurations` | Example config blocks (YAML, env, ini, properties) | fenced config blocks, config notes |
| `example_payloads` | Example request/response/event payloads | fenced payload blocks, sample message notes |

**d. Write the output file**

```
Write: temp/<short_sha>/arch_extracted_<flat_path>.json
```

Use this exact schema:

```json
{
  "source_file":  "<original path from changed_files.json, e.g. architecture/payment-service.puml>",
  "commit":       "<short_sha>",
  "extracted_at": "<ISO 8601 UTC timestamp>",
  "agent":        "claude",

  "components": [
    { "name": "...", "type": "...", "purpose": "..." }
  ],
  "notes": [
    { "component": "...", "category": "DEV|BW|BUSINESS", "text": "...", "date": "<date if stated, else null>" }
  ],
  "json_schema_examples": [
    { "component": "...", "name": "...", "schema": "..." }
  ],
  "relationships": [
    {
      "rel_statement": "<raw Rel_ statement>",
      "source": "...",
      "target": "...",
      "description": "...",
      "technology": "...",
      "data_flow": "..."
    }
  ],
  "state_models": [
    { "component": "...", "name": "...", "states": ["..."], "substates": ["..."], "transitions": ["..."] }
  ],
  "reconciliation_logic": [
    { "component": "...", "description": "...", "trigger": "...", "resolution": "..." }
  ],
  "error_handling": [
    { "component": "...", "scenario": "...", "requirement": "...", "behaviour": "..." }
  ],
  "rate_limiting": [
    { "component": "...", "algorithm": "...", "limits": "...", "configuration": "...", "scope": "..." }
  ],
  "queue_management": [
    { "component": "...", "strategy": "FIFO|prioritization|masking|dead-letter|...", "details": "...", "rationale": "..." }
  ],
  "health_checks": [
    { "component": "...", "type": "liveness|readiness|startup|...", "probe": "...", "requirement": "..." }
  ],
  "example_configurations": [
    { "component": "...", "name": "...", "format": "yaml|env|ini|json|...", "content": "..." }
  ],
  "example_payloads": [
    { "component": "...", "name": "...", "direction": "request|response|event", "content": "..." }
  ]
}
```

### 3. Confirm and move to next file

After writing each file, report: `✓ extracted temp/<short_sha>/<filename>`.
Continue until all pending files are processed.

---

## Idempotency

Skip any `new_*` file that already has a corresponding `arch_extracted_*.json` unless the user explicitly asks to re-extract (`--force`).

---

## Guardrails

- Extract only what is in the document. If a value is ambiguous, omit it rather than guess.
- Preserve `Rel_` statements verbatim in `rel_statement` in addition to the parsed fields.
- Never commit extracted files to git. `temp/` should be listed in `.gitignore`.
- If a file is binary or unparseable, write a minimal JSON with all category arrays empty and add `"skipped_reason": "binary or unparseable"`.

---

## Helper scripts

The scripts do not perform extraction — they handle file-system discovery and status reporting only. They default to files matching `architecture`.

| Script (Bash) | Script (PowerShell) | Purpose |
|---|---|---|
| `architecture-processor.sh list` | `architecture-processor.ps1 list` | Print pending files |
| `architecture-processor.sh status` | `architecture-processor.ps1 status` | Show done vs pending counts |

Options accepted by both:
- `--commit <sha>` / `-Commit <sha>` — scope to one commit
- `--filter <str>` / `-Filter <str>` — override the default `architecture` filter
- `--temp <dir>` / `-Temp <dir>` — override temp base dir
