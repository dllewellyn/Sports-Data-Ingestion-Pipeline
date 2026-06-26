---
name: investigation
description: Run a structured investigation into an open question, spike, or unknown before any specification or build work begins. Uses an interview to scope the question, scaffolds a predefined structure for investigation code and findings, drives the investigation to evidence-backed conclusions, then proposes handing off to the Specification skill. USE WHEN the user wants to investigate, explore, spike, prototype, or de-risk something whose answer is not yet known.
---

# Investigation

Investigation is the **discovery phase that comes before specification**. Its job is to turn an open question or unknown into evidence-backed conclusions and recommendations — *not* to build the final solution. The output of an investigation is what feeds the next phase: the **Specification** skill.

Treat throwaway code, experiments, and prototypes as evidence. They exist to answer the question, not to ship.

## When to use this skill

- "I want to investigate / explore / look into X"
- "Can we spike / prototype / de-risk Y before committing?"
- "I'm not sure whether approach A or B is better — find out"
- "Why does Z happen?" where the answer requires gathering evidence

If the question is already understood and the user wants to define *what to build*, that is the **Specification** skill's job, not this one.

## The workflow

Follow these phases in order. Do not skip the interview.

### 1. Interview the user (mandatory)

Do **not** start investigating until you have interviewed the user about what they want to investigate. Ask one focused batch of questions, then confirm your understanding before scaffolding.

Use the `AskUserQuestion` tool for the interview where it helps, and cover at minimum:

1. **The question** — What single question must this investigation answer? Phrase it as a question with a yes/no, a decision, or a measurable answer.
2. **Why now** — What decision or downstream work is blocked until this is answered? (This anchors the eventual Specification hand-off.)
3. **Hypotheses** — What does the user already suspect the answer is? What are the candidate approaches/options?
4. **Done criteria** — What evidence would make the user confident enough to stop investigating and move to specification? (e.g. "a benchmark showing < 200ms", "a working spike that hits the real API", "a clear yes/no on feasibility").
5. **Constraints & scope** — Time box? Off-limits areas? Data/credentials available? What is explicitly *out* of scope?

End the interview by playing back a one-paragraph summary: *"Here's the investigation as I understand it … Shall I scaffold it?"* Wait for confirmation.

### 2. Propose & scaffold the structure

Once the user confirms, propose the predefined investigation structure (see `references/structure.md`), then create it. Use the **`scaffold` sub-skill** to generate the directory and starter files. Default location is `investigations/<slug>/` at the repo root unless the user prefers elsewhere.

The structure separates **code** (spikes/experiments — disposable) from **findings** (durable conclusions). Always show the user the structure before creating it so they can adjust the layout or slug.

### 3. Run the investigation

Work the question using whatever evidence-gathering is appropriate: spikes, benchmarks, reading code, querying data, reproducing a bug, comparing options. Rules:

- Put experimental code under the investigation's `code/` directory; keep it clearly disposable and labelled as a spike, not production code.
- Capture raw evidence (logs, query output, screenshots, measurements) under `evidence/`.
- Log each experiment and what it showed in `findings.md` as you go — don't wait until the end.
- If you discover the question was the wrong question, surface that to the user rather than answering a question they didn't ask.

### 4. Synthesize findings

Use the **`synthesize-findings` sub-skill** to turn the accumulated evidence into conclusions. The result must answer the original question against the done criteria from the interview, and state a clear recommendation (or an explicit "still inconclusive — here's what's missing").

### 5. Propose the Specification hand-off

When the investigation reaches its done criteria, **propose moving to the Specification skill**. Do not silently stop. Say something like:

> The investigation answers the original question: **<answer>**. The recommended direction is **<recommendation>**. The natural next step is to define *what to build* — shall I start the **Specification** skill, using this investigation's findings as input?

If the findings are inconclusive, say so plainly and recommend either continuing the investigation or narrowing the question — do **not** push to specification on weak evidence.

## Sub-skills

- **`scaffold`** — creates the predefined investigation directory and starter files.
- **`synthesize-findings`** — converts gathered evidence into conclusions, a recommendation, and a Specification-ready summary.

## Guardrails

- Never let investigation code drift into production code. It is evidence; it gets thrown away or rewritten under specification.
- Always tie conclusions back to the *done criteria* agreed in the interview.
- Surface contradictions and knock-on effects you discover, even if the user didn't ask about them.
