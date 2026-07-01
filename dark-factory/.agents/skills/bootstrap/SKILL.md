---
name: bootstrap
description: Tailor a freshly-installed Dark Factory framework to the host codebase — analyse its guard-rails, architecture, software patterns, and coding standards with parallel sub-agents, synthesise project-specific governance, and delegate the constitution write to `speckit-constitution`, then offer an evidence-backed ARCHITECTURE.md. USE WHEN the framework has just been installed (via `install.sh`) into a project and the user wants to generate a project-tailored constitution — "bootstrap this project", "set up the constitution", or `/bootstrap`.
---

# Bootstrap

Bootstrap is the **one-time tailoring step that runs after `install.sh`** has copied the framework into
a project. `install.sh` is mechanical — it lands files and wires symlinks but knows nothing about the
host codebase. Bootstrap is the intelligent counterpart: it *reads the actual project*, derives the
rules that should govern it, and turns them into a tailored `.specify/memory/constitution.md` — the
canonical file every downstream phase (`specification`, `plan`, `tasks`, `implementor`, the `speckit-*`
gates) reads and enforces.

It does **not** write the constitution itself. It gathers evidence, synthesises principle inputs, and
**delegates the write to the existing `speckit-constitution` skill**, which owns template-fill,
semantic-version bumping, dependent-template propagation, and the Sync Impact Report. Bootstrap's job is
discovery + synthesis + an independent review of the result.

## When to use this skill

- "I just ran `install.sh` — now tailor the constitution to this repo."
- "Bootstrap this project / set up governance for this codebase."
- `/bootstrap`.

If the framework is **not** installed yet (no `.specify/`, no `.agents/`), this skill stops and tells
the user to run `install.sh` first. If the constitution has **already been tailored**, it confirms
before overwriting.

## The workflow

### 0. Guards (hard gate — do not analyse until these pass)

1. **Framework present.** Verify all of:
   - `.specify/memory/constitution.md` exists,
   - `.specify/templates/constitution-template.md` exists,
   - the `speckit-constitution` skill is available (`.agents/skills/speckit-constitution/SKILL.md`).
   If any is missing, **stop** and instruct the user to run `install.sh` from a Dark Factory checkout
   first. Do not attempt a partial bootstrap.
2. **Clobber guard.** Read `.specify/memory/constitution.md` and decide whether it is still the
   **unmodified seed** — recognisable by the heading `# Dark Factory Constitution` together with the
   blockquote beginning `> Seeded from the standing global engineering principles`.
   - **Still the seed** → proceed; this is the expected post-install state.
   - **Already tailored** (heading/seed-blockquote changed, or a Sync Impact Report comment is present)
     → surface this and ask the user whether to re-tailor (overwrite) before continuing. Never silently
     overwrite project-specific governance.

### 1. Orientation

Run the existing **`get-codebase-primer`** skill (or, if unavailable, a single `Explore` agent) to get
a fast orientation: languages, entry points, top-level layout, build/test tooling. This primer is shared
context for the four analysis agents — it stops them re-deriving the basics in parallel.

### 2. Fan-out — four parallel analysis sub-agents

Spawn **four lightweight `Explore`/`general-purpose` sub-agents in parallel** (single message, multiple
tool calls). Do **not** use the heavy `analyze-*` audit skills — those produce graded reports and are
the wrong shape (and far heavier) for principle extraction. Each agent returns the fixed structured
schema in `references/analysis-rubrics.md` so the findings compose cleanly:

| Agent | Looks for | Feeds |
|-------|-----------|-------|
| **Guard-rails** | pre-commit config, CI workflows, linters, formatters, type-checkers, test runner, coverage gates, required checks | the constitution's *Quality Gates* section + test-discipline principle |
| **Architecture** | directory layout, layering, module boundaries, entry points, data/control flow | structural principles + the optional ARCHITECTURE.md |
| **Software patterns** | frameworks in use, notable design patterns, idioms, dependency conventions | technology-stack constraints |
| **Coding standards** | style/format configs, naming conventions, language/runtime versions, doc conventions | the *Additional Constraints* section |

