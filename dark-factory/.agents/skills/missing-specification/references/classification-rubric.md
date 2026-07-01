# Classification rubric

How to assign each commit exactly one class, how to match a commit to an existing
spec, and how to group the leftovers into candidate specs.

## The golden rule: judge the diff, not the message

A Conventional Commit type (`feat`, `fix`, `style`, `chore`, …) is a **hint about
intent, never the decision**. A `chore:` that adds a Docker service is substantive;
a `feat:` that only renames a variable is not. Always confirm against
`git-history.sh show <sha>` (its `--stat`) and, where the stat is ambiguous, the diff
(`git-history.sh show <sha> --diff`). What matters is: *did observable behaviour, a
data contract, or a pipeline capability change?*

## The three classes

### Covered
An existing `specs/NNN-*/spec.md` already describes this change.

- **Test:** the commit's behavioural effect maps onto that spec's summary,
  goals, a BDD capability/scenario, or an acceptance criterion — or onto a step in
  its sibling `plan.md` in the same feature directory (plans name concrete
  files/assets, which makes the match precise).
- **Record:** `sha → spec id`, naming the matching capability as evidence.
- Example in this repo: ESPN ingestion commits map to spec `002`; football-data
  bronze commits map to spec `001`.

### Unspecified (substantive) — the gap
Observable behaviour / data contract / pipeline capability changed, and **no**
existing spec covers it. These become new specs.

Treat as substantive when the commit does any of:
- adds or changes a **data source** or ingestion path (a new provider, endpoint,
  file family, registry);
- adds or changes a **data contract / schema** — Pydantic/Pandera models, dbt
  models/sources/seeds, canonical or link tables, the warehouse shape;
- adds or changes a **pipeline capability** — a Dagster asset/job/schedule, a
  materialization, an orchestration edge;
- adds or changes **runtime behaviour or configuration** users/operators rely on
  (new settings, a service in compose, idempotency/throttling/skip-existing logic);
- changes **validation, encoding, partitioning, or identity** rules that affect
  correctness.

### Non-substantive — record, don't spec
No product behaviour changes. Note the SHA in the ledger and move on:
- pure `style`/lint/format reflows (e.g. "apply ruff format");
- dependency/version bumps with no behavioural change;
- comment-only or doc-only edits (`docs:` touching `*.md`, `CLAUDE.md`, `ERD.md`);
- `.agents/skills/**` and other agent-tooling edits;
- CI/`chore` plumbing that alters no runtime behaviour.

**Caveat:** a *cluster* of "chore"-typed commits can jointly deliver a capability
(e.g. several commits standing up a containerised service). Judge the cluster's net
effect, not each commit in isolation — if the net effect is a new capability, it's
substantive.

## Edge calls

- **Bug fix to specified behaviour** → Covered by the spec that owns that behaviour
  (the fix corrects an AC already in scope). Only flag it unspecified if the fix
  introduces *new* behaviour the spec never described.
- **Investigation/spike commits** (`investigate:`) → usually non-substantive for
  spec purposes (the durable output is the investigation doc, not shipped product),
  unless the spike left runtime code in the build.
- **Refactor with no behavioural change** (`refactor:`) → non-substantive.
- **A commit spanning two features** → split it across two clusters in the ledger;
  classify each part.
- **Reclassify freely.** If, while reading later commits or specs, you realise an
  earlier call was wrong (a spec *does* cover it, or a "chore" was load-bearing),
  fix the ledger. Don't create an overlapping spec for already-covered work.

## Grouping the unspecified into candidate specs

Cluster by the **outcome delivered**, not by commit count or author or date:

- **Same data source / subsystem → one spec.** All the commits that stand up a
  provider's ingestion (model + bronze asset + dbt source + staging + job +
  schedule + its fixes) are one feature, hence one spec — even if that's a dozen
  commits across weeks.
- **Shared canonical/warehouse change → its own spec** when it's a capability in its
  own right (e.g. canonical domain tables + link scaffolds), separate from the
  providers that later populate it.
- **A self-contained standalone change** (one capability, few commits, no siblings)
  → its own small spec.
- **Split when an outcome forks.** If a cluster contains two genuinely distinct
  outcomes, make two specs and say why — one-outcome-per-spec beats one bloated spec.

For each cluster, draft: a one-line outcome, the ordered list of SHAs it contains,
and a proposed `NNN-<slug>`. Play the grouping back to the user before writing —
cluster boundaries determine how many specs exist and what each owns.
