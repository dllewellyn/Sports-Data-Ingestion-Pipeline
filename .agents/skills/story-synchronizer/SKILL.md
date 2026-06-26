---
name: story-synchronizer
description: Reconcile the structured findings from transcript-processor and architecture-processor against the user_stories/ backlog into a single reviewable change set (temp/story_changeset.json) — per-story impact analysis plus big-picture synthesis (duplicates, conflicts, sequencing, gaps). Never writes to Azure DevOps and never edits story files. Use when asked to sync findings to stories, propose backlog changes, or run the story synchronizer.
compatibility: Requires Bash >= 4 (or PowerShell >= 7) for the discovery scripts; runs after the processors have produced findings.
---

# Skill: Story Synchronizer

## Purpose

Turn the structured knowledge produced by `transcript-processor` and `architecture-processor` into a single, reviewable **change set** for the user-story backlog. You (the agent) do the analysis and synthesis using your tools — no external API calls.

The skill runs in **two phases with two distinct agent roles**:

1. **Per-story impact analysis** — looks at the `user_stories/` folder.
   - If it is **missing or empty** → propose wholly new user stories from the findings (*greenfield* mode).
   - If it is **populated** → for **every** existing story, work out what needs to change or be added, driven by **each** finding from both processors (*update* mode).
2. **Big-picture synthesis** — looks at the whole backlog together with every proposed change, sees the picture across all tickets, and reconciles it: catches duplicates, conflicts, sequencing/dependencies, gaps, and findings no story covers.

The result is a `story_changeset.json` plus a human-readable enumeration. **This skill never writes to Azure DevOps and never edits the story files.** The change set is handed off to a separate agent (the `ado-cli-skill` executor, and a ticket-formatting agent) that makes the actual changes.

## When to invoke

- User asks to "synchronise the stories", "update the backlog from the findings", "what needs to change in the tickets", "run the story synchronizer"
- A pipeline step calls for reconciling extracted knowledge against the backlog after the processors have run

---

## Inputs

| Input | Path | Produced by |
|-------|------|-------------|
| Transcript findings | `temp/<short_sha>/extracted_*.json` | `transcript-processor` |
| Architecture findings | `temp/<short_sha>/arch_extracted_*.json` | `architecture-processor` |
| Existing user stories | `user_stories/<id>.json` (full ADO work-item JSON) | `ado-cli-skill` (`download-user-stories`) |

The stories directory defaults to `<repo_root>/user_stories`. Override with `--stories <dir>` if the download was written elsewhere (e.g. `.agents/skills/ado-cli-skill/user_stories`).

Each finding carries a `source_file` (e.g. `transcripts/session-42.txt`, `architecture/payment-service.puml`). **This is the evidence reference** you cite in every proposed change — quote both the `source_file` and the finding JSON path.

---

## Output

A single aggregate change set (findings span many commits, so output is one file, not per-commit):

```
temp/story_changeset.json
```

`temp/` is gitignored derived output — never commit it. Re-running overwrites it.

---

## Step-by-step instructions

### 0. Discover the work

```bash
./scripts/bash/story-synchronizer.sh status     # counts + greenfield vs update mode
./scripts/bash/story-synchronizer.sh findings    # sha  type  finding_file  (one per line)
./scripts/bash/story-synchronizer.sh stories      # "missing" | "empty" | id<TAB>filename per story
```

Read **every** finding file listed by `findings`, and **every** story file listed by `stories`. Do not sample — coverage must be complete.

Decide the **mode** from `stories`:
- output `missing` or `empty` → **greenfield mode**
- one or more `id<TAB>filename` lines → **update mode**

---

### Phase 1 — Per-story impact analysis (agent role A)

Aggregate all findings first. The relevant finding categories are:

