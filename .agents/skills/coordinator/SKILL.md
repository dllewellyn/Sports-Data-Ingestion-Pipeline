---
name: coordinator
description: Orchestrate the full git → knowledge-extraction → backlog pipeline (git-sync-extractor → per-commit transcript/architecture processors → story-synchronizer → ticket-formatter → changelog-generator), delegating heavy file work to sub-agents so the coordinator's own context stays lean. Use when asked to "run the pipeline", "sync history into the backlog end to end", "extract and reconcile everything", or to drive more than one of the pipeline skills in sequence.
compatibility: Requires the six pipeline skills under .agents/skills/ and their Bash >= 4 (or PowerShell >= 7) entrypoints. Assumes user_stories/ has already been downloaded (via ado-cli-skill) or is intentionally greenfield — this skill never calls az. python3 is needed by ticket-formatter (spec validation + HTML view) and git-sync-extractor (Bash JSON escaping).
---

# Skill: Pipeline Coordinator

## Purpose

Drive the whole knowledge-extraction pipeline end to end as a **single orchestrated run**, so the user gets one coherent experience instead of invoking six skills by hand and stitching the outputs together. You (the coordinator) own the *sequencing, the hand-offs, and the conversation* — but you delegate every piece of heavy file work to **sub-agents**, keeping only their compact summaries in your own context.

The pipeline you orchestrate:

```
git-sync-extractor            (deterministic CLI — run inline; output is small)
        ↓  temp/<short_sha>/{changed_files.json, new_*, changed_*.diff}
one sub-agent PER COMMIT      → transcript-processor + architecture-processor (--commit <sha>)
        ↓  temp/<sha>/{extracted_*.json, arch_extracted_*.json}
story-synchronizer            (one sub-agent — reads ALL findings + ALL stories)
        ↓  temp/story_changeset.json  + numbered enumeration
ticket-formatter              (one sub-agent PER AGREED TICKET — authors bodies, writes
        ↓                      user_stories/, renders the HTML `view` — THE review UI)
   user confirms / asks for changes (delegated back to the right step)
        ↓
changelog-generator           (one sub-agent — writes CHANGELOG.md)
```

This is a **pure orchestration skill**: it ships no scripts of its own and does no deterministic
work. It drives the existing skills' entrypoints through sub-agents. The six pipeline skills (and
their `SKILL.md` contracts) are the source of truth for *how* each step behaves — read those if you
need a step's detail; do not reimplement them here.

## When to invoke

- "Run the pipeline", "do the whole extraction end to end", "sync git history into the backlog",
  "extract everything and reconcile it against the stories", "update the backlog and changelog from
  recent commits".
- Any request that spans **more than one** pipeline skill in sequence. (A request for a *single*
  step — "just process the transcripts" — should go straight to that skill, not through here.)

---

## The one rule that makes this skill worth it: preserve your own context

The reason to coordinate via sub-agents is that the raw materials are **large** (transcripts,
`.puml` diagrams, diffs) and the derived findings multiply across commits. If you read them
yourself, your context fills with content you never needed to hold.

So:

- **Never read `temp/<sha>/new_*`, `changed_*.diff`, the `*_extracted_*.json` findings, or the
  `user_stories/*.json` files yourself.** Those reads belong to sub-agents.
- Each sub-agent does the reading/extraction/authoring and **returns only a compact summary** — counts,
  ids, a short enumeration, a diff path. You relay those summaries to the user and use them to decide
  the next step.
- The only files you may read directly are small control/summary artifacts when you genuinely need
  them to route work (e.g. a quick `status` output). Prefer asking a sub-agent over reading findings.

When you spawn sub-agents for independent work (notably the per-commit processing), launch them
**in a single message with multiple tool calls** so they run concurrently.

---

## Step-by-step orchestration

### Step 0 — Preflight (inline; output is tiny, safe to hold)

Run the extractor's `status` and check the backlog state:

```bash
.agents/skills/git-sync-extractor/scripts/bash/git-sync-extractor.sh status
.agents/skills/story-synchronizer/scripts/bash/story-synchronizer.sh stories
```

- If `status` shows **no `.last-sync`** (first run), the extractor would otherwise prompt
  interactively. **Surface the choice to the user** — "start from the first commit, or from a
  specific ref?" — and capture their answer so you can pass `--from <ref>` in Step 1 (which skips
  the prompt). Do not let the interactive prompt block a sub-agent.
- `stories` returns `missing` / `empty` (→ greenfield: story-synchronizer proposes new stories) or
  one `id<TAB>filename` line per story (→ update mode). If the user expected existing stories and the
  dir is missing/empty, **tell them** they may need to run `ado-cli-skill`'s `download-user-stories`
  first — but do **not** call `az` yourself; that is out of this skill's scope.

