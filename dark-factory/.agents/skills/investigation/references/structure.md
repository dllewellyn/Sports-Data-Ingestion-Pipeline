# Predefined investigation structure

Every investigation lives in its own directory and separates **disposable code** from **durable findings**.

```
investigations/
└── <slug>/                     # kebab-case, derived from the investigation question
    ├── README.md               # the question, why it matters, hypotheses, status, done criteria
    ├── findings.md             # running log of experiments → conclusions → recommendation
    ├── decisions.md            # decisions made + rationale; and open questions still outstanding
    ├── code/                   # spikes, experiments, throwaway prototypes (NOT production code)
    │   └── README.md           # what each spike is, how to run it, what it proved
    └── evidence/               # raw artefacts: logs, query output, screenshots, measurements, data samples
        └── .gitkeep
```

## File responsibilities

### `README.md` — the charter
Written during scaffolding from the interview answers. Stable for the life of the investigation.

```markdown
# Investigation: <title>

**Status:** scoping | in-progress | concluded | inconclusive
**Owner:** <name>
**Started:** <YYYY-MM-DD>

## Question
The single question this investigation answers.

## Why now
The decision or downstream work blocked until this is answered.

## Hypotheses / options
- H1: …
- H2: …

## Done criteria
The evidence that lets us stop and move to specification.

## Scope & constraints
In scope / out of scope / time box / available data & credentials.
```

### `findings.md` — the working log
Append as you go. One entry per experiment, newest insight summarized at the top.

```markdown
# Findings

## Conclusion (top — fill in once concluded)
- Answer to the question:
- Recommendation:
- Confidence: high | medium | low — because …

## Log
### <date> — <experiment name>
- What I did:
- What I observed (link to evidence/…):
- What it tells us:
```

### `decisions.md` — decisions & open questions
```markdown
# Decisions

## Made
- D1: <decision> — rationale, date.

## Open questions
- Q1: <still unresolved>
```

### `code/` — disposable spikes
Experimental code only. Label clearly as spikes. Never imported by production code. Each spike's purpose and run instructions go in `code/README.md`.

### `evidence/` — raw artefacts
Anything that backs a finding: command output, benchmark numbers, screenshots, sample payloads. Reference these from `findings.md`.

## Conventions

- `<slug>` is kebab-case, derived from the question (e.g. `can-we-stream-from-api`, `compare-duckdb-vs-postgres`).
- Keep `code/` and `evidence/` out of production build paths; add to `.gitignore` if they shouldn't be committed.
- The investigation is "done" when `findings.md`'s conclusion satisfies the `README.md` done criteria.
