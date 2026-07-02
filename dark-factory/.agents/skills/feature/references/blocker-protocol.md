# Blocker protocol — when the autonomous run may pause the user

Feature runs the spec → plan → implement chain **autonomously**. The user opted into "stop only when blocked", so the default is **keep going**: resolve from the inputs, the repo, and sensible conventions. Pausing the user is the exception, reserved for decisions that are genuinely theirs to make or actions that are unsafe to take unbidden. This file draws that line.

## What IS a blocker (pause and ask)

Pause the run and ask the user when:

1. **Irreducible product ambiguity** — a requirement the stories/inputs/repo genuinely don't settle and where the choices lead to materially different builds (e.g. "should a partial-failure backfill re-raise or record-and-continue?" when neither the stories nor existing patterns answer it). A best guess here would silently bake in a product decision.
2. **A review gap that can't be closed from the inputs** — the output review or adherence check found a real gap, and fixing it requires information or a judgement call you don't have (not just more work — *missing input*).
3. **A missing convention/rule that needs sign-off** — the Plan phase's convention audit found a needed rule that doesn't exist. Drafting it is fine; **adopting + committing a new rule on the user's behalf is their call** (`create-rule` is approval-gated). Surface the draft and ask.
4. **A destructive or irreversible action** — anything that deletes/overwrites data the agent didn't create, rewrites history, pushes, or touches something outside the feature's scope. Always confirm first (this is a standing rule, not specific to Feature). A concrete recurring instance: **pre-existing uncommitted changes already sitting in a file the plan is about to edit** (found via the Phase-0/pre-implementation `git status`/`git diff` check) — never silently edit on top of them or silently fold them into this feature's commits; ask whether to commit them separately first, stage narrowly around them, or pause if they're someone else's in-progress work.
5. **A contradiction or knock-on effect with no safe default** — a phase reveals the stories conflict, or the work collides with a repo constraint, in a way you can't resolve without choosing what the user actually wants.
6. **`self-learn` proposals** — these are always shown for approval; that's a normal gate, not a failure, and it's the one routine pause per phase.

## What is NOT a blocker (resolve it yourself, record the assumption)

Do **not** pause for:

- Anything answerable from the feature description, investigation findings, the constitution, `CLAUDE.md`, `ARCHITECTURE.md`, or an existing code pattern — read it and proceed, recording the assumption in the artifact.
- Naming, slug, file-number, ordering, or other mechanical choices with an obvious convention.
- A review gap that's just *more work* (a missing test, an unhandled edge case the spec already names) — feed it back and re-delegate; that's the loop working, not a blocker.
- An adherence `DEVIATED` result — re-delegate with the deviation called out; never accept it, but don't ask the user about it either.
- A best-guess that's low-stakes and easily reversed — make it, record it, move on. (Reserve the user's attention for the genuinely consequential.)

The test: *would a competent engineer with these inputs make this call themselves, or would they walk over and ask the product owner?* Only the latter is a blocker.

## How to ask (when you must)

- **Batch** the blockers you can see at a phase boundary into a single `AskUserQuestion` round rather than drip-feeding — respect the user's attention.
- For each blocker give: the **decision needed**, **why the inputs don't settle it**, the **concrete options** (with your recommended option first, marked *(Recommended)*), and **what each implies** for the build. The user should be able to decide without re-reading the spec.
- Use `AskUserQuestion` with real options; allow the implicit "Other". Don't ask open-ended "what do you want?" when you can frame the actual fork.
- After the answer, **fold it into the artifact** (as a resolved decision, not a lingering assumption) and **re-delegate the affected phase** so the change flows through that skill's own logic — don't hand-patch the artifact and skip the phase's review.

## Mid-phase vs at-the-gate

- A sub-agent surfaces blockers in its **hand-off report** (it cannot pause mid-run — it records and returns). So most blockers are handled at the phase boundary, after Step 1 returns.
- A genuinely run-stopping blocker discovered *by Feature itself* mid-orchestration (e.g. the repo is in a state that makes the whole run unsafe) is the rare case to stop immediately. Otherwise, collect at the gate and ask once.

## Never, to keep moving

- Never weaken/skip a test or a quality gate, narrow a test to pass, or add `--no-verify`/`--skip`/`xfail` to dodge a blocker.
- Never override or skip a reviewer (adherence, output, or `implementor`'s per-task review) to advance.
- Never invent a convention/rule and commit it as if it were agreed.
- Never guess past an irreducible product ambiguity — that's exactly the case to ask.