State the plan and the detected mode to the user before proceeding.

### Step 1 — Extract (inline)

Run the deterministic extractor with whatever patterns/refs the user named (and the `--from` from
Step 0 if this is a first run):

```bash
.agents/skills/git-sync-extractor/scripts/bash/git-sync-extractor.sh run [--from <ref>] [--pattern <p> ...]
```

It is a deterministic CLI — **run it and report**, don't audit or edit it. Then capture the list of
commits that produced output (each is a `temp/<short_sha>/` directory). The extractor's summary plus
a `find temp -maxdepth 1 -mindepth 1 -type d` gives you the SHAs.

**If no commits had matching files**, there is nothing to process — report that and stop. Don't fan
out over an empty set.

### Step 2 — Process each commit (FAN OUT: one sub-agent per commit, in parallel)

For **each** `temp/<short_sha>/` directory, spawn **one** sub-agent. Send them all in a single
message so they run concurrently. Each sub-agent's job is to run **both** processors scoped to that
commit and return only a summary.

Sub-agent prompt template (fill in `<sha>`):

> Process git commit `<sha>` for the knowledge pipeline. Follow two skills, both scoped to this
> commit only:
> 1. **transcript-processor** — `.agents/skills/transcript-processor/SKILL.md`. Run
>    `.agents/skills/transcript-processor/scripts/bash/transcript-processor.sh list --commit <sha>`,
>    then for each pending net-new file read it and write `temp/<sha>/extracted_<flat>.json` exactly
>    per that skill's schema (seven categories, evidence only — no fabrication).
> 2. **architecture-processor** — `.agents/skills/architecture-processor/SKILL.md`. Run
>    `.agents/skills/architecture-processor/scripts/bash/architecture-processor.sh list --commit <sha>`,
>    then for each pending net-new file write `temp/<sha>/arch_extracted_<flat>.json` per that skill's
>    schema.
>
> Both processors are idempotent — skip files that already have output. Do **not** process
> `changed_*.diff` (modified files are out of scope for the processors).
>
> Return ONLY a compact report: for each file processed, its flat name and a per-category count
> (e.g. `extracted_transcripts__session-42.txt.json: 3 design_decisions, 1 regulatory, 2 open_questions`),
> plus any files skipped (already done / binary). **Do not paste file contents or the JSON you wrote.**

Collect the per-commit summaries. Report a roll-up to the user: N commits processed, totals per
category, any skips.

### Step 3 — Synchronize against the backlog (one sub-agent)

Findings now span many commits and story-synchronizer is holistic, so use **one** sub-agent for the
whole reconciliation:

> Run the **story-synchronizer** skill — `.agents/skills/story-synchronizer/SKILL.md`. Use its
> discovery scripts (`status` / `findings` / `stories`), read **every** finding file and **every**
> story file (complete coverage, no sampling), perform both phases (per-story impact analysis +
> big-picture synthesis), and write `temp/story_changeset.json` in the skill's exact schema. Every
> proposed change must carry an evidence reference (source file + finding file + category).
>
> Return the **numbered human enumeration** the skill specifies — Story changes, New story
> proposals, Portfolio observations, Open questions (blocking), and the "reviewed unchanged" count —
> with the `what` + `why` (file references) for each. Do **not** return the raw findings or story
> files. Do **not** call `az` or edit any story file.

Relay that enumeration to the user verbatim-ish (it is already the compact, reviewable form). This is
the substance the user reasons about when deciding which tickets to act on.

### Step 4 — Format agreed tickets + open the review UI (one sub-agent per ticket)

Work with the user to agree which changeset items become tickets. **Surface blocking open questions
first** — if a change is gated on a `CLARIFY`/`UNKNOWN`/`TBD`, get the user's answer or set it aside;
do not guess past it.

For **each agreed ticket**, hand a sub-agent the agreed content (assembled from the changeset entry
you already hold — the title, type, intent, parent, and the evidence references) and have it run the
**ticket-formatter** skill:

> Run the **ticket-formatter** skill — `.agents/skills/ticket-formatter/SKILL.md` — for this single
> agreed ticket. Spec (agreed content): `<the ticket's epic/stories, sections, parent, and evidence
> for lineage>`. Write the spec JSON, `validate` it (do not proceed if validation fails — fix the
> spec, never `--skip`), author the canonical Markdown bodies, create/update the `user_stories/`
> files (create → `new-<slug>.json`, update → keyed on numeric id; preserve unauthored fields),
> produce the diffs and `result.json` (populate `lineage` from the evidence — never fabricate it),
> then run `view` to render and open `temp/ticket_formatter/view.html`.
>
> Return ONLY: which files were created/updated, a one-line-per-item diff summary, and the path to
> the rendered `view.html`. Do **not** call `az` or push anywhere — this is local only.