- **transcript**: `design_decisions`, `regulatory_requirements`, `terminology`, `trade_offs`, `open_questions`, `timeline_decisions`, `architecture_evolution`
- **architecture**: `components`, `notes`, `relationships`, `state_models`, `reconciliation_logic`, `error_handling`, `rate_limiting`, `queue_management`, `health_checks`, `example_configurations`, `example_payloads`, `json_schema_examples`

**Update mode** — for **each** existing story (read its `System.Title`, `System.Description`, `System.WorkItemType`, `System.State`, acceptance criteria, etc.):
- Walk every finding and decide whether it implies a change to this story.
- Classify the story's `action` as `update` or `no_change`.
- For each change, record the target field, the current value, the proposed value, the rationale, and the **evidence** (source file + finding file + category).
- A finding that touches no existing story is a **coverage gap** → record it as a `new_story_proposal`.

**Greenfield mode** — there are no stories yet:
- Group the findings into coherent units of deliverable work and emit each as a `new_story_proposal`.
- Keep proposals **lightweight and easily understood** — title, work-item type, a plain-language summary, suggested parent, and evidence. Do **not** author full acceptance criteria or ADO field payloads here; a separate ticket-formatting agent owns completeness and formatting.

**Rules** (same as the processors):
- Use only what the findings explicitly state. Do not infer, embellish, or fabricate.
- Every proposed change **must** carry at least one evidence reference. No evidence → do not propose it.
- Prefer additive clarity (new acceptance criteria, added constraints) over rewriting unless a finding explicitly contradicts the current story.

---

### Phase 2 — Big-picture synthesis (agent role B)

Now step back and look at the **whole backlog plus all of Phase 1's proposals together**. This role sees what the per-story pass cannot:

- **Duplicates / overlap** — two proposals (or a proposal and an existing story) covering the same work → merge or cross-reference.
- **Conflicts** — two findings drive contradictory changes to the same story/field → flag, do not silently pick one.
- **Sequencing & dependencies** — use `timeline_decisions` to order work and note blockers.
- **Splits & grouping** — an Epic that should be split, or new proposals that belong under an existing Epic (set `suggested_parent`).
- **Gaps** — `regulatory_requirements` or `architecture_evolution` drivers not represented by any story.
- **Open questions** — surface `open_questions` (type `CLARIFY`/`UNKNOWN`/`TBD`) that block a change, rather than resolving them yourself.

Record these as `portfolio_observations` and reconcile the Phase 1 records accordingly (drop merged duplicates, annotate conflicts, set parents/order).

---

### 3. Write the change set

```
Write: temp/story_changeset.json
```

Use this exact schema:

```json
{
  "generated_at": "<ISO 8601 UTC timestamp>",
  "agent": "claude",
  "mode": "greenfield | update",
  "sources": {
    "findings": ["temp/<sha>/extracted_transcripts__session-42.txt.json", "..."],
    "stories_dir": "user_stories",
    "story_count": 0
  },

  "story_changes": [
    {
      "story_id": 1,
      "title": "<current System.Title>",
      "work_item_type": "Epic|User Story|Feature|...",
      "action": "update|no_change",
      "change_summary": "<one line: what is changing>",
      "proposed_changes": [
        {
          "field": "System.Description|acceptance_criteria|System.State|Microsoft.VSTS.Common.Priority|...",
          "current": "<existing value, or null>",
          "proposed": "<new or added value>",
          "rationale": "<why this change>",
          "evidence": [
            {
              "source_file": "transcripts/session-42.txt",
              "finding_file": "temp/<sha>/extracted_transcripts__session-42.txt.json",
              "category": "design_decisions",
              "detail": "<the specific finding text supporting this>"
            }
          ]
        }
      ]
    }
  ],

  "new_story_proposals": [
    {
      "proposed_title": "...",
      "work_item_type": "User Story|Epic|Feature|...",
      "summary": "<plain-language description of the deliverable>",
      "rationale": "<why this is needed>",
      "suggested_parent": "<existing Epic title/id, or null>",
      "evidence": [
        { "source_file": "...", "finding_file": "...", "category": "...", "detail": "..." }
      ]
    }
  ],

  "portfolio_observations": [
    {
      "type": "duplicate|conflict|gap|sequencing|split|regulatory",
      "summary": "...",
      "affected": ["<story id or title>", "..."],
      "recommendation": "...",
      "evidence": [ { "source_file": "...", "finding_file": "...", "category": "...", "detail": "..." } ]
    }
  ],

  "open_questions": [
    {
      "question": "...",
      "type": "CLARIFY|UNKNOWN|TBD",
      "blocks": ["<story title or proposal title>"],
      "evidence": [ { "source_file": "...", "finding_file": "...", "category": "open_questions", "detail": "..." } ]
    }
  ]
}
```

