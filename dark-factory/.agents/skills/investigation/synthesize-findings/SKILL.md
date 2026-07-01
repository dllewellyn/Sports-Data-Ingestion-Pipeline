---
name: investigation-synthesize-findings
description: Turn the evidence gathered during an investigation into a clear answer, a recommendation, and a Specification-ready summary, checked against the investigation's done criteria. USE WHEN an investigation has gathered enough evidence and needs conclusions written up. Sub-skill of the Investigation skill.
---

# Investigation — Synthesize Findings

Converts the running evidence in an investigation into conclusions and a hand-off summary. This is the bridge between investigation and specification.

## Preconditions

The investigation directory exists and `findings.md` / `evidence/` contain real evidence from experiments. You know the `Done criteria` from `README.md`.

## Steps

1. **Re-read the charter** — pull the original question and done criteria from `README.md`. Everything below is measured against them.
2. **Review the evidence** — read `findings.md` log entries and the artefacts in `evidence/`. Distinguish what was actually observed from what was assumed.
3. **Answer the question** — state the answer plainly. If the evidence doesn't reach the done criteria, say **inconclusive** and name exactly what's missing. Do not overstate confidence.
4. **Write the conclusion** into the top `Conclusion` section of `findings.md`:
   - Answer to the question
   - Recommendation (the direction to take, or "continue investigating: <next step>")
   - Confidence: high / medium / low — and *why*
   - Key evidence references (link to `evidence/…` and the relevant log entries)
5. **Record decisions** in `decisions.md` — any decisions the evidence now justifies, plus remaining open questions.
6. **Update status** in `README.md` — `concluded` or `inconclusive`.
7. **Flag knock-on effects** — surface contradictions, risks, or downstream impacts the evidence revealed that the user hasn't raised.

## Specification hand-off summary

Produce a short summary the **Specification** skill can consume directly. Include:

- **The answer** to the original question.
- **The recommended direction** and why.
- **Constraints / non-negotiables** the evidence established (performance bounds, API limits, data shapes, etc.).
- **Out of scope / explicitly rejected options** and the reason they were ruled out.
- **Open questions** that specification will need to resolve.

Then return to the parent `investigation` skill, which proposes starting the Specification skill — unless the result is inconclusive, in which case recommend continuing the investigation or narrowing the question instead.
