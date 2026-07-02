---
title: "Tasks: Bidirectional Identity Reconciliation"
---

# Tasks: Bidirectional Identity Reconciliation

**Feature directory**: `specs/013-bidirectional-identity-reconciliation/`
**Date**: 2026-07-02
**Plan**: `plan.md`
**Status**: Draft

## Ordering note — read before executing

This is a corrected revision of an earlier draft that reordered entire user-story phases (P2, P3
before P1) to satisfy plan.md's technical sequencing (`S1 + S3 ─▶ S6 ─▶ S7`, `S3 + S4 + S6 + S7 ─▶
S8`). That was a deviation: this skill's own mechanism for "shared prerequisites that block every user
story" is the **Foundational** phase, not phase relabeling. This revision fixes it by putting the
minimal, genuinely-real mechanism P1 needs directly into Foundational, so **User Story 1 (P1) is Phase
3 — immediately after Foundational, ahead of P2 and P3.**

Concretely, Foundational absorbs two slices carved out of `S1` and `S6`:

- **From `S1` (`find_learned_aliases`)**: the two "does bridge" tiers — a high-confidence match tagged
  `auto_confirmed` (FR-003) and a medium-confidence match tagged `needs_review` (FR-004) — plus the
  FR-011 no-seed-write-back invariant. This is the minimum a real, non-stubbed tiered-decision function
  must do to produce a bridge at all; it is exactly what `S8`'s end-to-end convergence proof calls.
  **Deferred to User Story 2 (Phase 4)**: the three scenarios that are User Story 2's actual
  differentiator per spec.md ("ambiguous or low-confidence name pairs are never silently merged") —
  the below-threshold no-bridge case (FR-005), the tied-candidates no-bridge case (FR-005, Edge Case),
  and the already-seeded-name-excluded case (Edge Case, seed precedence). These are genuinely separable
  from "can it bridge at all" — they are about the function's *refusal* to bridge, which User Story 1's
  convergence proof does not exercise and does not need.
- **From `S6` (`identity_reconciliation`)**: enough to read real ESPN + Matchbook bronze fixtures, score
  them against a real canonical-team-pool fixture, and write one real, correctly-shaped bridge row to
  `data/silver/learned_team_aliases.parquet` — the artifact `S8`'s convergence proof and `S3`'s dbt-side
  wiring both need to exist and be well-formed. **Deferred to User Story 3 (Phase 5)**: the
  traceability-*completeness* claim specifically (spec.md's own text: this "is not itself required for
  the core duplicate-elimination behaviour to work") — proving that **every** bridge row, across
  **both** `match_method` tags in the same run, carries all 5 non-null columns (SC-003), not just the
  one row Foundational already proved is well-formed.

Net effect: Foundational is genuinely load-bearing (nothing in it is stubbed or faked — the two "does
bridge" tiers and the one-row artifact proof are real, tested code), Phase 3 (User Story 1 / P1) can
start immediately once Foundational is green without waiting on Phase 4 or Phase 5, and Phases 4 and 5
each still independently prove their own story's distinct acceptance scenarios per the
"each story is independently testable" principle.

`S2` and `S3` (the dbt macro + its three call sites) remain in Foundational unchanged — they were
already correctly placed in the prior draft; nothing about the fix below touches their phase placement.

**Separately fixed in this revision**: the prior draft's `S3` red-state task ("seed a canonical team
pool + bridge fixture", no named file) is replaced below with a concrete, reusable, named fixture — a
new pytest harness file `tests/conform/test_learned_alias_resolution.py` that materializes a
self-contained scratch dbt run (mirroring the existing `tests/conform/test_exports.py` pattern) with
two named, on-disk fixture files: `data/bronze/espn/eng.1/2025.parquet` (two ESPN events — one team
named `"Wolverhampton Wanderers"`, one named `"Wolves"`) and `data/silver/learned_team_aliases.parquet`
(one row bridging `raw_name="Wolves"` onto `team_id=md5(lower("wolverhampton wanderers"))`). This is the
exact fixture quickstart.md's Scenario 1 already documents, reused here for consistency — so the red and
green states are reproducible by running the same named test file, not by an unspecified manual step.

## Phase 1: Setup

- [ ] T001 [S0] Write failing test `tests/conform/test_scoring.py` asserting
  `from data_platform.conform.scoring import HIGH_CONFIDENCE, MEDIUM_CONFIDENCE, HIGH_THRESHOLD,
  MEDIUM_THRESHOLD` and their values (0.95, 0.75, 0.85, 0.70) — fails with `ModuleNotFoundError` (the
  module doesn't exist yet).
- [ ] T002 [S0] Create `src/data_platform/conform/scoring.py` with the four constants (module docstring:
  "Shared fuzzy-match confidence tiers, reused by event-to-match linking and team-name reconciliation.");
  change `src/data_platform/conform/matchbook_scoring.py` to `from .scoring import HIGH_CONFIDENCE,
  MEDIUM_CONFIDENCE, HIGH_THRESHOLD, MEDIUM_THRESHOLD` instead of defining them (leave
  `KICKOFF_TOLERANCE_MINUTES` and the event/match-specific functions in place). Green: `PYTHONPATH=src
  uv run pytest tests/conform/test_scoring.py` passes; `tests/conform/test_conform.py` still passes
  unmodified (regression proof the re-export preserves every existing import path). Ruff clean on both
  touched files.

## Phase 2: Foundational (blocking prerequisites)

> Shared infrastructure every user story needs to exist before it can be proven: the 3-tier resolution
> formula in SQL (`S2`, `S3`), a real tiered-decision bridging function covering both "does bridge"
> outcomes (`S1`, minimal), and a real end-to-end asset that writes one well-formed bridge row from real
> bronze fixtures (`S6`, minimal). See the Ordering note above for exactly what is/isn't in scope here.

### Track A — dbt resolution formula (`S2`, `S3`)

- [ ] T003 [P] [S2] **Invoke the `dbt-model-build` skill** for macro-writing and singular-test
  conventions. Write failing singular test
  `dbt/data_platform/tests/assert_team_resolution_formula_parity.sql` against the macro's intended
  contract (`coalesce(seed, learned, md5(lower(name)))`, independently reconstructed via raw SQL over a
  small `values(...)` fixture covering all three tiers — non-tautological, mirroring
  `assert_resolver_provider_agnostic.sql`'s pattern) — `dbt parse` fails referencing an undefined macro
  before `resolve_team_id_expr` exists.
- [ ] T004 [S2] **`dbt-model-build` skill.** Implement `dbt/data_platform/macros/resolve_team_id_expr.sql`
  — `{% macro resolve_team_id_expr(seed_id_col, learned_id_col, name_col) %} coalesce({{ seed_id_col }},
  {{ learned_id_col }}, md5(lower({{ name_col }}))) {% endmacro %}`, documented header mirroring
  `canonical_match_id.sql`'s style. Green: `( cd dbt/data_platform && uv run --project ../.. dbt parse
  --profiles-dir . )` succeeds; `dbt build --select test_name:assert_team_resolution_formula_parity`
  passes against a running DuckLake catalog. Self-review: confirm the singular test does NOT call
  `resolve_team_id_expr` on both sides of its assertion; confirm it fails if the macro's precedence
  order is deliberately broken (swap `learned_id_col`/`seed_id_col`), then revert.
- [ ] T005 [S3] **`dbt-model-build` skill** (its `source()`-vs-raw-literal / `CircularDependencyError`
  section governs this task). **Concrete fixture (fixes the prior draft's vagueness):** create
  `tests/conform/test_learned_alias_resolution.py`, mirroring `tests/conform/test_exports.py`'s
  self-contained scratch-dbt-harness pattern (file-backed DuckLake `profiles.yml` under `tmp_path`, no
  live Postgres catalog needed). The harness writes exactly two fixture files:
  - `data/bronze/espn/eng.1/2025.parquet` — two ESPN bronze events (schema matching
    `test_exports.py`'s `_ESPN_EVENTS`): event 1 `home_team_name="Wolverhampton Wanderers"` (no seed
    alias — self-mints `team_id=md5(lower("wolverhampton wanderers"))`), event 2
    `home_team_name="Wolves"` (no seed alias either — this is the name the bridge below targets).
  - `data/silver/learned_team_aliases.parquet` — one row: `raw_name="Wolves",
    team_id=md5(lower("wolverhampton wanderers")), source_provider="espn", confidence=0.97,
    match_method="auto_confirmed"` (the exact fixture quickstart.md Scenario 1 documents).
  Plus the usual bootstrap-empty `matchbook_`/`football_data_`-prefixed additions files (mirrors
  `test_exports.py`'s `_ADDITIONS_SCHEMAS` loop) so `int_team`'s unions don't error on a missing file.
  Run `dbt build --select team_aliases stg_espn_events int_team --indirect-selection=empty --threads 1`
  against this harness and assert (RED, captured now): the resulting `int_team` row count for these two
  events is **2** distinct `team_id`s — because before this task, `int_team.sql` doesn't read
  `learned_team_aliases.parquet` at all, so the old 2-tier `coalesce(seed, self-mint)` mints "Wolves" as
  its own team. This assertion is what makes the red state a committed, reproducible artifact rather
  than a manual check.
- [ ] T006 [S3] **`dbt-model-build` skill.** Wire `{{ resolve_team_id_expr(...) }}` plus a `left join
  read_parquet('{{ env_var("DATA_DIR", "/app/data") }}/silver/learned_team_aliases.parquet') l on
  e.name = l.raw_name` (raw literal, never `{{ source(...) }}` — research.md §4's
  `CircularDependencyError`-avoidance decision) into the resolution CTE of
  `dbt/data_platform/models/intermediate/int_team.sql`,
  `dbt/data_platform/models/intermediate/int_match.sql` (`espn_matches` CTE only), and
  `dbt/data_platform/models/intermediate/int_espn_team_link.sql` — all three call the macro with
  identical argument order. Register `learned_team_aliases` in
  `dbt/data_platform/models/_sources.yml` and `BronzeAwareTranslator._SOURCE_ASSET_KEYS`
  (`src/data_platform/assets/dbt.py`) for documentation/consistency only (mirrors the
  `matchbook_t60_enrichment` precedent — present in both places, referenced via `source()` in neither
  model). Green: re-run T005's harness — the same two-event fixture now resolves to **1** `team_id`
  (both "Wolverhampton Wanderers" and "Wolves" converge onto
  `md5(lower("wolverhampton wanderers"))`); `dbt build --select intermediate.int_team+
  --indirect-selection=empty` also passes against the real DuckLake catalog. Self-review: confirm the
  `left join` is on the raw pre-resolution name column, not the already-resolved `team_id`; confirm all
  three call sites use the macro identically; confirm the seed still wins when both a seed alias and a
  learned bridge exist for the same name; grep-confirm no `{{ source(...) }}` reference to
  `learned_team_aliases` in any of the three model files.

### Track B — `find_learned_aliases` core: both "does bridge" tiers (`S1`, minimal)

- [ ] T007 [P] [S1] Write failing tests `tests/conform/test_reconcile.py` — three cases: (1)
  high-confidence bridge tagged `auto_confirmed` (FR-003), (2) medium-confidence bridge tagged
  `needs_review` (FR-004), (3) FR-011 — `team_aliases.csv`'s mtime/content asserted unchanged after
  calling `find_learned_aliases`. All fail (`ImportError` for cases 1–2, a missing-assertion no-op for
  case 3) before `conform/reconcile.py` exists. (The three "does NOT bridge" cases — below-threshold,
  tied-candidates, already-seeded — are User Story 2's own tests; see T018.)
- [ ] T008 [S1] Implement `src/data_platform/conform/reconcile.py` —
  `find_learned_aliases(raw_names: pd.Series, canonical_teams: pd.DataFrame, high_threshold=HIGH_THRESHOLD,
  medium_threshold=MEDIUM_THRESHOLD) -> pd.DataFrame`: for each raw name, score against
  `canonical_teams.name` and each entry of `canonical_teams.similar_names` via
  `rapidfuzz.fuzz.token_sort_ratio`, take the best-scoring candidate, apply the tiered decision (bridge
  at `auto_confirmed` when the top score ≥ `high_threshold`; bridge at `needs_review` when it's in
  `[medium_threshold, high_threshold)`), return `raw_name, team_id, confidence, match_method` rows (no
  `source_provider` — the caller stamps that). No I/O, no DuckLake import (mirrors `resolve.py`'s
  discipline) — this implementation covers the two bridge-producing branches only; the below-threshold
  and tie-detection branches are hardened in T019. Green: `PYTHONPATH=src uv run pytest
  tests/conform/test_reconcile.py` passes, all 3 cases in T007. Ruff clean. Self-review: confirm no
  seed-file I/O anywhere in the module (FR-011); confirm no `duckdb` import (FR-013).

### Track C — `identity_reconciliation` core: one real, well-formed bridge (`S6`, minimal)

> Depends on both tracks above: needs `find_learned_aliases` (T008) to score with, and needs T006's
> settled bootstrap-empty file path/shape so the asset writes exactly what `int_team.sql`'s
> `read_parquet()` literal already expects (per plan.md's Sequencing section).

- [ ] T009 [S6] **Invoke the `dagster-asset-build` skill** for the thin-wrapper, bootstrap-empty, and
  config-property conventions. Write a failing artifact-level pytest (new file, e.g.
  `tests/conform/test_identity_reconciliation.py`) that seeds: an ESPN bronze fixture and a canonical
  -team-pool fixture (`canonical_team_export.parquet`-shaped) already containing a team named
  `"Wolverhampton Wanderers"` with `team_id=md5(lower("wolverhampton wanderers"))`, and a Matchbook
  bronze fixture with one event named `"Wolves vs Some Other Team"` (parseable via
  `conform.matchbook_event_name.parse_event_name` to raw name `"Wolves"` — the same fixture shape as
  quickstart.md Scenario 1). Invoke the asset's underlying engine function directly (not through
  Dagster's execution harness — mirrors how `run_conform` is tested in `test_conform.py`), and assert
  `learned_team_aliases.parquet` is written with exactly one row: `raw_name="Wolves",
  team_id=md5(lower("wolverhampton wanderers")), source_provider="matchbook",
  match_method="auto_confirmed"`. Fails (module doesn't exist) before this task.
- [ ] T010 [S6] **`dagster-asset-build` skill.** Add `learned_team_aliases_path` as a new `@property`
  on `Settings` in `src/data_platform/config.py` (`silver_dir / "learned_team_aliases.parquet"` —
  check for property-name collisions first, per the skill's convention). Implement
  `src/data_platform/assets/intermediate/identity_reconciliation.py` — thin `@asset` wrapper (no
  `from __future__ import annotations`), `AssetKey(["identity_reconciliation"])`,
  `deps=[AssetKey(["espn_bronze"]), AssetKey(["matchbook_events_bronze"])]`; body: read ESPN bronze
  Parquet (`pd.read_parquet` glob over `settings.espn_bronze_dir`) for `home_team_name`/`away_team_name`,
  read Matchbook bronze Parquet (`settings.matchbook_events_bronze_dir`) and parse team names via
  `conform.matchbook_event_name.parse_event_name`, read
  `settings.matchbook_conform_canonical_dir / "team.parquet"` as the candidate pool, call
  `reconcile.find_learned_aliases` once per provider (stamping `source_provider`), concatenate, and write
  atomically (tmp-file + rename, mirroring `_ensure_empty_parquet`) to `settings.learned_team_aliases_path`
  — bootstrap-write-empty first if absent (correct columns, zero rows), mirroring
  `matchbook_conform.py`'s `_bootstrap_additions`. OTel span via `otel.get_tracer()`. Green: T009's
  pytest passes; `PYTHONPATH=src uv run pytest tests/` (full suite) stays green. Ruff clean; grep-confirm
  no `duckdb.connect` anywhere in the file (FR-013). Self-review: confirm the asset reads bronze Parquet
  directly, never `stg_espn_events` or any DuckLake connection; confirm `source_provider` is correctly
  stamped per input set; confirm the write is atomic and the bootstrap-empty path is exercised by a test
  (first-ever-run case).

**Checkpoint**: the 3-tier resolution formula is wired into every ESPN-side SQL call site (`S2`/`S3`),
`find_learned_aliases` correctly produces both bridge tiers with no seed write-back (`S1` core), and
`identity_reconciliation` writes one real, correctly-shaped bridge row from real bronze fixtures (`S6`
core). Nothing here is stubbed. **Phase 3 (User Story 1 / P1) can start immediately.**

## Phase 3: User Story 1 — A team minted by either provider resolves to one canonical id, regardless of mint order (Priority: P1) 🎯 MVP

**Goal**: the core defect fix — bidirectional convergence (ESPN-first and Matchbook-first) to one
canonical `team_id`/`match_id`, proven end-to-end.
**Independent Test**: seed ESPN to mint under name A, then Matchbook under differently-spelled name B in
a later run; after reconciliation, the next full rebuild resolves B onto A's `team_id` (and the reverse
order too), with the canonical team model showing exactly one row.

> Two independent tracks below (`S4`→`S5`, and `S7`) can proceed concurrently — neither depends on the
> other, only on Phase 2 already being complete. Both must finish before `S8` (T016/T017).

- [ ] T011 [P] [US1] [S4] Extend `tests/conform/test_resolve.py` — a case where `resolve_team_id` is
  called with a `learned_aliases` frame bridging name B onto an existing `team_id` for name A; asserts
  `resolve_team_id("A", seed, learned) == resolve_team_id("B", seed, learned)`, exercised in both query
  framings (queried in either order — the resolver is stateless, so this proves the formula itself has
  no order-dependence). Fails (`TypeError`: unexpected keyword) before the parameter exists.
- [ ] T012 [US1] [S4] Extend `src/data_platform/conform/resolve.py` — `resolve_team_id(name: str, aliases:
  pd.DataFrame, learned_aliases: pd.DataFrame | None = None) -> str`: seed lookup first (unchanged), then
  `learned_aliases` lookup on `raw_name == name` if provided and non-empty, then the unchanged self-mint
  fallback. Wire `src/data_platform/conform/matchbook.py`'s mint path to read
  `settings.learned_team_aliases_path` (the property added in T010) the same way it already reads
  `team_aliases.csv`, and pass it through **every** `resolve_team_id` call site in its mint chain. Green:
  `PYTHONPATH=src uv run pytest tests/conform/test_resolve.py` passes including the new bidirectional
  case; every pre-existing case still passes unmodified (`learned_aliases=None` default — Constitution I
  compliance, not a compat shim). Ruff clean; no new DuckLake access. Self-review: temporarily remove the
  `learned_aliases` branch and confirm T011 turns red, then restore; confirm `matchbook.py` passes the
  SAME `learned_aliases` frame to every `resolve_team_id` call site (a missed call site silently
  reintroduces duplicate-mint risk).
- [ ] T013 [US1] [S5] Extend `tests/conform/test_parity.py` with 3 new cases that independently
  reconstruct `coalesce(seed, learned, md5(lower(name)))` via raw `hashlib`/dict lookups (NOT calling
  `resolve_team_id`) — a name present in a synthetic seed, a name present only in a synthetic learned
  frame, a name in neither — asserting equality against `resolve.resolve_team_id`'s real output for all
  three. Green: `PYTHONPATH=src uv run pytest tests/conform/test_parity.py` passes, all cases including
  the three new ones. No production code change (T012 already implements the function under test).
  Self-review: confirm the "expected" side of every new assertion is built WITHOUT calling
  `resolve.resolve_team_id`; deliberately break `resolve_team_id`'s tier order and confirm THIS test (not
  just T011/T012's) turns red, then revert — proving it's a genuine independent check.
- [ ] T014 [P] [US1] [S7] **Invoke the `dagster-asset-build` skill** — its mandatory daemon/queued-run
  verification standard governs T015. Wire `identity_reconciliation` into
  `src/data_platform/definitions.py`: add it to the `assets=[...]` list; add
  `AssetKey(["identity_reconciliation"])` to both `espn_assets` and `matchbook_assets`
  `AssetSelection`s; change `matchbook_conform`'s `deps=` to include
  `AssetKey(["identity_reconciliation"])` alongside its existing `AssetKey(["matchbook_events_bronze"])`.
  No change to `dbt_models`'s own construction. (Startable as soon as Phase 2's T010 exists; file-disjoint
  from T011's test file, so can run concurrently with the `S4` track.)
- [ ] T015 [US1] [S7] **`dagster-asset-build` skill — the mandatory verification standard, not just
  `dagster definitions validate`.** Run `uv run dagster definitions validate -w workspace.yaml` (necessary,
  not sufficient). Then launch a real **queued** run (UI/daemon, not `dagster job execute`) of
  `matchbook_ingestion` and confirm: no `CircularDependencyError` at `Definitions` build time;
  `identity_reconciliation` completes before `matchbook_conform` starts (inspect step ordering in the
  Dagster UI/run logs). Launch a queued `espn_ingestion` run and confirm `identity_reconciliation`
  executes there too (FR-012 — both providers covered). Matches quickstart.md Scenario 4. Self-review:
  independently launch both queued runs (don't trust a self-report); confirm `identity_reconciliation`
  appears in BOTH job selections, not just one.
- [ ] T016 [US1] [S8] Extend `tests/conform/test_mint_chain.py` with three new cases: (a) ESPN mints under
  name A first, then a synthetic Matchbook event under fuzzy-matching name B runs through `run_conform`
  with the T009/T010-shaped learned-alias bridge already present — asserts `home_team_id`/`away_team_id`
  equal ESPN's `team_id`, not a fresh mint; (b) the reverse order (Matchbook mints first; ESPN's dbt-side
  resolution simulated via `resolve_team_id_expr`'s Python parity twin) resolves onto Matchbook's id; (c)
  a known-negative case (two genuinely different clubs whose names happen to score below threshold)
  asserting NO convergence (the SC-002 false-positive guard).
- [ ] T017 [US1] [S8] Run T016's three cases to green (`PYTHONPATH=src uv run pytest
  tests/conform/test_mint_chain.py`). Separately, run `dbt build --select intermediate.int_team+
  intermediate.int_match+ intermediate.int_espn_team_link+ --indirect-selection=empty` against seeded
  bronze fixtures for both mint orderings, confirming single-row convergence for the bridged pair at
  BOTH team level (`int_team`) and match level (`int_match`, SC-004 — not just team-level) and continued
  separation for the known-negative pair. Green: full `PYTHONPATH=src uv run pytest`; `uv run pre-commit
  run --all-files` clean. Self-review (MOST adversarial per plan.md): confirm "both orders converge" is
  tested as two genuinely distinct scenarios, not one parameterized to look like two; confirm the
  known-negative pair is a real, plausible false-positive risk, not a trivially-dissimilar pair that
  proves nothing; confirm SC-004 is actually asserted on `int_match`/`match_id`, not just `int_team`.

**Checkpoint**: User Story 1 (the feature's primary reason to exist) is fully proven — bidirectional
convergence at both team and match level, in both mint orders, with zero false-positive merges.

## Phase 4: User Story 2 — Ambiguous or low-confidence name pairs are never silently merged (Priority: P2)

**Goal**: complete the consistent, auditable confidence policy — the three "does NOT bridge" outcomes
that are this story's actual differentiator (Phase 2 already proved the two "does bridge" outcomes).
**Independent Test**: feed a below-threshold raw name and a raw name tied between two candidates directly
to `find_learned_aliases`; confirm neither produces a bridge and both remain free to self-mint. Feed a
name already covered by the `team_aliases` seed; confirm it's excluded from bridging consideration.

> Depends only on Phase 2 (`T008`'s `find_learned_aliases`), not on Phase 3 — could run concurrently with
> or before Phase 3 if desired; sequenced here (third) to keep priority order P1 → P2 → P3 readable.

- [ ] T018 [US2] [S1] Extend `tests/conform/test_reconcile.py` with three new cases — the ones Phase 2
  deliberately deferred: (4) a name scoring below `MEDIUM_THRESHOLD` against every candidate produces no
  row (FR-005), (5) two candidates tied at the top score at or above `MEDIUM_THRESHOLD` produces no row
  for that name (FR-005, Edge Case — ambiguous tie), (6) a raw name already covered by a
  `team_aliases` seed match is excluded from bridging consideration (Edge Case — seed precedence; the
  test constructs the caller-level contract: a seed-matched name is never present in the `raw_names`
  `find_learned_aliases` is fed, and confirms no row for it is ever produced even if it would otherwise
  score highly). Cases 4–5 fail before T019's hardening (T008's minimal implementation from Phase 2 may
  silently default to the highest-scoring candidate on a tie, which is exactly the FR-005 violation this
  case exists to catch); case 6 passes trivially by construction but documents the contract explicitly.
- [ ] T019 [US2] [S1] Harden `src/data_platform/conform/reconcile.py`'s tiered-decision logic: explicit
  tie-detection (compare the top two candidate scores per raw name; a tie at or above
  `medium_threshold` yields no row, never an arbitrary pick) and confirm the below-threshold branch
  (already a natural consequence of the tiered `coalesce`, but now explicitly asserted) never falls back
  to the best-available candidate. Green: `PYTHONPATH=src uv run pytest tests/conform/test_reconcile.py`
  passes, all 6 cases (the 3 from T007 plus the 3 from T018). Ruff clean. Self-review: revert the
  tie-detection branch and confirm T018's tie case turns red, then restore; confirm the below-threshold
  and tie-handling cases don't silently default to the highest-scoring candidate (FR-005 — this is
  exactly the reward-hacking risk plan.md's S1 self-review flags).

**Checkpoint**: User Story 2's confidence policy is complete — all four acceptance scenarios
(`auto_confirmed`, `needs_review`, below-threshold, ambiguous tie) are independently proven via
`find_learned_aliases` alone, with no Dagster/dbt integration required.

## Phase 5: User Story 3 — Every automatic bridge is traceable (Priority: P3)

**Goal**: prove the traceability-*completeness* claim specifically — every bridge row produced in a run,
across both `match_method` tags, carries all 5 non-null columns (Phase 2 already proved one row is
well-formed; this generalizes that to "every row, every tag").
**Independent Test**: after a reconciliation run that produces at least one `auto_confirmed` and one
`needs_review` bridge in the SAME run, inspect every row of `learned_team_aliases.parquet` and confirm
each carries raw name, resolved `team_id`, source provider, confidence score, and match method.

> Depends only on Phase 2 (`T010`'s `identity_reconciliation`), not on Phase 3 or Phase 4 — sequenced
> here (fourth) to keep priority order P1 → P2 → P3 readable.

- [ ] T020 [US3] [S6] Extend `tests/conform/test_identity_reconciliation.py` (from T009) with a second
  fixture pair alongside the existing "Wolves"/"Wolverhampton Wanderers" high-confidence pair: a second
  ESPN canonical team plus a second Matchbook event whose parsed raw name scores in
  `[MEDIUM_THRESHOLD, HIGH_THRESHOLD)` against it (a genuine `needs_review` case), so the same
  reconciliation run produces one `auto_confirmed` row and one `needs_review` row. Assert **every** row
  of the written `learned_team_aliases.parquet` — not just the one T009 already checked — has non-null
  `raw_name`, `team_id`, `source_provider`, `confidence`, `match_method` (SC-003, User Story 3 Acceptance
  Scenario 1). This is new coverage: T009 only proved one row's shape from one bridge tag; this proves
  the completeness claim across both tags in one run. Fails before this task if the medium-confidence
  fixture pair isn't yet exercised (T009's fixture only produced one `auto_confirmed` row).
- [ ] T021 [US3] [S6] Add the second fixture pair to `identity_reconciliation`'s test harness data (no
  production code change expected — T010's implementation already builds its output DataFrame uniformly
  across all scored names, so this task's job is to prove that genuinely, not to special-case it). Green:
  `PYTHONPATH=src uv run pytest tests/conform/test_identity_reconciliation.py` passes, including T020's
  new multi-row, multi-tag assertion. Self-review: confirm the `needs_review` row in the fixture is a
  real medium-confidence pair (scores in `[MEDIUM_THRESHOLD, HIGH_THRESHOLD)` via `token_sort_ratio`,
  not an artificially-forced value); confirm the assertion iterates every row of the DataFrame rather
  than indexing a single known-good row (that would silently narrow SC-003's "100% of bridges" claim).

**Checkpoint**: User Story 3's traceability claim is proven at full generality — every bridge row,
regardless of confidence tier, carries all 5 required columns.

## Phase 6: Polish & cross-cutting

- [ ] T022 [P] [S6] Update `data flows.md` per CLAUDE.md's living-doc convention (conform logic changed
  materially) — document the new `identity_reconciliation` asset, the
  `data/silver/learned_team_aliases.parquet` artifact, and the three-tier (curated seed → learned bridge
  → self-mint) resolution formula now used by `int_team`/`int_match`/`int_espn_team_link` and
  `resolve_team_id`.
- [ ] T023 [P] [S8] Run quickstart.md Scenarios 1–4 end-to-end (ESPN-first/Matchbook-first bidirectional
  convergence, confidence tiers, traceability, orchestration guardrail) and confirm each produces its
  documented expected outcome exactly as written.

## Dependencies & Execution Order

- **Setup (Phase 1, `S0`)**: no dependencies — start immediately.
- **Foundational (Phase 2, `S2`→`S3`, plus minimal `S1`/`S6`)**: depends on Setup. Two independent
  tracks run first: Track A (`T003`→`T004`→`T005`→`T006`, the dbt macro + its wiring) and Track B
  (`T007`→`T008`, `find_learned_aliases`'s two bridge tiers) — file-disjoint, no cross-dependency, so
  `T003`/`T007` are both immediately startable in parallel. Track C (`T009`→`T010`, the
  `identity_reconciliation` asset) is the join point: it needs Track B's `find_learned_aliases` (`T008`)
  to score with, and per plan.md's Sequencing section should follow Track A's `T006` so the bootstrap
  -empty file shape/path it writes matches what `int_team.sql`'s `read_parquet()` literal already
  expects. Blocks every user-story phase.
- **User Story 1 (Phase 3, `S4`/`S5`/`S7`/`S8`)**: depends on Phase 2 only. The `S4`→`S5` track
  (`T011`–`T013`) and the `S7` track (`T014`–`T015`) are independent of each other (file-disjoint,
  `T011`/`T014` both immediately startable once Phase 2 completes) but each depends on Phase 2's
  respective piece (`T011` needs nothing beyond Setup's constants transitively; `T014` needs `T010`'s
  asset module to exist to be selected into jobs). `T016`/`T017` (`S8`, the end-to-end proof) need
  **both** tracks finished, per plan.md's Sequencing diagram (`S3 + S4 + S6 + S7 ─▶ S8`).
- **User Story 2 (Phase 4, `S1` remainder)**: depends on Phase 2's `T008` only — does **not** depend on
  Phase 3. Sequenced third (after Phase 3) to keep the priority order P1 → P2 → P3 readable in document
  order, not because of a hard dependency; an implementor could run Phase 4 concurrently with Phase 3
  without breaking anything.
- **User Story 3 (Phase 5, `S6` remainder)**: depends on Phase 2's `T010` only — does **not** depend on
  Phase 3 or Phase 4. Sequenced fourth for the same readability reason as Phase 4.
- **Polish (Phase 6)**: depends on Phases 3–5 all completing (documents/validates the finished feature
  in full, including the P2/P3 hardening).
- **Within a phase**: failing test precedes its implementation (`T001`→`T002`, `T003`→`T004`,
  `T005`→`T006`, `T007`→`T008`, `T009`→`T010`, `T011`→`T012`→`T013`, `T016`→`T017`, `T018`→`T019`,
  `T020`→`T021`). Models/macros before wiring before end-to-end proof.
- **Repo ordering gotchas carried from the plan**: single-writer DuckDB does not apply here (no
  `warehouse.duckdb` access anywhere in this feature); `dbt build --select intermediate.int_team+
  --indirect-selection=empty` is required (not a bare prefix) per CLAUDE.md's dbt-selector-vs-AssetKey
  distinction; the bootstrap-empty-Parquet discipline (`T010` must bootstrap-write-empty before `T006`'s
  `read_parquet()` literal is exercised against a fresh checkout) is load-bearing — `T005`/`T006`'s own
  test harness supplies its own fixture file directly so it doesn't depend on `T010` having run first;
  `T017`'s full-stack `dbt build` is the first point a genuinely clean-environment ordering matters, and
  by then `T010` has already landed (Phase 2 completes before Phase 3).

### Parallel opportunities

- Phase 2: `T003` (`S2` red, dbt test file) and `T007` (`S1` red, `tests/conform/test_reconcile.py`) are
  both immediately startable and file-disjoint — run concurrently. Once `T004` and `T008` (their
  respective green steps) are also both file-disjoint and dependency-satisfied, they may likewise
  proceed concurrently even though only the first pair is tagged `[P]` above.
- Phase 3: `T011` (`S4` red test, `tests/conform/test_resolve.py`) and `T014` (`S7` wiring,
  `src/data_platform/definitions.py`) are both immediately startable once Phase 2 completes, and touch
  disjoint files — run concurrently.
- Phases 4 and 5 (`T018`/`T019` and `T020`/`T021`) depend only on Phase 2, not on Phase 3 or on each
  other — an implementor with spare capacity could run them concurrently with Phase 3, or in either
  order relative to each other.
- Phase 6: `T022` (`data flows.md`) and `T023` (running quickstart scenarios, no file writes) are
  file-disjoint and independent — run concurrently.
- No other tasks are marked `[P]`: every other pair either shares a file, or the plan's own Sequencing
  & dependencies section documents a real ordering between them (see the CircularDependencyError
  -avoidance and bootstrap-empty-before-read constraints above) — marking them parallel would risk a
  write conflict or a read against a not-yet-written file.

## Notes

- `[P]` = different files, no unmet dependency. A wrong `[P]` causes parallel write conflicts.
- `[Sn]` links each task to its plan step (traceability, `plan.md`'s S0–S8). `[USn]` maps it to a user
  story (US1/US2/US3); Setup/Foundational/Polish tasks omit `[USn]` per convention — Foundational's `S1`
  and `S6` tasks (`T007`–`T010`) are the shared minimal core those steps' user stories (US2, US3)
  build on, not a story-specific deliverable themselves.
- `S2`/`S3`/`S6`/`S7` tasks explicitly note the mandated skill (`dbt-model-build`, `dagster-asset-build`)
  per plan.md's "Skills to use" table — invoke it rather than re-deriving the conventions from scratch.
- Verify tests fail before implementing. Commit after each task or logical group.
