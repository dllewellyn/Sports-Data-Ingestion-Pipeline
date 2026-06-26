---
name: ticket-formatter
description: Take a single agreed ticket spec and write it into the local user_stories/ backlog (creating new files or updating existing ones, keyed on numeric id / title slug), authoring Markdown bodies and emitting a diff of the change. Purely local — never calls az or touches Azure DevOps. Use once per agreed ticket to format and persist it after content sign-off.
compatibility: Requires python3 for spec validation; Bash >= 4 (or PowerShell >= 7). No az, no network.
---

# Skill: Ticket Formatter

## Purpose

Take a **single, fully-agreed ticket spec** and write it into the local **`user_stories/`
backlog** — creating new story files and updating existing ones — then emit a **diff** plus
the resulting bodies so the change can be shown to the user.

This is a **purely local filesystem** operation. It does **not** call `az`, the
`ado-cli-skill`, or any network service. It is the per-ticket executor that runs **once per
ticket, after the content has been agreed** (e.g. from a `story-synchronizer` change set the
user signed off). It only formats an agreed spec and persists it to `user_stories/`.

**Markdown is the source of truth.** Every section is authored in Markdown and stored in the
work item's `System.Description` (and, for stories, `Microsoft.VSTS.Common.AcceptanceCriteria`).
The diff the user reviews is a Markdown diff.

### Scope boundaries

- **Create and Update only — no delete.** New tickets become new `user_stories/*.json`
  files; existing ones are updated in place. Nothing is ever removed.
- **Local only.** It never writes to Azure DevOps. Pushing `user_stories/` to ADO (e.g. via
  `ado-cli-skill`) is a **separate, later** step that is out of scope for this skill.
- It does not synthesise findings or pick changes. Hand it an explicit, agreed spec.

## When to invoke

- "Apply this ticket to the backlog", "write the agreed epic and its stories into
  user_stories", "create/update the local story files", "run the ticket formatter".
- After `story-synchronizer` produced a change set **and the user agreed a specific
  ticket**, that ticket is rendered into a spec and handed here, one ticket at a time.

---

## Inputs

| Input | Path | Notes |
|-------|------|-------|
| Ticket spec | a JSON file you are given (e.g. `temp/ticket_spec.json`) | The agreed content. Schema below. |
| Existing backlog (for updates) | `user_stories/<id>.json` | Full work-item JSON; the "before" image for updates. |

Requirements: `python3` for spec validation; Bash 4+ or PowerShell 5+. No `az`, no network.

The `user_stories/` directory defaults to `<repo_root>/user_stories`. Override with
`--stories <dir>` if the backlog lives elsewhere (e.g.
`.agents/skills/ado-cli-skill/user_stories`).

### Ticket-spec schema

One Epic and its child stories. `id: null` ⇒ **create** a new local file; a numeric `id` ⇒
**update** `user_stories/<id>.json`. Print the canonical template with
`ticket-formatter.sh template`; a worked example lives in
`examples/ticket_spec.example.json`.

```json
{
  "epic": {
    "id": null,
    "work_item_type": "Epic",
    "title": "<epic title>",
    "state": null,
    "parent": null,
    "sections": {
      "overview": "<markdown>",
      "glossary": "<markdown table of domain terms>",
      "component_architecture": "<markdown>",
      "definition_of_ready": "<markdown checklist>",
      "definition_of_done": "<markdown checklist>"
    }
  },
  "stories": [
    {
      "id": null,
      "work_item_type": "User Story",
      "title": "<story title>",
      "state": null,
      "sections": {
        "user_story": "As a <role>, I want <capability>, so that <benefit>.",
        "description": "<markdown>",
        "acceptance_criteria": "<markdown>",
        "dependencies": "<markdown>",
        "notes": "<markdown>"
      }
    }
  ]
}
```

Required: `epic.title`, `epic.work_item_type`, all five `epic.sections`; per story
`title`, `work_item_type`, and `sections.user_story` + `sections.acceptance_criteria`.
The required Epic content the user asked for maps as: **Epic Overview** → `overview`;
**Glossary** → `glossary`; **Component Architecture Overview** → `component_architecture`;
**Epic-level DOR / DOD** → `definition_of_ready` / `definition_of_done`; **Individual User
Stories** → the `stories[]` array, **each with full detail** in its `sections`.

