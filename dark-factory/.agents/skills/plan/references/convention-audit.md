# Convention & rule audit

Phase 2 of the plan skill, and a **hard gate**: for every kind of artifact the plan will create or touch, confirm the governing convention exists — and where one that *should* exist is missing, **create and commit it before** the implementation step that depends on it. The user's requirement: conventions are established up front, never discovered mid-build.

## The principle

Before the plan says "write a new Python ingestion module", it must answer: *what rules govern an ingestion module here?* If the answer is "none written down", the rule is authored and agreed first. This keeps every step's self-review able to check against a real convention instead of an implicit one.

## Step 1 — Enumerate the artifact types this plan introduces

Walk the spec and list each distinct artifact the build will create or modify. Typical for this repo:

- New **Python file / module** (any).
- **API / network code** (the system's edge — only `assets/bronze.py` touches the network today).
- **Ingestion code** into a specific module/package.
- New **dbt model** (silver/gold) and its **tests**.
- New **Dagster asset module** (runtime-introspected — special constraints).
- New **Pydantic schema** / **Pandera frame contract** / **config field**.
- New **pytest** test file (note: no suite exists yet — see `tdd-and-guardrails.md`).

## Step 2 — For each artifact type, find the governing convention (delegate the search)

Spawn a sub-agent per artifact type (or one sweeping agent) to locate the rules and the nearest analogous existing code. Search these in order:

1. **Project `CLAUDE.md`** — *Python conventions*, *Non-obvious constraints*, *Configuration & telemetry*. This is the primary contract.
2. **`ARCHITECTURE.md`** — package structure, layering, dependency-direction rules, and the "add a new data source" guide.
3. **`pyproject.toml`** — the ruff lint set (`E,W,F,I,UP,B,C4,SIM`), formatter, Python pin (`>=3.12,<3.13`). These are enforced, not advisory.
4. **Any rules location** — `.claude/rules/` (project), `~/.claude/CLAUDE.md` and `~/.claude/rules/` (global), `.github/` instructions. (Today the project keeps conventions in `CLAUDE.md`, not a `rules/` dir — note where the project actually stores them and stay consistent.)
5. **The nearest existing code of the same type** — the strongest convention is the pattern already in the tree. New ingestion code mirrors `assets/bronze.py` + `models/schemas.py` + `models/validation.py`; a new dbt model mirrors `dbt/data_platform/models/silver|gold/`; a new asset module mirrors `assets/`.

For each artifact type, decide: **exists** (rule found / clear existing pattern) or **gap** (no rule and no clear pattern, or the patterns conflict).

## Step 3 — Close every gap BEFORE implementation

For each gap, author the missing convention now and get user approval:

- Use the **`create-rule`** command/skill (`~/.claude/commands/create-rule.md`): it researches best practice, drafts a concise ALWAYS/NEVER rule (with a minimal example for concept rules), checks for duplicates, and appends to the agreed target file **only after confirmation**.
- Put the rule where this project already keeps conventions (project `CLAUDE.md`) unless the user wants a dedicated `.claude/rules/` location — if so, propose creating it explicitly (`create-rule` warns rather than auto-creating a missing target).
- Keep rules concise and true/false-framed. For a concept (e.g. "how ingestion modules layer validation"), include a one-line example.
- **Commit the convention as its own atomic commit** (`docs:` or `chore:`) before the implementation steps — so the build is reviewed against a committed standard.

Example gaps this repo could surface:
- *No written rule for API client retry/error handling* → add one before planning a new fetcher.
- *No rule for where new dbt tests live or how they're named* → add one before planning warehouse tests.
- *No pytest harness or layout convention* → establish the harness + a layout rule (this is also a Phase-4 guardrail prerequisite; see `tdd-and-guardrails.md` → *No test suite yet*).

## Step 4 — Produce the audit table

Output the table that becomes §3 of the plan:

| Artifact type | Governing convention | Status |
|---------------|----------------------|--------|
| new ingestion module | CLAUDE.md *Python conventions* + `assets/bronze.py` pattern | exists |
| API retry/error handling | new rule authored this run | created this run |
| pytest unit tests | pytest harness + `tests/` layout rule | created this run |

**Gate:** no implementation step in §6 may depend on a row still marked **gap**. If the user declines to close a gap, record it as a flagged Open Question and do not plan the dependent step as ready.