Every finding **must cite evidence** (a file path / config key). A principle with no codebase evidence
is not allowed — see the review gate in step 4.

### 3. Synthesise → delegate the write to `speckit-constitution`

1. Synthesise the four findings into a single **principle-input payload** mapped to the constitution
   template's placeholders (`references/analysis-rubrics.md` defines the exact payload shape):
   `PROJECT_NAME`, `RATIFICATION_DATE` (today), project-specific `PRINCIPLES` (each with its evidence),
   `ADDITIONAL_CONSTRAINTS`, `DEVELOPMENT_WORKFLOW`/quality-gates, `GUIDANCE_FILE`.
2. **Preserve the framework principles.** The seed's non-negotiables (I. No Backward Compatibility,
   II. No Reward Hacking, III. Test-First, IV. Honesty & Permission to Fail, V. Surface Contradictions)
   are universal to this workflow — keep them. Bootstrap *adds and extends* with project-specific
   principles; it does not replace I–V.
3. **Invoke `speckit-constitution`** with that payload as its input, instructing it to amend the
   existing `.specify/memory/constitution.md` (fill `PROJECT_NAME`, set the ratification date, add the
   project principles/constraints, bump the version, propagate to the spec/plan/tasks templates, and
   prepend the Sync Impact Report). Let `speckit-constitution` own the actual file write — do not write
   the constitution by hand.

### 4. Independent review (producer never certifies its own work)

Spawn a **separate** review sub-agent (prompt in `references/review-rubric.md`) that reads the produced
constitution against the gathered evidence and checks:
- every project-specific principle is backed by cited codebase evidence (no invented rules),
- no leftover `[PLACEHOLDER]` tokens, dates are ISO `YYYY-MM-DD`, version line matches the report,
- the framework non-negotiables I–V survived intact,
- no reward-hacking (no vacuous/placeholder principles to look complete).
If the review fails, fix the inputs and re-run step 3 — do not hand a failed constitution to the user.

### 5. Offer ARCHITECTURE.md (approval-gated)

The architecture agent's findings are already in hand. **Offer** to seed an `ARCHITECTURE.md`
(consumed by `code-architecture-review` and `improvement-review`) — package structure, layering, and
dependency-direction rules drawn directly from the analysis. Write it only on explicit approval.

Do **not** create a project `CLAUDE.md`: the install wires `CLAUDE.md → AGENTS.md` as a symlink, and the
constitution is the canonical home for rules. A separate `CLAUDE.md` would collide and split governance.

### 6. Hand off

Summarise what was tailored (new constitution version + bump rationale, principles added, whether
ARCHITECTURE.md was written) and point the user at the next step: `/specification` to define a feature,
or `/feature` to drive the whole chain.

## Guardrails

- **No bootstrap without an install.** The framework files and `speckit-constitution` must be present;
  a missing framework is a stop-and-instruct, not a partial run.
- **Never silently overwrite a tailored constitution.** The clobber guard asks first.
- **Reuse, don't reimplement.** The constitution write is `speckit-constitution`'s job; the orientation
  pass is `get-codebase-primer`'s. Bootstrap orchestrates — it does not duplicate them.
- **Evidence or it's not a principle.** Every project-specific rule cites a file/config. The independent
  reviewer rejects invented or placeholder principles (constitution II — no reward hacking).
- **Preserve the non-negotiables.** Framework principles I–V are kept; bootstrap extends, it does not
  replace them.
- **One canonical rule home.** Constitution only — no competing project `CLAUDE.md`.

## References

- [`references/analysis-rubrics.md`](references/analysis-rubrics.md) — the four fan-out sub-agent prompts, the shared structured output schema, and the principle-input payload shape handed to `speckit-constitution`.
- [`references/review-rubric.md`](references/review-rubric.md) — the independent review sub-agent's prompt and pass/fail verdict format.
