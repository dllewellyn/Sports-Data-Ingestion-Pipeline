# Data Model: Bidirectional Identity Reconciliation

**Feature directory**: `specs/013-bidirectional-identity-reconciliation/`

## Entity: Learned Team Alias (bridge)

**Artifact**: `data/silver/learned_team_aliases.parquet`, written by the `identity_reconciliation`
Dagster asset. Bootstrap-written empty (correct columns, zero rows) before first use, following the
existing `bootstrap_additions_files` / `_ensure_empty_parquet` discipline in
`assets/intermediate/matchbook_conform.py` — every SQL call site reads it via `read_parquet()`, which
errors on a missing file.

| Column | Type | Description |
|---|---|---|
| `raw_name` | `varchar` | The unseeded raw team name observed in a provider's bronze data (ESPN `home_team_name`/`away_team_name`, or a Matchbook event-name half from `parse_event_name`). |
| `team_id` | `varchar` | The canonical `team_id` this raw name resolves to (an existing canonical team — either seed-derived or previously self-minted by either provider). Never a newly-minted id; reconciliation only bridges onto teams that already exist in the canonical pool. |
| `source_provider` | `varchar` | Which provider's bronze data the raw name came from (`espn` \| `matchbook`). |
| `confidence` | `double` | The fuzzy-match score (0.0–1.0) against the winning candidate. |
| `match_method` | `varchar` | `auto_confirmed` (≥ `HIGH_THRESHOLD`) or `needs_review` (≥ `MEDIUM_THRESHOLD`, < `HIGH_THRESHOLD`). |

**Validation rules**:
- One row per distinct `(raw_name, source_provider)` — recomputed from scratch each run, not
  accumulated (FR-010's idempotency requirement; a raw name's bridge in run N+1 fully supersedes its
  row from run N).
- `raw_name` MUST NOT already have a `team_aliases` seed match (seed always takes precedence — Edge
  Case "seed alias always takes precedence").
- `confidence` MUST be `>= MEDIUM_THRESHOLD` for any row to exist at all (rows below threshold, or
  ambiguous ties, are simply never written — no "unresolved" row is emitted for them; their absence
  from this file, plus absence from the seed, is what routes a name to a provider's normal self-mint
  path).

**State transitions**: none — this is a pure, fully-recomputed derived artifact, not a stateful
entity. It has no lifecycle beyond "absent" → "written this run."

**Relationships**: `team_id` is a foreign reference into the canonical team pool
(`int_team.team_id` / `canonical_team_export.team_id`) — always to a *pre-existing* id, by
construction (Decision 3, research.md): the fuzzy-match candidates are drawn from the current
canonical export, so a bridge can only point at an id already present in it.

## Entity (touched, not new): Canonical Team Pool

`int_team` (dbt model) / `canonical_team_export.parquet` — unchanged shape (`team_id, name,
similar_names`). This feature changes **how a name resolves to a `team_id`** (three-tier: seed →
learned bridge → self-mint) but does not add, remove, or rename any column on this entity.

## Resolution formula (shared across every call site — FR-006)

```
team_id = coalesce(
    seed_lookup(raw_name),        -- team_aliases.csv, alias -> team_id
    learned_lookup(raw_name),     -- learned_team_aliases.parquet, raw_name -> team_id
    md5(lower(raw_name))          -- self-mint, unchanged formula
)
```

Realised as:
- **dbt macro** `resolve_team_id_expr(seed_id_col, learned_id_col, name_col)` →
  `coalesce({{ seed_id_col }}, {{ learned_id_col }}, md5(lower({{ name_col }})))`, in
  `dbt/data_platform/macros/resolve_team_id_expr.sql`.
- **Python** `resolve.resolve_team_id(name, aliases, learned_aliases=None)` — extended with the middle
  tier; unchanged behaviour when `learned_aliases` is `None`/empty (backward-source-compatible with
  every existing caller and test).

Both sides are proven never to drift via the parity test extension (Testable Units, plan.md).
