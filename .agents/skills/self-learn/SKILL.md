---
name: self-learn
description: Close the self-learning loop — review the current session's conversation, the git changes it produced, and the existing skills, then route durable learnings to the right home (CLAUDE.md, an updated skill, or a brand-new skill). Approval-gated; may legitimately propose nothing. USE WHEN a unit of work wraps up and you want to codify what was learned so a future instance doesn't rediscover it the hard way, or when the user asks to "run the self-learning loop" / "capture learnings" / "reflect on what we learned".
---

# Self-Learn (the self-learning loop)

The job of this skill is to **turn a finished piece of work into durable institutional knowledge**. During a session you discover things — a non-obvious constraint, a tool gotcha, a failure mode and its fix, a repeatable procedure. Left in the transcript, that knowledge dies when the context window closes. This skill mines it and routes each learning to exactly one durable home:

1. **`CLAUDE.md`** — project-wide facts, constraints, gotchas, commands, conventions. Things you want loaded into *every* future session's context.
2. **An existing skill** — when the learning improves how a repeatable workflow we already have should run (a better step, a new guardrail, a corrected command).
3. **A new skill** — when a repeatable, multi-step procedure emerged that nothing covers yet (e.g. "we just built a data-ingestion engine — capture the templates, scripts and best practices so the next ingestion is a skill invocation, not a from-scratch build").

This is reflection, not invention. **Proposing nothing is a valid, common outcome.** Most sessions produce one or two CLAUDE.md lines and no skill changes. Do not manufacture learnings to look productive — that is reward hacking and it pollutes the very files future instances depend on.

## When to use

- The user says "run the self-learning loop", "capture what we learned", "update your skills/docs based on this".
- A substantive task just concluded (a feature landed, a bug was root-caused, a new subsystem was added) and there are hard-won, non-obvious learnings worth persisting.
- You notice yourself thinking "a future instance would hit this same wall."

Do **not** use it for trivial sessions (a one-line fix, a question answered) — there is nothing durable to capture.

## The three sources to gather

Always pull from all three before triaging. Each candidate learning must be **traceable to evidence** in one of them; cite it (a commit, a diff hunk, a moment in the conversation).

1. **Conversation / session history.** What did we get wrong before getting it right? What surprised us? What did the user have to correct or explain? What "aha" unblocked us? These are the richest source of gotchas and conventions.
2. **Git changes.** Run read-only git to see what actually changed (never push/checkout/reset — see global git rules):
   - `git status` and `git diff` for uncommitted work, `git log --oneline -20` and `git diff <base>..HEAD` for committed work this session.
   - New files/dirs often signal a *new capability* worth a skill; recurring edit patterns signal a *convention* worth CLAUDE.md.
3. **Existing skills + CLAUDE.md.** Read `CLAUDE.md` (project + the "Maintaining this file" section) and list `.claude/skills/*/SKILL.md`. You cannot decide "new vs update vs already-covered" without knowing what already exists. **Prefer updating an existing skill or CLAUDE.md line over creating a duplicate.**

## Workflow

### 1. Gather context

Pull the three sources above. If the session is long, focus on the decisions and corrections, not every keystroke.

### 2. Extract candidate learnings

For each, write one sentence stating the learning and one citing its evidence. Apply the **bar for durability** — keep a candidate only if it is *both*:

- **Non-obvious** — not discoverable from the file tree, not generic Python/git advice, not already in CLAUDE.md or a skill.
- **Reusable** — it will plausibly matter again, to a future instance or teammate.

Drop anything that fails either test. (See `references/triage-rubric.md` for worked examples of keep/drop.)

### 3. Triage each survivor to one destination

Use the decision rubric in [`references/triage-rubric.md`](references/triage-rubric.md). In short:

- **→ CLAUDE.md** if it's a declarative fact/constraint/command/convention that applies across tasks. Put hard-won constraints under the existing **"Non-obvious constraints"** heading; keep additions concise and follow the file's own "Maintaining this file" guidance.
- **→ Update an existing skill** if it sharpens a workflow we already have. Identify the closest skill by its `description`/`USE WHEN`. Edit the relevant step or add a guardrail — don't bolt on unrelated scope.
- **→ New skill** if a repeatable multi-step procedure with its own templates/scripts/best-practices emerged. Use [`references/new-skill-template.md`](references/new-skill-template.md) and follow the conventions in `.claude/skills/README.md` (one responsibility, `USE WHEN` description, `references/` for templates, parent-prefixed sub-skill names).

A learning maps to **exactly one** destination. If it seems to fit two, it's usually a concise CLAUDE.md line *plus* a pointer from a skill — write the line, reference it from the skill.

### 4. Present proposals for approval (do not silently edit)

Show the user a compact table: each learning, its evidence, its destination, and the concrete change (the exact CLAUDE.md lines, the skill edit diff, or the new skill's name + description + outline). Group by destination. If you found nothing durable, say so plainly — "no durable learnings this session" is a complete, honest result. Wait for the user to approve, amend, or drop items.

### 5. Apply approved changes

- **CLAUDE.md / skill edits:** make them surgically with `Edit`. Match the file's existing tone and density. Remove guidance that the learning makes stale rather than letting it accumulate (no backward-compat cruft — see global design principles).
- **New skill:** scaffold `SKILL.md` (+ `references/` for any templates/scripts) from the template, then **register it in `.claude/skills/README.md`** (the Skills table, and the phased-workflow list if it belongs to a phase).

### 6. Commit (only if the user wants it)

If the user asks to commit, use an atomic, Conventional-Commits commit (`docs:` for CLAUDE.md, `chore:`/`feat:` for skills). Per the project's "Maintaining this file" rule, CLAUDE.md learnings ideally land **in the same commit as the work that produced them** when that work is still uncommitted. Never `push`.

## Guardrails

- **Empty is valid.** Never invent learnings. A session with no durable takeaway gets an honest "nothing to codify."
- **Evidence or it doesn't go in.** Every proposed change cites a commit, diff, or conversation moment.
- **Dedupe, don't duplicate.** Update the existing line/skill in place; never add a second copy of guidance that already exists.
- **One destination per learning**, and one responsibility per skill.
- **Respect the source files' own rules:** CLAUDE.md's "Maintaining this file" section and `.claude/skills/README.md`'s conventions are binding.
- **Approval-gated.** Steps 1–3 are read-only analysis. No file is edited before the user approves the proposal in step 4.
- Surface contradictions and knock-on effects you spot while reflecting, even if they're outside the immediate learnings.

## Relationship to the global `codify-*` skills

The global `codify-session-history` / `codify-git-history` / `codify-pr-reviews` skills do something adjacent but heavier: they run the external `enaible` CLI to produce auditable, deterministic *tooling/doc enforcement* proposals across many sessions. This skill is the lightweight, project-local counterpart — an in-session reflection loop that writes directly to *this* repo's `CLAUDE.md` and `.claude/skills/`. Reach for the `codify-*` skills when you need cross-session, evidence-indexed enforcement artifacts; reach for `self-learn` to close the loop on the work you just did.