---

## Output

The deliverable is the updated **backlog**, written in the same full work-item JSON shape
that `ado-cli-skill`'s `download-user-stories` produces (so a later ADO push is trivial):

```
user_stories/<id>.json            # updated in place (spec item had a numeric id)
user_stories/new-<slug>.json      # created (spec item had id: null); <slug> = kebab-cased title
```

A new file carries the authored fields but **no** `System.Id` / ADO system metadata (it is
not in ADO yet). The `new-<slug>` filename is **stable** across runs, so re-applying the same
spec updates the same file rather than spawning duplicates.

All other artefacts are regenerable and gitignored under `temp/`:

```
temp/ticket_formatter/<id>.body.md      # canonical Markdown body (mirrors System.Description)
temp/ticket_formatter/<id>.before.md    # pre-change body (empty file for new tickets)
temp/ticket_formatter/<id>.diff         # unified Markdown diff (before → after)
temp/ticket_formatter/result.json       # machine summary: created/updated ids + diff paths
```

---

## Step-by-step instructions

### 0. Validate the spec and see the plan

```bash
./scripts/bash/ticket-formatter.sh validate temp/ticket_spec.json
```

This prints, per work item, whether it will **CREATE** (no `id`) or **UPDATE** (has `id`).
Do not proceed if validation fails — fix the spec, do not work around it.

### 1. Author the canonical Markdown bodies

Assemble each body in a **fixed section order** so diffs stay stable across runs. Write each
to `temp/ticket_formatter/<id>.body.md` (for a create, name it after the slug,
`temp/ticket_formatter/new-<slug>.body.md`).

**Epic body** (in this order):

```markdown
# <title>

<overview>

<glossary>

<component_architecture>

<definition_of_ready>

<definition_of_done>

## User Stories
- <story title>  (<id or new-slug>)
- ...
```

**User-story body** (in this order):

```markdown
# <title>

> <user_story>     <!-- the "As a … I want … so that …" line -->

<description>

<dependencies>

<notes>
```

The story's `acceptance_criteria` is **not** in the Description body — it is stored in its own
field (next step). Use only what the spec contains; never invent content.

### 2. Snapshot the "before" (updates only)

For each work item with an `id`, copy the current body so the diff is real. Read
`user_stories/<id>.json`, extract `fields["System.Description"]` into
`temp/ticket_formatter/<id>.before.md`, and keep the whole file as
`temp/ticket_formatter/<id>.before.json`. For a **create**, the before image is an empty file
(`: > temp/ticket_formatter/new-<slug>.before.md`).

### 3. Write into `user_stories/`

Process the **Epic first**, then each story (so the Epic's id/slug is known for the children's
parent link).

**Update** (`id` present) — read `user_stories/<id>.json`, set these inside `fields`,
**preserving every other existing field**, then write the file back:

- `System.Title` ← title
- `System.Description` ← the assembled Markdown body
- `System.WorkItemType` ← work_item_type
- `System.State` ← state (only if the spec sets it)
- `Microsoft.VSTS.Common.AcceptanceCriteria` ← acceptance_criteria (stories only)

**Create** (`id: null`) — write a new `user_stories/new-<slug>.json` with this minimal,
ADO-shaped skeleton (no `System.Id`, no ADO timestamps — it is not in ADO yet):

```json
{
  "fields": {
    "System.WorkItemType": "User Story",
    "System.Title": "<title>",
    "System.State": "<state or 'New'>",
    "System.Description": "<assembled Markdown body>",
    "Microsoft.VSTS.Common.AcceptanceCriteria": "<acceptance_criteria, stories only>"
  },
  "relations": null,
  "localStatus": "new"
}
```