The rendered **`view.html` is the review UI.** Point the user to it. Then:

- **User is happy** → proceed to Step 5.
- **User asks for changes** → route the rework to the right step; do **not** hand-edit outputs:
  - wording/sections/acceptance criteria of *this* ticket → adjust the agreed spec and **re-run its
    ticket-formatter sub-agent** (idempotent — same file rewritten, fresh diff + view).
  - which stories exist, how findings map, duplicates/sequencing → **re-run the story-synchronizer
    sub-agent** (Step 3) with the user's guidance, then re-agree tickets.
  - a missed commit/file or wrong patterns → go back to Step 1/2 to extract & process it, then
    re-synchronize.

ticket-formatter is create/update-only, local, and convergent, so iterating is safe and leaves no
duplicates.

### Step 5 — Changelog (one sub-agent), then report

Once the user is happy with the backlog changes, record the commit-level knowledge history:

> Run the **changelog-generator** skill — `.agents/skills/changelog-generator/SKILL.md`. Use its
> `list` to find commits in `temp/` not yet in `CHANGELOG.md`, read each manifest, the processors'
> findings, and the `changed_*.diff` files, and insert one reverse-chronological OKF entry per
> commit (with the `okf:commit=<sha>` marker; existing entries are immutable). Author only — write
> only `CHANGELOG.md`. Return ONLY the count and the short_shas logged.

Then give the user a final roll-up of the whole run: commits extracted & processed, the changeset
summary, the tickets created/updated in `user_stories/` (with their `view.html`), and the changelog
entries added. Note that **pushing `user_stories/` to Azure DevOps is a separate downstream step**
(via `ado-cli-skill`) that this coordinator does not perform.

---

## Idempotency & resumption

Every underlying step is idempotent, so re-running the coordinator is safe and resumes naturally:

- `git-sync-extractor` only processes commits after `.last-sync`.
- The processors skip files that already have `extracted_*`/`arch_extracted_*` output.
- `story-synchronizer` regenerates `temp/story_changeset.json` holistically each run.
- `ticket-formatter` keys on numeric id / title slug, so the same spec converges on the same file.
- `changelog-generator` skips commits already bearing an `okf:commit` marker.

If a run is interrupted, just invoke the coordinator again — it picks up the pending work at each
step.

---

## Guardrails

- **Delegate the heavy reads.** Do not read raw materials or findings into your own context; that is
  the entire reason this skill exists. Hold summaries, not contents.
- **Run deterministic tools, don't rebuild them.** `git-sync-extractor` is a CLI — run and report.
  The other five are agent skills with their own contracts; have sub-agents follow those contracts
  rather than reimplementing the logic here.
- **Never call `az` or write to Azure DevOps.** The pipeline is local up to (and including)
  `user_stories/`. Pushing to ADO is out of scope.
- **Source data is read-only** except the two deliberate writers: sub-agents write derived output
  (`*_extracted_*.json`, `story_changeset.json`, `CHANGELOG.md`) and `ticket-formatter` writes
  `user_stories/`. Nothing deletes source data or `temp/` commit folders.
- **Honour quality gates.** If `ticket-formatter validate` fails, stop and surface it — never
  `--skip`/`--no-verify` or fake success.
- **Surface, don't guess.** First-run start point, missing `user_stories/`, and blocking open
  questions go back to the user. Don't resolve a `CLARIFY`/`UNKNOWN`/`TBD` on your own.
- **Never commit `temp/`** (it is gitignored, regenerated). `CHANGELOG.md` and `user_stories/` are
  the durable, committable outputs.

---

## Skills this coordinator drives

| Step | Skill | Entrypoint (Bash; PowerShell equivalents exist) | Runs as |
|---|---|---|---|
| Extract | `git-sync-extractor` | `git-sync-extractor.sh run\|status\|reset` | inline (deterministic CLI) |
| Process | `transcript-processor` | `transcript-processor.sh list --commit <sha>` | per-commit sub-agent |
| Process | `architecture-processor` | `architecture-processor.sh list --commit <sha>` | per-commit sub-agent |
| Reconcile | `story-synchronizer` | `story-synchronizer.sh status\|findings\|stories` | one sub-agent |
| Format + UI | `ticket-formatter` | `ticket-formatter.sh validate\|diff\|view` | one sub-agent per agreed ticket |
| Changelog | `changelog-generator` | `changelog-generator.sh list\|status` | one sub-agent |

PowerShell entrypoints live under each skill's `scripts/powershell/` with `-Pascal` parameter names
(e.g. `-Commit`, `-From`, `-Pattern`); use them on PowerShell-only hosts.