`no_change` stories may be omitted from `story_changes` to keep the file focused, but state in the chat enumeration how many were reviewed-and-unchanged so the user knows coverage was complete.

---

### 4. Enumerate to the user (the handoff summary)

After writing the file, print a numbered, human-readable list. For **every** change and proposal give:

- **What** — a one-line summary of the change.
- **Why** — the rationale, **with file references** (the `source_file`, e.g. the transcript `.txt` or the `.puml`, and the finding JSON).

Suggested shape:

```
## Story changes
1. [#1 "Payment Epic" — UPDATE] Add idempotency-key acceptance criterion to the capture flow.
   Why: design decision to dedupe retried captures — transcripts/session-42.txt
        (temp/ab12/extracted_transcripts__session-42.txt.json › design_decisions)

## New story proposals
1. [NEW · User Story] "Dead-letter handling for the settlement queue"
   Why: queue strategy mandates a DLQ — architecture/payment-service.puml
        (temp/cd34/arch_extracted_architecture__payment-service.puml.json › queue_management)

## Portfolio observations
1. [SEQUENCING] Story #4 must land before #1 (auth precedes capture) — timeline_decisions in session-42.

## Open questions (blocking)
1. [CLARIFY] PCI scope of stored card data — blocks proposal "Tokenization service".

Reviewed unchanged: 6 stories.
Wrote: temp/story_changeset.json
```

End by stating the change set is ready to hand to the executor / ticket-formatting agent — **do not** apply it yourself.

---

## Idempotency

Re-running regenerates `temp/story_changeset.json` from the current findings and stories. There is no per-file skip — the synthesis is holistic and cheap to redo. If the user wants to preserve a prior run, they move/rename the file first.

---

## Guardrails

- Analyse only what the findings and stories contain. If a fact is ambiguous, surface it as an `open_question` rather than guessing.
- Every `proposed_change`, `new_story_proposal`, and `portfolio_observation` carries at least one evidence reference. Unsupported items are not emitted.
- **Read-only on source data.** Never edit or delete files in `user_stories/` or `temp/<sha>/`; the only file this skill writes is `temp/story_changeset.json`.
- **Never** call `ado-ticket` create/update or otherwise mutate Azure DevOps. Producing the change set is the boundary of this skill.
- Keep new-story proposals lightweight; acceptance-criteria authoring and ADO field formatting belong to the downstream ticket-formatting agent.
- Never commit `temp/`.

---

## Helper scripts

The scripts do not perform synthesis — they handle file-system discovery and status reporting only.

| Script (Bash) | Script (PowerShell) | Purpose |
|---|---|---|
| `story-synchronizer.sh status` | `story-synchronizer.ps1 status` | Counts of findings/stories + greenfield vs update mode |
| `story-synchronizer.sh findings` | `story-synchronizer.ps1 findings` | List every finding file (`sha  type  finding_file`) |
| `story-synchronizer.sh stories` | `story-synchronizer.ps1 stories` | `missing` / `empty` / one `id  filename` line per story |

Options accepted by both:
- `--temp <dir>` / `-Temp <dir>` — temp base dir (default `<repo_root>/temp`)
- `--stories <dir>` / `-Stories <dir>` — user stories dir (default `<repo_root>/user_stories`)
