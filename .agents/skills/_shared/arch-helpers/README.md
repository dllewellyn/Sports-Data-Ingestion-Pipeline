# Shared architecture helpers

**This directory is not a skill** (no `SKILL.md`). It holds the deterministic half
of `code-architecture-review`: the ARCHITECTURE.md rules that are decidable from
imports and call sites, encoded as an AST scan so the review starts from a precise
violation list instead of greps the agent re-types and eyeballs each run.

Stdlib-only Python 3 (`ast`) — no dependency added to the target repo, and it can
drop straight into the target's pre-commit so drift is caught before review.

| Helper | Lang | Used by | Replaces |
|--------|------|---------|----------|
| `arch-lint.py` | python3 | `code-architecture-review` §2 | the ad-hoc `grep -rnE …` recipes for rules 1, 3, 4, 5, 7 |

## What it checks (ARCHITECTURE.md §3–§4)

Only the rules decidable from imports/calls:

- **Rule 1** — network libraries imported outside the bronze edge file
- **Rule 3** — `duckdb.connect()` called from Python (dbt owns warehouse writes)
- **Rule 4** — an asset module importing another asset module (composition root only)
- **Rule 5** — a leaf (`config.py` / `models/*`) importing `assets`/`definitions`
- **Rule 7** — `os.getenv` / `os.environ` outside `config.py`

Rules **2** (validate-in-order), **6** (transformation belongs in dbt) and **8**
(ARCHITECTURE.md staleness) need reading and judgement — `arch-lint.py` does **not**
fake them; they remain the agent's job. A finding is a **signal**, not a verdict:
confirm each in context (a match in a comment, a `:memory:` duckdb read, etc. is not
a violation).

## Quick reference

```bash
# Defaults match this repo's layout (src/data_platform, assets/bronze.py edge, config.py):
python3 .agents/skills/_shared/arch-helpers/arch-lint.py
# Override for a different package root / edge / config module:
python3 .agents/skills/_shared/arch-helpers/arch-lint.py \
  --src src/data_platform --edge assets/bronze.py --config config.py
```

Exit 0 = no mechanical violations; exit 1 = findings printed as `path:line: [Rule N] …`.

> Smoke-tested on a synthetic tree. The rule set encodes ARCHITECTURE.md §3–§4 — if
> that contract changes, this script changes with it (it is part of the rule 8
> ripple set).
