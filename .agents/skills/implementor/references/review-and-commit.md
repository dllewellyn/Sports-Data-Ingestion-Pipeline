# Independent review gate & commit protocol

Phases 3.2–3.4 of the implementor skill. After an implementer returns, a **separate, read-only, adversarial** sub-agent decides whether the task genuinely passes — and only a PASS gets an atomic commit.

## This extends the plan skill's reviewer — don't duplicate it

The base reviewer protocol (why a separate agent, when to spawn, read-only/adversarial stance, the verdict format) lives in [`../plan/references/self-review.md`](../plan/references/self-review.md). Use it as-is. This file adds the **three checks the implementor cares about most** and the commit protocol. Do not restate the base protocol — reference it.

## The reviewer is never the implementer

The agent that wrote the code is the worst judge of whether it cut a corner. Spawn a **fresh** `general-purpose` agent (or invoke the `code-review` skill on the diff) with no stake in the implementation. It is **read-only**: it inspects, runs the test and guardrails, and judges — it does not edit. Keeping it from fixing keeps its judgement uncontaminated.

## What the reviewer checks (base checks + the three implementor additions)

Base checks (from `self-review.md`): meets the spec scenario/AC · the test is real and can fail · conventions honoured · no reward-hacking · no backward-compat scaffolding · guardrails in place.

The implementor adds, explicitly:

1. **Plan was followed.** The change matches the plan step's implementation outline and green criterion. If the implementer deviated (its report flags one, or the diff shows it), the deviation is justified and still satisfies the spec — an unexplained departure from the plan is a GAP.
2. **No scope drift — the agent did not stray.** The diff touches **only** this task's footprint (the files in the task's write set). Edits to other plan steps' files, refactors of unrelated code, or features the spec didn't ask for (gold-plating) are a FAIL — even if they "work". The build must do what the plan said, no more.
3. **The test is genuinely useful, not just present.** Beyond "can it fail" — does the test assert the **observable outcome from the spec scenario** (the BDD `Then`), or does it assert something trivial/tautological that would pass regardless? A test that exists only to make the step look done, asserts an implementation detail instead of behaviour, or covers the happy path while the spec called out a failure mode → GAP with the missing assertion named.

## Reviewer prompt (delta over the base template)

**Telemetry:** immediately before spawning, run `python3 .agents/skills/_shared/telemetry/emit.py label-next --role review:<task_id> --phase implementor` so the independent review shows up as its own span in the feature-run trace — this is what proves, in the dashboard, that the review sub-agent actually ran for each task (best-effort no-op if telemetry is off).

Spawn with the base prompt from `self-review.md`, then append:

> **Additionally, decide:**
> - **Plan adherence:** does the diff match plan step `S…`'s outline and green criterion? If the implementer deviated, is the deviation justified and does it still meet the spec? (yes/no + why)
> - **Scope:** does the diff touch ONLY this task's files `<write set>`? List any file changed outside that set — each is a scope-drift finding.
> - **Test usefulness:** does the test assert the spec scenario's observable `Then`, or is it trivial/tautological/asserting a mechanism? Name any missing assertion (e.g. a failure mode the spec called out but the test doesn't exercise).
>
> Fold these into the verdict: PASS | GAPS | REWARD-HACKING. Any scope drift, unjustified plan deviation, or non-useful test is at least GAPS.

## Verdict → action

| Verdict | Action |
|---------|--------|
| **PASS** | Commit the task (below). Mark it `done`. Advance to the next ready task / parallel batch. |
| **GAPS** | Feed the findings (file:line + required fixes) back to a **fresh implementer** to fix the code — or the test if the test itself was the problem. Then **re-spawn a fresh reviewer**. Repeat until PASS. |
| **REWARD-HACKING** | Same loop as GAPS, but the fix must *remove* the hack (stub/mock/hardcoded value/silent fallback/suppressed gate), not paper over it. Re-review from scratch. |

**Never** edit the test or weaken a gate to flip a verdict. **Never** override the reviewer to keep moving. **Never** commit a non-PASS task. If a task can't reach PASS because the *plan* is wrong (the outline contradicts the spec or a repo constraint), stop and surface it to the user — that's plan feedback, not something to force green.

## Commit protocol (PASS only)

One atomic commit per passing task — the known-good, resumable checkpoint. **Make the
commit through the shared guarded helper**, which encodes every rule below structurally
so the commit can't be made wrong:

```bash
bash .agents/skills/_shared/git-helpers/bash/git-commit-safe.sh \
  -m "feat(football): extra-family bronze ingestor (plan S3)" \
  src/data_platform/assets/football.py tests/test_football.py
```

(PowerShell: `pwsh .agents/skills/_shared/git-helpers/powershell/git-commit-safe.ps1 …`.)

The helper, by construction:

- **Stages only the task's footprint** — pass exactly the task's files as the path
  args; it refuses if anything is staged *outside* them (no sweeping unrelated work in).
- **Enforces Conventional Commits** — `feat|fix|refactor|build|ci|chore|docs|style|perf|test(scope): …`,
  with the message tracing to the plan step. It rejects a non-conventional subject.
- **Lets the gate run** — pre-commit (ruff) executes; the helper **never** passes
  `--no-verify`/`--skip`. If a hook fails the commit fails (non-zero) and the task
  isn't green — fix and re-review; never bypass.
- **Appends the co-author trailer** automatically:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Exposes none of the forbidden verbs** — it can only `add` + `commit`. It never
  pushes / checks out / switches / `reset --hard` / `clean` / `restore` / `rm`.
- **Refuses the default branch** unless you pass `--allow-default-branch`: if on `main`
  and the user expects a feature branch, raise it first — the helper never switches
  branches (forbidden); ask the user to create/switch, or pass the flag to commit here.

Use the repo's package manager (`uv`) — no tooling swaps; no repo-wide search/replace
scripts (`sed -i`, `perl -pi`).
