---
title: "Decision record — T008/T009 sequencing (recorded by implementor, non-interactive)"
---

# Decision record — T008/T009 sequencing (recorded by implementor, non-interactive)

**Date**: 2026-07-01
**Branch**: `fix/telemetry-feature-run-identity`
**Scope**: feature `003-audit-trail-checks`, plan step S1, tasks T008 + T009.

## The contradiction surfaced

tasks.md and plan.md describe the S1 secret-redaction work as a two-task red/green pair:

- **T008** — a *failing* negative-redaction test: a ≥40-char opaque path segment
  (`dist/assets/index-<40hex>.js`) and `src/services/auth_secret_loader.py` must NOT be
  masked. Described as RED because "the current catch-all over-masks the long opaque segment".
- **T009** — *tighten* the generic catch-all in `subagent_stop.py` so it no longer over-masks
  real paths (require no `/` + whole-value anchor), making T008 green.

However, the authoritative contract `contracts/telemetry-capture.md` §"Secret redaction rule (R10)"
already specifies the **tightened** regex verbatim:

```python
_SECRET_GENERIC_RE = re.compile(r"\A[A-Za-z0-9+/]{40,}\Z")
# fires only when: "/" not in value AND _SECRET_GENERIC_RE.fullmatch(value)
```

T007's implementation copied that R10 block **verbatim** (independently reviewed as a verbatim
match). So the "over-masking catch-all" that T008 was meant to catch **never existed in the
committed code** — the whole-value-anchored, `/`-free rule was installed by T007.

Empirically confirmed against the committed `subagent_stop.py`:

```
'dist/assets/index-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0.js' -> (verbatim, False)   # NOT masked
'src/services/auth_secret_loader.py'                            -> (verbatim, False)   # NOT masked
'sk-ABCD1234EFGH5678IJKL'                                       -> ('sk-A…IJKL', True)  # masked
```

## Decision (assume-and-record)

A genuine red for T008 is impossible **without first loosening** the regex that T007 correctly
installed — i.e. deliberately re-introducing the over-masking bug just to watch a test go red,
then re-tightening. That is a constraint-bypass / reward-hacking pattern (weaken-then-restore to
manufacture red) and is explicitly forbidden. It is NOT an in-loop fix.

Therefore:

1. **T008** is implemented as a **regression-guard** negative test (added to
   `tests/test_tool_input_capture.py`) that LOCKS IN the correct non-over-masking behaviour. It is
   green against the already-correct T007 regex. It is red-first *in principle* — it fails against
   any implementation with the naive unanchored `/`-permissive catch-all the plan warned about — it
   is simply not red against the committed code, because the committed code already carries the fix
   the contract mandated. This is the honest outcome, not corner-cutting: the test still has real
   falsifying power (proved below).
2. **T009** requires **no production change** — the tightened, restricted R10 rule the task asks
   for is already present in `subagent_stop.py` (installed verbatim from the contract by T007). The
   task's green criterion ("T008 green, T006 stays green") is satisfied by the committed code. T009
   is recorded as satisfied-by-T007; the T008 test is the durable proof it stays satisfied.

## Falsifying power of the T008 guard (proof it is a real test)

The guard asserts the two path values are returned VERBATIM with no `value_redacted`. It fails if
`_SECRET_GENERIC_RE` were reverted to an unanchored/`/`-permissive form (e.g. `[A-Za-z0-9+/]{40,}`
with `.search`), which would mask the 40-hex segment inside `dist/assets/index-<40hex>.js`. So the
test genuinely guards the restriction; it is not tautological.

## Constitution / guardrail note

No gate was weakened, no `# noqa`, no test narrowed. The red-first principle is honoured in spirit
(the test discriminates the correct rule from the buggy one); the deviation is purely that the fix
landed one task earlier than the task numbering anticipated, because the contract pinned the fixed
regex and T007 implemented the contract faithfully. Surfaced here per Constitution V.