**Parent/child hierarchy** — set the child's parent link in its `relations` array using a
**local relation** (real `id` if the parent already exists, else the parent's `new-<slug>`):

```json
"relations": [
  { "rel": "System.LinkTypes.Hierarchy-Reverse", "targetId": "<epic id or new-slug>" }
]
```

This is a local shape (a real ADO relation uses a work-item `url`); a later ADO-push step
resolves `targetId` to the assigned ADO id and URL. If `epic.parent` is set, add the same
relation to the Epic pointing at `epic.parent`.

Write **valid JSON** (pretty-printed, 2-space indent). Do not corrupt fields you did not author.

### 4. Diff

For every created/updated item, produce the Markdown diff:

```bash
./scripts/bash/ticket-formatter.sh diff \
  temp/ticket_formatter/<id>.before.md temp/ticket_formatter/<id>.body.md \
  > temp/ticket_formatter/<id>.diff
```

For a create the before file is empty, so the diff is the whole body as additions.

Write `temp/ticket_formatter/result.json`:

```json
{
  "applied_at": "<ISO 8601 UTC>",
  "stories_dir": "user_stories",
  "epic": { "id": 42, "action": "created|updated", "file": "user_stories/42.json", "title": "...", "diff": "temp/ticket_formatter/42.diff" },
  "stories": [
    { "id": "new-idempotent-capture", "action": "created", "file": "user_stories/new-idempotent-capture.json", "parent": 42, "title": "...", "diff": "..." }
  ]
}
```

### 5. Report to the user (new/created stories + diff)

Print, per work item: **CREATED** or **UPDATED**, its id/file, and the **Markdown diff**. For
created items the diff is the whole body as additions. End with the resulting bodies in full so
the user sees the new and updated stories.

Suggested shape:

```
## Epic #42 "Payment capture & settlement" — UPDATED (user_stories/42.json)
  <unified diff of 42.before.md → 42.body.md>

## User Story "Idempotent capture" — CREATED (user_stories/new-idempotent-capture.json, parent #42)
  <whole body, as additions>

Wrote: user_stories/42.json, user_stories/new-idempotent-capture.json
Result: temp/ticket_formatter/result.json
```

---

## Idempotency

Re-running with the **same** spec must converge, not duplicate.

- **Updates** key on the numeric `id` → the same `user_stories/<id>.json` is rewritten.
- **Creates** key on the title **slug** → the same `user_stories/new-<slug>.json` is
  rewritten, never duplicated.
- Bodies are deterministic (fixed section order), so an unchanged spec re-applied yields an
  empty diff.

When a `new-<slug>` story is eventually pushed to ADO and assigned a real id, that is the push
step's job; folding the real id back into the spec (and renaming the file) keeps later runs
clean.

---

## Guardrails

- **Create/Update only — never delete** any `user_stories/` file or work item.
- **Local only — never call `az` or write to Azure DevOps.** That is a separate downstream
  step.
- **Markdown is authoritative.** Author, store, and diff Markdown. Do not convert to HTML.
- **Preserve unauthored fields.** On update, change only the fields you author; keep all other
  existing fields in `user_stories/<id>.json` intact and write valid JSON.
- **Spec is the contract.** Use only content present in the spec; never infer, embellish, or
  fabricate ticket text. If the spec is incomplete, stop and ask — do not guess.
- **No quality-gate bypass.** If `validate` fails, stop and surface it; never `--skip`, never
  fake success.
- Never commit `temp/`. Never print secrets or tokens.

---

## Helper scripts

The scripts do deterministic discovery/mechanical work only — they never call `az`, never
mutate the spec, and never push anywhere. The agent authors the bodies and writes the
`user_stories/` files and derived output.

| Script (Bash) | Script (PowerShell) | Purpose |
|---|---|---|
| `ticket-formatter.sh validate <spec>` | `ticket-formatter.ps1 validate <spec>` | Validate spec JSON; print create/update plan |
| `ticket-formatter.sh diff <before> <after>` | `ticket-formatter.ps1 diff <before> <after>` | Unified Markdown diff of two files |
| `ticket-formatter.sh template` | `ticket-formatter.ps1 template` | Print the canonical spec template |
| `ticket-formatter.sh status` | `ticket-formatter.ps1 status` | Report `user_stories/` + output dir state |

Options (both): `--stories <dir>` / `-Stories <dir>`, `--out <dir>` / `-Out <dir>`.
