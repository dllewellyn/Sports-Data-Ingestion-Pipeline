# Report template

Copy this shape. Rank opportunities by value/effort/risk (highest net value first).
Every opportunity carries `path:line` evidence and a **complete ripple set**. Omit any
empty section. If nothing is warranted, use the empty-result form at the bottom — that
is a complete, honest result.

```
# Improvement review — <scope: changeset (uncommitted + commits since plan) | branch vs main | full repo>

Verdict: <N opportunities (M worth doing now) | no improvements warranted>

## Opportunities

### 1. <short title>
- Lens: architecture | reuse | repackaging
- Value / Effort / Risk: <high|med|low> / <high|med|low> / <high|med|low>
- What & why: <the sub-optimal shape and the upside of changing it>
- Evidence: <path:line> — <short quote/identifier>; <path:line> …
- Proposed change: <the refactor, at outcome altitude — not a full design>
- Ripple set (must change together):
  - code: <importers / dbt ref() / definitions.py prefixed AssetKey / tests — path:line>
  - ARCHITECTURE.md: <§/section or the data-flow diagram> — <what update>
  - ERD.md: <canonical/link tables touched> — <what update>  (or: n/a)
  - CLAUDE.md: <constraint/config/command> — <what update>   (or: n/a)
  - skills: <skill name> — <which step/example goes stale + the edit>  (or: none)
  - dbt/config/docs: <schema.yml / profiles.yml / compose / notebooks / README> — <what>
  - open questions: <any coupling you couldn't confirm>      (omit if none)
- KISS check: <why this is earned — real 2nd caller / concrete need / real layering harm — not speculative>
- Route: plan→implementor (new change, ripple set = scope) | flag to self-learn (candidate skill) | code-architecture-review (conformance) | trivial

### 2. <short title>
…

## Deferred (worth doing later, not now)
- <title> — <why it can wait>

## Considered and intentionally not worth it
- <title> — <why a change here would be overengineering / unearned>

## Next step
<Which opportunities the user may want to route now. This skill proposes only — it
does not apply changes or auto-spawn the follow-up build.>
```

## Empty-result form

```
# Improvement review — <scope>

Verdict: no improvements warranted.

The changeset is well-placed (right layer/home), non-duplicative (no new duplication
within the diff or against existing code), and appropriately scoped (no unearned
abstraction). Considered: <one line on what you checked — placement, near-duplicates of
the repo's shared helpers, generalisation candidates — so the "nothing" is evidently
thorough, not lazy>.
```
