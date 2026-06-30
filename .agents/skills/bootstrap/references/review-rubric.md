# Bootstrap independent-review rubric

Run **after** `speckit-constitution` has written `.specify/memory/constitution.md`. Spawn a **separate**
sub-agent — the agent that produced the inputs must not certify its own output (mirrors the `feature`
orchestrator's review discipline). Read-only and adversarial: assume the constitution is wrong until the
evidence shows otherwise.

## Inputs to give the reviewer

- The written `.specify/memory/constitution.md` (with its Sync Impact Report).
- The four analysis-agent outputs (the findings + evidence that drove the principles).
- The seed's framework principles I–V (to confirm they survived).

## Checks (all must pass)

1. **Evidence-backed.** Every *project-specific* principle and constraint traces to a cited
   finding/file. Flag any rule with no basis in the analysis — invented rules fail the review.
2. **Non-negotiables intact.** Framework principles I–V (No Backward Compatibility, No Reward Hacking,
   Test-First, Honesty & Permission to Fail, Surface Contradictions) are present and unweakened.
3. **No placeholders.** No leftover `[ALL_CAPS]` tokens (except any the report explicitly defers with a
   justified `TODO(...)`).
4. **Well-formed.** Dates ISO `YYYY-MM-DD`; the version line matches the Sync Impact Report's
   old→new bump; headings follow the template hierarchy; principles are declarative (MUST/SHOULD), not
   vague ("should probably…").
5. **No reward-hacking.** No vacuous or padding principles added just to look thorough; no rule the repo
   cannot actually honour stated as if it already holds (those belong in `DEFERRED`/`TODO`).
6. **Dependent templates synced.** The report lists `spec-template.md`, `plan-template.md`,
   `tasks-template.md` as updated (or explains why none was needed).

## Verdict format

```
VERDICT: PASS | FAIL
violations:
  - check: <which check>
    detail: <what's wrong>
    fix: <the specific correction to the principle-input payload>
notes: <anything advisory but non-blocking>
```

On `FAIL`, the orchestrator corrects the principle-input payload and re-invokes `speckit-constitution`,
then re-reviews. Do **not** present a `FAIL` constitution to the user.
